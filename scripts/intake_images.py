#!/usr/bin/env python3
"""이미지 반입 (image-agent). 사용법: intake_images.py <run>

input/images/ 의 파일을 runs/{id}/03/images/ 로 이동하고 input/images/ 를 비운다.
이동 전후 sha256 을 03/images.json 에 기록한다 (G3 원본 바이트 판정).
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from common import ROOT, load_json, main_wrapper, now_iso, run_dir, sha256, write_json  # noqa: E402

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def run(argv) -> int:
    if len(argv) != 1:
        raise ValueError("사용법: intake_images.py <run>")
    r = run_dir(argv[0])
    src = ROOT / "input" / "images"
    files = sorted(p for p in src.iterdir() if p.suffix.lower() in IMAGE_EXT)
    if not files:
        print("input/images/ 에 이미지가 없습니다 (재개 조건: 이미지 파일 수 ≥ 1)")
        return 1
    dst = r / "03" / "images"
    dst.mkdir(parents=True, exist_ok=True)
    manifest_path = r / "03" / "images.json"
    manifest = load_json(manifest_path) if manifest_path.exists() else []
    bad = 0
    for p in files:
        before, size = sha256(p), p.stat().st_size
        target = dst / p.name
        shutil.move(str(p), target)
        after = sha256(target)
        manifest = [m for m in manifest if m["file"] != p.name]
        manifest.append({"file": p.name, "bytes": size, "sha256_before": before,
                         "sha256_after": after, "at": now_iso()})
        ok = before == after
        bad += not ok
        print(f"{'OK  ' if ok else 'FAIL'} {p.name} {size}B sha256={after[:12]}")
    write_json(manifest_path, manifest)
    return 1 if bad else 0


if __name__ == "__main__":
    main_wrapper(run)
