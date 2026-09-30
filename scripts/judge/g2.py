#!/usr/bin/env python3
"""G2 (S2 뒤) — 텍스트·로고·규격. ★1·★2·★3 포함. 사용법: g2.py <run>

입력: 01/brief.md, 01/sheet.json, 04/figma_snapshot.json (fetch.py 가 생성)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import (Gate, apply_substitutions, expected_frames, load_brief, load_json,  # noqa: E402
                    load_rules, main_wrapper, midword_breaks, normalize_copy, run_dir, sheet_rows)


def column_of(layer: str, rules: dict) -> str:
    """Google Sheets Sync: 레이어 "#X" ↔ 시트 열 "X"."""
    prefix = rules["text"]["sheet_column_prefix"]
    return layer[len(prefix):] if layer.startswith(prefix) else layer


def by_name(frame: dict) -> dict:
    return {n["name"]: n for n in frame.get("nodes", [])}


def run(argv) -> int:
    if len(argv) != 1:
        raise ValueError("사용법: g2.py <run>")
    r = run_dir(argv[0])
    rules = load_rules()
    brief = load_brief(r)
    sheet = load_json(r / "01" / "sheet.json")
    snap = load_json(r / "04" / "figma_snapshot.json")
    g = Gate("G2", r)
    t = rules["text"]

    frames = {f["name"]: f for f in snap["frames"]}
    expected = expected_frames(brief, rules)
    rows, row_errors = sheet_rows(sheet, brief, rules)
    g.check("★1 시트 행 구성 (한 행 | 강/고 행)", not row_errors, "; ".join(row_errors), "S1", "★1")

    # ---- ★2 요청 규격 완비
    section_expected = rules["naming"]["section"].format(made=brief["made_date"], job=brief["job_name"])
    g.check("레이어명 섹션", snap["section"]["name"] == section_expected,
            f"{snap['section']['name']!r} (기대 {section_expected!r})", "S2")
    g.check("프레임 수", len(snap["frames"]) == len(expected),
            f"{len(snap['frames'])} (기대 {len(expected)} = 배너 {len(brief['banners'])} × "
            f"세트 {len(rules['sets'][brief['split']])})", "S2", "★2")
    for e in expected:
        f = frames.get(e["name"])
        if not g.check(f"프레임 존재 {e['name']}", f is not None, "", "S2", "★2"):
            continue
        g.check(f"프레임 크기 {e['name']}", [f["width"], f["height"]] == e["size"],
                f"{f['width']}×{f['height']} (기대 {e['size'][0]}×{e['size'][1]})", "S2", "★2")
    extra = set(frames) - {e["name"] for e in expected}
    g.check("레이어명 프레임", not extra, f"규칙 밖 프레임: {sorted(extra)}" if extra else "", "S2")

    for e in expected:
        f = frames.get(e["name"])
        if f is None:
            continue
        nodes = by_name(f)
        fname = e["name"]
        banner = e["banner"]

        # ---- ★1 기획안 일치: 텍스트 레이어 1개 ↔ 같은 이름의 시트 열 1개 (합치거나 나누지 않음)
        columns = rows.get(e["set"], {})          # 한 행이면 모든 세트 공통, 강/고 행이면 자기 세트
        prefix = t["sheet_column_prefix"]
        required = list(t["fields"][banner])
        others = [n["name"] for n in f["nodes"] if n.get("type") == "TEXT"
                  and n["name"].startswith(prefix) and n["name"] not in required]
        refs = {}
        for node_name in required + others:
            node = nodes.get(node_name)
            if not g.check(f"★1 노드 존재 {fname}/{node_name}", node is not None, "", "S2", "★1"):
                continue
            col = column_of(node_name, rules)
            if not g.check(f"★1 시트 열 존재 {fname}/{node_name}", col in columns,
                           f"시트에 {col!r} 열 없음", "S1", "★1"):
                continue
            want, applied = apply_substitutions(str(columns[col]), rules)
            refs[node_name] = want
            for a in applied:
                g.notes.append(f"허용 치환 {a['from']}→{a['to']} ({fname}/{node_name}): "
                               f"시트 원문 {a['original']!r} / 반영값 {want!r}")
            got = node.get("characters", "")
            g.check(f"★1 {fname}/{node_name}", normalize_copy(got) == normalize_copy(want),
                    f"배너 {got!r} / 시트[{col}] {want!r}", "S2", "★1")

        # ---- ★3 브랜드 일치 + 로고 레이어
        logos = [n for n in f["nodes"] if re.fullmatch(rules["logo"]["layer_name_regex"], n["name"])]
        g.check(f"★3 로고 존재 {fname}", len(logos) >= 1, f"{len(logos)}개", "S2", "★3")
        wanted = set(brief["brands"])
        for lg in logos:
            ok = (lg.get("type") == "INSTANCE"
                  and lg.get("component_set") == rules["logo"]["component_set"]
                  and (lg.get("variant") or {}).get(rules["logo"]["variant_prop"]) in wanted)
            g.check(f"★3 {fname}/{lg['name']}", ok,
                    f"type={lg.get('type')} set={lg.get('component_set')} "
                    f"variant={lg.get('variant')} (요청 {sorted(wanted)})", "S2", "★3")

        # ---- 폰트 / 스타일 / 줄바꿈
        template = (snap.get("template") or {}).get(banner, {})
        for n in f["nodes"]:
            if n.get("type") != "TEXT":
                continue
            chars = n.get("characters", "")
            path = f"{fname}/{n['name']}"
            style = n.get("style", {})
            exempt = n["name"] in t["font_exceptions"] or chars in t["font_exceptions"]
            if not exempt:
                g.check(f"폰트 {path}", style.get("font_family") == t["font_family"],
                        repr(style.get("font_family")), "S2")
            tstyle = template.get(n["name"])
            if tstyle is not None:
                diffs = {k: (style.get(k), tstyle.get(k)) for k in t["style_keys"]
                         if style.get(k) != tstyle.get(k)}
                g.check(f"폰트 속성 {path}", not diffs,
                        ", ".join(f"{k}={a} (템플릿 {b})" for k, (a, b) in diffs.items()), "S2")
            elif not exempt:
                g.check(f"폰트 속성 {path}", False, "템플릿에 같은 이름 노드 없음", "S2")
            for ch in t["forbidden_chars"]:
                g.check(f"금지문자 {ch!r} {path}", ch not in chars, repr(chars), "S2")
            mw = midword_breaks(chars, refs.get(n["name"]))
            g.check(f"어절 중간 줄바꿈 {path}", not mw,
                    f"{len(mw)}건: {chars!r}" if mw else "", "S2")
            want_lines = chars.count("\n") + 1
            g.check(f"자동 줄바꿈 {path}", n.get("rendered_lines") == want_lines,
                    f"렌더 {n.get('rendered_lines')}줄 / \\n+1 = {want_lines}줄", "S2")
            if n["name"] == t["main_text_node"]:
                g.check(f"메인 줄 수 {path}", want_lines <= t["main_text_max_lines"],
                        f"{want_lines}줄 (최대 {t['main_text_max_lines']})", "S2")

        # ---- 브랜드명·혜택 간격
        pair = rules["benefit_gap"]["pairs"].get(banner)
        if pair:
            b, h = nodes.get(pair[0]), nodes.get(pair[1])
            if g.check(f"간격 노드 {fname}", b is not None and h is not None, f"{pair}", "S2"):
                gap = h["x"] - (b["x"] + b["width"])
                lo, hi = rules["benefit_gap"]["min"], rules["benefit_gap"]["max"]
                g.check(f"브랜드명·혜택 간격 {fname}", lo <= gap <= hi, f"{gap} (허용 {lo}~{hi})", "S2")
    return g.finish()


if __name__ == "__main__":
    main_wrapper(run)
