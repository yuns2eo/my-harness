"""게이트 판정 테스트 (docs/r8-verify.md §1). 합성 run 만 사용한다."""
import json

import numpy as np
import pytest
from PIL import Image

import factory as fx
from factory import load_snapshot, node, save_snapshot


def failed_ids(run, gate_name):
    data = json.loads((run / "04" / f"{gate_name}.json").read_text(encoding="utf-8"))
    return [c for c in data["checks"] if not c["ok"]]


def assert_fail(run, gate_name, needle, star=None):
    fails = failed_ids(run, gate_name)
    hit = [c for c in fails if needle in c["id"]]
    assert hit, f"{needle!r} FAIL 이 없음. 실제 FAIL: {[c['id'] for c in fails]}"
    if star:
        assert any(c["star"] == star for c in hit), f"{star} 표시 없음: {hit}"


# ======================================================================= 골든 PASS
def test_golden_all_pass(run, g):
    for name in ("g1", "g2", "g3", "g4"):
        code, out = g(name, run)
        assert code == 0, out
    assert (run / "04" / "approval-screen.md").exists()
    screen = (run / "04" / "approval-screen.md").read_text(encoding="utf-8")
    assert screen.count("https://www.figma.com/design/EXAMPLEFILEKEY/?node-id=") == 3
    assert "node-id=1-1" in screen                       # 콜론 → 하이픈
    code, out = g("approve", run)
    assert code == 0, out
    code, out = g("g5", run, "--phase", "pre")
    assert code == 0, out
    (run / "05" / "delivery.json").write_text(json.dumps({
        "drive": {"link": "https://example.invalid/d"},
        "notion": {"디자인 경로": "https://example.invalid/d", "진행 상황": "완료"},
        "slack": {"ts": "1.2", "raw_text_after_send": "<@UTEST|요청자> 전달드립니다! https://example.invalid/d"},
        "reactions": [":example-start:", ":example-done:"],
    }, ensure_ascii=False), encoding="utf-8")
    code, out = g("g5", run, "--phase", "post")
    assert code == 0, out
    assert (run / "04" / "qa-report.md").exists()


# ======================================================================= 필수 FAIL 5개
def test_F1_discount_one_char(run, g):
    snap = load_snapshot(run)
    node(snap, "main", "#benefit")["characters"] = "최대 25%"
    save_snapshot(run, snap)
    code, out = g("g2", run)
    assert code == 1
    assert_fail(run, "g2", "#benefit", star="★1")


def test_F2_split_but_one_set(run, g):
    brief = dict(fx.BRIEF, split="dog+cat")
    fx.write_brief(run, brief)
    code, out = g("g2", run)
    assert code == 1
    assert_fail(run, "g2", "프레임 수", star="★2")
    assert_fail(run, "g2", "프레임 존재", star="★2")


def test_F3_other_brand_logo(run, g):
    snap = load_snapshot(run)
    node(snap, "strip", "logo")["variant"] = {"brand": "다른브랜드"}
    save_snapshot(run, snap)
    code, _ = g("g2", run)
    assert code == 1
    assert_fail(run, "g2", "★3", star="★3")


def test_F4_midword_linebreak(run, g):
    snap = load_snapshot(run)
    n = node(snap, "main", "#M_main_text")
    n["characters"] = "테스트펫 가을 사료 할\n인전"
    n["rendered_lines"] = 2
    save_snapshot(run, snap)
    code, _ = g("g2", run)
    assert code == 1
    assert_fail(run, "g2", "어절 중간 줄바꿈")


def test_F5_mask_group(run, g):
    snap = load_snapshot(run)
    f = next(f for f in snap["frames"] if f["banner"] == "main")
    f["nodes"].append({"id": "m:1", "name": "Mask group", "type": "GROUP", "x": 141, "y": -34,
                       "width": 234, "height": 234, "is_mask": True, "fills": []})
    save_snapshot(run, snap)
    code, _ = g("g3", run)
    assert code == 1
    assert_fail(run, "g3", "마스크 그룹 0")


# ======================================================================= 필수 PASS: 흰 동물 + 밝은 배경
def test_white_subject_on_bright_bg_detected(run, g):
    snap = load_snapshot(run)
    f = next(f for f in snap["frames"] if f["banner"] == "main")
    bg_lum = float(np.asarray(Image.new("RGB", (1, 1), fx.BG_RGB).convert("L"))[0, 0])
    fx.render_png(f, run / "04" / "preview" / f"{f['name']}.png", subject_lum=bg_lum + 8)
    code, out = g("g3", run)
    assert code == 0, out


