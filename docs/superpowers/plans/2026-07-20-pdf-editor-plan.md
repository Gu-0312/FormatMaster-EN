# PDF 编辑器实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为格式大师增加可视化 PDF 编辑器，支持缩略图预览、页面 CRUD（增删改排旋转复制）、拖拽排序、水印、页码编号和元数据编辑。

**Architecture:** 新建 `core/pdf_editor.py` 封装 PyMuPDF 核心操作，新建 `gui/pdf_editor_panel.py` 封装 UI 面板，在 `main.py` 的 PDF 面板模式选择器中新增"编辑器"模式进行集成。

**Tech Stack:** Python 3.11+, PyMuPDF (fitz), Pillow, tkinter Canvas

---

## 文件结构

| 文件 | 操作 | 职责 |
|---|---|---|
| `core/pdf_editor.py` | 创建 | PDF 编辑器引擎：打开/保存/缩略图/页面 CRUD/水印/元数据/撤销 |
| `gui/pdf_editor_panel.py` | 创建 | 编辑器 UI 面板：缩略图 Canvas、工具栏、交互事件、状态栏 |
| `main.py` | 修改 | 在 `_p_pdf()` 中新增"编辑器"模式分支，集成 PdfEditorPanel |

---

### Task 1: 创建 core/pdf_editor.py — 核心引擎

**Files:**
- Create: `core/pdf_editor.py`

- [ ] **Step 1: 创建 PdfEditor 类骨架**

```python
"""PDF 编辑器核心引擎"""
import os
from typing import Optional


class PdfEditor:
    """PDF 编辑器核心引擎，封装 PyMuPDF 操作"""

    MAX_UNDO = 20
    THUMB_CACHE_MAX = 200
    THUMB_SIZE = (150, 200)

    def __init__(self):
        self._doc = None
        self._path = None
        self._page_order = []       # list[int] — 当前页面顺序（索引指向 doc）
        self._undo_stack = []       # list[(description, list[int])]
        self._thumb_cache = {}      # dict[int, PhotoImage]
        self._thumb_access = []     # LRU tracking
        self._modified = False
        self._closed = False

    # === 生命周期 ===
    def open(self, path: str) -> bool: ...
    def save(self, path: str) -> bool: ...
    def close(self): ...

    # === 只读属性 ===
    @property
    def page_count(self) -> int: ...
    @property
    def metadata(self) -> dict: ...
    @property
    def modified(self) -> bool: ...
    @property
    def file_path(self) -> Optional[str]: ...

    # === 缩略图 ===
    def get_thumbnail(self, page_num: int) -> Optional[object]: ...

    # === 页面操作 ===
    def reorder_pages(self, new_order: list[int]) -> bool: ...
    def delete_pages(self, indices: list[int]) -> bool: ...
    def insert_pdf(self, at_index: int, pdf_path: str) -> bool: ...
    def insert_image(self, at_index: int, img_path: str) -> bool: ...
    def rotate_pages(self, indices: list[int], angle: int) -> bool: ...
    def duplicate_pages(self, indices: list[int], at_index: int) -> bool: ...
    def insert_blank(self, at_index: int, width: int = 595, height: int = 842) -> bool: ...

    # === 增强操作 ===
    def add_watermark(self, text: str, pos: str = "右下角",
                      opacity: float = 0.3, rotation: int = 0) -> bool: ...
    def add_page_numbers(self, start: int = 1, pos: str = "底部居中",
                         fmt: str = "{n}") -> bool: ...
    def set_metadata(self, meta: dict) -> bool: ...
    def crop_pages(self, indices: list[int], margin: tuple) -> bool: ...

    # === 撤销 ===
    def undo(self) -> bool: ...

    # === 内部 ===
    def _snapshot(self): ...
    def _ensure_thumb(self, idx: int): ...
    def _clear_thumb_cache(self): ...
```

- [ ] **Step 2: 实现生命周期方法**

```python
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

def close(self):
    self._close_doc()
    self._closed = True

def save(self, path: str) -> bool:
    import fitz
    if not self._doc:
        raise RuntimeError("没有打开的文档")
    try:
        # 构建页面顺序：按 self._page_order 重新排列
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
```

- [ ] **Step 3: 实现缩略图生成与缓存**

```python
def get_thumbnail(self, page_num: int) -> Optional[object]:
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
    from PIL import Image
    from tkinter import ImageTk
    page = self._doc[real_idx]
    w, h = self.THUMB_SIZE
    zoom = min(w / page.rect.width, h / page.rect.height)
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    tk_img = ImageTk.PhotoImage(img)
    # LRU cache management
    if len(self._thumb_cache) >= self.THUMB_CACHE_MAX:
        oldest = self._thumb_access.pop(0)
        self._thumb_cache.pop(oldest, None)
    self._thumb_cache[real_idx] = tk_img
    self._thumb_access.append(real_idx)

def _clear_thumb_cache(self):
    self._thumb_cache.clear()
    self._thumb_access = []
```

