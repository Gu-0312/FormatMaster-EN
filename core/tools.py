"""实用工具：PDF合并拆分、图片压缩、批量重命名"""
import os
import re
from PIL import Image


def _check_pymupdf_available():
    """检查 PyMuPDF (fitz) 是否可用
    风险规避：PyInstaller 打包后可能无法正常加载，需提前检测。
    返回 (bool, str)：(是否可用, 错误信息)
    """
    try:
        import fitz
        # 触发实际加载，避免仅是模块存在但运行时失败
        _ = fitz.__doc__
        return True, ""
    except ImportError as e:
        return False, f"PyMuPDF 未安装或打包后丢失：{e}"
    except Exception as e:
        return False, f"PyMuPDF 加载失败：{e}"


def pdf_encrypt(input_path, output_path, open_password=None, owner_password=None,
                encryption_method="AES-256", progress_cb=None):
    """PDF加密：设置打开密码和权限密码
    encryption_method: AES-128, AES-256

    风险规避：PyMuPDF 在 PyInstaller --onefile 模式下可能加载失败，
    所有 fitz 调用均包裹在 try/except 中，失败时抛出明确异常。
    """
    ok, err = _check_pymupdf_available()
    if not ok:
        raise RuntimeError(f"PDF 加密不可用：{err}")
    import fitz
    doc = fitz.open(input_path)
    
    if doc.needs_pass:
        if open_password:
            if not doc.authenticate(open_password):
                doc.close()
                raise RuntimeError("密码错误，无法打开加密文档")
        else:
            doc.close()
            raise RuntimeError("文件已加密，请输入打开密码以重新加密")
    
    if progress_cb:
        progress_cb(30, "正在加密…")
    
    perm = int(fitz.PDF_PERM_ACCESSIBILITY | fitz.PDF_PERM_PRINT | 
               fitz.PDF_PERM_COPY | fitz.PDF_PERM_ANNOTATE)
    
    encrypt_meth = fitz.PDF_ENCRYPT_AES_256
    if encryption_method == "AES-128":
        encrypt_meth = fitz.PDF_ENCRYPT_AES_128
    
    doc.save(output_path, encryption=encrypt_meth, user_pw=open_password, 
             owner_pw=owner_password, permissions=perm)
    doc.close()
    
    if progress_cb:
        progress_cb(100, "加密完成")
    return True


def pdf_decrypt(input_path, output_path, password, progress_cb=None):
    """PDF解密：移除密码保护"""
    ok, err = _check_pymupdf_available()
    if not ok:
        raise RuntimeError(f"PDF 解密不可用：{err}")
    import fitz
    doc = fitz.open(input_path)
    
    if doc.needs_pass:
        if not doc.authenticate(password):
            raise ValueError("密码错误")
    
    if progress_cb:
        progress_cb(30, "正在解密…")
    
    doc.save(output_path, encryption=fitz.PDF_ENCRYPT_NONE)
    doc.close()
    
    if progress_cb:
        progress_cb(100, "解密完成")
    return True


def pdf_is_encrypted(input_path):
    """检查PDF是否加密"""
    ok, _ = _check_pymupdf_available()
    if not ok:
        return False
    import fitz
    try:
        doc = fitz.open(input_path)
        result = doc.needs_pass
        doc.close()
        return result
    except Exception:
        return False


