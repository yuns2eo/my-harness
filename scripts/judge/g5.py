#!/usr/bin/env python3
"""G5 (S5) — 전달. 사용법: g5.py <run> --phase pre|post

pre : 업로드 전. PNG 수 = 프레임 수, 정확히 3x, 파일명 규칙, 승인 해시 일치
post: 전달 후. 05/delivery.json 에 링크·노션·댓글·이모지·멘션 검증 기록
"""
import re
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import (Gate, expected_frames, export_name, load_brief, load_json, load_rules,  # noqa: E402
                    main_wrapper, run_dir, sha256)


def pre(r: Path, rules: dict, brief: dict, g: Gate) -> None:
    expected = expected_frames(brief, rules)
    preview = r / "04" / "preview"
    pngs = sorted(p.name for p in preview.glob("*.png")) if preview.exists() else []
    g.check("PNG 수 = 프레임 수", len(pngs) == len(expected), f"{len(pngs)} / {len(expected)}", "S4")
    expected_names = {export_name(e["name"]) for e in expected}
    g.check("파일명 규칙", set(pngs) == expected_names,
            f"규칙 밖: {sorted(set(pngs) - expected_names)} / 누락: {sorted(expected_names - set(pngs))}", "S4")
    g.check("@3x 접미사 없음", not any("@" in n for n in pngs), "", "S4")

    ap_path = r / "04" / "approval.json"
    approval = load_json(ap_path) if ap_path.exists() else None
    g.check("승인 기록 존재", approval is not None, "04/approval.json", "S4")
    scale = rules["export_scale"]
    for e in expected:
        p = preview / export_name(e["name"])
        if not p.exists():
            continue
        w, h = Image.open(p).size
        want = (e["size"][0] * scale, e["size"][1] * scale)
        g.check(f"픽셀 크기 {p.name}", (w, h) == want, f"{w}×{h} (기대 {want[0]}×{want[1]})", "S4")
        if approval is not None:
            g.check(f"승인 해시 {p.name}", approval.get("png_sha256", {}).get(p.name) == sha256(p),
                    "승인 후 파일이 바뀜 → 업로드 중단", "S4")


def post(r: Path, rules: dict, g: Gate) -> None:
    dp = r / "05" / "delivery.json"
    if not g.check("05/delivery.json 존재", dp.exists(), "", "S5"):
        return
    d = load_json(dp)
    g.check("드라이브 링크 1", bool((d.get("drive") or {}).get("link")), "", "S5")
    notion = d.get("notion") or {}
    for prop in rules["notion"]["properties"]:
        g.check(f"노션 속성 {prop}", bool(notion.get(prop)), repr(notion.get(prop)), "S5")
    slack = d.get("slack") or {}
    g.check("Slack 댓글 ts 1", bool(slack.get("ts")), "", "S5")
    raw = slack.get("raw_text_after_send", "")
    g.check("Slack 멘션 토큰", bool(re.search(rules["slack"]["mention_regex"], raw)),
            f"재조회 원문: {raw!r} → 텍스트 멘션이면 알림 안 감 (재전송 금지, 보고)", "S5")
    reactions = set(d.get("reactions") or [])
    for emo in (rules["slack"]["start_emoji"], rules["slack"]["done_emoji"]):
        g.check(f"이모지 {emo}", emo in reactions, "", "S5")


def run(argv) -> int:
    if len(argv) != 3 or argv[1] != "--phase" or argv[2] not in ("pre", "post"):
        raise ValueError("사용법: g5.py <run> --phase pre|post")
    r = run_dir(argv[0])
    rules = load_rules()
    brief = load_brief(r)
    g = Gate("G5", r)
    if argv[2] == "pre":
        pre(r, rules, brief, g)
    else:
        post(r, rules, g)
    g.notes.append(f"phase={argv[2]}")
    return g.finish()


if __name__ == "__main__":
    main_wrapper(run)