- [ ] **Step 4: 实现页面操作（带快照）**

```python
def _snapshot(self):
    self._undo_stack.append(("page_op", list(self._page_order)))
    if len(self._undo_stack) > self.MAX_UNDO:
        self._undo_stack.pop(0)

def reorder_pages(self, new_order: list[int]) -> bool:
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
            # 调整 page_order 中大于 real_idx 的索引
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
        # Create temp PDF page from image
        img_bytes = pil_img.tobytes("jpeg", "RGB")
        rect = fitz.Rect(0, 0, pil_img.width, pil_img.height)
        page = self._doc.new_page(width=pil_img.width, height=pil_img.height)
        page.insert_image(rect, stream=img_bytes)
    except Exception:
        import fitz
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
    if not self._doc:
        return False
    if at_index < 0 or at_index > self.page_count:
        at_index = self.page_count
    self._snapshot()
    new_indices = []
    for i in sorted(indices):
        if 0 <= i < len(self._page_order):
            real_idx = self._page_order[i]
            self._doc.insert_pdf(self._doc, from_page=real_idx, to_page=real_idx,
                                 start_at=len(self._doc) - 1)
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
```

- [ ] **Step 5: 实现撤销**

```python
def undo(self) -> bool:
    if not self._undo_stack:
        return False
    desc, prev_order = self._undo_stack.pop()
    self._page_order = prev_order
    self._modified = len(self._undo_stack) > 0
    self._clear_thumb_cache()
    return True
```

- [ ] **Step 6: 实现增强操作（水印/页码/元数据）**

```python
def add_watermark(self, text: str, pos: str = "右下角",
                  opacity: float = 0.3, rotation: int = 0) -> bool:
    import fitz
    if not self._doc or not text:
        return False
    positions = {
        "左上角": (fitz.PDF_ANNOT_SQUARE, 0.05, 0.05),
        "右上角": (fitz.PDF_ANNOT_SQUARE, 0.65, 0.05),
        "左下角": (fitz.PDF_ANNOT_SQUARE, 0.05, 0.85),
        "右下角": (fitz.PDF_ANNOT_SQUARE, 0.65, 0.85),
        "居中":   (fitz.PDF_ANNOT_SQUARE, 0.35, 0.45),
    }
    annot_type, rx, ry = positions.get(pos, (fitz.PDF_ANNOT_SQUARE, 0.65, 0.85))
    self._snapshot()
    for i, real_idx in enumerate(self._page_order):
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
        "底部居中": (0.5, 0.95, fitz.TEXT_ALIGN_CENTER),
        "底部左对齐": (0.05, 0.95, fitz.TEXT_ALIGN_LEFT),
        "底部右对齐": (0.85, 0.95, fitz.TEXT_ALIGN_RIGHT),
        "顶部居中": (0.5, 0.03, fitz.TEXT_ALIGN_CENTER),
    }
    rx, ry, align = positions.get(pos, (0.5, 0.95, fitz.TEXT_ALIGN_CENTER))
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
```

- [ ] **Step 7: 验证文件可导入**

Run: `python -c "from core.pdf_editor import PdfEditor; print('OK')"`
Expected: `OK`

---

### Task 2: 创建 gui/pdf_editor_panel.py — UI 面板

**Files:**
- Create: `gui/pdf_editor_panel.py`

- [ ] **Step 1: 创建 PdfEditorPanel 类骨架**

