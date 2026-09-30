"""피사체 측정 — 표준편차 방식 (r5-gates §3).

열마다 밝기 표준편차 ≥ threshold 인 구간 = 가로 범위.
행 표준편차는 그 가로 범위 안에서만 계산한다 (넓은 띠배너에서 배경 비율이
커져 행 표준편차가 희석되는 것을 막기 위해).
텍스트·로고·버튼 bbox 는 측정에서 제외한다.
"""
from __future__ import annotations

import numpy as np
from PIL import Image


def luminance(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("L"), dtype=np.float64)


def exclusion_mask(shape, boxes_pt, scale: int) -> np.ndarray:
    """True = 측정에 사용. boxes_pt: [(x, y, w, h)] Figma pt 좌표."""
    mask = np.ones(shape, dtype=bool)
    h, w = shape
    for x, y, bw, bh in boxes_pt:
        x0, y0 = max(0, int(x * scale)), max(0, int(y * scale))
        x1, y1 = min(w, int((x + bw) * scale + 0.999)), min(h, int((y + bh) * scale + 0.999))
        if x1 > x0 and y1 > y0:
            mask[y0:y1, x0:x1] = False
    return mask


def _masked_std(arr: np.ndarray, mask: np.ndarray, axis: int) -> np.ndarray:
    cnt = mask.sum(axis=axis)
    vals = np.where(mask, arr, 0.0)
    mean = vals.sum(axis=axis) / np.maximum(cnt, 1)
    sq = np.where(mask, arr ** 2, 0.0).sum(axis=axis) / np.maximum(cnt, 1)
    std = np.sqrt(np.maximum(sq - mean ** 2, 0.0))
    std[cnt < 2] = 0.0
    return std


def _span(flags: np.ndarray):
    idx = np.flatnonzero(flags)
    if idx.size == 0:
        return None
    return int(idx[0]), int(idx[-1])


def measure_subject(img: Image.Image, exclude_boxes_pt, scale: int, threshold: float):
    """→ dict(left, right, top, bottom, width, height) in pt, 또는 None."""
    lum = luminance(img)
    mask = exclusion_mask(lum.shape, exclude_boxes_pt, scale)
    col_std = _masked_std(lum, mask, axis=0)
    xs = _span(col_std >= threshold)
    if xs is None:
        return None
    x0, x1 = xs
    sub, sub_mask = lum[:, x0:x1 + 1], mask[:, x0:x1 + 1]
    row_std = _masked_std(sub, sub_mask, axis=1)
    ys = _span(row_std >= threshold)
    if ys is None:
        return None
    y0, y1 = ys
    return {
        "left": x0 / scale, "right": (x1 + 1) / scale,
        "top": y0 / scale, "bottom": (y1 + 1) / scale,
        "width": (x1 - x0 + 1) / scale, "height": (y1 - y0 + 1) / scale,
    }


def column_mean_diff(img: Image.Image, x_pt: float, scale: int, exclude_boxes_pt) -> float | None:
    """세로 경계선: x_pt 경계 양옆 인접 열의 평균색 차이 (RGB 채널 최대값)."""
    rgb = np.asarray(img.convert("RGB"), dtype=np.float64)
    h, w, _ = rgb.shape
    xp = int(round(x_pt * scale))
    if xp <= 0 or xp >= w:
        return None
    mask = exclusion_mask((h, w), exclude_boxes_pt, scale)
    rows = mask[:, xp - 1] & mask[:, xp]
    if rows.sum() == 0:
        return None
    left = rgb[rows, xp - 1].mean(axis=0)
    right = rgb[rows, xp].mean(axis=0)
    return float(np.abs(left - right).max())
