"""图像批量预设裁剪"""
import os
from PIL import Image


PRESETS = {
    "1:1 正方形 (1080×1080)": (1080, 1080),
    "4:3 横版 (1200×900)": (1200, 900),
    "16:9 横版 (1920×1080)": (1920, 1080),
    "9:16 竖版 (1080×1920)": (1080, 1920),
    "3:4 竖版 (900×1200)": (900, 1200),
    "微信封面 (900×383)": (900, 383),
    "小红书竖版 (1242×1660)": (1242, 1660),
    "抖音竖版 (720×1280)": (720, 1280),
    "B站封面 (1146×717)": (1146, 717),
    "微博封面 (980×300)": (980, 300),
    "YouTube 封面 (1280×720)": (1280, 720),
}


def crop_to_preset(input_path, output_path, preset_size, mode="cover", progress_cb=None):
    try:
        img = Image.open(input_path)
    except FileNotFoundError:
        if progress_cb:
            progress_cb(-1, "错误：找不到图片文件")
        return False
    except Exception:
        if progress_cb:
            progress_cb(-1, "错误：无法打开图片")
        return False

    target_w, target_h = preset_size
    img_w, img_h = img.size
    target_ratio = target_w / target_h
    img_ratio = img_w / img_h

    if mode == "cover":
        if img_ratio > target_ratio:
            new_h = img_h
            new_w = int(new_h * target_ratio)
        else:
            new_w = img_w
            new_h = int(new_w / target_ratio)
        left = (img_w - new_w) // 2
        top = (img_h - new_h) // 2
        img = img.crop((left, top, left + new_w, top + new_h))
    else:
        if img_ratio > target_ratio:
            new_w = img_w
            new_h = int(new_w / target_ratio)
        else:
            new_h = img_h
            new_w = int(new_h * target_ratio)
        img = img.resize((new_w, new_h), Image.LANCZOS)

    img = img.resize((target_w, target_h), Image.LANCZOS)

    if img.mode == 'RGBA':
        bg = Image.new('RGB', img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg
    elif img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')

    if progress_cb:
        progress_cb(80, "保存...")
    img.save(output_path, quality=95)
    img.close()
    if progress_cb:
        progress_cb(100, "裁剪完成")
    return True


def batch_crop(files, output_dir, preset_size, mode="cover", progress_cb=None):
    total = len(files)
    success = 0
    for i, fp in enumerate(files):
        if progress_cb:
            progress_cb(int(i * 90 / max(total, 1)), f"处理 {i+1}/{total}...")
        name = os.path.splitext(os.path.basename(fp))[0] + ".jpg"
        out = os.path.join(output_dir, name)
        if crop_to_preset(fp, out, preset_size, mode, progress_cb):
            success += 1
    if progress_cb:
        progress_cb(100, f"完成  {success}/{total}")
    return success