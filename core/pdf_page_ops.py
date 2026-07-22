"""PDF 页面操作：旋转、删除、提取"""
import os


def pdf_rotate(input_path, output_path, rotation=90, pages="all", progress_cb=None):
    import fitz
    try:
        doc = fitz.open(input_path)
    except Exception:
        if progress_cb:
            progress_cb(-1, "错误：无法打开PDF文件")
        return False
    total = len(doc)
    if pages == "all":
        targets = list(range(total))
    else:
        try:
            targets = []
            for part in pages.split(","):
                part = part.strip()
                if "-" in part:
                    s, e = part.split("-", 1)
                    targets.extend(range(int(s)-1, int(e)))
                else:
                    targets.append(int(part)-1)
        except Exception:
            if progress_cb:
                progress_cb(-1, "错误：页码格式不正确（如 1,3,5-7）")
            doc.close()
            return False
    for i, page in enumerate(doc):
        if i in targets:
            page.set_rotation(page.rotation + rotation)
        if progress_cb:
            progress_cb(int(i * 90 / max(total, 1)), f"处理第{i+1}/{total}页...")
    doc.save(output_path)
    doc.close()
    if progress_cb:
        progress_cb(100, f"旋转完成  处理{len(targets)}页")
    return True


def pdf_delete_pages(input_path, output_path, pages, progress_cb=None):
    import fitz
    try:
        doc = fitz.open(input_path)
    except Exception:
        if progress_cb:
            progress_cb(-1, "错误：无法打开PDF文件")
        return False
    total = len(doc)
    try:
        to_delete = set()
        for part in pages.split(","):
            part = part.strip()
            if "-" in part:
                s, e = part.split("-", 1)
                for p in range(int(s)-1, int(e)):
                    to_delete.add(p)
            else:
                to_delete.add(int(part)-1)
    except Exception:
        if progress_cb:
            progress_cb(-1, "错误：页码格式不正确")
        doc.close()
        return False
    to_delete = sorted(to_delete, reverse=True)
    for i, p in enumerate(to_delete):
        if p < 0 or p >= len(doc):
            continue
        doc.delete_page(p)
        if progress_cb:
            progress_cb(int(i * 90 / max(len(to_delete), 1)), f"删除第{p+1}页...")
    doc.save(output_path)
    doc.close()
    kept = total - len(to_delete)
    if progress_cb:
        progress_cb(100, f"删除完成  剩余{kept}页")
    return True


def pdf_extract_pages(input_path, output_dir, pages, progress_cb=None):
    import fitz
    try:
        doc = fitz.open(input_path)
    except Exception:
        if progress_cb:
            progress_cb(-1, "错误：无法打开PDF文件")
        return False
    base = os.path.splitext(os.path.basename(input_path))[0]
    try:
        page_list = []
        for part in pages.split(","):
            part = part.strip()
            if "-" in part:
                s, e = part.split("-", 1)
                for p in range(int(s)-1, int(e)):
                    page_list.append(p)
            else:
                page_list.append(int(part)-1)
    except Exception:
        if progress_cb:
            progress_cb(-1, "错误：页码格式不正确")
        doc.close()
        return False
    for i, p in enumerate(page_list):
        if p < 0 or p >= len(doc):
            continue
        new_doc = fitz.open()
        new_doc.insert_pdf(doc, from_page=p, to_page=p)
        out_path = os.path.join(output_dir, f"{base}_p{p+1}.pdf")
        new_doc.save(out_path)
        new_doc.close()
        if progress_cb:
            progress_cb(int(i * 90 / max(len(page_list), 1)), f"提取第{p+1}页...")
    doc.close()
    if progress_cb:
        progress_cb(100, f"提取完成  共{len(page_list)}页")
    return True