```python
"""PDF 编辑器 UI 面板"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os

from core.pdf_editor import PdfEditor


class PdfEditorPanel:
    """PDF 编辑器可视化面板"""

    THUMB_W = 150
    THUMB_H = 200
    PADDING = 10
    COLUMNS = 4

    def __init__(self, parent, log_func=None, task_callback=None):
        self.parent = parent
        self.log = log_func or (lambda *a: None)
        self.task_cb = task_callback
        self.editor = PdfEditor()
        self.selected = set()
        self.drag_data = None

        self._build_ui()

    def _build_ui(self):
        """构建编辑器 UI"""
        # 顶部栏：打开/保存/另存为
        top = tk.Frame(self.parent, bg="#F5F6FA")
        top.pack(fill=tk.X, padx=16, pady=(10, 4))

        tk.Button(top, text="📂 打开", command=self._open_file,
                  bg="#FFFFFF", fg="#1A1A2E", font=("Microsoft YaHei UI", 10, "bold"),
                  relief="solid", bd=1, padx=16, pady=4, cursor="hand2").pack(side=tk.LEFT, padx=2)
        tk.Button(top, text="💾 保存", command=self._save_file,
                  bg="#FFFFFF", fg="#1A1A2E", font=("Microsoft YaHei UI", 10, "bold"),
                  relief="solid", bd=1, padx=16, pady=4, cursor="hand2").pack(side=tk.LEFT, padx=2)
        tk.Button(top, text="📝 另存为", command=self._save_as,
                  bg="#FFFFFF", fg="#1A1A2E", font=("Microsoft YaHei UI", 10, "bold"),
                  relief="solid", bd=1, padx=16, pady=4, cursor="hand2").pack(side=tk.LEFT, padx=2)

        self._info_label = tk.Label(top, text="未打开文件", bg="#F5F6FA",
                                    fg="#9CA3AF", font=("Microsoft YaHei UI", 9))
        self._info_label.pack(side=tk.RIGHT, padx=8)

        # 工具栏
        toolbar = tk.Frame(self.parent, bg="#FFFFFF", highlightbackground="#E5E7EB",
                           highlightthickness=1)
        toolbar.pack(fill=tk.X, padx=16, pady=4)

        tools = [
            ("↻ 旋转", self._rotate_90),
            ("✕ 删除", self._delete_selected),
            ("➕ 插入PDF", self._insert_pdf),
            ("🖼 插入图片", self._insert_image),
            ("📄 复制", self._duplicate_selected),
            ("⬜ 空白页", self._insert_blank),
            ("🔤 水印", self._add_watermark),
            ("# 页码", self._add_page_numbers),
            ("📋 元数据", self._edit_metadata),
            ("↩ 撤销", self._undo),
        ]
        for text, cmd in tools:
            tk.Button(toolbar, text=text, command=cmd,
                      bg="#FFFFFF", fg="#1A1A2E",
                      font=("Microsoft YaHei UI", 9),
                      relief="flat", padx=10, pady=4, cursor="hand2").pack(side=tk.LEFT, padx=1)

        # 选中操作区
        sel_frame = tk.Frame(toolbar, bg="#FFFFFF")
        sel_frame.pack(side=tk.RIGHT, padx=4)
        tk.Button(sel_frame, text="☐ 全选", command=self._toggle_select_all,
                  bg="#FFFFFF", fg="#6B7280",
                  font=("Microsoft YaHei UI", 9),
                  relief="flat", padx=8, pady=4, cursor="hand2").pack(side=tk.LEFT)
        tk.Button(sel_frame, text="☐ 反选", command=self._invert_selection,
                  bg="#FFFFFF", fg="#6B7280",
                  font=("Microsoft YaHei UI", 9),
                  relief="flat", padx=8, pady=4, cursor="hand2").pack(side=tk.LEFT)

        # 缩略图画布 + 滚动
        canvas_frame = tk.Frame(self.parent, bg="#F5F6FA")
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=4)

        h_scroll = tk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL)
        v_scroll = tk.Scrollbar(canvas_frame, orient=tk.VERTICAL)

        self.canvas = tk.Canvas(canvas_frame, bg="#F5F6FA",
                                highlightthickness=0,
                                xscrollcommand=h_scroll.set,
                                yscrollcommand=v_scroll.set)
        h_scroll.config(command=self.canvas.xview)
        v_scroll.config(command=self.canvas.yview)

        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_drop)

        # 状态栏
        self._status_bar = tk.Frame(self.parent, bg="#FFFFFF",
                                    highlightbackground="#E5E7EB",
                                    highlightthickness=1)
        self._status_bar.pack(fill=tk.X, padx=16, pady=(0, 8))

        self._status_label = tk.Label(self._status_bar, text="就绪",
                                      bg="#FFFFFF", fg="#6B7280",
                                      font=("Microsoft YaHei UI", 9))
        self._status_label.pack(side=tk.LEFT, padx=12, pady=4)

        self._thumb_frame = None  # 用于存储缩略图引用防止GC
        self._thumb_ids = {}     # canvas item id -> page_num
        self._page_items = {}    # page_num -> canvas item id
```

- [ ] **Step 2: 实现文件打开/保存**

```python
def _open_file(self):
    path = filedialog.askopenfilename(
        title="选择PDF文件",
        filetypes=[("PDF文件", "*.pdf"), ("所有文件", "*.*")]
    )
    if not path:
        return
    try:
        self.editor.open(path)
        self.selected.clear()
        self._render_thumbnails()
        self._update_status()
        self.log(f"已打开：{os.path.basename(path)} ({self.editor.page_count} 页)", "success")
    except RuntimeError as e:
        messagebox.showerror("打开失败", str(e))
        self.log(f"打开失败：{e}", "error")

def _save_file(self):
    if not self.editor.file_path:
        self._save_as()
        return
    try:
        self.editor.save(self.editor.file_path)
        self._update_status()
        self.log("保存成功", "success")
    except RuntimeError as e:
        messagebox.showerror("保存失败", str(e))

def _save_as(self):
    if not self.editor.page_count:
        return
    path = filedialog.asksaveasfilename(
        title="另存为",
        defaultextension=".pdf",
        filetypes=[("PDF文件", "*.pdf")]
    )
    if not path:
        return
    try:
        self.editor.save(path)
        self._update_status()
        self.log(f"已保存至：{os.path.basename(path)}", "success")
    except RuntimeError as e:
        messagebox.showerror("保存失败", str(e))
```