def pdf_compress(input_path, output_path, target_dpi=150, quality=80, progress_cb=None):
    """PDF压缩：降低图片分辨率，减小体积"""
    ok, err = _check_pymupdf_available()
    if not ok:
        raise RuntimeError(f"PDF 压缩不可用：{err}")
    import fitz
    from PIL import Image
    import io

    doc = fitz.open(input_path)
    total_pages = len(doc)
    
    for i in range(total_pages):
        if progress_cb:
            progress_cb(int(i * 80 / max(total_pages, 1)), f"处理第 {i+1}/{total_pages} 页…")
        
        page = doc[i]
        images = page.get_images(full=True)
        
        for img_index, img in enumerate(images):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            
            try:
                img_pil = Image.open(io.BytesIO(image_bytes))
                
                current_w, current_h = img_pil.size
                current_dpi = img_pil.info.get("dpi", (target_dpi, target_dpi))
                
                if current_dpi[0] > target_dpi:
                    scale = target_dpi / current_dpi[0]
                    new_w = int(current_w * scale)
                    new_h = int(current_h * scale)
                    img_pil = img_pil.resize((new_w, new_h), Image.LANCZOS)
                
                if image_ext.lower() in ('jpg', 'jpeg'):
                    img_bytes_new = io.BytesIO()
                    img_pil.save(img_bytes_new, format='JPEG', quality=quality, optimize=True)
                    img_bytes_new = img_bytes_new.getvalue()
                elif image_ext.lower() == 'png':
                    img_bytes_new = io.BytesIO()
                    img_pil.save(img_bytes_new, format='PNG', optimize=True)
                    img_bytes_new = img_bytes_new.getvalue()
                else:
                    img_bytes_new = image_bytes
                
                if len(img_bytes_new) < len(image_bytes):
                    doc.update_image(xref, img_bytes_new)
                
                img_pil.close()
            except Exception:
                pass
    
    if progress_cb:
        progress_cb(90, "正在保存…")
    
    doc.save(output_path)
    doc.close()
    
    orig_size = os.path.getsize(input_path)
    new_size = os.path.getsize(output_path)
    saved_ratio = f"{(1 - new_size / max(orig_size, 1)) * 100:.0f}%" if orig_size > 0 else "0%"
    
    if progress_cb:
        progress_cb(100, f"压缩完成  节省 {saved_ratio}")
    return True


# ═══════════════════════════════════════════════
#  PDF 合并 / 拆分
# ═══════════════════════════════════════════════
def pdf_merge(pdf_list, output_path, progress_cb=None):
    """合并多个PDF为一个"""
    from pypdf import PdfWriter
    from pypdf.errors import PdfReadError
    writer = PdfWriter()
    total = len(pdf_list)
    for i, pdf in enumerate(pdf_list):
        if progress_cb:
            progress_cb(int(i * 90 / max(total, 1)), f"合并第 {i+1}/{total} 个…")
        try:
            writer.append(pdf)
        except PdfReadError:
            if progress_cb:
                progress_cb(-1, f"错误：文件 {os.path.basename(pdf)} 已损坏或加密，无法合并")
            writer.close()
            return False
        except FileNotFoundError:
            if progress_cb:
                progress_cb(-1, f"错误：找不到文件 {os.path.basename(pdf)}")
            writer.close()
            return False
    if progress_cb:
        progress_cb(95, "正在保存…")
    try:
        writer.write(output_path)
    except Exception:
        if progress_cb:
            progress_cb(-1, "错误：无法写入输出文件，请检查磁盘空间或权限")
        writer.close()
        return False
    writer.close()
    if progress_cb:
        progress_cb(100, "合并完成")
    return True


