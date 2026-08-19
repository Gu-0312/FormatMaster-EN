"""文档格式转换"""
import os
import re
import io

from core.doc_pdf import DocPdfMixin
from core.doc_word import DocWordMixin
from core.doc_excel import DocExcelMixin
from core.doc_misc import DocMiscMixin


class DocumentConverter(DocPdfMixin, DocWordMixin, DocExcelMixin, DocMiscMixin):
    def __init__(self):
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def convert(self, input_path, output_path, progress_callback=None):
        self._cancel = False
        ext = os.path.splitext(input_path)[1].lower()
        out_ext = os.path.splitext(output_path)[1].lower()

        if progress_callback:
            progress_callback(10, "正在转换...")

        try:
            handler = self._get_handler(ext, out_ext)
            if handler is None:
                if progress_callback:
                    progress_callback(-1, f"不支持 {ext} → {out_ext} 转换")
                return False

            result = handler(input_path, output_path, progress_callback)

            if result and os.path.exists(output_path):
                if progress_callback:
                    progress_callback(100, "转换完成")
                return True
            else:
                if progress_callback:
                    progress_callback(-1, "转换失败：输出文件未生成")
                return False

        except Exception as e:
            if progress_callback:
                progress_callback(-1, f"错误: {str(e)[:200]}")
            return False

    def _get_handler(self, in_ext, out_ext):
        key = (in_ext, out_ext)
        handlers = {
            # PDF → 其他
            (".pdf", ".docx"): self._pdf_to_docx,
            (".pdf", ".doc"): self._pdf_to_docx,
            (".pdf", ".txt"): self._pdf_to_txt,
            (".pdf", ".jpg"): self._pdf_to_image,
            (".pdf", ".jpeg"): self._pdf_to_image,
            (".pdf", ".png"): self._pdf_to_image,
            (".pdf", ".html"): self._pdf_to_html,
            (".pdf", ".pptx"): self._pdf_to_pptx,
            (".pdf", ".xlsx"): self._pdf_to_xlsx,
            # Word → 其他
            (".docx", ".pdf"): self._docx_to_pdf,
            (".docx", ".txt"): self._docx_to_txt,
            (".docx", ".html"): self._docx_to_html,
            (".docx", ".jpg"): self._docx_to_image,
            (".docx", ".png"): self._docx_to_image,
            (".docx", ".pptx"): self._docx_to_pptx,
            (".docx", ".md"): self._docx_to_md,
            (".doc", ".pdf"): self._docx_to_pdf,
            (".doc", ".txt"): self._docx_to_txt,
            (".doc", ".docx"): self._doc_copy,
            (".docx", ".doc"): self._doc_copy,
            (".doc", ".md"): self._docx_to_md,
            (".doc", ".html"): self._docx_to_html,
            # WPS → 其他
            (".wps", ".docx"): self._doc_copy,
            (".wps", ".pdf"): self._docx_to_pdf,
            (".wps", ".txt"): self._docx_to_txt,
            (".docx", ".wps"): self._doc_copy,
            (".wps", ".html"): self._docx_to_html,
            (".wps", ".md"): self._docx_to_md,
            # Excel → 其他
            (".xlsx", ".pdf"): self._xlsx_to_pdf,
            (".xlsx", ".csv"): self._xlsx_to_csv,
            (".xlsx", ".txt"): self._xlsx_to_txt,
            (".xlsx", ".jpg"): self._xlsx_to_image,
            (".xlsx", ".png"): self._xlsx_to_image,
            (".xlsx", ".html"): self._xlsx_to_html,
            (".xlsx", ".md"): self._xlsx_to_md,
            (".xls", ".xlsx"): self._xls_to_xlsx,
            (".xls", ".pdf"): self._xls_to_pdf,
            (".xls", ".csv"): self._xls_to_csv,
            (".xls", ".txt"): self._xls_to_txt,
            (".xls", ".jpg"): self._xls_to_image,
            (".xls", ".png"): self._xls_to_image,
            (".xls", ".html"): self._xls_to_html,
            (".xls", ".md"): self._xls_to_md,
            (".csv", ".xlsx"): self._csv_to_xlsx,
            (".csv", ".pdf"): self._csv_to_pdf,
            (".csv", ".txt"): self._doc_copy,
            (".csv", ".html"): self._csv_to_html,
            (".csv", ".md"): self._csv_to_md,
            (".txt", ".xlsx"): self._txt_to_xlsx,
            (".txt", ".docx"): self._txt_to_docx,
            (".txt", ".pptx"): self._txt_to_pptx,
            (".txt", ".pdf"): self._txt_to_pdf,
            (".txt", ".html"): self._txt_to_html,
            (".txt", ".md"): self._txt_to_md,
            # PPT → 其他
            (".pptx", ".pdf"): self._pptx_to_pdf,
            (".pptx", ".txt"): self._pptx_to_txt,
            (".pptx", ".jpg"): self._pptx_to_image,
            (".pptx", ".png"): self._pptx_to_image,
            (".pptx", ".docx"): self._pptx_to_docx,
            (".pptx", ".html"): self._pptx_to_html,
            (".pptx", ".md"): self._pptx_to_md,
            (".ppt", ".pptx"): self._doc_copy,
            (".ppt", ".pdf"): self._ppt_to_pdf,
            (".ppt", ".txt"): self._ppt_to_txt,
            (".pptx", ".ppt"): self._doc_copy,
            # WPS演示
            (".dps", ".pptx"): self._doc_copy,
            (".pptx", ".dps"): self._doc_copy,
            (".dps", ".pdf"): self._pptx_to_pdf,
            (".dps", ".txt"): self._pptx_to_txt,
            # WPS表格
            (".et", ".xlsx"): self._doc_copy,
            (".xlsx", ".et"): self._doc_copy,
            (".et", ".pdf"): self._xlsx_to_pdf,
            (".et", ".csv"): self._xlsx_to_csv,
            # 图片 → 文档
            (".jpg", ".pdf"): self._image_to_pdf,
            (".jpeg", ".pdf"): self._image_to_pdf,
            (".png", ".pdf"): self._image_to_pdf,
            (".bmp", ".pdf"): self._image_to_pdf,
            (".tiff", ".pdf"): self._image_to_pdf,
            (".webp", ".pdf"): self._image_to_pdf,
            (".jpg", ".docx"): self._image_to_docx,
            (".jpeg", ".docx"): self._image_to_docx,
            (".png", ".docx"): self._image_to_docx,
            (".bmp", ".docx"): self._image_to_docx,
            # HTML → 其他
            (".html", ".pdf"): self._html_to_pdf,
            (".htm", ".pdf"): self._html_to_pdf,
            (".html", ".docx"): self._html_to_docx,
            (".htm", ".docx"): self._html_to_docx,
            (".html", ".txt"): self._html_to_txt,
            (".htm", ".txt"): self._html_to_txt,
            (".html", ".md"): self._html_to_md,
            (".htm", ".md"): self._html_to_md,
            (".html", ".xlsx"): self._html_to_xlsx,
            (".htm", ".xlsx"): self._html_to_xlsx,
            # Markdown → 其他
            (".md", ".html"): self._md_to_html,
            (".md", ".pdf"): self._md_to_pdf,
            (".md", ".docx"): self._md_to_docx,
            (".md", ".txt"): self._md_to_txt,
            # EPUB → 其他
            (".epub", ".pdf"): self._epub_to_pdf,
            (".epub", ".txt"): self._epub_to_txt,
            (".epub", ".html"): self._epub_to_html,
            (".epub", ".docx"): self._epub_to_docx,
            # RTF → 其他
            (".rtf", ".txt"): self._rtf_to_txt,
            (".rtf", ".pdf"): self._rtf_to_pdf,
            (".rtf", ".docx"): self._rtf_to_docx,
            # ODT → 其他
            (".odt", ".pdf"): self._odt_to_pdf,
            (".odt", ".docx"): self._odt_to_docx,
            (".odt", ".txt"): self._odt_to_txt,
            # OFD → PDF
            (".ofd", ".pdf"): self._ofd_to_pdf,
            # Word ↔ Excel
            (".docx", ".xlsx"): self._docx_to_xlsx,
            (".xlsx", ".docx"): self._xlsx_to_docx,
        }
        return handlers.get(key)

    # ========== 工具方法 ==========

    def _read_text(self, path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            import chardet
            with open(path, 'rb') as f:
                raw = f.read()
            enc = chardet.detect(raw).get("encoding", "utf-8") or "utf-8"
            return raw.decode(enc, errors="replace")

    def _write_text(self, path, text):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)

    def _make_table_data(self, ws):
        data = []
        for row in ws.iter_rows(values_only=True):
            data.append([str(c) if c is not None else '' for c in row])
        if not data:
            data = [['(空表格)']]
        return data

    def _safe_html(self, text):
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    def _build_html_page(self, body):
        return f"<html><head><meta charset='utf-8'></head><body>{body}</body></html>"

    # ========== EPUB 工具 ==========

    def _read_epub(self, inp):
        """按 spine 顺序读取 EPUB 章节（标准库 zipfile + lxml，无需 ebooklib）。

        返回 [(filename, bytes)]；OPF/spine 解析失败时按文件名排序兜底。
        """
        import zipfile
        from lxml import etree
        with zipfile.ZipFile(inp) as z:
            names = z.namelist()
            # 1) container.xml → OPF 路径
            opf = None
            try:
                container = z.read("META-INF/container.xml")
                root = etree.fromstring(container)
                for el in root.iter():
                    if el.tag.rsplit("}", 1)[-1] == "rootfile":
                        opf = el.get("full-path")
                        break
            except Exception:  # noqa: BLE001
                opf = None
            # 2) OPF → manifest(id→href) + spine(idref 顺序)
            order = []
            if opf:
                try:
                    opf_root = etree.fromstring(z.read(opf))
                    manifest = {}
                    for el in opf_root.iter():
                        tag = el.tag.rsplit("}", 1)[-1]
                        if tag == "item":
                            manifest[el.get("id")] = el.get("href")
                        elif tag == "itemref":
                            ref = el.get("idref")
                            if ref and ref in manifest and manifest[ref]:
                                order.append(manifest[ref])
                except Exception:  # noqa: BLE001
                    order = []
            # 3) 收集 XHTML 文件
            picked = [n for n in names
                      if n.lower().endswith((".xhtml", ".html", ".htm"))
                      and not n.startswith("META-INF")]
            if order:
                def _key(n):
                    base = n.rsplit("/", 1)[-1]
                    for i, h in enumerate(order):
                        hb = h.rsplit("/", 1)[-1]
                        if n == h or base == hb or n.endswith(h):
                            return i
                    return len(order)
                picked.sort(key=_key)
            else:
                picked.sort(key=lambda n: n.lower())
            out = []
            for n in picked:
                try:
                    out.append((n, z.read(n)))
                except Exception:  # noqa: BLE001
                    continue
            return out
