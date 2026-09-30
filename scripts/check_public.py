#!/usr/bin/env python3
"""공개 검사 (docs/r8-verify.md §2). 사용법: check_public.py [--history]

git 이 추적(또는 추적 예정: untracked 이면서 ignore 아님)하는 파일에서
사내 값, 공개 금지어, 실제 ID 가 붙은 링크가 0건이어야 한다. pre-commit 훅으로 실행.
--history 를 주면 모든 커밋 기록(git log --all -p)도 같은 기준으로 검사한다.

사내 값과 금지어는 rules.local.yaml(gitignore)에만 둔다. 이 파일에 적으면 그 자체로 공개된다.
  PUBLIC_FORBIDDEN_WORDS: [...]   대소문자 무시
  그 밖의 키                        값 그대로 (채널, 이모지, ID 등)
"""
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "rules.local.yaml"
EXAMPLE = ROOT / "rules.local.example.yaml"
SKIP = {"rules.local.example.yaml"}   # 예시값 파일
MUST_IGNORE = ["rules.local.yaml", ".harness-maintenance"]
FORBIDDEN_KEY = "PUBLIC_FORBIDDEN_WORDS"

PATTERNS = {
    "Slack user ID": r"\bU[A-Z0-9]{8,}\b",
    "Slack 메시지 링크": r"[a-z0-9-]+\.slack\.com/archives/[A-Z0-9]+",
    "Figma 실제 링크": r"figma\.com/(?:design|file|proto)/[A-Za-z0-9]{10,}",
    "Notion 실제 링크": r"notion\.so/\S*[0-9a-f]{32}",
    "Drive 실제 링크": r"drive\.google\.com/\S*/[A-Za-z0-9_-]{20,}",
    "Sheets 실제 링크": r"docs\.google\.com/spreadsheets/d/[A-Za-z0-9_-]{20,}",
}


def git(*args) -> str:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        print(f"ERROR: git {' '.join(args)} 실패 ({out.stderr.strip()})", file=sys.stderr)
        sys.exit(2)
    return out.stdout


def tracked_files() -> list[str]:
    return [f for f in git("ls-files", "--cached", "--others", "--exclude-standard").splitlines() if f]


def load_local() -> tuple[list[str], list[str]]:
    """(사내 값, 금지어)."""
    if not LOCAL.exists():
        print("경고: rules.local.yaml 없음 → 사내 값·금지어 대조는 건너뜀")
        return [], []
    data = yaml.safe_load(LOCAL.read_text(encoding="utf-8")) or {}
    words = [str(w).strip() for w in data.get(FORBIDDEN_KEY) or [] if str(w).strip()]
    vals = []
    for k, v in data.items():
        if k == FORBIDDEN_KEY or isinstance(v, (list, dict)):
            continue
        s = str(v).strip()
        if len(s) >= 4:
            vals.append(s)
            core = s.strip("#:")          # "#채널명", ":이모지:" 의 본문만으로도 검사
            if core != s and len(core) >= 4:
                vals.append(core)
    return vals, words


def example_values() -> list[str]:
    """예시값(공개용)이 들어간 링크 매치는 사내 값이 아니므로 통과시킨다."""
    if not EXAMPLE.exists():
        return []
    data = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8")) or {}
    return [str(v) for v in data.values() if not isinstance(v, (list, dict)) and len(str(v)) >= 4]


def scan_lines(where: str, lines, values, words, allow, hits) -> None:
    lowered = [w.lower() for w in words]
    for i, line in enumerate(lines, 1):
        for v in values:
            if v in line:
                hits.append((where, i, "rules.local 값", v))
        low = line.lower()
        for w in lowered:
            if w in low:
                hits.append((where, i, "공개 금지어", w))
        for label, rx in PATTERNS.items():
            for m in re.finditer(rx, line):
                if not any(a in m.group(0) for a in allow):
                    hits.append((where, i, label, m.group(0)))


def main(argv) -> int:
    history = "--history" in argv
    files = tracked_files()
    allow = example_values()
    values, words = load_local()
    hits = []
    for must in MUST_IGNORE:
        if must in files:
            hits.append((must, 0, "gitignore 누락", must))
    for rel in files:
        if rel in SKIP or rel in MUST_IGNORE:
            continue
        p = ROOT / rel
        if not p.is_file():
            continue
        raw = p.read_bytes()
        if b"\0" in raw[:4096]:
            continue
        scan_lines(rel, raw.decode("utf-8", errors="ignore").splitlines(), values, words, allow, hits)
    if history:
        log = git("log", "--all", "-p", "--format=commit %H%n%an <%ae>%n%B")
        scan_lines("커밋 기록", log.splitlines(), values, words, allow, hits)

    scope = f"파일 {len(files)}개" + (" + 커밋 기록 전체" if history else "")
    print(f"check_public: {scope}, 사내 값 {len(values)}종, 금지어 {len(words)}종")
    for where, i, label, v in hits:
        print(f"  FAIL {where}:{i} [{label}] {v[:2]}…")   # 값 전체를 로그에 남기지 않는다
    print("PASS (0건)" if not hits else f"FAIL ({len(hits)}건)")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