def test_white_subject_measure_unit():
    import subject as sj
    f = fx.build_frame("main", "x", 1)
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "a.png"
        fx.render_png(f, p, subject_lum=243)
        s = sj.measure_subject(Image.open(p), [], 3, 12)
    assert s is not None and 171 <= s["height"] <= 173
    # 같은 이미지를 RGB 거리 20 기준으로 보면 피사체 평균이 배경과 거의 같다 (색 거리 방식이 실패하는 이유)
    assert abs(243 - np.mean(fx.BG_RGB)) < 20


# ======================================================================= G1
def test_g1_missing_field(run, g):
    fx.write_brief(run, dict(fx.BRIEF, main_copy=""))
    code, _ = g("g1", run)
    assert code == 1
    assert_fail(run, "g1", "V2")


def test_g1_new_brand_needs_logo(run, g):
    fx.write_brief(run, dict(fx.BRIEF, logo_variants_found=[]))
    code, _ = g("g1", run)
    assert code == 1
    assert_fail(run, "g1", "V12")
    (run / "01" / "logo.svg").write_text("<svg/>")
    fx.write_brief(run, dict(fx.BRIEF, logo_variants_found=[], logo_file="logo.svg"))
    code, out = g("g1", run)
    assert code == 0, out


def test_g1_missing_sheet(run, g):
    (run / "01" / "sheet.json").unlink()
    code, _ = g("g1", run)
    assert code == 1


# ======================================================================= G2 개별 규칙
def mutate(run, banner, name, **kw):
    snap = load_snapshot(run)
    n = node(snap, banner, name)
    for k, v in kw.items():
        if k == "style":
            n["style"].update(v)
        else:
            n[k] = v
    save_snapshot(run, snap)


@pytest.mark.parametrize("banner,name,kw,needle", [
    ("main", "#sub_text", {"style": {"font_family": "Inter"}}, "폰트 261001"),
    ("strip", "#L_main_text_bold", {"style": {"font_size": 22}}, "폰트 속성"),
    ("renewal", "#R_sub_text", {"style": {"letter_spacing": -0.5}}, "폰트 속성"),
    ("main", "#M_main_text", {"characters": "테스트펫 가을 사료 할인전", "rendered_lines": 2}, "자동 줄바꿈"),
    ("main", "#M_main_text", {"characters": "테스트펫\n가을\n사료\n할인전", "rendered_lines": 4}, "메인 줄 수"),
    ("main", "#benefit", {"x": 88}, "간격"),
    ("main", "#benefit", {"x": 83}, "간격"),
    ("main", "logo", {"type": "RECTANGLE"}, "★3"),
])
def test_g2_rule_fail(run, g, banner, name, kw, needle):
    mutate(run, banner, name, **kw)
    code, _ = g("g2", run)
    assert code == 1
    assert_fail(run, "g2", needle)


def test_g2_middle_dot_forbidden(run, g):
    mutate(run, "main", "#sub_text", characters="최대 20%·할인")
    code, _ = g("g2", run)
    assert code == 1
    assert_fail(run, "g2", "금지문자")


def test_g2_allowed_substitution_passes_with_note(tmp_path, g):
    cols = dict(fx.SHEET["columns"], brand_name="테스트펫·친구", R_brand_name="테스트펫·친구")
    run = fx.build_run(tmp_path, sheet=dict(fx.SHEET, columns=cols))
    snap = load_snapshot(run)
    for f in snap["frames"]:
        for n in f["nodes"]:
            if n["name"].endswith("brand_name"):
                n["characters"] = "테스트펫&친구"
    save_snapshot(run, snap)
    code, out = g("g2", run)
    assert code == 0, out
    notes = json.loads((run / "04" / "g2.json").read_text(encoding="utf-8"))["notes"]
    assert any("·→&" in n for n in notes)


def test_g2_frame_size_and_section_name(run, g):
    snap = load_snapshot(run)
    snap["frames"][0]["width"] = 376
    snap["section"]["name"] = "wrong"
    save_snapshot(run, snap)
    code, _ = g("g2", run)
    assert code == 1
    assert_fail(run, "g2", "프레임 크기", star="★2")
    assert_fail(run, "g2", "레이어명 섹션")


def test_g2_legit_linebreak_passes(run, g):
    # 공백 자리 줄바꿈("가을\n사료")은 PASS (골든 run 의 메인 문구)
    code, out = g("g2", run)
    assert code == 0, out


# ======================================================================= G3 개별 규칙
def rerender(run, banner, **kw):
    snap = load_snapshot(run)
    f = next(f for f in snap["frames"] if f["banner"] == banner)
    fx.render_png(f, run / "04" / "preview" / f"{f['name']}.png", **kw)


def test_g3_sha_mismatch(run, g):
    (run / "03" / "images" / "gpt_main.png").write_bytes(b"recaptured")
    code, _ = g("g3", run)
    assert code == 1
    assert_fail(run, "g3", "원본 바이트")