- [ ] **Step 3: 实现缩略图渲染**

```python
def _render_thumbnails(self):
    self.canvas.delete("thumb")
    self._thumb_ids.clear()
    self._page_items.clear()
    self._thumb_frame = []  # keep references

    n = self.editor.page_count
    if n == 0:
        self._update_status()
        return

    cols = max(1, self.COLUMNS)
    tw = self.THUMB_W
    th = self.THUMB_H
    pad = self.PADDING

    total_w = cols * (tw + pad) + pad
    total_h = ((n + cols - 1) // cols) * (th + pad) + pad

    self.canvas.config(scrollregion=(0, 0, total_w, total_h))

    def _load_range(start, end):
        for i in range(start, min(end, n)):
            self._render_single_thumb(i)

    # 只加载可视区域附近的缩略图
    self._visible_range_start = 0
    self._visible_range_end = min(cols * 10, n)
    _load_range(0, self._visible_range_end)

    # 绑定滚动事件以懒加载
    self.canvas.bind("<Configure>", self._on_canvas_configure, add="+")

def _render_single_thumb(self, page_num):
    import threading
    from tkinter import ImageTk

    def _load():
        try:
            tk_img = self.editor.get_thumbnail(page_num)
            if tk_img:
                self.parent.after(0, _place, tk_img)
        except Exception:
            pass

    def _place(tk_img):
        cols = max(1, self.COLUMNS)
        tw = self.THUMB_W
        th = self.THUMB_H
        pad = self.PADDING

        row = page_num // cols
        col = page_num % cols
        x = pad + col * (tw + pad)
        y = pad + row * (th + pad)

        # 背景
        bg_id = self.canvas.create_rectangle(
            x, y, x + tw, y + th,
            fill="#FFFFFF", outline="#E5E7EB", width=1,
            tags="thumb"
        )
        # 图片
        img_id = self.canvas.create_image(
            x + tw // 2, y + th // 2,
            image=tk_img, tags="thumb"
        )
        # 页码
        text_id = self.canvas.create_text(
            x + tw // 2, y + th - 14,
            text=f"第 {page_num + 1} 页",
            fill="#6B7280", font=("Microsoft YaHei UI", 8),
            tags="thumb"
        )
        self._thumb_frame.append(tk_img)  # prevent GC
        self._thumb_ids[img_id] = page_num
        self._page_items[page_num] = {
            "bg": bg_id, "img": img_id, "text": text_id,
            "bbox": (x, y, x + tw, y + th)
        }
        self._highlight_page(page_num)

    threading.Thread(target=_load, daemon=True).start()

def _highlight_page(self, page_num):
    items = self._page_items.get(page_num)
    if not items:
        return
    if page_num in self.selected:
        self.canvas.itemconfig(items["bg"], outline="#F05A42", width=3)
    else:
        self.canvas.itemconfig(items["bg"], outline="#E5E7EB", width=1)

def _on_canvas_configure(self, event):
    # 懒加载：滚动时加载更多缩略图
    pass

def _update_status(self):
    n = self.editor.page_count
    sel = len(self.selected)
    modified = "⚠ 未保存" if self.editor.modified else ""
    info = f"共 {n} 页"
    if sel:
        info += f" | 选中 {sel} 页"
    self._info_label.config(text=f"{os.path.basename(self.editor.file_path or '')} | {info}")
    status = f"{info}"
    if modified:
        status += f" | {modified}"
    self._status_label.config(text=status)
```

- [ ] **Step 4: 实现点击/选中交互**

