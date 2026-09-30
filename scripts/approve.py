#!/usr/bin/env python3
"""S4 승인 기록 (오케스트레이터 전용). 사용법: approve.py <run>

디자이너가 "승인"이라고 했을 때만 실행한다. G4 PASS 가 아니면 거부.
04/approval.json 에 승인 시각, qa-report 해시, PNG 별 sha256 을 기록한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from common import load_json, main_wrapper, now_iso, run_dir, sha256, write_json  # noqa: E402


def run(argv) -> int:
    if len(argv) != 1:
        raise ValueError("사용법: approve.py <run>")
    r = run_dir(argv[0])
    g4 = r / "04" / "g4.json"
    if not (g4.exists() and load_json(g4)["passed"]):
        print("G4 PASS 가 아니라 승인할 수 없습니다")
        return 1
    pngs = sorted((r / "04" / "preview").glob("*.png"))
    write_json(r / "04" / "approval.json", {
        "approved_at": now_iso(), "approver": "designer",
        "qa_report_sha256": sha256(r / "04" / "qa-report.md"),
        "png_sha256": {p.name: sha256(p) for p in pngs},
    })
    print(f"승인 기록: PNG {len(pngs)}개")
    return 0


if __name__ == "__main__":
    main_wrapper(run)
