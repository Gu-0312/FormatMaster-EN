"""图片 EXIF 查看/清除"""
import os
from PIL import Image
from PIL.ExifTags import TAGS


def get_exif(image_path):
    try:
        img = Image.open(image_path)
        exif_data = img._getexif()
        if not exif_data:
            return []
        result = []
        for tag_id, value in exif_data.items():
            tag_name = TAGS.get(tag_id, str(tag_id))
            result.append((tag_name, str(value)[:200]))
        return result
    except Exception:
        return []


def clear_exif(input_path, output_path, progress_cb=None):
    try:
        img = Image.open(input_path)
        data = list(img.getdata())
        mode = img.mode
        size = img.size
        new_img = Image.new(mode, size)
        new_img.putdata(data)
        ext = os.path.splitext(output_path)[1].lower()
        save_kw = {}
        if ext in ('.jpg', '.jpeg'):
            save_kw['quality'] = 95
        new_img.save(output_path, **save_kw)
        img.close()
        new_img.close()
        if progress_cb:
            progress_cb(100, "EXIF清除完成")
        return True
    except FileNotFoundError:
        if progress_cb:
            progress_cb(-1, "错误：找不到图片文件")
        return False
    except Exception as e:
        if progress_cb:
            progress_cb(-1, f"错误：{e}")
        return False