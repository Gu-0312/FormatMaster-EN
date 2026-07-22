"""图片 OCR 文字识别"""
import os


def ocr_image(input_path, lang="chi_sim+eng", progress_cb=None):
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        if progress_cb:
            progress_cb(-1, "错误：缺少 pytesseract 库")
        return ""
    try:
        if progress_cb:
            progress_cb(30, "打开图片...")
        img = Image.open(input_path)
        if progress_cb:
            progress_cb(50, "识别中...")
        text = pytesseract.image_to_string(img, lang=lang)
        img.close()
        if progress_cb:
            progress_cb(100, "识别完成")
        return text.strip()
    except FileNotFoundError:
        if progress_cb:
            progress_cb(-1, "错误：找不到图片文件")
        return ""
    except Exception as e:
        if progress_cb:
            progress_cb(-1, f"错误：{e}")
        return ""


def ocr_to_file(input_path, output_path, lang="chi_sim+eng", progress_cb=None):
    text = ocr_image(input_path, lang, progress_cb)
    if text:
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(text)
            return True
        except Exception as e:
            if progress_cb:
                progress_cb(-1, f"错误：无法保存文件 - {e}")
            return False
    return False


def batch_ocr(files, output_dir, lang="chi_sim+eng", progress_cb=None):
    total = len(files)
    success = 0
    for i, fp in enumerate(files):
        if progress_cb:
            progress_cb(int(i * 90 / max(total, 1)), f"识别 {i+1}/{total}...")
        name = os.path.splitext(os.path.basename(fp))[0] + ".txt"
        out = os.path.join(output_dir, name)
        if ocr_to_file(fp, out, lang):
            success += 1
    if progress_cb:
        progress_cb(100, f"完成  {success}/{total}")
    return success