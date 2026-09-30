#!/usr/bin/env python3
"""PreToolUse 훅 — 에이전트별 편집 폴더와 외부 쓰기 권한 강제 (docs/r6-roles.md).

stdin: Claude Code 훅 입력 JSON. 서브에이전트 호출이면 agent_type 에 에이전트 이름이 온다.
exit 0 = 허용, exit 2 = 차단 (stderr 가 Claude 에게 전달됨).
유지보수: 저장소 루트에 .harness-maintenance 파일이 있을 때만 파일 편집 제한을 건너뛴다.
      외부 쓰기 제한(Figma, Slack, 드라이브, 노션)은 플래그가 있어도 유지한다.
표준 라이브러리만 쓴다 (.venv 없이도 동작).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ORCH = "orchestrator"
MAINTENANCE_FLAG = ROOT / ".harness-maintenance"

# 에이전트 → 편집 가능한 run 하위 경로 (정규식, ROOT 기준 상대경로)
EDIT = {
    "brief-agent": [r"runs/[^/]+/01/.+"],
    "figma-agent": [r"runs/[^/]+/02/.+"],
    "image-agent": [r"runs/[^/]+/03/.+"],
    "judge": [],                                   # 판정 스크립트만 쓴다
    "delivery-agent": [r"runs/[^/]+/05/.+"],
    ORCH: [r"runs/[^/]+/state\.json", r"runs/[^/]+/04/approval\.json"],
}

# 외부 쓰기 MCP 도구 → 허용 에이전트
EXTERNAL = [
    (r"mcp__plugin_figma_figma__(use_figma|create_new_file|upload_assets|add_code_connect_map|"
     r"send_code_connect_mappings|generate_figma_design|generate_diagram)", {"figma-agent"}),
    (r"mcp__claude_ai_Slack__slack_add_reaction", {"brief-agent", "delivery-agent"}),
    (r"mcp__claude_ai_Slack__slack_(send_message|send_message_draft|schedule_message|"
     r"create_canvas|update_canvas|create_conversation)", {"delivery-agent"}),
    (r"mcp__claude_ai_Notion__notion-(update-page|create-pages|create-comment|move-pages|"
     r"duplicate-page|update-data-source|create-database)", {"delivery-agent"}),
    (r"mcp__claude_ai_Google_Drive__(create_file|update_file|copy_file|trash_file|share_file)",
     {"delivery-agent"}),
]
FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def block(msg: str) -> None:
    print(f"[harness guard] 차단: {msg}", file=sys.stderr)
    sys.exit(2)


def main() -> None:
    data = json.load(sys.stdin)
    tool = data.get("tool_name", "")
    agent = data.get("agent_type") or ORCH

    if tool in FILE_TOOLS:
        if MAINTENANCE_FLAG.exists():
            sys.exit(0)
        ti = data.get("tool_input") or {}
        raw = ti.get("file_path") or ti.get("notebook_path") or ""
        p = Path(raw)
        if not p.is_absolute():
            p = Path(data.get("cwd") or ROOT) / p
        try:
            rel = p.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            block(f"{agent}: 저장소 밖 경로 {raw}")
        allowed = EDIT.get(agent)
        if allowed is None:
            block(f"알 수 없는 에이전트 {agent}")
        if not any(re.fullmatch(rx, rel) for rx in allowed):
            block(f"{agent} 는 {rel} 을 편집할 수 없습니다 (편집 폴더: {allowed or '없음'})")
        sys.exit(0)

    if tool.startswith("mcp__"):
        for rx, agents in EXTERNAL:
            if re.fullmatch(rx, tool):
                if agent not in agents:
                    block(f"{agent} 는 외부 쓰기 {tool} 권한이 없습니다 (허용: {sorted(agents)})")
                sys.exit(0)
    sys.exit(0)


if __name__ == "__main__":
    main()
