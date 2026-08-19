# -*- coding: utf-8 -*-
"""qr_maker — 二维码美化生成器（2026-08-19 新增）。

在 qrcode 库基础上增强外观：
- 模块样式：经典方块 / 圆角方块 / 圆点 / 菱形
- 前景渐变：无 / 垂直 / 对角（fg → fg 亮化色）
- Logo 嵌入：中心圆形遮罩 + 白边（需高容错 ERROR_CORRECT_H）
- 颜色/边距/尺寸自定义

全部为纯内存 Pillow 操作，毫秒级，可同步调用。
"""
import os

from PIL import Image, ImageDraw

try:
    import qrcode
    from qrcode.constants import ERROR_CORRECT_H
except Exception:  # noqa: BLE001 - 依赖缺失降级
    qrcode = None

# 模块样式
STYLE_SQUARE = "square"          # 经典方块
STYLE_ROUNDED = "rounded"        # 圆角方块
STYLE_DOT = "dot"                # 圆点
STYLE_DIAMOND = "diamond"        # 菱形
STYLES = (STYLE_SQUARE, STYLE_ROUNDED, STYLE_DOT, STYLE_DIAMOND)

# 渐变方向
GRAD_NONE = "none"
GRAD_VERTICAL = "vertical"
GRAD_DIAGONAL = "diagonal"


def _parse_color(text, default="#000000"):
    """支持 #RRGGBB / #RGB / 颜色名，失败回退默认。"""
    try:
        return Image.new("RGB", (1, 1), (text or default)).getpixel((0, 0))
    except Exception:  # noqa: BLE001
        try:
            return Image.new("RGB", (1, 1), default).getpixel((0, 0))
        except Exception:  # noqa: BLE001
            return (0, 0, 0)


def _lighten(rgb, factor=0.45):
    """向白色方向混合 factor，得到渐变末端色。"""
    return tuple(int(c + (255 - c) * factor) for c in rgb)


def _grad_color(c1, c2, t):
    """t∈[0,1] 线性插值两个颜色。"""
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def _draw_module(draw, x, y, m, color, style):
    """按样式绘制一个模块（坐标已含边距换算）。"""
    if style == STYLE_SQUARE:
        draw.rectangle([x, y, x + m - 1, y + m - 1], fill=color)
    elif style == STYLE_ROUNDED:
        r = max(1, m // 4)
        draw.rounded_rectangle([x, y, x + m - 1, y + m - 1], radius=r,
                               fill=color)
    elif style == STYLE_DOT:
        r = m // 2 - 1
        cx, cy = x + m / 2, y + m / 2
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    else:  # diamond
        cx, cy = x + m / 2, y + m / 2
        r = m / 2 - 1
        draw.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r),
                      (cx - r, cy)], fill=color)


def make_fancy_qr(content, size=400, fg="#000000", bg="#FFFFFF",
                  style=STYLE_SQUARE, gradient=GRAD_NONE,
                  logo_path=None, border=4, logo_ratio=0.24):
    """生成美化二维码 PIL Image。

    content: 文本/网址/WiFi/名片内容
    size: 输出像素尺寸
    fg/bg: 前景/背景色
    style: square / rounded / dot / diamond
    gradient: none / vertical / diagonal（fg → 亮化色）
    logo_path: 中心 Logo 图片路径（可选，圆形遮罩+白边）
    border: 空白边距（模块数）
    logo_ratio: Logo 占二维码宽度的比例
    """
    if qrcode is None:
        raise RuntimeError("缺少 qrcode 库，请先安装：pip install qrcode[pil]")
    if style not in STYLES:
        style = STYLE_SQUARE
    if gradient not in (GRAD_NONE, GRAD_VERTICAL, GRAD_DIAGONAL):
        gradient = GRAD_NONE

    qr = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_H,
                       box_size=10, border=int(border) if border else 4)
    qr.add_data(str(content))
    qr.make(fit=True)
    matrix = qr.modules                     # 含 border 的布尔矩阵
    count = qr.modules_count

    m = max(1, size // count)               # 模块像素尺寸
    canvas = Image.new("RGB", (m * count, m * count), _parse_color(bg, "#FFFFFF"))
    draw = ImageDraw.Draw(canvas)

    fg_c = _parse_color(fg, "#000000")
    grad_end = _lighten(fg_c)

    for i, row in enumerate(matrix):
        for j, cell in enumerate(row):
            if not cell:
                continue
            t = 0.0
            if gradient == GRAD_VERTICAL:
                t = i / max(count - 1, 1)
            elif gradient == GRAD_DIAGONAL:
                t = (i + j) / max(2 * (count - 1), 1)
            color = _grad_color(fg_c, grad_end, t) if gradient != GRAD_NONE \
                else fg_c
            _draw_module(draw, j * m, i * m, m, color, style)

    # 缩放至目标尺寸（重采样让圆点/圆角平滑）
    canvas = canvas.resize((size, size), Image.LANCZOS)

    # 中心 Logo（圆形遮罩 + 白边，白边提升辨识度与可扫描性）
    if logo_path and os.path.isfile(logo_path):
        try:
            with Image.open(logo_path) as _f:
                logo = _f.convert("RGBA")
            logo_w = int(size * logo_ratio)
            logo = logo.resize((logo_w, logo_w), Image.LANCZOS)
            pad = max(2, logo_w // 8)
            emblem = Image.new("RGBA", (logo_w + pad * 2, logo_w + pad * 2),
                               (255, 255, 255, 255))
            mask = Image.new("L", (logo_w + pad * 2, logo_w + pad * 2), 0)
            ImageDraw.Draw(mask).ellipse(
                [0, 0, logo_w + pad * 2 - 1, logo_w + pad * 2 - 1], fill=255)
            emblem.paste(logo, (pad, pad))
            emblem.putalpha(mask)
            ox = (size - emblem.size[0]) // 2
            oy = (size - emblem.size[1]) // 2
            canvas.paste(emblem, (ox, oy), emblem)
        except Exception:  # noqa: BLE001 - Logo 失败不影响二维码主体
            pass
    return canvas
