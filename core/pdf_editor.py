"""PDF 可视化编辑器核心引擎"""
from typing import Optional
from PIL import Image
from PIL import ImageTk


class PdfEditor:
    MAX_UNDO = 20
    THUMB_CACHE_MAX = 200
    THUMB_SIZE = (150, 200)

    def __init__(self):
        self._doc = None
        self._path = None
        self._page_order = []
        self._undo_stack = []
        self._thumb_cache = {}
        self._thumb_access = []
        self._modified = False
        self._closed = False

    def open(self, path: str) -> bool:
        import fitz
        try:
            doc = fitz.open(path)
        except Exception as e:
            raise RuntimeError(f"无法打开 PDF：{e}")
        if doc.needs_pass:
            doc.close()
            raise RuntimeError("文件已加密，请先解密")
        self._close_doc()
        self._doc = doc
        self._path = path
        self._page_order = list(range(len(doc)))
        self._undo_stack = []
        self._thumb_cache = {}
        self._thumb_access = []
        self._modified = False
        self._closed = False
        return True

    def save(self, path: str) -> bool:
        import fitz
        if not self._doc:
            raise RuntimeError("没有打开的文档")
        try:
            new_doc = fitz.open()
            for idx in self._page_order:
                new_doc.insert_pdf(self._doc, from_page=idx, to_page=idx)
            new_doc.save(path, deflate=True, garbage=4)
            new_doc.close()
            self._path = path
            self._modified = False
            return True
        except Exception as e:
            raise RuntimeError(f"保存失败：{e}")

    def close(self):
        self._close_doc()
        self._closed = True

    def _close_doc(self):
        if self._doc:
            try:
                self._doc.close()
            except Exception:
                pass
        self._doc = None
        self._path = None
        self._page_order = []
        self._undo_stack = []
        self._thumb_cache = {}
        self._thumb_access = []

    @property
    def page_count(self) -> int:
        return len(self._page_order) if self._doc else 0

    @property
    def metadata(self) -> dict:
        if not self._doc:
            return {}
        return {
            "title": self._doc.metadata.get("title", ""),
            "author": self._doc.metadata.get("author", ""),
            "subject": self._doc.metadata.get("subject", ""),
            "keywords": self._doc.metadata.get("keywords", ""),
        }

    @property
    def modified(self) -> bool:
        return self._modified

    @property
    def file_path(self) -> Optional[str]:
        return self._path

    def get_thumbnail(self, page_num: int) -> Optional[ImageTk.PhotoImage]:
        if not self._doc or page_num < 0 or page_num >= self.page_count:
            return None
        real_idx = self._page_order[page_num]
        if real_idx in self._thumb_cache:
            self._thumb_access.remove(real_idx)
            self._thumb_access.append(real_idx)
            return self._thumb_cache[real_idx]
        self._ensure_thumb(real_idx)
        return self._thumb_cache.get(real_idx)

    def _ensure_thumb(self, real_idx: int):
        import fitz
        page = self._doc[real_idx]
        w, h = self.THUMB_SIZE
        zoom = min(w / page.rect.width, h / page.rect.height)
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        tk_img = ImageTk.PhotoImage(img)
        if len(self._thumb_cache) >= self.THUMB_CACHE_MAX:
            oldest = self._thumb_access.pop(0)
            self._thumb_cache.pop(oldest, None)
        self._thumb_cache[real_idx] = tk_img
        self._thumb_access.append(real_idx)

    def _clear_thumb_cache(self):
        self._thumb_cache.clear()
        self._thumb_access = []

    def reorder_pages(self, new_order: list[int]) -> bool:
        if not self._doc:
            return False
        if sorted(new_order) != list(range(len(new_order))):
            return False
        self._snapshot()
        self._page_order = [self._page_order[i] for i in new_order]
        self._modified = True
        self._clear_thumb_cache()
        return True

    def delete_pages(self, indices: list[int]) -> bool:
        if not self._doc:
            return False
        sorted_idx = sorted(set(indices), reverse=True)
        if sorted_idx and (sorted_idx[0] >= self.page_count or sorted_idx[-1] < 0):
            return False
        self._snapshot()
        for i in sorted_idx:
            if 0 <= i < len(self._page_order):
                real_idx = self._page_order[i]
                self._doc.delete_page(real_idx)
                self._page_order.pop(i)
                self._page_order = [r if r < real_idx else r - 1 for r in self._page_order]
        self._modified = True
        self._clear_thumb_cache()
        return True

    def insert_pdf(self, at_index: int, pdf_path: str) -> bool:
        import fitz
        if not self._doc:
            return False
        if at_index < 0 or at_index > self.page_count:
            at_index = self.page_count
        try:
            src = fitz.open(pdf_path)
        except Exception:
            return False
        self._snapshot()
        new_indices = []
        for i in range(len(src)):
            self._doc.insert_pdf(src, from_page=i, to_page=i,
                                 start_at=len(self._doc) - 1)
            new_indices.append(len(self._doc) - 1)
        src.close()
        self._page_order = (self._page_order[:at_index] +
                            new_indices +
                            self._page_order[at_index:])
        self._modified = True
        self._clear_thumb_cache()
        return True

    def insert_image(self, at_index: int, img_path: str) -> bool:
        import fitz
        if not self._doc:
            return False
        if at_index < 0 or at_index > self.page_count:
            at_index = self.page_count
        try:
            from PIL import Image as PILImage
            pil_img = PILImage.open(img_path)
            if pil_img.mode != "RGB":
                pil_img = pil_img.convert("RGB")
            img_bytes = pil_img.tobytes("jpeg", "RGB")
            rect = fitz.Rect(0, 0, pil_img.width, pil_img.height)
            page = self._doc.new_page(width=pil_img.width, height=pil_img.height)
            page.insert_image(rect, stream=img_bytes)
        except Exception:
            img = fitz.Pixmap(img_path)
            page = self._doc.new_page(width=img.width, height=img.height)
            page.insert_image(fitz.Rect(0, 0, img.width, img.height), pixmap=img)
        self._snapshot()
        new_idx = len(self._doc) - 1
        self._page_order.insert(at_index, new_idx)
        self._modified = True
        self._clear_thumb_cache()
        return True

    def rotate_pages(self, indices: list[int], angle: int) -> bool:
        if not self._doc:
            return False
        if angle not in (90, 180, 270):
            return False
        self._snapshot()
        for i in indices:
            if 0 <= i < len(self._page_order):
                real_idx = self._page_order[i]
                page = self._doc[real_idx]
                page.set_rotation((page.rotation or 0) + angle)
        self._modified = True
        self._clear_thumb_cache()
        return True

    def duplicate_pages(self, indices: list[int], at_index: int) -> bool:
        import fitz
        if not self._doc:
            return False
        if at_index < 0 or at_index > self.page_count:
            at_index = self.page_count
        self._snapshot()
        new_indices = []
        for i in sorted(indices):
            if 0 <= i < len(self._page_order):
                real_idx = self._page_order[i]
                tmp = fitz.open()
                tmp.insert_pdf(self._doc, from_page=real_idx, to_page=real_idx)
                self._doc.insert_pdf(tmp, from_page=0, to_page=0,
                                     start_at=len(self._doc) - 1)
                tmp.close()
                new_indices.append(len(self._doc) - 1)
        self._page_order = (self._page_order[:at_index] +
                            new_indices +
                            self._page_order[at_index:])
        self._modified = True
        self._clear_thumb_cache()
        return True

    def insert_blank(self, at_index: int, width: int = 595, height: int = 842) -> bool:
        import fitz
        if not self._doc:
            return False
        if at_index < 0 or at_index > self.page_count:
            at_index = self.page_count
        self._snapshot()
        self._doc.new_page(width=width, height=height)
        new_idx = len(self._doc) - 1
        self._page_order.insert(at_index, new_idx)
        self._modified = True
        self._clear_thumb_cache()
        return True

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        desc, prev_order = self._undo_stack.pop()
        self._page_order = prev_order
        self._modified = len(self._undo_stack) > 0
        self._clear_thumb_cache()
        return True

    def _snapshot(self):
        self._undo_stack.append(("page_op", list(self._page_order)))
        if len(self._undo_stack) > self.MAX_UNDO:
            self._undo_stack.pop(0)

    def add_watermark(self, text: str, pos: str = "右下角",
                      opacity: float = 0.3, rotation: int = 0) -> bool:
        import fitz
        if not self._doc or not text:
            return False
        positions = {
            "左上角": (0.05, 0.05),
            "右上角": (0.65, 0.05),
            "左下角": (0.05, 0.85),
            "右下角": (0.65, 0.85),
            "居中":   (0.35, 0.45),
        }
        rx, ry = positions.get(pos, (0.65, 0.85))
        self._snapshot()
        for real_idx in self._page_order:
            page = self._doc[real_idx]
            r = page.rect
            x = r.x0 + r.width * rx
            y = r.y0 + r.height * ry
            annot = page.add_freetext_annot(
                fitz.Rect(x, y, x + r.width * 0.3, y + r.height * 0.1),
                text,
                fontsize=max(12, r.width / 50),
                fontname="helv",
                text_color=0.5,
                fill_color=None,
                border_width=0,
            )
            annot.set_opacity(opacity)
            if rotation:
                annot.set_rotation(rotation)
            annot.update()
        self._modified = True
        return True

    def add_page_numbers(self, start: int = 1, pos: str = "底部居中",
                         fmt: str = "{n}") -> bool:
        import fitz
        if not self._doc:
            return False
        positions = {
            "底部居中": (0.5, 0.95),
            "底部左对齐": (0.05, 0.95),
            "底部右对齐": (0.85, 0.95),
            "顶部居中": (0.5, 0.03),
        }
        rx, ry = positions.get(pos, (0.5, 0.95))
        self._snapshot()
        for i, real_idx in enumerate(self._page_order):
            page = self._doc[real_idx]
            r = page.rect
            num = start + i
            text = fmt.replace("{n}", str(num))
            page.insert_text(
                fitz.Point(r.x0 + r.width * rx, r.y0 + r.height * ry),
                text,
                fontname="helv",
                fontsize=10,
                color=(0.4, 0.4, 0.4),
            )
        self._modified = True
        return True

    def set_metadata(self, meta: dict) -> bool:
        if not self._doc:
            return False
        md = self._doc.metadata
        for k in ("title", "author", "subject", "keywords"):
            if k in meta:
                md[k] = meta[k]
        self._doc.set_metadata(md)
        self._modified = True
        return True

    def crop_pages(self, indices: list[int], margin: tuple) -> bool:
        import fitz
        if not self._doc:
            return False
        left, top, right, bottom = margin
        self._snapshot()
        for i in indices:
            if 0 <= i < len(self._page_order):
                real_idx = self._page_order[i]
                page = self._doc[real_idx]
                r = page.rect
                new_rect = fitz.Rect(
                    r.x0 + left, r.y0 + top,
                    r.x0 + r.width - right, r.y0 + r.height - bottom
                )
                page.set_cropbox(new_rect)
        self._modified = True
        self._clear_thumb_cache()
        return True
