#!/usr/bin/env python3
"""판정 입력 수집 (읽기 전용). 사용법: fetch.py <run>

Figma REST API 로 복제 섹션과 원본 템플릿 섹션을 읽어
  04/figma_snapshot.json  (G2·G3 가 읽는 정규화 스냅샷)
  04/preview/{프레임명}.png  (3x export = 전달 PNG)
를 만든다. Figma 에 쓰지 않는다. 토큰은 환경변수 FIGMA_TOKEN.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import export_name, load_json, load_rules, main_wrapper, run_dir, write_json  # noqa: E402

API = "https://api.figma.com/v1"


def get(url: str, token: str):
    req = urllib.request.Request(url, headers={"X-Figma-Token": token})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def hex_color(fills) -> str | None:
    for f in fills or []:
        if f.get("type") == "SOLID" and f.get("visible", True):
            c = f["color"]
            return "#" + "".join(f"{round(c[k] * 255):02X}" for k in ("r", "g", "b"))
    return None


def flatten(node, origin, comps, sets, out):
    bb = node.get("absoluteBoundingBox") or {}
    item = {
        "id": node["id"], "name": node["name"], "type": node["type"],
        "x": round(bb.get("x", 0) - origin[0], 2), "y": round(bb.get("y", 0) - origin[1], 2),
        "width": round(bb.get("width", 0), 2), "height": round(bb.get("height", 0), 2),
        "is_mask": bool(node.get("isMask")),
        "fills": [{"type": f.get("type")} for f in node.get("fills", []) if isinstance(f, dict)],
    }
    if node["type"] == "TEXT":
        st = node.get("style", {})
        lh = st.get("lineHeightPx") or 1
        item["characters"] = node.get("characters", "")
        item["style"] = {"font_family": st.get("fontFamily"), "font_weight": st.get("fontWeight"),
                         "font_size": st.get("fontSize"), "line_height": st.get("lineHeightPx"),
                         "letter_spacing": st.get("letterSpacing")}
        item["rendered_lines"] = max(1, round(item["height"] / lh))
    if node["type"] == "INSTANCE":
        comp = comps.get(node.get("componentId"), {})
        item["component_set"] = sets.get(comp.get("componentSetId"), {}).get("name")
        item["variant"] = {k.split("#")[0]: v.get("value")
                           for k, v in (node.get("componentProperties") or {}).items()
                           if v.get("type") == "VARIANT"}
    out.append(item)
    if node["type"] in ("INSTANCE",):  # 인스턴스 내부는 판정 대상 아님
        return
    for ch in node.get("children", []):
        flatten(ch, origin, comps, sets, out)


def banner_of(name: str, rules: dict) -> str | None:
    for key, b in rules["banners"].items():
        if b["label"] in name:
            return key
    return None


def read_section(doc, rules):
    comps, sets = doc.get("components", {}), doc.get("componentSets", {})
    sec = doc["document"]
    frames = []
    for fr in sec.get("children", []):
        if fr["type"] not in ("FRAME", "COMPONENT", "INSTANCE"):
            continue
        bb = fr["absoluteBoundingBox"]
        nodes = []
        for ch in fr.get("children", []):
            flatten(ch, (bb["x"], bb["y"]), comps, sets, nodes)
        frames.append({"id": fr["id"], "name": fr["name"], "banner": banner_of(fr["name"], rules),
                       "width": round(bb["width"]), "height": round(bb["height"]),
                       "background": hex_color(fr.get("fills")), "nodes": nodes})
    return sec, frames


def run(argv) -> int:
    if len(argv) != 1:
        raise ValueError("사용법: fetch.py <run>")
    token = os.environ.get("FIGMA_TOKEN")
    if not token:
        raise KeyError("환경변수 FIGMA_TOKEN 이 없습니다")
    r = run_dir(argv[0])
    rules = load_rules()
    key = rules["figma"]["file_key"]
    fig = load_json(r / "02" / "figma.json")
    sec_id, tpl_id = fig["section_id"], rules["figma"]["template_section_id"]

    data = get(f"{API}/files/{key}/nodes?ids={urllib.parse.quote(f'{sec_id},{tpl_id}')}", token)
    sec, frames = read_section(data["nodes"][sec_id], rules)
    _, tpl_frames = read_section(data["nodes"][tpl_id], rules)

    template = {}
    for tf in tpl_frames:
        if tf["banner"] and tf["banner"] not in template:
            template[tf["banner"]] = {n["name"]: n["style"] for n in tf["nodes"] if n["type"] == "TEXT"}

    write_json(r / "04" / "figma_snapshot.json",
               {"file_key": key, "section": {"id": sec["id"], "name": sec["name"]},
                "frames": frames, "template": template})

    ids = ",".join(f["id"] for f in frames)
    urls = get(f"{API}/images/{key}?ids={urllib.parse.quote(ids)}&scale={rules['export_scale']}&format=png",
               token)["images"]
    out = r / "04" / "preview"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.png"):
        old.unlink()
    for f in frames:
        with urllib.request.urlopen(urls[f["id"]], timeout=120) as resp:
            (out / export_name(f["name"])).write_bytes(resp.read())
    print(f"fetch: 프레임 {len(frames)}개 → 04/figma_snapshot.json, 04/preview/")
    return 0


if __name__ == "__main__":
    main_wrapper(run)