def pdf_split(pdf_path, output_dir, page_ranges, progress_cb=None):
    """拆分PDF，page_ranges: list of (start, end) 1-based页码"""
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
            progress_cb(-1, "错误：PDF文件已损坏或加密，无法读取")
        return False
    total_pages = len(reader.pages)
    base = os.path.splitext(os.path.basename(pdf_path))[0]
    total = len(page_ranges)

    for idx, (start, end) in enumerate(page_ranges):
        if progress_cb:
            progress_cb(int(idx * 90 / max(total, 1)),
                        f"拆分第 {start}-{end} 页…")
        if start > total_pages:
            if progress_cb:
                progress_cb(-1, f"错误：起始页码 {start} 超过总页数 {total_pages}")
            return False
        writer = PdfWriter()
        try:
            for p in range(max(start - 1, 0), min(end, total_pages)):
                writer.add_page(reader.pages[p])
        except IndexError:
            if progress_cb:
                progress_cb(-1, f"错误：页码范围 {start}-{end} 超出文档页数")
            writer.close()
            return False
        suffix = f"_p{start}-{end}" if total > 1 else ""
        out = os.path.join(output_dir, base + suffix + ".pdf")
        try:
            writer.write(out)
        except Exception:
            if progress_cb:
                progress_cb(-1, "错误：无法写入拆分文件，请检查磁盘空间或权限")
            writer.close()
            return False
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
    try:
        img = Image.open(input_path)
    except FileNotFoundError:
        if progress_cb:
            progress_cb(-1, "错误：找不到图片文件")
        return False
    except Exception:
        if progress_cb:
            progress_cb(-1, "错误：无法打开图片，文件可能已损坏")
        return False

    # RGBA → RGB (JPG不支持透明)
    ext = os.path.splitext(output_path)[1].lower()
    try:
        if img.mode == 'RGBA' and ext in ('.jpg', '.jpeg'):
            bg = Image.new('RGB', img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg
        elif img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')
    except Exception:
        if progress_cb:
            progress_cb(-1, "错误：图片格式转换失败")
        img.close()
        return False

    if progress_cb:
        progress_cb(50, "压缩中…")

    # 限制最大分辨率
    if max_size:
        try:
            w, h = img.size
            mw, mh = max_size
            if w > mw or h > mh:
                ratio = min(mw / w, mh / h)
                img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        except Exception:
            if progress_cb:
                progress_cb(-1, "错误：图片缩放失败")
            img.close()
            return False

    save_kw = {}
    if ext in ('.jpg', '.jpeg'):
        save_kw = {'quality': quality, 'optimize': True}
    elif ext == '.png':
        save_kw = {'optimize': True}
    elif ext == '.webp':
        save_kw = {'quality': quality}

    if progress_cb:
        progress_cb(80, "保存…")
    try:
        img.save(output_path, **save_kw)
    except Exception:
        if progress_cb:
            progress_cb(-1, "错误：无法保存压缩图片，请检查磁盘空间或权限")
        img.close()
        return False
    img.close()

    if not os.path.exists(output_path):
        if progress_cb:
            progress_cb(-1, "错误：输出文件未生成")
        return False

    orig = os.path.getsize(input_path)
    new = os.path.getsize(output_path)
    ratio = f"{(1 - new / max(orig, 1)) * 100:.0f}%" if orig > 0 else "0%"
    if progress_cb:
        progress_cb(100, f"压缩完成  节省 {ratio}")
    return True


# ═══════════════════════════════════════════════
#  PDF 批量水印 & 页码
# ═══════════════════════════════════════════════

def pdf_add_watermark(input_path, output_path, text, pos="右下角",
                      opacity=0.3, rotation=0, progress_cb=None):
    import fitz
    if progress_cb: progress_cb(10, "打开PDF...")
    doc = fitz.open(input_path)
    positions = {
        "左上角": (0.05, 0.05), "右上角": (0.65, 0.05),
        "左下角": (0.05, 0.85), "右下角": (0.65, 0.85),
        "居中":   (0.35, 0.45),
    }
    rx, ry = positions.get(pos, (0.65, 0.85))
    total = len(doc)
    for i in range(total):
        if progress_cb: progress_cb(20 + int(70 * i / total), f"添加水印 {i+1}/{total}")
        page = doc[i]
        r = page.rect
        x = r.x0 + r.width * rx
        y = r.y0 + r.height * ry
        annot = page.add_freetext_annot(
            fitz.Rect(x, y, x + r.width * 0.3, y + r.height * 0.1),
            text, fontsize=max(12, r.width / 50), fontname="helv",
            text_color=0.5, fill_color=None, border_width=0,
        )
        annot.set_opacity(opacity)
        if rotation:
            annot.set_rotation(rotation)
        annot.update()
    if progress_cb: progress_cb(95, "保存...")
    doc.save(output_path, deflate=True, garbage=4)
    doc.close()
    if progress_cb: progress_cb(100, "完成")
    return True


def pdf_add_page_numbers(input_path, output_path, start=1, pos="底部居中",
                         fmt="{n}", progress_cb=None):
    import fitz
    if progress_cb: progress_cb(10, "打开PDF...")
    doc = fitz.open(input_path)
    positions = {
        "底部居中": (0.5, 0.95), "底部左对齐": (0.05, 0.95),
        "底部右对齐": (0.85, 0.95), "顶部居中": (0.5, 0.03),
    }
    rx, ry = positions.get(pos, (0.5, 0.95))
    total = len(doc)
    for i in range(total):
        if progress_cb: progress_cb(20 + int(70 * i / total), f"添加页码 {i+1}/{total}")
        page = doc[i]
        r = page.rect
        num = start + i
        text = fmt.replace("{n}", str(num))
        page.insert_text(
            fitz.Point(r.x0 + r.width * rx, r.y0 + r.height * ry),
            text, fontname="helv", fontsize=10, color=(0.4, 0.4, 0.4),
        )
    if progress_cb: progress_cb(95, "保存...")
    doc.save(output_path, deflate=True, garbage=4)
    doc.close()
    if progress_cb: progress_cb(100, "完成")
    return True


# ═══════════════════════════════════════════════
#  批量重命名
# ═══════════════════════════════════════════════
def batch_rename(file_list, pattern, start_num=1, progress_cb=None, output_dir=None,
                 search_text="", replace_text="", case="none",
                 regex_pattern="", regex_replace=""):
    """批量重命名
    pattern 占位符:
      {n}      序号
      {name}   原文件名(不含扩展名)
      {ext}    扩展名
      {date}   修改日期 YYYYMMDD
      {time}   修改时间 HHMMSS
      {folder} 所在文件夹名
    示例: 照片_{n:03d}  →  照片_001.jpg
    output_dir: 自定义输出目录，为None时使用原文件目录
    search_text / replace_text: 查找替换
    regex_pattern / regex_replace: 正则替换（在查找替换之后执行）
    case: none / upper / lower / title
    """
    total = len(file_list)
    renamed = []

    for i, fp in enumerate(file_list):
        if progress_cb:
            progress_cb(int(i * 90 / max(total, 1)), f"重命名 {i+1}/{total}…")
        d = output_dir if output_dir else os.path.dirname(fp)
        name = os.path.splitext(os.path.basename(fp))[0]
        ext = os.path.splitext(fp)[1]
        date_str = ""
        time_str = ""
        folder_str = os.path.basename(os.path.dirname(fp))
        try:
            mtime = os.path.getmtime(fp)
            date_str = __import__('datetime').datetime.fromtimestamp(mtime).strftime("%Y%m%d")
            time_str = __import__('datetime').datetime.fromtimestamp(mtime).strftime("%H%M%S")
        except Exception:
            date_str = "00000000"
            time_str = "000000"

        # 格式化序号
        n = start_num + i
        fmt = pattern.replace("{name}", name).replace("{ext}", ext).replace("{date}", date_str)
        fmt = fmt.replace("{time}", time_str).replace("{folder}", folder_str)
        # 处理 {n:03d} 这种格式
        def _fmt_n(m):
            spec = m.group(1).lstrip(":") if m.group(1) else ""
            if spec:
                return format(n, spec)
            return str(n)
        fmt = re.sub(r'\{n(:.*?)?\}', _fmt_n, fmt)

        new_name = fmt + ext if not fmt.endswith(ext) else fmt

        if search_text:
            new_name = new_name.replace(search_text, replace_text)

        if regex_pattern:
            try:
                new_name = __import__('re').sub(regex_pattern, regex_replace, new_name)
            except Exception:
                pass

        if case == "upper":
            new_name = new_name.upper()
        elif case == "lower":
            new_name = new_name.lower()
        elif case == "title":
            new_name = new_name.title()

        new_path = os.path.join(d, new_name)
        if new_path != fp and not os.path.exists(new_path):
            os.rename(fp, new_path)
            renamed.append((fp, new_path))

    if progress_cb:
        progress_cb(100, f"重命名完成  {len(renamed)} 个文件")
    return renamed
