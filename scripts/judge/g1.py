#!/usr/bin/env python3
"""G1 (S1 뒤) — 요청 완비. 사용법: g1.py <run>"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from common import Gate, load_brief, load_json, load_rules, main_wrapper, run_dir, sheet_rows  # noqa: E402

REQUIRED = {  # V 번호 → brief 키
    "V1": "brands", "V2": "main_copy", "V3": "sub_copy", "V4": "benefit",
    "V5": "discount_rate", "V6": "split", "V7": "banners", "V8": "plan_month",
    "V9a": "job_name", "V9b": "made_date", "V11": "gpt_image",
}


def empty(v) -> bool:
    return v is None or (isinstance(v, (str, list, dict)) and len(v) == 0)


def run(argv) -> int:
    if len(argv) != 1:
        raise ValueError("사용법: g1.py <run>")
    r = run_dir(argv[0])
    rules = load_rules()
    g = Gate("G1", r)

    brief_path = r / "01" / "brief.md"
    if not g.check("brief.md 존재", brief_path.exists(), str(brief_path), "S1"):
        return g.finish()
    brief = load_brief(r)

    for v, key in REQUIRED.items():
        g.check(f"{v} {key}", not empty(brief.get(key)), repr(brief.get(key)), "S1")

    g.check("V6 split 값", brief.get("split") in rules["sets"], repr(brief.get("split")), "S1")
    banners = brief.get("banners") or []
    g.check("V7 banners 값", bool(banners) and all(b in rules["banners"] for b in banners),
            repr(banners), "S1")
    g.check("V8 plan_month 형식", bool(re.fullmatch(r"\d{4}-\d{2}", str(brief.get("plan_month", "")))),
            repr(brief.get("plan_month")), "S1")
    g.check("V9 made_date 형식", bool(re.fullmatch(rules["naming"]["date_regex"],
                                                 str(brief.get("made_date", "")))),
            repr(brief.get("made_date")), "S1")
    g.check("V11 gpt_image 값", brief.get("gpt_image") in ("Y", "N"), repr(brief.get("gpt_image")), "S1")
    g.check("V5 discount_rate 정수", isinstance(brief.get("discount_rate"), int),
            repr(brief.get("discount_rate")), "S1")

    # V12: logo variant 가 없는 신규 브랜드면 로고 파일 필수
    found = set(brief.get("logo_variants_found") or [])
    for brand in brief.get("brands") or []:
        if brand in found:
            g.check(f"V12 로고 [{brand}]", True, "기존 logo variant", "S1")
        else:
            lf = brief.get("logo_file")
            ok = bool(lf) and (r / "01" / lf).exists()
            g.check(f"V12 로고 [{brand}]", ok, f"신규 브랜드 → logo_file={lf!r}", "S1")

    # 시트 스냅샷: 요청 배너의 텍스트 레이어마다 같은 이름의 열 (Google Sheets Sync, ★1 기준)
    sheet_path = r / "01" / "sheet.json"
    if g.check("시트 스냅샷 01/sheet.json 존재", sheet_path.exists(), "", "S1") \
            and brief.get("split") in rules["sets"]:
        rows, errors = sheet_rows(load_json(sheet_path), brief, rules)
        g.check("시트 행 구성 (한 행 | 강/고 행)", not errors, "; ".join(errors), "S1")
        prefix = rules["text"]["sheet_column_prefix"]
        for suffix, columns in rows.items():
            for banner in [b for b in banners if b in rules["text"]["fields"]]:
                for layer in rules["text"]["fields"][banner]:
                    col = layer[len(prefix):] if layer.startswith(prefix) else layer
                    g.check(f"시트 열 {col}{suffix}", not empty(columns.get(col)),
                            repr(columns.get(col)), "S1")
    return g.finish()


if __name__ == "__main__":
    main_wrapper(run)
