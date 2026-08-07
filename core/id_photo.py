"""id_photo — 证件照工具（换底色）。

用色度键算法把照片背景替换为红/蓝/白标准证件照底色：
四角采样原背景色 → 按颜色距离逐像素替换，边缘做羽化渐变避免生硬。
纯 numpy + PIL 实现，无外部依赖。
"""
import os

import numpy as np
from PIL import Image

# 标准证件照底色（RGB）
BG_COLORS = {
    "红底": (219, 64, 64),
    "蓝底": (67, 142, 219),
    "白底": (255, 255, 255),
}
# 默认蓝色（最常用）
DEFAULT_COLOR = "蓝底"

# 完全替换距离阈值 / 渐变过渡区间
_T_FULL = 70.0
_T_SOFT = 130.0


def change_background(input_path, output_path, color=DEFAULT_COLOR,
                      progress_callback=None):
    """把照片背景替换为指定底色。

    color: BG_COLORS 的 key（红底/蓝底/白底）。
    progress_callback(pct, msg)：进度回调；返回 False 表示失败。
    """
    try:
        target = BG_COLORS.get(color, BG_COLORS[DEFAULT_COLOR])
    except (TypeError, ValueError):
        return False
    try:
        img = Image.open(input_path).convert("RGB")
    except (OSError, IOError):
        if progress_callback:
            progress_callback(-1, "错误：无法打开图片，文件可能已损坏")
        return False

    if progress_callback:
        progress_callback(10, "分析背景…")

    arr = np.asarray(img, dtype=np.float32)
    h, w = arr.shape[:2]

    # 四角采样原背景色（各角 8x8 区域均值）
    corners = [arr[:8, :8].reshape(-1, 3), arr[:8, -8:].reshape(-1, 3),
               arr[-8:, :8].reshape(-1, 3), arr[-8:, -8:].reshape(-1, 3)]
    bg = np.mean(np.concatenate(corners), axis=0)

    if progress_callback:
        progress_callback(30, "识别背景区域…")

    # 逐像素颜色距离（欧氏）
    dist = np.sqrt(((arr - bg) ** 2).sum(axis=2))
    mask_full = dist <= _T_FULL
    mask_soft = (dist > _T_FULL) & (dist <= _T_SOFT)

    # 替换为纯目标色
    arr[mask_full] = target
    # 羽化过渡：按距离线性混合原色与目标色
    if mask_soft.any():
        t = (dist[mask_soft] - _T_FULL) / (_T_SOFT - _T_FULL)  # 0→1 原色占比
        t = t[..., None]
        orig = arr[mask_soft]
        arr[mask_soft] = orig * t + np.asarray(target, dtype=np.float32) * (1 - t)

    if progress_callback:
        progress_callback(70, "生成新底色…")

    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    try:
        out.save(output_path, quality=95)
    except (OSError, IOError) as e:
        if progress_callback:
            progress_callback(-1, f"保存失败：{e}")
        return False
    out.close()
    img.close()

    if progress_callback:
        progress_callback(100, "处理完成")
    return True
