#!/usr/bin/env python3
"""하네스 설정 검사 (docs/r8-verify.md §3). 사용법: check_harness.py"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ["brief-agent", "figma-agent", "image-agent", "judge", "delivery-agent"]
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
FIGMA_WRITE = re.compile(r"mcp__plugin_figma_figma__(use_figma|create_new_file|upload_assets|generate_)")

results = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))


def numbers_in(obj, out: set) -> set:
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.add(str(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            numbers_in(v, out)
    elif isinstance(obj, list):
        for v in obj:
            numbers_in(v, out)
    return out


def table_first_col(md: str, heading_rx: str) -> set:
    m = re.search(heading_rx + r"[^\n]*\n\s*((?:\|[^\n]*\n)+)", md)
    if not m:
        return set()
    out = set()
    for row in m.group(1).splitlines()[2:]:
        cell = row.split("|")[1].strip()
        for part in cell.split(" / "):
            out.add(part.strip().strip('"'))
    return out


def frontmatter(path: Path) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), re.S)
    return yaml.safe_load(m.group(1)) if m else {}


def tools_of(fm: dict) -> list[str]:
    t = fm.get("tools", [])
    return [x.strip() for x in t.split(",")] if isinstance(t, str) else list(t)


def guard_cases() -> None:
    """guard.py 를 임시 저장소에 복사해 실제 차단 여부를 확인한다."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "scripts" / "hooks").mkdir(parents=True)
        shutil.copy(ROOT / "scripts" / "hooks" / "guard.py", tmp / "scripts" / "hooks" / "guard.py")

        def call(agent, tool, path=None):
            payload = {"tool_name": tool, "cwd": str(tmp), "tool_input": {}}
            if agent:
                payload["agent_type"] = agent
            if path:
                payload["tool_input"]["file_path"] = str(tmp / path)
            p = subprocess.run([sys.executable, str(tmp / "scripts/hooks/guard.py")],
                               input=json.dumps(payload), capture_output=True, text=True)
            return p.returncode

        run = "runs/260101_test"
        own = {"brief-agent": "01", "figma-agent": "02", "image-agent": "03", "delivery-agent": "05"}
        for agent, folder in own.items():
            check(f"훅 {agent} 자기 폴더 허용", call(agent, "Write", f"{run}/{folder}/x.md") == 0)
            other = "02" if folder != "02" else "01"
            check(f"훅 {agent} 남의 폴더 차단", call(agent, "Write", f"{run}/{other}/x.md") == 2)
            check(f"훅 {agent} rules.yaml 차단", call(agent, "Edit", "rules.yaml") == 2)
        check("훅 judge 04/ 직접 쓰기 차단", call("judge", "Write", f"{run}/04/qa-report.md") == 2)
        check("훅 오케스트레이터 state.json 허용", call(None, "Write", f"{run}/state.json") == 0)
        check("훅 오케스트레이터 approval.json 허용", call(None, "Write", f"{run}/04/approval.json") == 0)
        check("훅 오케스트레이터 scripts/ 차단", call(None, "Edit", "scripts/judge/g1.py") == 2)
        check("훅 오케스트레이터 01/ 차단", call(None, "Write", f"{run}/01/brief.md") == 2)
        check("훅 저장소 밖 차단", call("brief-agent", "Write", "../outside.md") == 2)
        check("훅 오케스트레이터 Figma 쓰기 차단", call(None, "mcp__plugin_figma_figma__use_figma") == 2)
        check("훅 figma-agent Figma 쓰기 허용", call("figma-agent", "mcp__plugin_figma_figma__use_figma") == 0)
        check("훅 오케스트레이터 Slack 전송 차단", call(None, "mcp__claude_ai_Slack__slack_send_message") == 2)
        check("훅 brief-agent Slack 전송 차단", call("brief-agent", "mcp__claude_ai_Slack__slack_send_message") == 2)
        check("훅 delivery-agent Slack 전송 허용",
              call("delivery-agent", "mcp__claude_ai_Slack__slack_send_message") == 0)
        check("훅 읽기 MCP 허용", call(None, "mcp__claude_ai_Slack__slack_read_thread") == 0)

        (tmp / ".harness-maintenance").touch()
        check("훅 플래그: 오케스트레이터 scripts/ 편집 허용", call(None, "Edit", "scripts/judge/g1.py") == 0)
        check("훅 플래그: 외부 쓰기 제한 유지 (Slack)", call(None, "mcp__claude_ai_Slack__slack_send_message") == 2)
        check("훅 플래그: 외부 쓰기 제한 유지 (Drive)", call(None, "mcp__claude_ai_Google_Drive__trash_file") == 2)


