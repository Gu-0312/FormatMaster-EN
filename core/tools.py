"""实用工具：PDF合并拆分、图片压缩、批量重命名"""
import os
import re
from PIL import Image


# ═══════════════════════════════════════════════
#  PDF 合并 / 拆分
# ═══════════════════════════════════════════════
def pdf_merge(pdf_list, output_path, progress_cb=None):
    """合并多个PDF为一个"""
    from pypdf import PdfWriter
    writer = PdfWriter()
    total = len(pdf_list)
    for i, pdf in enumerate(pdf_list):
        if progress_cb:
            progress_cb(int(i * 90 / max(total, 1)), f"合并第 {i+1}/{total} 个…")
        writer.append(pdf)
    if progress_cb:
        progress_cb(95, "正在保存…")
    writer.write(output_path)
    writer.close()
    if progress_cb:
        progress_cb(100, "合并完成")
    return True


def pdf_split(pdf_path, output_dir, page_ranges, progress_cb=None):
    """拆分PDF，page_ranges: list of (start, end) 1-based页码"""
    from pypdf import PdfReader, PdfWriter
    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)
    base = os.path.splitext(os.path.basename(pdf_path))[0]
    total = len(page_ranges)

    for idx, (start, end) in enumerate(page_ranges):
        if progress_cb:
            progress_cb(int(idx * 90 / max(total, 1)),
                        f"拆分第 {start}-{end} 页…")
        writer = PdfWriter()
        for p in range(max(start - 1, 0), min(end, total_pages)):
            writer.add_page(reader.pages[p])
        suffix = f"_p{start}-{end}" if total > 1 else ""
        out = os.path.join(output_dir, base + suffix + ".pdf")
        writer.write(out)
        writer.close()

    if progress_cb:
        progress_cb(100, "拆分完成")
    return True


def pdf_get_page_count(pdf_path):
    from pypdf import PdfReader
    return len(PdfReader(pdf_path).pages)


# ═══════════════════════════════════════════════
#  图片压缩
# ═══════════════════════════════════════════════
def image_compress(input_path, output_path, quality=80, max_size=None, progress_cb=None):
    """压缩图片：quality 1-100，max_size (w,h) 限制最大分辨率"""
    if progress_cb:
        progress_cb(20, "打开图片…")
    img = Image.open(input_path)

    # RGBA → RGB (JPG不支持透明)
    ext = os.path.splitext(output_path)[1].lower()
    if img.mode == 'RGBA' and ext in ('.jpg', '.jpeg'):
        bg = Image.new('RGB', img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg
    elif img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')

    if progress_cb:
        progress_cb(50, "压缩中…")

    # 限制最大分辨率
    if max_size:
        w, h = img.size
        mw, mh = max_size
        if w > mw or h > mh:
            ratio = min(mw / w, mh / h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    save_kw = {}
    if ext in ('.jpg', '.jpeg'):
        save_kw = {'quality': quality, 'optimize': True}
    elif ext == '.png':
        save_kw = {'optimize': True}
    elif ext == '.webp':
        save_kw = {'quality': quality}

    if progress_cb:
        progress_cb(80, "保存…")
    img.save(output_path, **save_kw)
    img.close()

    orig = os.path.getsize(input_path)
    new = os.path.getsize(output_path)
    ratio = f"{(1 - new / max(orig, 1)) * 100:.0f}%" if orig > 0 else "0%"
    if progress_cb:
        progress_cb(100, f"压缩完成  节省 {ratio}")
    return True


# ═══════════════════════════════════════════════
#  批量重命名
# ═══════════════════════════════════════════════
def batch_rename(file_list, pattern, start_num=1, progress_cb=None):
    """批量重命名
    pattern 占位符:
      {n}    序号
      {name} 原文件名(不含扩展名)
      {ext}  扩展名
      {date} 修改日期 YYYYMMDD
    示例: 照片_{n:03d}  →  照片_001.jpg
    """
    total = len(file_list)
    renamed = []

    for i, fp in enumerate(file_list):
        if progress_cb:
            progress_cb(int(i * 90 / max(total, 1)), f"重命名 {i+1}/{total}…")
        d = os.path.dirname(fp)
        name = os.path.splitext(os.path.basename(fp))[0]
        ext = os.path.splitext(fp)[1]
        date_str = ""
        try:
            date_str = __import__('datetime').datetime.fromtimestamp(
                os.path.getmtime(fp)).strftime("%Y%m%d")
        except Exception:
            date_str = "00000000"

        # 格式化序号
        n = start_num + i
        fmt = pattern.replace("{name}", name).replace("{ext}", ext).replace("{date}", date_str)
        # 处理 {n:03d} 这种格式
        def _fmt_n(m):
            spec = m.group(1).lstrip(":") if m.group(1) else ""
            if spec:
                return format(n, spec)
            return str(n)
        fmt = re.sub(r'\{n(:.*?)?\}', _fmt_n, fmt)

        new_name = fmt + ext if not fmt.endswith(ext) else fmt
        new_path = os.path.join(d, new_name)
        if new_path != fp and not os.path.exists(new_path):
            os.rename(fp, new_path)
            renamed.append((fp, new_path))

    if progress_cb:
        progress_cb(100, f"重命名完成  {len(renamed)} 个文件")
    return renamed