```python
def _on_click(self, event):
    x = self.canvas.canvasx(event.x)
    y = self.canvas.canvasy(event.y)
    item = self.canvas.find_closest(x, y)[0] if self.canvas.find_closest(x, y) else None
    if item is None:
        return
    page_num = self._thumb_ids.get(item)
    if page_num is None:
        # 也检查是否在某个缩略图区域内
        for pn, info in self._page_items.items():
            bx1, by1, bx2, by2 = info["bbox"]
            if bx1 <= x <= bx2 and by1 <= y <= by2:
                page_num = pn
                break
    if page_num is None:
        return

    if event.state & 0x0004:  # Ctrl
        # toggle
        if page_num in self.selected:
            self.selected.discard(page_num)
        else:
            self.selected.add(page_num)
    elif event.state & 0x0001:  # Shift
        # range select
        if self.selected:
            min_s = min(self.selected)
            max_s = max(self.selected)
            start = min(min_s, page_num)
            end = max(max_s, page_num)
            for i in range(start, end + 1):
                self.selected.add(i)
        else:
            self.selected = {page_num}
    else:
        if page_num in self.selected and len(self.selected) == 1:
            # start drag
            self.drag_data = {"page": page_num, "x": x, "y": y}
        else:
            self.selected = {page_num}

    for pn in self._page_items:
        self._highlight_page(pn)
    self._update_status()

def _on_drag(self, event):
    if self.drag_data:
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        # visual feedback could be added here

def _on_drop(self, event):
    if self.drag_data:
        src = self.drag_data["page"]
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        # find target page at drop position
        target = None
        for pn, info in self._page_items.items():
            bx1, by1, bx2, by2 = info["bbox"]
            if bx1 <= x <= bx2 and by1 <= y <= by2:
                target = pn
                break
        if target is not None and target != src:
            new_order = list(range(self.editor.page_count))
            new_order.pop(src)
            new_order.insert(target if target < src else target, src)
            try:
                self.editor.reorder_pages(new_order)
                self.selected.clear()
                self._render_thumbnails()
                self._update_status()
                self.log("页面已重新排序", "success")
            except RuntimeError as e:
                self.log(f"排序失败：{e}", "error")
        self.drag_data = None

def _toggle_select_all(self):
    n = self.editor.page_count
    if len(self.selected) == n:
        self.selected.clear()
    else:
        self.selected = set(range(n))
    for pn in self._page_items:
        self._highlight_page(pn)
    self._update_status()

def _invert_selection(self):
    n = self.editor.page_count
    all_pages = set(range(n))
    self.selected = all_pages - self.selected
    for pn in self._page_items:
        self._highlight_page(pn)
    self._update_status()
```

- [ ] **Step 5: 实现工具栏操作**

```python
def _rotate_90(self):
    if not self.selected:
        messagebox.showinfo("提示", "请先选择要旋转的页面")
        return
    try:
        self.editor.rotate_pages(list(self.selected), 90)
        self._render_thumbnails()
        self._update_status()
        self.log(f"已旋转 {len(self.selected)} 页", "success")
    except RuntimeError as e:
        self.log(f"旋转失败：{e}", "error")

def _delete_selected(self):
    if not self.selected:
        messagebox.showinfo("提示", "请先选择要删除的页面")
        return
    if not messagebox.askyesno("确认删除", f"确定删除选中的 {len(self.selected)} 页吗？"):
        return
    try:
        self.editor.delete_pages(list(self.selected))
        self.selected.clear()
        self._render_thumbnails()
        self._update_status()
        self.log("页面已删除", "success")
    except RuntimeError as e:
        self.log(f"删除失败：{e}", "error")

def _insert_pdf(self):
    path = filedialog.askopenfilename(
        title="选择要插入的PDF",
        filetypes=[("PDF文件", "*.pdf")]
    )
    if not path:
        return
    at = min(self.selected) if self.selected else self.editor.page_count
    try:
        self.editor.insert_pdf(at, path)
        self._render_thumbnails()
        self._update_status()
        self.log(f"已插入PDF：{os.path.basename(path)}", "success")
    except RuntimeError as e:
        self.log(f"插入失败：{e}", "error")

def _insert_image(self):
    path = filedialog.askopenfilename(
        title="选择图片",
        filetypes=[("图片文件", "*.jpg *.jpeg *.png *.bmp *.tiff *.webp")]
    )
    if not path:
        return
    at = min(self.selected) if self.selected else self.editor.page_count
    try:
        self.editor.insert_image(at, path)
        self._render_thumbnails()
        self._update_status()
        self.log(f"已插入图片：{os.path.basename(path)}", "success")
    except RuntimeError as e:
        self.log(f"插入失败：{e}", "error")

def _duplicate_selected(self):
    if not self.selected:
        messagebox.showinfo("提示", "请先选择要复制的页面")
        return
    at = min(self.selected) + len(self.selected)
    try:
        self.editor.duplicate_pages(list(self.selected), at)
        self.selected.clear()
        self._render_thumbnails()
        self._update_status()
        self.log(f"已复制 {len(self.selected)} 页", "warning")
    except RuntimeError as e:
        self.log(f"复制失败：{e}", "error")

def _insert_blank(self):
    at = min(self.selected) if self.selected else self.editor.page_count
    try:
        self.editor.insert_blank(at)
        self._render_thumbnails()
        self._update_status()
        self.log("已插入空白页", "success")
    except RuntimeError as e:
        self.log(f"插入失败：{e}", "error")

def _add_watermark(self):
    if not self.editor.page_count:
        return
    dialog = _WatermarkDialog(self.parent)
    self.parent.wait_window(dialog.dialog)
    if dialog.result:
        text, pos, opacity = dialog.result
        try:
            self.editor.add_watermark(text, pos, opacity)
            self._render_thumbnails()
            self._update_status()
            self.log("水印已添加", "success")
        except RuntimeError as e:
            self.log(f"水印添加失败：{e}", "error")

def _add_page_numbers(self):
    if not self.editor.page_count:
        return
    dialog = _PageNumDialog(self.parent)
    self.parent.wait_window(dialog.dialog)
    if dialog.result:
        start, pos, fmt = dialog.result
        try:
            self.editor.add_page_numbers(start, pos, fmt)
            self._render_thumbnails()
            self._update_status()
            self.log("页码已添加", "success")
        except RuntimeError as e:
            self.log(f"页码添加失败：{e}", "error")

def _edit_metadata(self):
    if not self.editor.page_count:
        return
    meta = self.editor.metadata
    dialog = _MetadataDialog(self.parent, meta)
    self.parent.wait_window(dialog.dialog)
    if dialog.result:
        try:
            self.editor.set_metadata(dialog.result)
            self._update_status()
            self.log("元数据已更新", "success")
        except RuntimeError as e:
            self.log(f"元数据更新失败：{e}", "error")

def _undo(self):
    try:
        if self.editor.undo():
            self._render_thumbnails()
            self._update_status()
            self.log("已撤销", "info")
        else:
            self.log("没有可撤销的操作", "info")
    except RuntimeError as e:
        self.log(f"撤销失败：{e}", "error")
```

