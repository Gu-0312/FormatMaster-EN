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
    text, _ = ocr_image_with_boxes(input_path, lang, progress_cb)
    return text


def ocr_image_with_boxes(input_path, lang="chi_sim+eng", progress_cb=None):
    """OCR 识别并返回 (text, boxes)。

    boxes: 识别行归一化矩形列表 [(x0, y0, x1, y1), ...]（0~1 比例，可叠加到原图）。
    识别失败返回 ("", [])。
    """
    try:
        from PIL import Image
    except ImportError:
        if progress_cb:
            progress_cb(-1, "错误：缺少 Pillow 库")
        return "", []

    try:
        if progress_cb:
            progress_cb(30, "打开图片...")
        if not os.path.isfile(input_path):
            if progress_cb:
                progress_cb(-1, "错误：找不到图片文件")
            return "", []

        if progress_cb:
            progress_cb(50, "识别中...")

        engine = _get_engine()
        result, elapse = engine(input_path)

        if progress_cb:
            progress_cb(100, "识别完成")

        if not result:
            return "", []

        try:
            with Image.open(input_path) as im:
                iw, ih = im.size
        except Exception:  # noqa: BLE001 - 取尺寸失败则跳过归一化
            iw = ih = 1

        lines = []
        boxes = []
        for item in result:
            bbox, text = item[0], item[1]
            lines.append(text)
            try:
                xs = [p[0] for p in bbox]
                ys = [p[1] for p in bbox]
                x0 = min(xs) / max(iw, 1)
                y0 = min(ys) / max(ih, 1)
                x1 = max(xs) / max(iw, 1)
                y1 = max(ys) / max(ih, 1)
                boxes.append((x0, y0, x1, y1))
            except Exception:  # noqa: BLE001 - 单行框异常忽略
                pass
        return "\n".join(lines), boxes
    except Exception as e:
        if progress_cb:
            progress_cb(-1, f"错误：{e}")
        return "", []


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


def write_result(output_path, text, fmt="txt"):
    """把 OCR 文本写出为 txt 或 docx。

    fmt: "txt" 纯文本 / "docx" Word 文档（python-docx）。
    返回是否成功。
    """
    try:
        if fmt == "docx":
            from docx import Document
            doc = Document()
            for line in text.splitlines():
                doc.add_paragraph(line)
            doc.save(output_path)
        else:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(text)
        return True
    except Exception:
        return False
