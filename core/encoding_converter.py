"""文件编码批量转换"""
import os
import codecs


ENCODINGS = [
    ("UTF-8", "utf-8"),
    ("GBK (简体中文)", "gbk"),
    ("GB2312", "gb2312"),
    ("Big5 (繁体中文)", "big5"),
    ("Shift-JIS (日语)", "shift_jis"),
    ("EUC-KR (韩语)", "euc-kr"),
    ("ISO-8859-1 (西欧)", "iso-8859-1"),
    ("ASCII", "ascii"),
]


def detect_encoding(filepath):
    try:
        import chardet
    except ImportError:
        return None
    with open(filepath, "rb") as f:
        raw = f.read(65536)
    result = chardet.detect(raw)
    return result["encoding"] if result and result["encoding"] else None


def convert_encoding(input_path, output_path, src_enc, tgt_enc, progress_cb=None):
    try:
        with open(input_path, "r", encoding=src_enc, errors="replace") as f:
            content = f.read()
        with open(output_path, "w", encoding=tgt_enc, errors="replace") as f:
            f.write(content)
        if progress_cb:
            progress_cb(100, "转换完成")
        return True
    except FileNotFoundError:
        if progress_cb:
            progress_cb(-1, "错误：找不到输入文件")
        return False
    except Exception as e:
        if progress_cb:
            progress_cb(-1, f"错误：{e}")
        return False


def batch_convert_encoding(files, output_dir, src_enc, tgt_enc, progress_cb=None):
    total = len(files)
    success = 0
    for i, fp in enumerate(files):
        if progress_cb:
            progress_cb(int(i * 90 / max(total, 1)), f"转换 {i+1}/{total}...")
        name = os.path.basename(fp)
        out = os.path.join(output_dir, name)
        try:
            with open(fp, "r", encoding=src_enc, errors="replace") as f:
                content = f.read()
            with open(out, "w", encoding=tgt_enc, errors="replace") as f:
                f.write(content)
            success += 1
        except Exception:
            continue
    if progress_cb:
        progress_cb(100, f"完成  {success}/{total}")
    return success