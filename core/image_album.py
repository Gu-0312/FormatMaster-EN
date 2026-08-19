"""image_album — 图片拼接 / 合成 PDF 相册。

- merge_vertical / merge_horizontal：多图拼成一张长图（宽度/高度统一，白底空隙）
- to_pdf：多图一键合成 PDF 相册（每图一页，A4 或按原尺寸）
纯 PIL 实现，无外部依赖。
"""
import os

from PIL import Image

_BG = (255, 255, 255)


def _load(files, progress_callback=None):
    """打开全部图片并统一为 RGB。"""
    imgs = []
    total = len(files)
    for i, f in enumerate(files):
        try:
            with Image.open(f) as _f:
                im = _f.convert("RGB")
            imgs.append(im)
        except (OSError, IOError):
            if progress_callback:
                progress_callback(-1, f"无法打开: {os.path.basename(f)}")
            return None
        if progress_callback:
            progress_callback(int((i + 1) / total * 40), f"读取 {i+1}/{total}…")
    return imgs


def _close(imgs):
    for im in imgs:
        try:
            im.close()
        except Exception:
            pass


def merge_vertical(files, output_path, gap=10, progress_callback=None):
    """纵向拼接：所有图统一到最大宽度，依次向下排列。"""
    imgs = _load(files, progress_callback)
    if imgs is None:
        return False
    w = max(im.width for im in imgs)
    h = sum(im.height for im in imgs) + gap * (len(imgs) - 1)
    canvas = Image.new("RGB", (w, h), _BG)
    y = 0
    for i, im in enumerate(imgs):
        if im.width != w:
            im = im.resize((w, int(im.height * w / im.width)), Image.LANCZOS)
        canvas.paste(im, (0, y))
        y += im.height + gap
        if progress_callback:
            progress_callback(int(40 + (i + 1) / len(imgs) * 50), f"拼接 {i+1}/{len(imgs)}…")
    try:
        canvas.save(output_path, quality=95)
    except (OSError, IOError) as e:
        if progress_callback:
            progress_callback(-1, f"保存失败：{e}")
        return False
    canvas.close()
    _close(imgs)
    if progress_callback:
        progress_callback(100, "完成")
    return True


def merge_horizontal(files, output_path, gap=10, progress_callback=None):
    """横向拼接：所有图统一到最大高度，依次向右排列。"""
    imgs = _load(files, progress_callback)
    if imgs is None:
        return False
    h = max(im.height for im in imgs)
    w = sum(im.width for im in imgs) + gap * (len(imgs) - 1)
    canvas = Image.new("RGB", (w, h), _BG)
    x = 0
    for i, im in enumerate(imgs):
        if im.height != h:
            im = im.resize((int(im.width * h / im.height), h), Image.LANCZOS)
        canvas.paste(im, (x, 0))
        x += im.width + gap
        if progress_callback:
            progress_callback(int(40 + (i + 1) / len(imgs) * 50), f"拼接 {i+1}/{len(imgs)}…")
    try:
        canvas.save(output_path, quality=95)
    except (OSError, IOError) as e:
        if progress_callback:
            progress_callback(-1, f"保存失败：{e}")
        return False
    canvas.close()
    _close(imgs)
    if progress_callback:
        progress_callback(100, "完成")
    return True


def to_pdf(files, output_path, page_mode="A4", progress_callback=None):
    """多图合成 PDF 相册：每张图一页。

    page_mode: "A4"（A4 纸居中）或 "original"（按图片原始尺寸）。
    """
    imgs = _load(files, progress_callback)
    if imgs is None:
        return False
    try:
        if page_mode == "original":
            # 原始尺寸：多页 PDF
            first = imgs[0]
            first.save(output_path, "PDF", save_all=True,
                       append_images=imgs[1:] if len(imgs) > 1 else [])
        else:
            # A4（2480×3508 @300dpi），白底居中，等比缩放
            page = (2480, 3508)
            pages = []
            for im in imgs:
                canvas = Image.new("RGB", page, _BG)
                scale = min(page[0] / im.width, page[1] / im.height, 1.0)
                if scale < 1.0:
                    im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
                canvas.paste(im, ((page[0] - im.width) // 2, (page[1] - im.height) // 2))
                pages.append(canvas)
            pages[0].save(output_path, "PDF", save_all=True,
                          append_images=pages[1:] if len(pages) > 1 else [])
            for c in pages:
                c.close()
        if progress_callback:
            progress_callback(100, "完成")
        return True
    except (OSError, IOError) as e:
        if progress_callback:
            progress_callback(-1, f"保存失败：{e}")
        return False
    finally:
        _close(imgs)