- [ ] **Step 6: 实现子对话框**

```python
class _WatermarkDialog:
    """水印设置对话框"""
    def __init__(self, parent):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("添加水印")
        self.dialog.geometry("360x240")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.result = None

        tk.Label(self.dialog, text="水印文字:").pack(padx=16, pady=(16, 4), anchor=tk.W)
        self.text_entry = tk.Entry(self.dialog, width=40)
        self.text_entry.pack(padx=16, pady=2)
        self.text_entry.insert(0, "格式大师")

        tk.Label(self.dialog, text="位置:").pack(padx=16, pady=(8, 2), anchor=tk.W)
        self.pos_var = tk.StringVar(value="右下角")
        pos_frame = tk.Frame(self.dialog)
        pos_frame.pack(padx=16, pady=2)
        for p in ["左上角", "右上角", "左下角", "右下角", "居中"]:
            tk.Radiobutton(pos_frame, text=p, variable=self.pos_var,
                           value=p, bg="#ffffff").pack(side=tk.LEFT, padx=2)

        tk.Label(self.dialog, text="透明度:").pack(padx=16, pady=(8, 2), anchor=tk.W)
        self.opacity_scale = tk.Scale(self.dialog, from_=0.1, to=1.0,
                                      resolution=0.1, orient=tk.HORIZONTAL)
        self.opacity_scale.set(0.3)
        self.opacity_scale.pack(padx=16, pady=2, fill=tk.X)

        btn_frame = tk.Frame(self.dialog)
        btn_frame.pack(pady=16)
        tk.Button(btn_frame, text="确定", command=self._ok,
                  bg="#F05A42", fg="white", padx=24, pady=4).pack(side=tk.LEFT, padx=8)
        tk.Button(btn_frame, text="取消", command=self._cancel,
                  bg="#E5E7EB", fg="#1A1A2E", padx=24, pady=4).pack(side=tk.LEFT, padx=8)

    def _ok(self):
        text = self.text_entry.get().strip()
        if not text:
            messagebox.showwarning("提示", "请输入水印文字")
            return
        self.result = (text, self.pos_var.get(), self.opacity_scale.get())
        self.dialog.destroy()

    def _cancel(self):
        self.dialog.destroy()


class _PageNumDialog:
    """页码设置对话框"""
    def __init__(self, parent):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("添加页码")
        self.dialog.geometry("340x200")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.result = None

        tk.Label(self.dialog, text="起始页码:").pack(padx=16, pady=(16, 4), anchor=tk.W)
        self.start_entry = tk.Entry(self.dialog, width=10)
        self.start_entry.pack(padx=16, pady=2, anchor=tk.W)
        self.start_entry.insert(0, "1")

        tk.Label(self.dialog, text="位置:").pack(padx=16, pady=(8, 2), anchor=tk.W)
        self.pos_var = tk.StringVar(value="底部居中")
        self.pos_combo = ttk.Combobox(self.dialog, textvariable=self.pos_var,
                                       values=["底部居中", "底部左对齐", "底部右对齐", "顶部居中"],
                                       width=20)
        self.pos_combo.pack(padx=16, pady=2, anchor=tk.W)

        tk.Label(self.dialog, text="格式 (使用 {n} 表示页码):").pack(padx=16, pady=(8, 2), anchor=tk.W)
        self.fmt_entry = tk.Entry(self.dialog, width=30)
        self.fmt_entry.pack(padx=16, pady=2, anchor=tk.W)
        self.fmt_entry.insert(0, "— {n} —")

        btn_frame = tk.Frame(self.dialog)
        btn_frame.pack(pady=16)
        tk.Button(btn_frame, text="确定", command=self._ok,
                  bg="#F05A42", fg="white", padx=24, pady=4).pack(side=tk.LEFT, padx=8)
        tk.Button(btn_frame, text="取消", command=self._cancel,
                  bg="#E5E7EB", fg="#1A1A2E", padx=24, pady=4).pack(side=tk.LEFT, padx=8)

    def _ok(self):
        try:
            start = int(self.start_entry.get())
        except ValueError:
            messagebox.showwarning("提示", "起始页码必须是数字")
            return
        self.result = (start, self.pos_var.get(), self.fmt_entry.get())
        self.dialog.destroy()

    def _cancel(self):
        self.dialog.destroy()


class _MetadataDialog:
    """元数据编辑对话框"""
    def __init__(self, parent, meta):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("编辑元数据")
        self.dialog.geometry("360x260")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.result = None

        fields = [("标题", "title"), ("作者", "author"),
                  ("主题", "subject"), ("关键词", "keywords")]
        self.entries = {}
        for i, (label, key) in enumerate(fields):
            tk.Label(self.dialog, text=label + ":").grid(
                row=i, column=0, padx=16, pady=(12 if i == 0 else 6, 2), sticky=tk.W)
            entry = tk.Entry(self.dialog, width=40)
            entry.grid(row=i, column=1, padx=(0, 16), pady=(12 if i == 0 else 6, 2))
            entry.insert(0, meta.get(key, ""))
            self.entries[key] = entry

        btn_frame = tk.Frame(self.dialog)
        btn_frame.grid(row=len(fields), column=0, columnspan=2, pady=16)
        tk.Button(btn_frame, text="确定", command=self._ok,
                  bg="#F05A42", fg="white", padx=24, pady=4).pack(side=tk.LEFT, padx=8)
        tk.Button(btn_frame, text="取消", command=self._cancel,
                  bg="#E5E7EB", fg="#1A1A2E", padx=24, pady=4).pack(side=tk.LEFT, padx=8)

    def _ok(self):
        self.result = {k: v.get() for k, v in self.entries.items()}
        self.dialog.destroy()

    def _cancel(self):
        self.dialog.destroy()
```

