"""PDF 按页提取 / 拆分增强

支持三种模式：
  - range: 按页码范围提取到单个 PDF（如 "1,3,5-8"）
  - each: 每页存为一个独立 PDF
  - selected: 提取指定页码列表，每页一个 PDF
"""
import os


def pdf_extract_pages(pdf_path, output_dir, mode="range", page_spec="", progress_cb=None):
    """PDF 按页提取增强。

    参数:
      pdf_path: 输入 PDF 路径
      output_dir: 输出目录
      mode: "range" / "each" / "selected"
      page_spec: 页码规格字符串（mode="range" 时如 "1,3,5-8"，
                 mode="selected" 时如 "1,3,5"）
    返回 bool。
    """
    from pypdf import PdfReader, PdfWriter
    from pypdf.errors import PdfReadError

    os.makedirs(output_dir, exist_ok=True)
    try:
        reader = PdfReader(pdf_path)
    except FileNotFoundError:
        if progress_cb:
            progress_cb(-1, "错误：找不到PDF文件")
        return False
    except PdfReadError:
        if progress_cb:
            progress_cb(-1, "错误：PDF文件已损坏或加密")
        return False

    total_pages = len(reader.pages)
    base = os.path.splitext(os.path.basename(pdf_path))[0]

    def _parse_ranges(spec):
        """解析 "1,3,5-8" → [(1,3), (5,5), (7,8)]"""
        ranges = []
        for part in spec.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                s, e = part.split("-", 1)
                ranges.append((int(s.strip()), int(e.strip())))
            else:
                n = int(part)
                ranges.append((n, n))
        return ranges

    def _parse_pages(spec):
        """解析 "1,3,5" → [1, 3, 5]"""
        pages = []
        for part in spec.split(","):
            part = part.strip()
            if part:
                pages.append(int(part))
        return pages

    try:
        if mode == "range":
            ranges = _parse_ranges(page_spec)
            if not ranges:
                if progress_cb:
                    progress_cb(-1, "错误：页码范围为空")
                return False
            total = len(ranges)
            for idx, (start, end) in enumerate(ranges):
                if progress_cb:
                    progress_cb(int(idx * 90 / max(total, 1)), f"提取第 {start}-{end} 页…")
                if start > total_pages:
                    if progress_cb:
                        progress_cb(-1, f"错误：起始页码 {start} 超过总页数 {total_pages}")
                    return False
                writer = PdfWriter()
                for p in range(max(start - 1, 0), min(end, total_pages)):
                    writer.add_page(reader.pages[p])
                suffix = f"_p{start}-{end}" if start != end else f"_p{start}"
                out = os.path.join(output_dir, base + suffix + ".pdf")
                with open(out, "wb") as f:
                    writer.write(f)

        elif mode == "each":
            for i in range(total_pages):
                if progress_cb:
                    progress_cb(int(i * 90 / max(total_pages, 1)), f"提取第 {i+1}/{total_pages} 页…")
                writer = PdfWriter()
                writer.add_page(reader.pages[i])
                out = os.path.join(output_dir, f"{base}_p{i+1}.pdf")
                with open(out, "wb") as f:
                    writer.write(f)

        elif mode == "selected":
            pages = _parse_pages(page_spec)
            if not pages:
                if progress_cb:
                    progress_cb(-1, "错误：未指定页码")
                return False
            total = len(pages)
            for idx, pg in enumerate(pages):
                if progress_cb:
                    progress_cb(int(idx * 90 / max(total, 1)), f"提取第 {pg} 页…")
                if pg < 1 or pg > total_pages:
                    if progress_cb:
                        progress_cb(-1, f"错误：页码 {pg} 超出范围（1-{total_pages}）")
                    return False
                writer = PdfWriter()
                writer.add_page(reader.pages[pg - 1])
                out = os.path.join(output_dir, f"{base}_p{pg}.pdf")
                with open(out, "wb") as f:
                    writer.write(f)
        else:
            if progress_cb:
                progress_cb(-1, f"错误：未知模式 {mode}")
            return False

        if progress_cb:
            progress_cb(100, "提取完成")
        return True
    except Exception as e:
        if progress_cb:
            progress_cb(-1, f"错误：{e}")
        return False
