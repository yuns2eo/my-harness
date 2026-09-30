"""하네스 공용 함수. 수치는 전부 rules.yaml(+ rules.local.yaml)에서 읽는다."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PLACEHOLDER = re.compile(r"\$\{([A-Z0-9_]+)\}")


# ---------------------------------------------------------------- rules
def _substitute(obj, local: dict):
    if isinstance(obj, str):
        def repl(m):
            key = m.group(1)
            if key not in local:
                raise KeyError(f"rules.local 에 {key} 가 없습니다")
            return str(local[key])
        return PLACEHOLDER.sub(repl, obj)
    if isinstance(obj, list):
        return [_substitute(v, local) for v in obj]
    if isinstance(obj, dict):
        return {k: _substitute(v, local) for k, v in obj.items()}
    return obj


def local_rules_path() -> Path:
    env = os.environ.get("HARNESS_RULES_LOCAL")
    if env:
        return Path(env)
    return ROOT / "rules.local.yaml"


def load_rules(resolve: bool = True) -> dict:
    rules = yaml.safe_load((ROOT / "rules.yaml").read_text(encoding="utf-8"))
    if not resolve:
        return rules
    path = local_rules_path()
    if not path.exists():
        raise FileNotFoundError(f"{path} 가 없습니다. rules.local.example.yaml 을 복사해 채우세요")
    local = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return _substitute(rules, local)


# ---------------------------------------------------------------- run 파일
def run_dir(arg: str) -> Path:
    p = Path(arg)
    if not p.is_absolute() and not p.exists():
        p = ROOT / "runs" / arg
    if not p.is_dir():
        raise FileNotFoundError(f"run 폴더가 없습니다: {arg}")
    return p


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_brief(run: Path) -> dict:
    """01/brief.md 의 YAML front matter (V1~V13)."""
    text = (run / "01" / "brief.md").read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise ValueError("01/brief.md 에 YAML front matter 가 없습니다")
    return yaml.safe_load(m.group(1)) or {}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- 명명 규칙
def expected_frames(brief: dict, rules: dict) -> list[dict]:
    """★2: 요청 배너 × 세트 → 있어야 하는 프레임 목록."""
    out = []
    sets = rules["sets"][brief["split"]]
    for set_suffix in sets:
        for banner in brief["banners"]:
            label = rules["banners"][banner]["label"]
            name = rules["naming"]["frame"].format(
                made=brief["made_date"], job=brief["job_name"], label=label, set=set_suffix)
            out.append({"banner": banner, "set": set_suffix, "name": name,
                        "size": rules["banners"][banner]["size"]})
    return out


def sheet_rows(sheet: dict, brief: dict, rules: dict) -> tuple[dict, list[str]]:
    """세트 접미사 → 시트 열 값. (rows, 오류 목록)

    01/sheet.json 은 둘 중 하나:
      {"columns": {...}}                      시트 한 행 → 모든 세트에 똑같이 적용
      {"sets": {"강": {...}, "고": {...}}}     강/고 행이 따로 → 세트별로 자기 행과 비교
    """
    suffixes = rules["sets"][brief["split"]]
    has_cols, has_sets = "columns" in sheet, "sets" in sheet
    if has_cols == has_sets:
        return {}, ["sheet.json 에 columns 와 sets 중 정확히 하나만 있어야 합니다"]
    if has_cols:
        return {s: sheet["columns"] or {} for s in suffixes}, []
    by_label = sheet["sets"] or {}
    labels = [s.lstrip("_") for s in suffixes]
    errors = []
    if set(by_label) != set(labels):
        errors.append(f"시트 세트 행 {sorted(by_label)} ≠ 요청 세트 {labels}")
    return {s: by_label.get(s.lstrip("_"), {}) for s in suffixes}, errors


def export_name(frame_name: str) -> str:
    return f"{frame_name}.png"


def figma_link(rules: dict, node_id: str) -> str:
    return rules["figma"]["link_format"].format(
        file_key=rules["figma"]["file_key"], node_id_dash=node_id.replace(":", "-"))


# ---------------------------------------------------------------- ★1 비교
def apply_substitutions(text: str, rules: dict) -> tuple[str, list[dict]]:
    applied = []
    for sub in rules["text"]["allowed_substitutions"]:
        if sub["from"] in text:
            applied.append({"from": sub["from"], "to": sub["to"], "original": text})
            text = text.replace(sub["from"], sub["to"])
    return text, applied


def normalize_copy(text: str) -> str:
    """r5-gates §2: 양쪽 모두 \\n → 공백 1개. 나머지는 바이트 동일 비교."""
    return text.replace("\r\n", "\n").replace("\n", " ")


def is_hangul(ch: str) -> bool:
    return "\uac00" <= ch <= "\ud7a3"


def midword_breaks(text: str, reference: str | None = None) -> list[int]:
    """어절 중간 줄바꿈 위치. 규칙: 모든 \\n 은 원래 공백이 있던 자리여야 한다.

    reference(시트 원문)가 있으면 그것과 맞춰 본다:
      - \\n 을 전부 공백으로 바꾼 값 == 시트  → 전부 공백 자리 (0건)
      - 어떤 \\n 하나를 지웠을 때 == 시트     → 그 \\n 은 공백 없는 자리에 끼워 넣은 것 (FAIL)
    시트와 맞출 수 없으면(★1 도 FAIL 인 경우) 대체 규칙: \\n 앞뒤가 둘 다 한글이면 FAIL.
    """
    idx = [i for i, ch in enumerate(text) if ch == "\n"]
    if reference is not None:
        ref = normalize_copy(reference)
        if normalize_copy(text) == ref:
            return []
        hits = [i for i in idx if normalize_copy(text[:i] + text[i + 1:]) == ref]
        if hits:
            return hits
    return [i for i in idx if 0 < i < len(text) - 1
            and is_hangul(text[i - 1]) and is_hangul(text[i + 1])]


# ---------------------------------------------------------------- 게이트 결과
@dataclass
class Gate:
    gate: str
    run: Path
    checks: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def check(self, check_id: str, ok: bool, detail: str = "", back_to: str = "", star: str = ""):
        self.checks.append({"id": check_id, "ok": bool(ok), "detail": detail,
                            "back_to": back_to, "star": star})
        return ok

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(c["ok"] for c in self.checks)

    def finish(self) -> int:
        out = {"gate": self.gate, "passed": self.passed, "at": now_iso(),
               "checks": self.checks, "notes": self.notes}
        write_json(self.run / "04" / f"{self.gate.lower()}.json", out)
        write_qa_report(self.run)
        fails = [c for c in self.checks if not c["ok"]]
        print(f"{self.gate}: {'PASS' if self.passed else 'FAIL'} "
              f"({len(self.checks) - len(fails)}/{len(self.checks)})")
        for c in fails:
            star = f"[{c['star']}] " if c["star"] else ""
            print(f"  FAIL {star}{c['id']}: {c['detail']} → 복귀 {c['back_to'] or '-'}")
        return 0 if self.passed else 1


def write_qa_report(run: Path) -> None:
    lines = ["# qa-report", "", "> 판정 스크립트가 자동 생성. 직접 편집 금지.", ""]
    for gate in ("g1", "g2", "g3", "g4", "g5"):
        p = run / "04" / f"{gate}.json"
        if not p.exists():
            continue
        data = load_json(p)
        lines += [f"## {gate.upper()} — {'PASS' if data['passed'] else 'FAIL'} ({data['at']})", "",
                  "| 결과 | ★ | 항목 | 측정/사유 | 복귀 |", "|---|---|---|---|---|"]
        for c in data["checks"]:
            detail = str(c["detail"]).replace("|", "\\|").replace("\n", "\\n")
            lines.append(f"| {'PASS' if c['ok'] else '**FAIL**'} | {c['star']} | {c['id']} "
                         f"| {detail} | {c['back_to']} |")
        for n in data.get("notes", []):
            lines.append(f"\n- 참고: {n}")
        lines.append("")
    (run / "04").mkdir(parents=True, exist_ok=True)
    (run / "04" / "qa-report.md").write_text("\n".join(lines), encoding="utf-8")


def main_wrapper(fn):
    """usage/환경 오류는 exit 2, FAIL 은 exit 1, PASS 는 exit 0."""
    try:
        sys.exit(fn(sys.argv[1:]))
    except (FileNotFoundError, KeyError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)