- [ ] **Step 7: 添加 public 方法供外部集成**

```python
def is_modified(self) -> bool:
    return self.editor.modified

def is_open(self) -> bool:
    return self.editor.page_count > 0

def cleanup(self):
    """关闭编辑器时释放资源"""
    self.editor.close()
```

- [ ] **Step 8: 验证文件可导入**

Run: `python -c "from gui.pdf_editor_panel import PdfEditorPanel; print('OK')"`
Expected: `OK`

---

### Task 3: 修改 main.py — 集成编辑器模式

**Files:**
- Modify: `main.py`

- [ ] **Step 1: 在 main.py 顶部添加导入**

找到 imports 区域（~line 46），在 `from core.m3u8_downloader import M3U8Downloader` 之后添加：

```python
from gui.pdf_editor_panel import PdfEditorPanel
```

- [ ] **Step 2: 修改 _p_pdf() 方法，添加编辑器模式分支**

找到 `_p_pdf` 方法定义（约 line 3012），修改模式选择器 values 添加"编辑器（可视化）"选项。

在 `self.pdf_mode` 的 values 列表中添加 `"编辑器（可视化）"`：

```python
self.pdf_mode = ttk.Combobox(mode_frame, textvariable=self._pdf_mode_var,
    values=["合并（多个→一个）", "拆分（一个→多个）",
            "加密（设置密码）", "解密（移除密码）",
            "压缩", "编辑器（可视化）"],
    width=26, state="readonly")
```

- [ ] **Step 3: 在 _p_pdf() 中创建编辑器容器**

在 PDF 面板的方法中，找到控件创建区域（在进度条/状态标签之后），添加一个 Frame 作为编辑器容器：

```python
# 编辑器容器（默认隐藏）
self.pdf_editor_container = tk.Frame(self.content, bg=D["page"])
self.pdf_editor_container.pack(fill=tk.BOTH, expand=True, padx=16, pady=4)
self.pdf_editor_container.pack_forget()  # 默认隐藏
self.pdf_editor_panel = None  # 延迟创建
```

- [ ] **Step 4: 绑定模式切换事件**

为 `self.pdf_mode` 添加 `<<ComboboxSelected>>` 事件，在 PDF 面板初始化方法中：

```python
self.pdf_mode.bind("<<ComboboxSelected>>", self._on_pdf_mode_change)
```

