"""图片批量水印 — 文字水印 + 图片水印

支持：字体/字号/颜色/透明度/旋转角度/位置，以及 PNG 透明图叠加。
纯 Pillow 实现，无额外依赖。
"""
import os
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from typing import Optional, Tuple, List

# 水印位置映射（x_ratio, y_ratio）
POSITIONS = {
    "左上角": (0.02, 0.02),
    "右上角": (0.65, 0.02),
    "左下角": (0.02, 0.85),
    "右下角": (0.65, 0.85),
    "居中":   (0.35, 0.45),
}

# Windows 常见中文字体路径
_FONT_PATHS = [
    "C:/Windows/Fonts/msyh.ttc",      # 微软雅黑
    "C:/Windows/Fonts/simhei.ttf",     # 黑体
    "C:/Windows/Fonts/simsun.ttc",     # 宋体
    "C:/Windows/Fonts/arial.ttf",      # Arial
]


def _get_font(size: int, font_path: str = "") -> ImageFont.FreeTypeFont:
    """获取字体对象，优先用指定路径，否则尝试系统字体，最后回退默认。"""
    if font_path and os.path.exists(font_path):
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            pass
    for p in _FONT_PATHS:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _hex_to_rgba(hex_color: str, alpha: int = 255) -> Tuple[int, int, int, int]:
    """#RRGGBB → (R, G, B, A)"""
    h = hex_color.lstrip("#")
    if len(h) == 6:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (r, g, b, alpha)
    return (255, 255, 255, alpha)


def _calc_position(img_w: int, img_h: int, wm_w: int, wm_h: int, pos: str) -> Tuple[int, int]:
    """根据位置名称计算水印左上角坐标。"""
    rx, ry = POSITIONS.get(pos, (0.65, 0.85))
    x = int(img_w * rx - wm_w * rx)
    y = int(img_h * ry - wm_h * ry)
    return max(0, x), max(0, y)


def add_text_watermark(
    img: Image.Image,
    text: str,
    font_size: int = 48,
    color: str = "#FFFFFF",
    opacity: float = 0.8,
    rotation: int = 0,
    position: str = "右下角",
    font_path: str = "",
) -> Image.Image:
    """在图片上添加文字水印，返回新 Image 对象。"""
    if not text:
        return img

    if img.mode != "RGBA":
        img = img.convert("RGBA")

    # 创建水印透明层
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font = _get_font(font_size, font_path)
    alpha = int(255 * max(0, min(1, opacity)))
    fill = _hex_to_rgba(color, alpha)

    # 测量文字大小
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    # 先在临时层上画文字，再旋转
    if rotation != 0:
        tmp = Image.new("RGBA", (tw + 20, th + 20), (0, 0, 0, 0))
        tmp_draw = ImageDraw.Draw(tmp)
        tmp_draw.text((10 - bbox[0], 10 - bbox[1]), text, fill=fill, font=font)
        tmp = tmp.rotate(rotation, expand=True, resample=Image.BICUBIC)
        x, y = _calc_position(img.size[0], img.size[1], tmp.size[0], tmp.size[1], position)
        overlay.paste(tmp, (x, y), tmp)
    else:
        x, y = _calc_position(img.size[0], img.size[1], tw, th, position)
        draw.text((x - bbox[0], y - bbox[1]), text, fill=fill, font=font)

    return Image.alpha_composite(img, overlay)


def add_image_watermark(
    img: Image.Image,
    watermark_path: str,
    scale: float = 0.2,
    opacity: float = 0.8,
    rotation: int = 0,
    position: str = "右下角",
) -> Image.Image:
    """在图片上叠加 PNG 透明图片水印。"""
    if not watermark_path or not os.path.exists(watermark_path):
        return img

    if img.mode != "RGBA":
        img = img.convert("RGBA")

    try:
        wm = Image.open(watermark_path).convert("RGBA")
    except Exception:
        return img

    # 按比例缩放水印
    base_w = img.size[0]
    new_w = max(1, int(base_w * scale))
    ratio = new_w / wm.size[0]
    new_h = max(1, int(wm.size[1] * ratio))
    wm = wm.resize((new_w, new_h), Image.LANCZOS)

    # 调整透明度
    if opacity < 1.0:
        alpha = wm.split()[3]
        alpha = ImageEnhance.Brightness(alpha).enhance(max(0, min(1, opacity)))
        wm.putalpha(alpha)

    # 旋转
    if rotation != 0:
        wm = wm.rotate(rotation, expand=True, resample=Image.BICUBIC)

    # 创建透明层并粘贴水印
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    x, y = _calc_position(img.size[0], img.size[1], wm.size[0], wm.size[1], position)
    overlay.paste(wm, (x, y), wm)

    return Image.alpha_composite(img, overlay)


