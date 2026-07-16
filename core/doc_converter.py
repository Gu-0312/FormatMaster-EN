"""文档格式转换"""
import os
import io


class DocumentConverter:
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
            # Word → 其他
            (".docx", ".pdf"): self._docx_to_pdf,
            (".docx", ".txt"): self._docx_to_txt,
            (".docx", ".html"): self._docx_to_html,
            (".doc", ".pdf"): self._docx_to_pdf,
            (".doc", ".txt"): self._docx_to_txt,
            (".doc", ".docx"): self._doc_copy,
            (".docx", ".doc"): self._doc_copy,
            # WPS → 其他
            (".wps", ".docx"): self._doc_copy,
            (".wps", ".pdf"): self._docx_to_pdf,
            (".wps", ".txt"): self._docx_to_txt,
            (".docx", ".wps"): self._doc_copy,
            # Excel → 其他
            (".xlsx", ".pdf"): self._xlsx_to_pdf,
            (".xlsx", ".csv"): self._xlsx_to_csv,
            (".xlsx", ".txt"): self._xlsx_to_txt,
            (".csv", ".xlsx"): self._csv_to_xlsx,
            (".csv", ".txt"): self._doc_copy,
            (".txt", ".xlsx"): self._txt_to_xlsx,
            # PPT → 其他
            (".pptx", ".pdf"): self._pptx_to_pdf,
            (".pptx", ".txt"): self._pptx_to_txt,
            (".pptx", ".jpg"): self._pptx_to_image,
            (".pptx", ".png"): self._pptx_to_image,
            (".ppt", ".pptx"): self._doc_copy,
            (".pptx", ".ppt"): self._doc_copy,
            # WPS演示
            (".dps", ".pptx"): self._doc_copy,
            (".pptx", ".dps"): self._doc_copy,
            # WPS表格
            (".et", ".xlsx"): self._doc_copy,
            (".xlsx", ".et"): self._doc_copy,
            # 图片 → PDF
            (".jpg", ".pdf"): self._image_to_pdf,
            (".jpeg", ".pdf"): self._image_to_pdf,
            (".png", ".pdf"): self._image_to_pdf,
            (".bmp", ".pdf"): self._image_to_pdf,
            (".tiff", ".pdf"): self._image_to_pdf,
            (".webp", ".pdf"): self._image_to_pdf,
            # TXT → PDF
            (".txt", ".pdf"): self._txt_to_pdf,
            # HTML → PDF
            (".html", ".pdf"): self._html_to_pdf,
            (".htm", ".pdf"): self._html_to_pdf,
        }
        return handlers.get(key)

    # ========== PDF 转换 ==========

    def _pdf_to_docx(self, inp, out, cb):
        if cb: cb(20, "解析PDF...")
        from pdf2docx import Converter
        cv = Converter(inp)
        if cb: cb(50, "生成Word...")
        cv.convert(out)
        cv.close()
        return True

    def _pdf_to_txt(self, inp, out, cb):
        import fitz
        doc = fitz.open(inp)
        text = []
        total = len(doc)
        for i, page in enumerate(doc):
            if self._cancel: return False
            text.append(page.get_text())
            if cb:
                cb(20 + int(i * 70 / max(total, 1)), f"读取第{i+1}/{total}页...")
        doc.close()
        with open(out, 'w', encoding='utf-8') as f:
            f.write('\n'.join(text))
        return True

    def _pdf_to_image(self, inp, out, cb):
        import fitz
        doc = fitz.open(inp)
        total = len(doc)
        out_dir = os.path.dirname(out)
        base = os.path.splitext(os.path.basename(out))[0]
        ext = os.path.splitext(out)[1]
        for i, page in enumerate(doc):
            if self._cancel: return False
            pix = page.get_pixmap(dpi=200)
            if total == 1:
                pix.save(out)
            else:
                pix.save(os.path.join(out_dir, f"{base}_{i+1}{ext}"))
            if cb:
                cb(20 + int(i * 70 / max(total, 1)), f"渲染第{i+1}/{total}页...")
        doc.close()
        return True

    def _pdf_to_html(self, inp, out, cb):
        import fitz
        doc = fitz.open(inp)
        if cb: cb(30, "转换中...")
        html_parts = ["<html><head><meta charset='utf-8'></head><body>"]
        for page in doc:
            html_parts.append(page.get_text("html"))
        html_parts.append("</body></html>")
        doc.close()
        with open(out, 'w', encoding='utf-8') as f:
            f.write('\n'.join(html_parts))
        return True

    # ========== Word 转换 ==========

    def _docx_to_pdf(self, inp, out, cb):
        if cb: cb(30, "启动Word...")
        import win32com.client
        import pythoncom

        pythoncom.CoInitialize()
        word = None
        doc = None
        try:
            word = win32com.client.DispatchEx("Word.Application")
            word.Visible = False
            word.DisplayAlerts = 0  # wdAlertsNone

            if cb: cb(50, "打开文档...")
            abs_inp = os.path.abspath(inp)
            abs_out = os.path.abspath(out)
            doc = word.Documents.Open(abs_inp, ReadOnly=True)

            if cb: cb(70, "导出PDF...")
            # 17 = wdExportFormatPDF
            doc.SaveAs2(abs_out, FileFormat=17)
            doc.Close(0)  # wdDoNotSaveChanges
            doc = None
            word.Quit()
            word = None
            return True
        except Exception as e:
            if doc:
                try: doc.Close(0)
                except: pass
            if word:
                try: word.Quit()
                except: pass
            raise e
        finally:
            pythoncom.CoUninitialize()

    def _docx_to_txt(self, inp, out, cb):
        if cb: cb(30, "读取文档...")
        import docx
        doc = docx.Document(inp)
        text = '\n'.join(p.text for p in doc.paragraphs)
        with open(out, 'w', encoding='utf-8') as f:
            f.write(text)
        return True

    def _docx_to_html(self, inp, out, cb):
        if cb: cb(30, "转换中...")
        import docx
        doc = docx.Document(inp)
        html = ['<html><head><meta charset="utf-8"></head><body>']
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                html.append('<br>')
                continue
            tag = 'p'
            if para.style and para.style.name:
                sn = para.style.name.lower()
                if 'heading 1' in sn or '标题 1' in sn: tag = 'h1'
                elif 'heading 2' in sn or '标题 2' in sn: tag = 'h2'
                elif 'heading 3' in sn or '标题 3' in sn: tag = 'h3'
            html.append(f'<{tag}>{text}</{tag}>')
        html.append('</body></html>')
        with open(out, 'w', encoding='utf-8') as f:
            f.write('\n'.join(html))
        return True

    def _doc_copy(self, inp, out, cb):
        if cb: cb(50, "复制转换中...")
        import shutil
        shutil.copy2(inp, out)
        return True

    # ========== Excel 转换 ==========

    def _xlsx_to_pdf(self, inp, out, cb):
        if cb: cb(30, "读取表格...")
        import openpyxl
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
        from reportlab.lib import colors

        wb = openpyxl.load_workbook(inp, data_only=True)
        ws = wb.active
        if cb: cb(50, "生成PDF...")

        data = []
        for row in ws.iter_rows(values_only=True):
            data.append([str(c) if c is not None else '' for c in row])

        if not data:
            data = [['(空表格)']]

        pdf_doc = SimpleDocTemplate(out, pagesize=landscape(A4))
        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.95, 0.95)]),
        ]))
        pdf_doc.build([table])
        return True

    def _xlsx_to_csv(self, inp, out, cb):
        import openpyxl
        wb = openpyxl.load_workbook(inp, data_only=True)
        ws = wb.active
        import csv
        with open(out, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            total = ws.max_row or 1
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if self._cancel: return False
                writer.writerow(row)
                if cb:
                    cb(20 + int(i * 70 / total), f"写入第{i+1}行...")
        return True

    def _xlsx_to_txt(self, inp, out, cb):
        import openpyxl
        wb = openpyxl.load_workbook(inp, data_only=True)
        ws = wb.active
        lines = []
        for row in ws.iter_rows(values_only=True):
            lines.append('\t'.join(str(c) if c is not None else '' for c in row))
        with open(out, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        return True

    def _csv_to_xlsx(self, inp, out, cb):
        import csv
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        with open(inp, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if self._cancel: return False
                ws.append(row)
                if cb and i % 100 == 0:
                    cb(20 + min(70, i // 10), f"写入第{i+1}行...")
        wb.save(out)
        return True

    def _txt_to_xlsx(self, inp, out, cb):
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        with open(inp, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if self._cancel: return False
                parts = line.strip().split('\t')
                if len(parts) == 1:
                    parts = line.strip().split(',')
                ws.append(parts)
                if cb and i % 100 == 0:
                    cb(20 + min(70, i // 10), f"写入第{i+1}行...")
        wb.save(out)
        return True

    # ========== PPT 转换 ==========

    def _pptx_to_pdf(self, inp, out, cb):
        if cb: cb(30, "读取演示文稿...")
        from pptx import Presentation
        from reportlab.lib.pagesizes import landscape, A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet

        prs = Presentation(inp)
        if cb: cb(50, "生成PDF...")
        pdf_doc = SimpleDocTemplate(out, pagesize=landscape(A4))
        styles = getSampleStyleSheet()
        story = []

        for i, slide in enumerate(prs.slides):
            if self._cancel: return False
            story.append(Paragraph(f"--- 幻灯片 {i+1} ---", styles['Heading1']))
            for shape in slide.shapes:
                if hasattr(shape, 'text') and shape.text.strip():
                    safe = shape.text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    story.append(Paragraph(safe, styles['Normal']))
            story.append(Spacer(1, 24))
            if cb:
                cb(50 + int(i * 40 / max(len(prs.slides), 1)), f"幻灯片{i+1}...")

        pdf_doc.build(story)
        return True

    def _pptx_to_txt(self, inp, out, cb):
        from pptx import Presentation
        prs = Presentation(inp)
        text_parts = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, 'text') and shape.text.strip():
                    text_parts.append(shape.text)
        with open(out, 'w', encoding='utf-8') as f:
            f.write('\n\n'.join(text_parts))
        return True

    def _pptx_to_image(self, inp, out, cb):
        from pptx import Presentation
        from PIL import Image, ImageDraw, ImageFont
        prs = Presentation(inp)
        out_dir = os.path.dirname(out)
        base = os.path.splitext(os.path.basename(out))[0]
        ext = os.path.splitext(out)[1]
        total = len(prs.slides)

        for i, slide in enumerate(prs.slides):
            if self._cancel: return False
            img = Image.new('RGB', (1280, 720), 'white')
            draw = ImageDraw.Draw(img)
            y = 50
            for shape in slide.shapes:
                if hasattr(shape, 'text') and shape.text.strip():
                    for line in shape.text.split('\n'):
                        if line.strip():
                            try:
                                font = ImageFont.truetype("msyh.ttc", 18)
                            except Exception:
                                font = ImageFont.load_default()
                            draw.text((60, y), line.strip(), fill='black', font=font)
                            y += 30
                            if y > 680: break
            if total == 1:
                img.save(out)
            else:
                img.save(os.path.join(out_dir, f"{base}_{i+1}{ext}"))
            if cb:
                cb(20 + int(i * 70 / total), f"幻灯片{i+1}/{total}...")
        return True

    # ========== 图片 转 PDF ==========

    def _image_to_pdf(self, inp, out, cb):
        from PIL import Image
        if cb: cb(30, "处理图片...")
        img = Image.open(inp)
        if img.mode == 'RGBA':
            bg = Image.new('RGB', img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        if cb: cb(70, "保存PDF...")
        img.save(out, 'PDF')
        return True

    # ========== TXT → PDF ==========

    def _txt_to_pdf(self, inp, out, cb):
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        font_name = 'SimSun'
        try:
            for fp in ["C:/Windows/Fonts/simsun.ttc", "C:/Windows/Fonts/msyh.ttc"]:
                if os.path.exists(fp):
                    pdfmetrics.registerFont(TTFont(font_name, fp))
                    break
            else:
                font_name = 'Helvetica'
        except Exception:
            font_name = 'Helvetica'

        if cb: cb(30, "读取文本...")
        with open(inp, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        pdf_doc = SimpleDocTemplate(out, pagesize=A4)
        styles = getSampleStyleSheet()
        style = styles['Normal']
        style.fontName = font_name

        story = []
        for line in lines:
            safe = line.rstrip().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            if safe:
                story.append(Paragraph(safe, style))
            else:
                story.append(Spacer(1, 12))

        if cb: cb(70, "生成PDF...")
        pdf_doc.build(story)
        return True

    def _html_to_pdf(self, inp, out, cb):
        if cb: cb(30, "读取HTML...")
        with open(inp, 'r', encoding='utf-8') as f:
            content = f.read()

        # 简单提取文本
        import re
        text = re.sub(r'<[^>]+>', ' ', content)
        text = re.sub(r'\s+', ' ', text).strip()

        with open(out.replace('.pdf', '_temp.txt'), 'w', encoding='utf-8') as f:
            f.write(text)
        result = self._txt_to_pdf(out.replace('.pdf', '_temp.txt'), out, cb)
        try:
            os.remove(out.replace('.pdf', '_temp.txt'))
        except OSError:
            pass
        return result
