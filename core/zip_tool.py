"""ZIP 压缩/解压"""
import os
import zipfile


def zip_compress(files, output_path, progress_cb=None):
    total = len(files)
    try:
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, fp in enumerate(files):
                if progress_cb:
                    progress_cb(int(i * 90 / max(total, 1)), f"压缩 {i+1}/{total}...")
                arcname = os.path.basename(fp)
                zf.write(fp, arcname)
        if progress_cb:
            progress_cb(100, "压缩完成")
        return True
    except Exception as e:
        if progress_cb:
            progress_cb(-1, f"错误：{e}")
        return False


def zip_extract(input_path, output_dir, progress_cb=None):
    try:
        with zipfile.ZipFile(input_path, "r") as zf:
            names = zf.namelist()
            total = len(names)
            for i, name in enumerate(names):
                if progress_cb:
                    progress_cb(int(i * 90 / max(total, 1)), f"解压 {i+1}/{total}...")
                zf.extract(name, output_dir)
        if progress_cb:
            progress_cb(100, "解压完成")
        return True
    except zipfile.BadZipFile:
        if progress_cb:
            progress_cb(-1, "错误：ZIP文件已损坏")
        return False
    except Exception as e:
        if progress_cb:
            progress_cb(-1, f"错误：{e}")
        return False


def zip_list(input_path):
    try:
        with zipfile.ZipFile(input_path, "r") as zf:
            items = []
            for info in zf.infolist():
                items.append({
                    "name": info.filename,
                    "size": info.file_size,
                    "compress_size": info.compress_size,
                    "ratio": f"{info.compress_size/max(info.file_size,1)*100:.0f}%",
                })
            return items
    except Exception:
        return []