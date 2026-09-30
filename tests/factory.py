"""합성 run 생성기. 실제 상품 이미지·문구 없음 (공개 저장소). 이미지는 numpy 로 그린다.

build_run(tmp) → 모든 게이트가 PASS 하는 run 폴더. 테스트는 이것을 조금씩 망가뜨려 FAIL 을 확인한다.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
import common  # noqa: E402

RULES = yaml.safe_load((ROOT / "rules.yaml").read_text(encoding="utf-8"))
S = RULES["export_scale"]

BRIEF = {
    "brands": ["테스트펫"], "main_copy": "테스트펫 가을\n사료 할인전", "sub_copy": "최대 20% 할인",
    "benefit": "최대 20%", "discount_rate": 20, "split": "none",
    "banners": ["main", "strip", "renewal"], "plan_month": "2026-10", "job_name": "테스트펫브랜드전",
    "made_date": "261001", "product_images": ["product.png"], "gpt_image": "Y", "logo_file": None,
    "logo_variants_found": ["테스트펫"], "notes": "합성 테스트", "thread_url": "https://example.invalid/t",
    "requester_id": "UTEST", "notion_page_id": "test",
}
# Google Sheets Sync 방식: 시트 헤더 = 텍스트 레이어 이름("#" 제외), 1:1 비교
SHEET = {"columns": {
    "brand_name": "테스트펫", "benefit": "최대 20%",
    "M_main_text": "테스트펫 가을 사료 할인전", "sub_text": "최대 20% 할인",
    "L_main_text_basic": "테스트펫 가을 사료", "L_main_text_bold": "최대 20% 할인",
    "R_brand_name": "테스트펫", "R_benefit": "최대 20%",
    "R_main_text 1": "테스트펫 가을", "R_main_text 2": "사료 할인전", "R_sub_text": "최대 20% 할인",
}, "source_url": "https://example.invalid/s", "fetched_at": "2026-10-01T00:00:00+00:00"}
# 배너에 들어간 실제 텍스트가 시트와 다른 경우 (공백 자리 줄바꿈)
BANNER_TEXT = {"#M_main_text": "테스트펫 가을\n사료 할인전"}
STYLE = {"font_family": "Pretendard", "font_weight": 700, "font_size": 20, "line_height": 26,
         "letter_spacing": 0}
BG = "#F0EBE3"
BG_RGB = (240, 235, 227)

# 배너별 레이아웃 (pt). 피사체 박스는 subject 범위 안에 들어가게.
LAYOUT = {
    "main": {
        "texts": {"#brand_name": (16, 16, 60, 20), "#benefit": (85, 16, 60, 20),   # 간격 9
                  "#M_main_text": (16, 40, 120, 52), "#sub_text": (16, 100, 120, 26)},
        "logo": (16, 150, 32, 32),
        "slot": (141, -34, 234, 234),
        "subject": (200, 14, 150, 172),          # x, y, w, h → 높이 172 (170~175)
    },
    "strip": {
        "texts": {"#L_main_text_basic": (600, 40, 400, 26), "#L_main_text_bold": (600, 80, 400, 26)},
        "logo": (180, 47, 128, 128),
        "slot": (325, 0, 255, 222),
        "subject": (360, 17, 180, 188),          # 높이 188 (185~190), x 360~540 ⊂ 325~580
    },
    "renewal": {
        "texts": {"#R_main_text 1": (20, 20, 287, 26), "#R_main_text 2": (20, 46, 287, 26),
                  "#R_sub_text": (20, 80, 287, 20),
                  "#R_brand_name": (20, 108, 100, 10), "#R_benefit": (129, 108, 100, 10)},   # 간격 9
        "logo": (270, 20, 40, 40),
        "slot": (0, 120, 327, 207),
        "subject": (88.5, 135, 150, 170),        # 높이 170 (165~180), 중앙
    },
}


def sheet_text(layer: str) -> str:
    return SHEET["columns"][layer.lstrip("#")]


def text_node(name, x, y, w, h, chars):
    lines = chars.count("\n") + 1
    return {"id": f"t:{name}", "name": name, "type": "TEXT", "x": x, "y": y, "width": w, "height": h,
            "characters": chars, "style": dict(STYLE), "rendered_lines": lines, "is_mask": False, "fills": []}


def build_frame(banner: str, name: str, idx: int) -> dict:
    lay = LAYOUT[banner]
    w, h = RULES["banners"][banner]["size"]
    nodes = []
    for nm, (x, y, tw, th) in lay["texts"].items():
        chars = BANNER_TEXT.get(nm, sheet_text(nm))
        nodes.append(text_node(nm, x, y, tw, th, chars))
    lx, ly, lw, lh = lay["logo"]
    nodes.append({"id": f"l:{idx}", "name": "logo", "type": "INSTANCE", "x": lx, "y": ly, "width": lw,
                  "height": lh, "component_set": "logo", "variant": {"brand": "테스트펫"},
                  "is_mask": False, "fills": []})
    sx, sy, sw, sh = lay["slot"]
    nodes.append({"id": f"s:{idx}", "name": "#image", "type": "RECTANGLE", "x": sx, "y": sy, "width": sw,
                  "height": sh, "is_mask": False, "fills": [{"type": "IMAGE"}]})
    return {"id": f"{idx}:1", "name": name, "banner": banner, "width": w, "height": h,
            "background": BG, "nodes": nodes}


def render_png(frame: dict, path: Path, subject=None, subject_lum=None, slot_bg=None, seed=0):
    """배경: 단색 + 노이즈(std≈5). 피사체: 텍스처(std≈25). subject_lum 로 흰 피사체 가능."""
    rng = np.random.default_rng(seed)
    w, h = frame["width"] * S, frame["height"] * S
    img = np.empty((h, w, 3), dtype=np.float64)
    img[:] = BG_RGB
    img += rng.normal(0, 5, (h, w, 1))
    lay = LAYOUT[frame["banner"]]
    if slot_bg is not None:
        sx, sy, sw, sh = lay["slot"]
        x0, x1 = int(max(sx, 0) * S), int(min(sx + sw, frame["width"]) * S)
        img[:, x0:x1] = slot_bg
        img[:, x0:x1] += rng.normal(0, 5, (h, x1 - x0, 1))
    x, y, sw, sh = subject or lay["subject"]
    x0, y0, x1, y1 = int(x * S), int(y * S), int((x + sw) * S), int((y + sh) * S)
    base = subject_lum if subject_lum is not None else 150
    img[y0:y1, x0:x1] = base + rng.normal(0, 25, (y1 - y0, x1 - x0, 1))
    # 텍스트 영역에 글자 흉내 (측정 제외 영역이 제대로 빠지는지 확인용)
    for n in frame["nodes"]:
        if n["type"] == "TEXT":
            tx0, ty0 = int(n["x"] * S), int(n["y"] * S)
            tx1, ty1 = int((n["x"] + n["width"]) * S), int((n["y"] + n["height"]) * S)
            img[ty0:ty1:4, tx0:tx1] = 20
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(path)


def write_brief(run: Path, brief: dict) -> None:
    fm = yaml.safe_dump(brief, allow_unicode=True, sort_keys=False)
    (run / "01" / "brief.md").write_text(f"---\n{fm}---\n\n# 합성 요청\n", encoding="utf-8")


def build_run(tmp: Path, brief: dict | None = None, sheet: dict | None = None) -> Path:
    brief = dict(brief or BRIEF)
    run = tmp / f"{brief['made_date']}_{brief['job_name']}"
    for d in ("01", "02", "03/images", "04/preview", "05"):
        (run / d).mkdir(parents=True, exist_ok=True)
    write_brief(run, brief)
    (run / "01" / "sheet.json").write_text(json.dumps(sheet or SHEET, ensure_ascii=False), encoding="utf-8")

    frames = []
    idx = 1
    for e in common.expected_frames(brief, RULES):
        frames.append(build_frame(e["banner"], e["name"], idx))
        idx += 1
    template = {b: {nm: dict(STYLE) for nm in LAYOUT[b]["texts"]} for b in LAYOUT}
    snap = {"file_key": "EXAMPLEFILEKEY",
            "section": {"id": "0:9", "name": f"{brief['made_date']}_{brief['job_name']}"},
            "frames": frames, "template": template}
    save_snapshot(run, snap)
    (run / "02" / "figma.json").write_text(json.dumps(
        {"section_id": "0:9", "section_name": snap["section"]["name"],
         "frames": {f["name"]: f["id"] for f in frames}}, ensure_ascii=False), encoding="utf-8")

    for i, f in enumerate(frames):
        render_png(f, run / "04" / "preview" / f"{f['name']}.png", seed=i)

    img = run / "03" / "images" / "gpt_main.png"
    Image.fromarray(np.full((8, 8, 3), 200, dtype=np.uint8)).save(img)
    digest = hashlib.sha256(img.read_bytes()).hexdigest()
    (run / "03" / "images.json").write_text(json.dumps(
        [{"file": img.name, "bytes": img.stat().st_size, "sha256_before": digest, "sha256_after": digest,
          "at": "2026-10-01T00:00:00+00:00"}]), encoding="utf-8")
    return run


def load_snapshot(run: Path) -> dict:
    return json.loads((run / "04" / "figma_snapshot.json").read_text(encoding="utf-8"))


def save_snapshot(run: Path, snap: dict) -> None:
    (run / "04" / "figma_snapshot.json").write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")


def node(snap: dict, frame_banner: str, name: str) -> dict:
    f = next(f for f in snap["frames"] if f["banner"] == frame_banner)
    return next(n for n in f["nodes"] if n["name"] == name)