def process_watermark(
    input_path: str,
    output_path: str,
    wm_type: str = "text",
    text: str = "",
    font_size: int = 48,
    color: str = "#FFFFFF",
    opacity: float = 0.8,
    rotation: int = 0,
    position: str = "右下角",
    font_path: str = "",
    wm_image_path: str = "",
    scale: float = 0.2,
    progress_cb=None,
) -> bool:
    """处理单个文件的水印添加。"""
    if progress_cb:
        progress_cb(20, "打开图片...")
    try:
        img = Image.open(input_path)
    except Exception as e:
        if progress_cb:
            progress_cb(-1, f"错误：无法打开图片 - {e}")
        return False

    if progress_cb:
        progress_cb(40, "添加水印...")

    if wm_type == "text":
        img = add_text_watermark(img, text, font_size, color, opacity, rotation, position, font_path)
    elif wm_type == "image":
        img = add_image_watermark(img, wm_image_path, scale, opacity, rotation, position)

    if progress_cb:
        progress_cb(80, "保存...")

    # 保存：根据输出格式决定是否转 RGB
    ext = os.path.splitext(output_path)[1].lower()
    try:
        if ext in (".jpg", ".jpeg", ".bmp"):
            if img.mode == "RGBA":
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            img.save(output_path, quality=95, optimize=True)
        elif ext == ".png":
            img.save(output_path, optimize=True)
        elif ext == ".webp":
            img.save(output_path, quality=95)
        else:
            img.save(output_path)
        img.close()
    except Exception as e:
        if progress_cb:
            progress_cb(-1, f"错误：保存失败 - {e}")
        return False

    if progress_cb:
        progress_cb(100, "水印添加完成")
    return True


def batch_watermark(
    files: List[str],
    output_dir: str,
    wm_type: str = "text",
    text: str = "",
    font_size: int = 48,
    color: str = "#FFFFFF",
    opacity: float = 0.8,
    rotation: int = 0,
    position: str = "右下角",
    font_path: str = "",
    wm_image_path: str = "",
    scale: float = 0.2,
    progress_cb=None,
) -> int:
    """批量添加水印，返回成功数量。"""
    os.makedirs(output_dir, exist_ok=True)
    total = len(files)
    success = 0
    for i, fp in enumerate(files):
        if progress_cb:
            progress_cb(int(i * 90 / max(total, 1)), f"处理 {i+1}/{total}...")
        name = os.path.splitext(os.path.basename(fp))[0]
        ext = os.path.splitext(fp)[1]
        out = os.path.join(output_dir, f"{name}_watermark{ext}")
        if process_watermark(fp, out, wm_type, text, font_size, color, opacity,
                             rotation, position, font_path, wm_image_path, scale):
            success += 1
    if progress_cb:
        progress_cb(100, f"完成 {success}/{total}")
    return success


def generate_preview(
    input_path: str,
    wm_type: str = "text",
    text: str = "",
    font_size: int = 48,
    color: str = "#FFFFFF",
    opacity: float = 0.8,
    rotation: int = 0,
    position: str = "右下角",
    font_path: str = "",
    wm_image_path: str = "",
    scale: float = 0.2,
    max_preview_size: int = 400,
) -> Optional[Image.Image]:
    """生成预览图（缩小后添加水印），返回 PIL Image 对象。"""
    try:
        img = Image.open(input_path)
    except Exception:
        return None

    orig_w, orig_h = img.size
    # 缩小到预览尺寸
    if max(orig_w, orig_h) > max_preview_size:
        ratio = max_preview_size / max(orig_w, orig_h)
        img = img.resize((int(orig_w * ratio), int(orig_h * ratio)), Image.LANCZOS)

    if wm_type == "text":
        # 预览时按比例缩放字号
        preview_font = max(10, int(font_size * img.size[0] / max(orig_w, 1)))
        img = add_text_watermark(img, text, preview_font, color, opacity, rotation, position, font_path)
    elif wm_type == "image":
        img = add_image_watermark(img, wm_image_path, scale, opacity, rotation, position)

    return img