def test_g3_main_slot_coords(run, g):
    mutate(run, "main", "#image", x=140)
    code, _ = g("g3", run)
    assert code == 1
    assert_fail(run, "g3", "메인 슬롯 좌표")


def test_g3_subject_too_small(run, g):
    rerender(run, "main", subject=(200, 30, 150, 150))
    code, _ = g("g3", run)
    assert code == 1
    assert_fail(run, "g3", "피사체 높이")


def test_g3_strip_subject_outside(run, g):
    rerender(run, "strip", subject=(300, 17, 180, 188))
    code, _ = g("g3", run)
    assert code == 1
    assert_fail(run, "g3", "띠 피사체 위치")


def test_g3_renewal_off_center(run, g):
    rerender(run, "renewal", subject=(60, 135, 150, 170))
    code, _ = g("g3", run)
    assert code == 1
    assert_fail(run, "g3", "리뉴얼 가로 중앙")


def test_g3_subject_cut_at_edge(run, g):
    rerender(run, "main", subject=(220, 14, 155, 172))     # 오른쪽 끝에 붙음 = 잘림
    code, _ = g("g3", run)
    assert code == 1
    assert_fail(run, "g3", "좌우 여백")


def test_g3_seam(run, g):
    rerender(run, "main", slot_bg=(215, 205, 190))
    code, _ = g("g3", run)
    assert code == 1
    assert_fail(run, "g3", "경계선")


def test_g3_white_background(run, g):
    snap = load_snapshot(run)
    snap["frames"][0]["background"] = "#ffffff"
    save_snapshot(run, snap)
    code, _ = g("g3", run)
    assert code == 1
    assert_fail(run, "g3", "배경색")


# ======================================================================= G4 / 승인 / G5
def test_g4_blocks_when_star_fails(run, g):
    g("g1", run)
    mutate(run, "main", "#benefit", characters="최대 25%")
    g("g2", run)
    g("g3", run)
    code, _ = g("g4", run)
    assert code == 1
    assert not (run / "04" / "approval-screen.md").exists()
    code, _ = g("approve", run)
    assert code == 1


def pass_until_approval(run, g):
    for name in ("g1", "g2", "g3", "g4", "approve"):
        code, out = g(name, run)
        assert code == 0, out


def test_g5_pre_hash_changed_after_approval(run, g):
    pass_until_approval(run, g)
    rerender(run, "main", seed=99)
    code, _ = g("g5", run, "--phase", "pre")
    assert code == 1
    assert_fail(run, "g5", "승인 해시")


def test_g5_pre_wrong_scale_and_name(run, g):
    pass_until_approval(run, g)
    p = next((run / "04" / "preview").glob("*메인배너.png"))
    Image.open(p).resize((750, 400)).save(p.with_name(p.stem + "@3x.png"))
    p.unlink()
    code, _ = g("g5", run, "--phase", "pre")
    assert code == 1
    assert_fail(run, "g5", "파일명 규칙")
    assert_fail(run, "g5", "@3x")


def test_g5_post_text_mention_fails(run, g):
    (run / "05" / "delivery.json").write_text(json.dumps({
        "drive": {"link": "x"}, "notion": {"디자인 경로": "x", "진행 상황": "완료"},
        "slack": {"ts": "1", "raw_text_after_send": "@요청자 전달드립니다! x"},
        "reactions": [":example-start:", ":example-done:"]}, ensure_ascii=False), encoding="utf-8")
    code, _ = g("g5", run, "--phase", "post")
    assert code == 1
    assert_fail(run, "g5", "멘션")


def test_g5_post_missing_emoji(run, g):
    (run / "05" / "delivery.json").write_text(json.dumps({
        "drive": {"link": "x"}, "notion": {"디자인 경로": "x", "진행 상황": "완료"},
        "slack": {"ts": "1", "raw_text_after_send": "<@UTEST> 전달드립니다! x"},
        "reactions": [":example-start:"]}, ensure_ascii=False), encoding="utf-8")
    code, _ = g("g5", run, "--phase", "post")
    assert code == 1
    assert_fail(run, "g5", "이모지")


# ======================================================================= ★1 시트 열 1:1 (Google Sheets Sync)
def test_star1_sheet_column_missing(run, g):
    sheet = json.loads((run / "01" / "sheet.json").read_text(encoding="utf-8"))
    del sheet["columns"]["R_main_text 2"]
    (run / "01" / "sheet.json").write_text(json.dumps(sheet, ensure_ascii=False), encoding="utf-8")
    code, _ = g("g1", run)
    assert code == 1
    assert_fail(run, "g1", "시트 열 R_main_text 2")
    code, _ = g("g2", run)
    assert code == 1
    assert_fail(run, "g2", "시트 열 존재", star="★1")


