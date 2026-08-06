"""PDF 转图片 — PyMuPDF (fitz) 逐页渲染

支持 DPI 控制、输出格式(JPG/PNG)、页码范围、批量导出。
"""

import os


def pdf_to_images(pdf_path, output_dir, fmt="PNG", dpi=200, pages=None, progress_cb=None):
    """将 PDF 页面导出为图片。

    参数:
      pdf_path: 输入 PDF 路径
      output_dir: 输出目录
      fmt: 输出格式 "PNG" / "JPG"
      dpi: 渲染 DPI (72~600)
      pages: 页码范围，None 表示全部；支持 "1,3,5-8" 格式
      progress_cb: 进度回调 (pct: int, msg: str)

    返回 (success: bool, saved_files: list[str])。
    """
    try:
        import fitz
    except ImportError:
        if progress_cb:
            progress_cb(-1, "错误: PyMuPDF (fitz) 未安装")
        return False, []

    if not os.path.isfile(pdf_path):
        if progress_cb:
            progress_cb(-1, "错误: 找不到 PDF 文件")
        return False, []

    os.makedirs(output_dir, exist_ok=True)

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        if progress_cb:
            progress_cb(-1, f"错误: PDF 打开失败 - {e}")
        return False, []

    total_pages = doc.page_count
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]

    # 解析页码范围
    def _parse_pages(spec, total):
        if not spec or not spec.strip():
            return list(range(total))
        result = []
        for part in spec.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                s, e = part.split("-", 1)
                s, e = int(s.strip()), int(e.strip())
                s = max(1, s) - 1
                e = min(total, e)
                result.extend(range(s, e))
            else:
                n = int(part) - 1
                if 0 <= n < total:
                    result.append(n)
        return sorted(set(result))

    page_indices = _parse_pages(pages, total_pages)
    if not page_indices:
        doc.close()
        if progress_cb:
            progress_cb(-1, "错误: 页码范围为空")
        return False, []

    ext = ".png" if fmt.upper() == "PNG" else ".jpg"
    saved_files = []

    if progress_cb:
        progress_cb(0, f"开始导出 {len(page_indices)} 页…")

    for i, page_idx in enumerate(page_indices):
        try:
            page = doc.load_page(page_idx)
            pix = page.get_pixmap(dpi=dpi)
            page_num = page_idx + 1
            out_path = os.path.join(output_dir, f"{base_name}_p{page_num:03d}{ext}")
            pix.save(out_path)
            saved_files.append(out_path)
        except Exception as e:
            doc.close()
            if progress_cb:
                progress_cb(-1, f"错误: 第 {page_idx + 1} 页渲染失败 - {e}")
            return False, saved_files

        pct = int((i + 1) / len(page_indices) * 100)
        if progress_cb:
            progress_cb(pct, f"导出中… {i + 1}/{len(page_indices)} 页")

    doc.close()

    if progress_cb:
        progress_cb(100, f"完成，共导出 {len(saved_files)} 张图片")

    return True, saved_files


def pdf_to_single_image(pdf_path, output_path, page=0, fmt="PNG", dpi=200, progress_cb=None):
    """导出 PDF 的某一页为单张图片。

    返回 bool。
    """
    if not os.path.isfile(pdf_path):
        if progress_cb:
            progress_cb(-1, "错误: 找不到 PDF 文件")
        return False

    try:
        import fitz
        doc = fitz.open(pdf_path)
        page = doc.load_page(page)
        pix = page.get_pixmap(dpi=dpi)
        pix.save(output_path)
        doc.close()
        if progress_cb:
            progress_cb(100, "导出完成")
        return True
    except Exception as e:
        if progress_cb:
            progress_cb(-1, f"错误: {e}")
        return False