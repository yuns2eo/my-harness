#!/usr/bin/env python3
"""G4 (S4) — 승인 화면 준비. 사용법: g4.py <run>

G1~G3 가 전부 PASS 이고 Figma 링크 수 = 프레임 수일 때만 04/approval-screen.md 를 만든다.
승인 자체는 사람이 한다 (approve.py 가 04/approval.json 기록).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import (Gate, expected_frames, export_name, figma_link, load_brief, load_json,  # noqa: E402
                    load_rules, main_wrapper, run_dir)


def run(argv) -> int:
    if len(argv) != 1:
        raise ValueError("사용법: g4.py <run>")
    r = run_dir(argv[0])
    rules = load_rules()
    brief = load_brief(r)
    g = Gate("G4", r)

    for prev in ("g1", "g2", "g3"):
        p = r / "04" / f"{prev}.json"
        ok = p.exists() and load_json(p)["passed"]
        g.check(f"{prev.upper()} PASS", ok, "없음" if not p.exists() else "", prev.upper())

    snap = load_json(r / "04" / "figma_snapshot.json")
    frames = {f["name"]: f for f in snap["frames"]}
    expected = expected_frames(brief, rules)
    links = [(e["name"], figma_link(rules, frames[e["name"]]["id"]))
             for e in expected if e["name"] in frames]
    g.check("Figma 링크 수 = 프레임 수", len(links) == len(expected),
            f"{len(links)} / {len(expected)}", "S2")
    for name, _ in links:
        g.check(f"미리보기 {name}", (r / "04" / "preview" / export_name(name)).exists(), "", "S3 배치")

    code = g.finish()
    if code != 0:
        return code

    notes = []
    for prev in ("g2",):
        notes += load_json(r / "04" / f"{prev}.json").get("notes", [])
    sub = rules["subject"]
    lines = [
        f"# 승인 화면 — {rules['naming']['section'].format(made=brief['made_date'], job=brief['job_name'])}",
        "", "기계 게이트 G1~G3: **전부 PASS** (상세: `04/qa-report.md`)", "",
        "## Figma 프레임", *[f"- [{n}]({u})" for n, u in links], "",
        "## PNG 미리보기", *[f"- `04/preview/{export_name(n)}`" for n, _ in links], "",
        "## 사람 체크리스트",
        "- [ ] 제품 라벨·포장이 원본과 같다",
        f"- [ ] (메인) 동물 얼굴이 x{sub['face_x_max_main']} 왼쪽 — 그라데이션에 가리지 않는다",
        "- [ ] 여백·정렬·시각 보정",
        f"- [ ] 기타 요청사항(V13): {brief.get('notes') or '없음'}",
        *(f"- [ ] {n}" for n in notes),
        "", "승인하려면 \"승인\", 반려하려면 \"반려: 사유\"",
    ]
    (r / "04" / "approval-screen.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    main_wrapper(run)