- [ ] **Step 5: 实现 _on_pdf_mode_change 回调**

```python
def _on_pdf_mode_change(self, event=None):
    mode = self._pdf_mode_var.get()
    if "编辑器" in mode:
        self._show_pdf_editor()
    else:
        self._hide_pdf_editor()

def _show_pdf_editor(self):
    # 隐藏原有控件（文件选择、参数区等）
    self._set_pdf_controls_visible(False)
    # 显示编辑器
    self.pdf_editor_container.pack(fill=tk.BOTH, expand=True, padx=16, pady=4)
    if self.pdf_editor_panel is None:
        self.pdf_editor_panel = PdfEditorPanel(
            self.pdf_editor_container,
            log_func=self._log_status,
        )
    # 更新按钮状态
    self._update_convert_btn_state()

def _hide_pdf_editor(self):
    if self.pdf_editor_panel and self.pdf_editor_panel.is_modified():
        if not messagebox.askyesno("未保存", "编辑器中有未保存的修改，确定要切换吗？"):
            self._pdf_mode_var.set("编辑器（可视化）")
            return
    self.pdf_editor_container.pack_forget()
    self._set_pdf_controls_visible(True)

def _set_pdf_controls_visible(self, visible):
    """显示/隐藏原有 PDF 工具控件"""
    state = "normal" if visible else "hidden"
    # 需要引用 PDF 面板中的各个 Frame 控件
    # 通过遍历已有控件或维护一个 list 来实现
    for widget in getattr(self, '_pdf_control_widgets', []):
        try:
            if visible:
                widget.pack()
            else:
                widget.pack_forget()
        except Exception:
            pass
```

- [ ] **Step 6: 收集 PDF 控件引用**

在 `_p_pdf()` 方法中，将所有创建的控件（file frame, mode frame, param frame, progress bar 等）收集到 `self._pdf_control_widgets` 列表中。

在 PDF 面板方法末尾，返回前添加：

```python
# 收集所有控件以便显示/隐藏
self._pdf_control_widgets = [
    self._pdf_file_frame,     # 存放文件选择相关控件的 Frame
    self._pdf_mode_frame,     # 存放模式选择器的 Frame
    self._pdf_param_frame,    # 存放参数控件的 Frame
    self._pdf_progress_frame, # 存放进度条和状态标签的 Frame
]
```

需要确保这些 frame 变量在 `_p_pdf()` 中正确定义。

- [ ] **Step 7: 适配任务队列**

修改任务分发部分（约 line 791）确保编辑器模式下不使用任务队列。在 `_run_task_general` 中，PDF 编辑器不经过任务系统，因为操作是即时完成的。

实际上，编辑器模式不需要经过 task_queue，因为 `PdfEditorPanel` 内部直接调用 `PdfEditor` 的方法，操作即时完成。所以只需要在 `_switch` 到 PDF 面板时判断当前模式即可。

- [ ] **Step 8: 确保切换面板时编辑器正确释放**

在 `_switch` 方法中（切换侧边栏 tab 时），如果当前是 PDF 编辑器模式且编辑器有未保存修改，提示用户。

```python
def _switch(self, key):
    # 在切换前检查 PDF 编辑器状态
    if self.current_tab.get() == "pdf":
        if (hasattr(self, 'pdf_editor_panel') and
            self.pdf_editor_panel and
            self.pdf_editor_panel.is_modified()):
            if not messagebox.askyesno("未保存", "PDF 编辑器中有未保存的修改，确定要切换吗？"):
                return
    # ... 原有切换逻辑
```

---

### Task 4: 端到端验证

- [ ] **Step 1: 验证导入无错误**

Run: `python -c "from core.pdf_editor import PdfEditor; from gui.pdf_editor_panel import PdfEditorPanel; print('All imports OK')"`
Expected: `All imports OK`

- [ ] **Step 2: 验证 PyMuPDF 功能**

Run: `python -c "import fitz; doc = fitz.open(); doc.new_page(); print(f'Create OK: {len(doc)} page(s)'); doc.close()"`
Expected: `Create OK: 1 page(s)`

- [ ] **Step 3: 启动应用测试**

Run: `python main.py`
Expected: 应用正常启动，切换到 PDF 面板，模式选择器中能看到"编辑器（可视化）"选项。

- [ ] **Step 4: 功能测试清单**

手动测试以下场景：
1. 打开一个 PDF 文件 → 缩略图显示
2. 选中页面 → 高亮边框
3. 使用 Ctrl+单击多选 → 多页选中
4. 拖拽排序 → 页面顺序改变
5. 删除选中页 → 页面减少
6. 插入图片 → 新页面添加
7. 添加水印 → 水印出现在页面上
8. 添加页码 → 页码显示
9. 撤销操作 → 恢复到之前状态
10. 保存 → 文件重新打开验证
