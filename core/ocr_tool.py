"""图片 OCR 文字识别（基于 RapidOCR + ONNX Runtime，无需外部安装）"""
import os

_ocr_engine = None


def _get_engine():
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr_engine = RapidOCR()
    return _ocr_engine


# RapidOCR 内置中英文模型，语言参数主要用于界面兼容
_LANG_MAP = {
    "chi_sim+eng": None,    # 默认模型已支持中英
    "chi_sim": None,
    "eng": None,
    "chi_tra+eng": None,
    "chi_tra": None,
}


def ocr_image(input_path, lang="chi_sim+eng", progress_cb=None):
    try:
        from PIL import Image
    except ImportError:
        if progress_cb:
            progress_cb(-1, "错误：缺少 Pillow 库")
        return ""

    try:
        if progress_cb:
            progress_cb(30, "打开图片...")
        if not os.path.isfile(input_path):
            if progress_cb:
                progress_cb(-1, "错误：找不到图片文件")
            return ""

        if progress_cb:
            progress_cb(50, "识别中...")

        engine = _get_engine()
        result, elapse = engine(input_path)

        if progress_cb:
            progress_cb(100, "识别完成")

        if not result:
            return ""

        # RapidOCR 返回 [[bbox, text, confidence], ...]
        lines = [item[1] for item in result]
        return "\n".join(lines)
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