def test_star1_no_merge_across_layers(run, g):
    # basic+bold 를 이어 붙이면 같아도, 레이어마다 자기 열과 다르면 FAIL (합치거나 나누지 않음)
    mutate(run, "strip", "#L_main_text_basic", characters="테스트펫 가을")
    mutate(run, "strip", "#L_main_text_bold", characters="사료 최대 20% 할인")
    code, _ = g("g2", run)
    assert code == 1
    assert_fail(run, "g2", "#L_main_text_basic", star="★1")
    assert_fail(run, "g2", "#L_main_text_bold", star="★1")


def test_star1_extra_hash_layer_needs_column(run, g):
    snap = load_snapshot(run)
    f = next(f for f in snap["frames"] if f["banner"] == "strip")
    f["nodes"].append(fx.text_node("#L_extra", 600, 120, 200, 26, "추가 문구"))
    snap["template"]["strip"]["#L_extra"] = dict(fx.STYLE)
    save_snapshot(run, snap)
    code, _ = g("g2", run)
    assert code == 1
    assert_fail(run, "g2", "시트 열 존재 261001_테스트펫브랜드전_띠배너/#L_extra")


def test_renewal_benefit_gap(run, g):
    mutate(run, "renewal", "#R_benefit", x=135)
    code, _ = g("g2", run)
    assert code == 1
    assert_fail(run, "g2", "브랜드명·혜택 간격 261001_테스트펫브랜드전_리뉴얼배너")


# ======================================================================= 강/고 시트 행
DOGCAT = dict(fx.BRIEF, split="dog+cat")


def set_rows(go_overrides=None, drop=None):
    rows = {"강": dict(fx.SHEET["columns"]), "고": dict(fx.SHEET["columns"], **(go_overrides or {}))}
    if drop:
        del rows[drop]
    return {"sets": rows, "source_url": "https://example.invalid/s", "fetched_at": "x"}


def set_frame_text(run, set_suffix, layer, chars):
    snap = load_snapshot(run)
    for f in snap["frames"]:
        if f["name"].endswith(set_suffix):
            for n in f["nodes"]:
                if n["name"] == layer:
                    n["characters"] = chars
    save_snapshot(run, snap)


def test_dogcat_single_row_applies_to_both_sets(tmp_path, g):
    run = fx.build_run(tmp_path, brief=DOGCAT)            # sheet.json = 한 행(columns)
    for name in ("g1", "g2"):
        code, out = g(name, run)
        assert code == 0, out
    data = json.loads((run / "04" / "g2.json").read_text(encoding="utf-8"))
    assert sum(1 for c in data["checks"] if c["id"].startswith("★1 2610") and c["id"].count("_고/")) > 0


def test_dogcat_separate_rows_each_set_own_row(tmp_path, g):
    run = fx.build_run(tmp_path, brief=DOGCAT, sheet=set_rows({"sub_text": "고양이 최대 20% 할인"}))
    set_frame_text(run, "메인배너_고", "#sub_text", "고양이 최대 20% 할인")
    for name in ("g1", "g2"):
        code, out = g(name, run)
        assert code == 0, out


def test_dogcat_separate_rows_wrong_row_fails(tmp_path, g):
    # 고 세트에 강 행 문구를 넣으면 FAIL
    run = fx.build_run(tmp_path, brief=DOGCAT, sheet=set_rows({"sub_text": "고양이 최대 20% 할인"}))
    code, _ = g("g2", run)
    assert code == 1
    assert_fail(run, "g2", "메인배너_고/#sub_text", star="★1")
    ids = [c["id"] for c in failed_ids(run, "g2")]
    assert not any("_강/" in i for i in ids), ids


def test_dogcat_missing_set_row(tmp_path, g):
    run = fx.build_run(tmp_path, brief=DOGCAT, sheet=set_rows(drop="고"))
    code, _ = g("g1", run)
    assert code == 1
    assert_fail(run, "g1", "시트 행 구성")
    code, _ = g("g2", run)
    assert code == 1
    assert_fail(run, "g2", "시트 행 구성", star="★1")


def test_sheet_both_columns_and_sets_fails(tmp_path, g):
    sheet = dict(set_rows(), columns=fx.SHEET["columns"])
    run = fx.build_run(tmp_path, brief=DOGCAT, sheet=sheet)
    code, _ = g("g1", run)
    assert code == 1
    assert_fail(run, "g1", "시트 행 구성")


def test_single_set_request_with_set_rows_fails(tmp_path, g):
    run = fx.build_run(tmp_path, sheet=set_rows())        # split=none 인데 강/고 행
    code, _ = g("g1", run)
    assert code == 1
    assert_fail(run, "g1", "시트 행 구성")
