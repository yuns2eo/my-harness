#!/usr/bin/env python3
"""G3 (S3 뒤) — 이미지. 사용법: g3.py <run>

입력: 03/images.json, 03/images/, 04/figma_snapshot.json, 04/preview/*.png (fetch.py 가 생성)
"""
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import (Gate, expected_frames, export_name, load_brief, load_json, load_rules,  # noqa: E402
                    main_wrapper, run_dir, sha256)
from subject import column_mean_diff, measure_subject  # noqa: E402

BACK = "S3 배치"


def exclude_boxes(frame: dict, rules: dict):
    """텍스트·로고·버튼(= 이미지 슬롯이 아닌 모든 노드) bbox."""
    slot = rules["image"]["slot_name"]
    return [(n["x"], n["y"], n["width"], n["height"]) for n in frame["nodes"]
            if n["name"] != slot and not n["name"].startswith("__bg_extend")]


def run(argv) -> int:
    if len(argv) != 1:
        raise ValueError("사용법: g3.py <run>")
    r = run_dir(argv[0])
    rules = load_rules()
    brief = load_brief(r)
    snap = load_json(r / "04" / "figma_snapshot.json")
    g = Gate("G3", r)
    scale = rules["export_scale"]
    sub = rules["subject"]

    # ---- 원본 바이트 (반입 전후 sha256)
    ij = r / "03" / "images.json"
    if g.check("03/images.json 존재", ij.exists(), "", "S3"):
        images = load_json(ij)
        g.check("반입 이미지 ≥ 1", len(images) >= 1, f"{len(images)}개", "S3")
        for im in images:
            p = r / "03" / "images" / im["file"]
            now = sha256(p) if p.exists() else None
            g.check(f"원본 바이트 {im['file']}",
                    now is not None and im["sha256_before"] == im["sha256_after"] == now,
                    f"before={im['sha256_before'][:12]} after={im['sha256_after'][:12]} "
                    f"now={(now or '없음')[:12]}", "S3")

    frames = {f["name"]: f for f in snap["frames"]}
    for e in expected_frames(brief, rules):
        f = frames.get(e["name"])
        fname, banner = e["name"], e["banner"]
        if not g.check(f"프레임 존재 {fname}", f is not None, "", "S2"):
            continue

        # ---- 마스크 / 슬롯
        masks = [n["name"] for n in f["nodes"] if n.get("is_mask")]
        g.check(f"마스크 그룹 0 {fname}", not masks, f"마스크: {masks}" if masks else "", BACK)
        slot = next((n for n in f["nodes"] if n["name"] == rules["image"]["slot_name"]), None)
        if not g.check(f"이미지 슬롯 존재 {fname}", slot is not None, rules["image"]["slot_name"], BACK):
            continue
        fills = [fl.get("type") for fl in slot.get("fills", [])]
        g.check(f"슬롯 이미지 fill {fname}", rules["image"]["fill_type"] in fills, f"fills={fills}", BACK)
        if banner == "main":
            ms = rules["image"]["main_slot"]
            got = {"x": slot["x"], "y": slot["y"], "w": slot["width"], "h": slot["height"]}
            g.check(f"메인 슬롯 좌표 {fname}", got == ms, f"{got} (기대 {ms})", BACK)

        # ---- 배경색
        bg = (f.get("background") or "").upper()
        g.check(f"배경색 {fname}", bg not in [c.upper() for c in rules["background"]["forbidden"]],
                bg, BACK)

        # ---- 피사체 (표준편차 방식)
        png = r / "04" / "preview" / export_name(fname)
        if not g.check(f"미리보기 PNG {fname}", png.exists(), str(png.name), BACK):
            continue
        img = Image.open(png)
        boxes = exclude_boxes(f, rules)
        s = measure_subject(img, boxes, scale, sub["std_threshold"])
        if not g.check(f"피사체 검출 {fname}", s is not None, f"std ≥ {sub['std_threshold']} 구간 없음", BACK):
            continue
        lo, hi = sub["height"][banner]
        g.check(f"피사체 높이 {fname}", lo <= s["height"] <= hi, f"{s['height']:.1f} (허용 {lo}~{hi})", BACK)

        # 좌우 여백: 보이는 슬롯 영역(슬롯 ∩ 프레임) 기준
        vis_l = max(slot["x"], 0)
        vis_r = min(slot["x"] + slot["width"], f["width"])
        need = s["width"] * sub["side_margin_ratio"]
        ml, mr = s["left"] - vis_l, vis_r - s["right"]
        g.check(f"좌우 여백 {fname}", ml >= need and mr >= need,
                f"좌 {ml:.1f} / 우 {mr:.1f} (최소 {need:.1f})", BACK)

        if banner == "strip":
            x0, x1 = sub["strip_x_range"]
            g.check(f"띠 피사체 위치 {fname}", s["left"] >= x0 and s["right"] <= x1,
                    f"{s['left']:.1f}~{s['right']:.1f} (허용 {x0}~{x1})", BACK)
        if banner == "renewal":
            g.check(f"리뉴얼 상단 {fname}", s["top"] >= sub["renewal_top_min"],
                    f"top {s['top']:.1f} (최소 {sub['renewal_top_min']})", BACK)
            off = abs((s["left"] + s["right"]) / 2 - f["width"] / 2)
            g.check(f"리뉴얼 가로 중앙 {fname}", off <= sub["renewal_center_tolerance"],
                    f"중심 오차 {off:.1f} (허용 {sub['renewal_center_tolerance']})", BACK)

        # ---- 세로 경계선 (슬롯 좌/우 경계가 프레임 안에 있을 때)
        for edge in (slot["x"], slot["x"] + slot["width"]):
            d = column_mean_diff(img, edge, scale, boxes)
            if d is not None:
                g.check(f"경계선 x={edge} {fname}", d < rules["seam"]["max_col_diff"],
                        f"{d:.1f} (기준 < {rules['seam']['max_col_diff']})", BACK)
    return g.finish()


if __name__ == "__main__":
    main_wrapper(run)