def main() -> int:
    claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    rules = yaml.safe_load((ROOT / "rules.yaml").read_text(encoding="utf-8"))

    # 1. 길이
    n = len(claude.splitlines())
    check("CLAUDE.md ≤ 150줄", n <= 150, f"{n}줄")

    # 2. rules.yaml 수치 0건
    nums = numbers_in(rules, set())
    # ★1~3, §3 같은 라벨 번호는 제외하고 남은 숫자가 rules.yaml 값과 같으면 FAIL
    body = re.sub(r"[★§]\d+(?:~\d+)?", "", claude)
    found = [t for t in re.findall(r"(?<![0-9A-Za-z_./{])\d+(?:\.\d+)?(?![0-9A-Za-z_./}])", body)
             if t in nums]
    check("CLAUDE.md 안 rules.yaml 수치 0건", not found, f"발견: {sorted(set(found))}")

    # 3. 문서 경로 존재
    missing = []
    for ref in re.findall(r"`([^`]+)`", claude):
        cand = ref.split(" ")[0]
        if not re.match(r"^(docs/|scripts/|rules\.|\.claude/)", cand):
            continue
        paths = [cand.replace("{n}", str(i)) for i in range(1, 6)] if "{n}" in cand else [cand]
        for p in paths:
            ok = (ROOT / p).exists() or (p == "rules.local.yaml" and (ROOT / "rules.local.example.yaml").exists())
            if not ok:
                missing.append(p)
    check("CLAUDE.md 경로 전부 존재", not missing, f"없음: {missing}")

    # 4. CLAUDE.md 가 가리키는 rules 키 존재
    bad_keys = []
    for key in set(re.findall(r"`([a-z_]+\.[a-z_]+)`", claude)):
        if key.endswith((".md", ".json", ".yaml", ".py")):
            continue
        node = rules
        for part in key.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        if node is None:
            bad_keys.append(key)
    check("CLAUDE.md rules 키 존재", not bad_keys, f"없음: {bad_keys}")

    # 5. 에이전트 정의
    for a in AGENTS:
        p = ROOT / ".claude" / "agents" / f"{a}.md"
        if not p.exists():
            check(f"에이전트 {a} 존재", False)
            continue
        fm = frontmatter(p)
        check(f"에이전트 {a} name 일치", fm.get("name") == a, repr(fm.get("name")))
        check(f"에이전트 {a} tools 명시", bool(tools_of(fm)))
    jp = ROOT / ".claude" / "agents" / "judge.md"
    if jp.exists():
        tools = tools_of(frontmatter(jp))
        bad = [t for t in tools if t in WRITE_TOOLS or FIGMA_WRITE.match(t)]
        check("judge 쓰기 도구 없음", not bad, f"{bad}")
    figma_writers = [a for a in AGENTS if (ROOT / ".claude/agents" / f"{a}.md").exists()
                     and any(FIGMA_WRITE.match(t) for t in tools_of(frontmatter(ROOT / ".claude/agents" / f"{a}.md")))]
    check("Figma 쓰기 에이전트 = figma-agent 1개", figma_writers == ["figma-agent"], f"{figma_writers}")

    # 6. 훅 등록 + 동작
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    pre = settings.get("hooks", {}).get("PreToolUse", [])
    file_hook = any("Write" in h.get("matcher", "") and "Edit" in h.get("matcher", "")
                    and any("guard.py" in x.get("command", "") for x in h.get("hooks", [])) for h in pre)
    mcp_hook = any(h.get("matcher", "").startswith("mcp__")
                   and any("guard.py" in x.get("command", "") for x in h.get("hooks", [])) for h in pre)
    check("settings.json 편집 훅 등록", file_hook)
    check("settings.json MCP 훅 등록", mcp_hook)
    check("settings.json Slack 전송 ask", "mcp__claude_ai_Slack__slack_send_message"
          in settings.get("permissions", {}).get("ask", []))
    guard_cases()

    # 7. 트리거 표 일치
    r6 = (ROOT / "docs" / "r6-roles.md").read_text(encoding="utf-8")
    a = table_first_col(claude, r"## 트리거")
    b = table_first_col(r6, r"## 4\. 자연어 트리거")
    check("트리거 표 CLAUDE.md = r6-roles.md", a == b and bool(a),
          f"CLAUDE.md만: {sorted(a - b)} / r6만: {sorted(b - a)}")

    # 8. 자리표시자 ↔ 예시 키
    placeholders = set(re.findall(r"\$\{([A-Z0-9_]+)\}", (ROOT / "rules.yaml").read_text(encoding="utf-8")))
    example = yaml.safe_load((ROOT / "rules.local.example.yaml").read_text(encoding="utf-8")) or {}
    check("rules.yaml 자리표시자 ⊂ example 키", placeholders <= set(example),
          f"누락: {sorted(placeholders - set(example))}")

    # 9. 유지보수 플래그 상태 (정보)
    flag = (ROOT / ".harness-maintenance").exists()

    fails = [r for r in results if not r[1]]
    for name, ok, detail in results:
        if not ok:
            print(f"  FAIL {name}: {detail}")
    print(f"check_harness: {len(results) - len(fails)}/{len(results)} PASS"
          + ("  (주의: .harness-maintenance 존재 → 편집 잠금 해제 상태)" if flag else ""))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
