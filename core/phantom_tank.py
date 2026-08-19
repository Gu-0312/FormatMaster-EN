"""phantom_tank — 幻影坦克图片（制作 / 解密）。

原理：把两张图编码进一张带透明通道的灰度图——
- 白底（浅色主题）下显示「白底图」
- 黑底（深色主题）下显示「黑底图」

推导（0~1 归一化，a=白底图灰度, b=黑底图灰度, 要求 a≥b）：
- 输出灰度 c 与透明度 α 满足：
    白底: c·α + 1·(1-α) = a
    黑底: c·α + 0·(1-α) = b
- 解得 α = 1-(a-b)，c = b/α

解密：把 RGBA 分别合成到白底 / 黑底，得到两张可查看的图。
"""

import os

import numpy as np
from PIL import Image, ImageOps


def _load_gray(path):
    """读取图片为归一化 0~1 的灰度 float32 数组。"""
    with Image.open(path) as _f:
        img = _f.copy()
    img = ImageOps.exif_transpose(img)
    return img.convert("L"), np.asarray(img.convert("L"),
                                        dtype=np.float32) / 255.0


def make_phantom(white_path, black_path, out_path):
    """制作幻影坦克：白底显示 white，黑底显示 black → 输出 RGBA PNG。

    尺寸以白底图为准，黑底图等比缩放居中补齐（不拉伸变形）。
    white 灰度低于 black 的像素按 black 处理（该像素无法区分）。
    """
    w_img, a = _load_gray(white_path)
    _, b = _load_gray(black_path)

    # 黑底图适配白底图尺寸（等比缩放 + 居中画布）
    target = w_img.size
    scale = min(target[0] / b.shape[1], target[1] / b.shape[0])
    nw, nh = max(1, int(b.shape[1] * scale)), max(1, int(b.shape[0] * scale))
    with Image.open(black_path) as _f:
        b_img = _f.convert("L").resize(
            (nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("L", target, 0)
    canvas.paste(b_img, ((target[0] - nw) // 2, (target[1] - nh) // 2))
    b = np.asarray(canvas, dtype=np.float32) / 255.0

    a = np.maximum(a, 0.0)
    # 约束 b ≤ a（否则该像素无法区分）：黑底图压暗，保证白底图完全正确
    b = np.minimum(b, a)
    alpha = 1.0 - (a - b)
    c = np.divide(b, alpha, out=np.zeros_like(b), where=alpha > 1e-3)
    c = np.clip(c, 0.0, 1.0)
    alpha = np.clip(alpha, 0.0, 1.0)

    rgba = np.dstack([c, c, c, alpha])
    Image.fromarray((rgba * 255).astype(np.uint8), "RGBA").save(out_path)
    return out_path


def decode_phantom(phantom_path, white_out, black_out):
    """解密幻影坦克：分别合成到白底与黑底，输出两张可查看图。"""
    with Image.open(phantom_path) as _f:
        img = _f.convert("RGBA")
    arr = np.asarray(img, dtype=np.float32) / 255.0
    rgb, alpha = arr[..., :3], arr[..., 3:4]
    white = np.clip(rgb * alpha + (1.0 - alpha), 0.0, 1.0)
    black = np.clip(rgb * alpha, 0.0, 1.0)
    Image.fromarray((white * 255).astype(np.uint8), "RGB").save(white_out)
    Image.fromarray((black * 255).astype(np.uint8), "RGB").save(black_out)
    return white_out, black_out
