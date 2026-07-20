"""PDF 编辑器 UI 面板 - 优化排版版"""

import os
import math
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import ImageTk
from core.pdf_editor import PdfEditor
from utils.config import USER_PREFS

# ── Design Tokens ──
PAGE_BG = "#F5F6FA"
CARD_BG = "#FFFFFF"
CARD_ALT = "#FAFBFC"
ACCENT = "#F05A42"
ACCENT_DEEP = "#D04532"
ACCENT_PALE = "#FFF1EF"
ACCENT_LIGHT = "#FFE8E3"
BORDER = "#E5E7EB"
BORDER_HI = "#D1D5DB"
INK = "#1A1A2E"
INK_SEC = "#6B7280"
INK_DIS = "#9CA3AF"
INK_INV = "#FFFFFF"
SHADOW = "#E8E9ED"

THUMB_BASE_W = 150
THUMB_BASE_H = 200
PADDING = 16
TEXT_H = 28
FONT = "Microsoft YaHei UI"
MIN_GAP = 12
MAX_COLUMNS = 8
MIN_COLUMNS = 2


# ═══════════════════════════════════════════════
#  Dialog Windows
# ═══════════════════════════════════════════════

class _DialogBase(tk.Toplevel):
    """Dialog 基类，减少重复代码"""

    def __init__(self, parent, title, size):
        super().__init__(parent)
        self.title(title)
        self.geometry(size)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        self.result = None
        self.configure(bg=PAGE_BG)

    def center_on_parent(self):
        self.update_idletasks()
        pw = self.master.winfo_width()
        ph = self.master.winfo_height()
        px = self.master.winfo_x()
        py = self.master.winfo_y()
        w = self.winfo_width()
        h = self.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")

    def _make_row(self, parent, label_text, pady=(0, 8)):
        row = tk.Frame(parent, bg=PAGE_BG)
        row.pack(fill=tk.X, pady=pady)
        tk.Label(row, text=label_text, bg=PAGE_BG, fg=INK,
                 font=(FONT, 10), width=8, anchor=tk.W).pack(side=tk.LEFT, padx=(0, 8))
        return row

    def _make_entry(self, parent, textvariable, width=25):
        return tk.Entry(parent, textvariable=textvariable, font=(FONT, 10),
                        bg=CARD_BG, fg=INK, relief="solid",
                        highlightthickness=1, highlightbackground=BORDER,
                        highlightcolor=ACCENT, width=width)

    def _make_buttons(self, parent, on_ok, pady=(12, 0)):
        btn_frame = tk.Frame(parent, bg=PAGE_BG)
        btn_frame.pack(fill=tk.X, pady=pady)
        tk.Button(btn_frame, text="确定", font=(FONT, 10, "bold"),
                  bg=ACCENT, fg=INK_INV, relief="flat", padx=24, pady=4,
                  activebackground=ACCENT_DEEP, cursor="hand2",
                  command=on_ok).pack(side=tk.RIGHT, padx=(8, 0))
        tk.Button(btn_frame, text="取消", font=(FONT, 10),
                  bg=CARD_BG, fg=INK, relief="flat", padx=24, pady=4,
                  activebackground=CARD_ALT, cursor="hand2",
                  command=self.destroy).pack(side=tk.RIGHT)

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.wait_visibility()
        self.center_on_parent()


class _WatermarkDialog(_DialogBase):
    POSITIONS = ["左上角", "右上角", "左下角", "右下角", "居中"]

    def __init__(self, parent):
        super().__init__(parent, "添加水印", "380x260")

        self._pos_var = tk.StringVar(value=self.POSITIONS[3])
        self._opacity_var = tk.DoubleVar(value=0.3)
        self._text_var = tk.StringVar(value="格式大师")

        body = tk.Frame(self, bg=PAGE_BG, padx=20, pady=16)
        body.pack(fill=tk.BOTH, expand=True)

        # Title
        tk.Label(body, text="水印设置", bg=PAGE_BG, fg=INK,
                 font=(FONT, 12, "bold")).pack(anchor=tk.W, pady=(0, 12))

        # Text
        row1 = self._make_row(body, "水印文字")
        self._make_entry(row1, self._text_var, 28).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Position
        row2 = self._make_row(body, "位  置")
        for pos in self.POSITIONS:
            tk.Radiobutton(row2, text=pos, variable=self._pos_var,
                           value=pos, bg=PAGE_BG, fg=INK,
                           activebackground=PAGE_BG,
                           selectcolor=CARD_BG,
                           font=(FONT, 9)).pack(side=tk.LEFT, padx=(0, 6))

        # Opacity
        row3 = self._make_row(body, "不透明度")
        tk.Scale(row3, variable=self._opacity_var, from_=0.1, to=1.0,
                 resolution=0.1, orient=tk.HORIZONTAL, bg=PAGE_BG,
                 fg=INK, highlightthickness=0, length=160,
                 font=(FONT, 9), troughcolor=BORDER).pack(side=tk.LEFT)

        self._make_buttons(body, self._on_ok)

    def _on_ok(self):
        self.result = (
            self._text_var.get(),
            self._pos_var.get(),
            round(self._opacity_var.get(), 1),
        )
        self.destroy()


class _PageNumDialog(_DialogBase):
    POSITIONS = ["底部居中", "底部左对齐", "底部右对齐", "顶部居中"]

    def __init__(self, parent):
        super().__init__(parent, "添加页码", "380x280")

        self._start_var = tk.StringVar(value="1")
        self._pos_var = tk.StringVar(value=self.POSITIONS[0])
        self._fmt_var = tk.StringVar(value="— {n} —")

        body = tk.Frame(self, bg=PAGE_BG, padx=20, pady=16)
        body.pack(fill=tk.BOTH, expand=True)

        tk.Label(body, text="页码设置", bg=PAGE_BG, fg=INK,
                 font=(FONT, 12, "bold")).pack(anchor=tk.W, pady=(0, 12))

        # Start number
        row1 = self._make_row(body, "起始编号")
        self._make_entry(row1, self._start_var, 12).pack(side=tk.LEFT)

        # Position
        row2 = self._make_row(body, "位  置")
        ttk.Combobox(row2, textvariable=self._pos_var,
                     values=self.POSITIONS, state="readonly",
                     width=14, font=(FONT, 10)).pack(side=tk.LEFT)

        # Format
        row3 = self._make_row(body, "格  式")
        self._make_entry(row3, self._fmt_var, 22).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(row3, text="{n} = 页码", bg=PAGE_BG, fg=INK_SEC,
                 font=(FONT, 9)).pack(side=tk.LEFT, padx=(8, 0))

        self._make_buttons(body, self._on_ok)

    def _on_ok(self):
        try:
            start = int(self._start_var.get())
        except ValueError:
            messagebox.showwarning("输入错误", "起始编号必须为整数", parent=self)
            return
        self.result = (start, self._pos_var.get(), self._fmt_var.get())
        self.destroy()


class _MetadataDialog(_DialogBase):
    def __init__(self, parent, current: dict):
        super().__init__(parent, "编辑元数据", "400x300")

        body = tk.Frame(self, bg=PAGE_BG, padx=20, pady=16)
        body.pack(fill=tk.BOTH, expand=True)

        tk.Label(body, text="文档属性", bg=PAGE_BG, fg=INK,
                 font=(FONT, 12, "bold")).pack(anchor=tk.W, pady=(0, 12))

        fields = [
            ("标题", "title"),
            ("作者", "author"),
            ("主题", "subject"),
            ("关键词", "keywords"),
        ]
        self._entries = {}
        for label, key in fields:
            row = self._make_row(body, label)
            e = self._make_entry(row, None)
            e.insert(0, current.get(key, ""))
            e.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self._entries[key] = e

        self._make_buttons(body, self._on_ok, pady=(16, 0))

    def _on_ok(self):
        self.result = {key: e.get() for key, e in self._entries.items()}
        self.destroy()


# ═══════════════════════════════════════════════
#  Main Panel
# ═══════════════════════════════════════════════

class PdfEditorPanel(tk.Frame):
    def __init__(self, parent, log_func=None):
        super().__init__(parent, bg=PAGE_BG)
        self.parent = parent
        self.log_func = log_func

        self.editor = PdfEditor()
        self.selected = set()
        self._last_clicked_page = None
        self.drag_data = None
        self._page_items = {}
        self._item_to_page = {}
        self._thumb_refs = []
        self._info_label = None
        self._status_label = None
        self._render_gen = 0

        # 响应式布局参数
        self._columns = 4
        self._thumb_scale = 1.0

        self._build_ui()

    # ── UI Construction ──────────────────────────────────────

    def _build_ui(self):
        # ═══ Top bar ═══
        top_bar = tk.Frame(self, bg=PAGE_BG)
        top_bar.pack(fill=tk.X, padx=12, pady=(10, 4))

        # Left: file buttons
        left_frame = tk.Frame(top_bar, bg=PAGE_BG)
        left_frame.pack(side=tk.LEFT)

        btn_open = tk.Button(left_frame, text="📂  打开文件", font=(FONT, 10),
                             bg=CARD_BG, fg=INK, relief="solid", bd=1,
                             padx=14, pady=5, cursor="hand2",
                             activebackground=CARD_ALT, highlightbackground=BORDER,
                             command=self._open_file)
        btn_open.pack(side=tk.LEFT, padx=(0, 6))

        btn_save = tk.Button(left_frame, text="💾  保存", font=(FONT, 10, "bold"),
                             bg=ACCENT, fg=INK_INV, relief="flat",
                             padx=14, pady=5, cursor="hand2",
                             activebackground=ACCENT_DEEP,
                             command=self._save_file)
        btn_save.pack(side=tk.LEFT, padx=(0, 6))

        btn_save_as = tk.Button(left_frame, text="另存为", font=(FONT, 10),
                                bg=CARD_BG, fg=INK, relief="solid", bd=1,
                                padx=14, pady=5, cursor="hand2",
                                activebackground=CARD_ALT, highlightbackground=BORDER,
                                command=self._save_as)
        btn_save_as.pack(side=tk.LEFT)

        # Right: file info
        self._info_label = tk.Label(top_bar, text="未打开文件", bg=PAGE_BG,
                                    fg=INK_DIS, font=(FONT, 9), anchor=tk.E)
        self._info_label.pack(side=tk.RIGHT, padx=(8, 0))

        # ═══ Toolbar ═══
        toolbar = tk.Frame(self, bg=CARD_BG, highlightbackground=BORDER,
                           highlightthickness=1)
        toolbar.pack(fill=tk.X, padx=12, pady=(4, 8))

        # Tool groups with separators
        tool_groups = [
            # (text, command, accent)
            [
                ("🔀 旋转", self._rotate_90, False),
                ("🗑 删除", self._delete_selected, False),
                ("📋 复制", self._duplicate_selected, False),
            ],
            [
                ("📄 插入PDF", self._insert_pdf, False),
                ("🖼 插入图片", self._insert_image, False),
                ("⬜ 空白页", self._insert_blank, False),
            ],
            [
                ("🏷 水印", self._add_watermark, False),
                ("🔢 页码", self._add_page_numbers, False),
                ("📝 元数据", self._edit_metadata, False),
            ],
            [
                ("↩ 撤销", self._undo, False),
            ],
        ]

        for gi, group in enumerate(tool_groups):
            if gi > 0:
                sep = tk.Frame(toolbar, bg=BORDER, width=1)
                sep.pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=4)

            for text, cmd, accent in group:
                fg = ACCENT if accent else INK
                btn = tk.Button(toolbar, text=text, font=(FONT, 9),
                                bg=CARD_BG, fg=fg, relief="flat",
                                padx=8, pady=3, cursor="hand2",
                                activebackground=ACCENT_PALE if accent else CARD_ALT,
                                activeforeground=ACCENT_DEEP if accent else INK,
                                command=cmd)
                btn.pack(side=tk.LEFT, padx=1)

        # Right side: select all / invert
        right_tools = tk.Frame(toolbar, bg=CARD_BG)
        right_tools.pack(side=tk.RIGHT)

        tk.Button(right_tools, text="全选", font=(FONT, 9),
                  bg=CARD_BG, fg=ACCENT, relief="flat",
                  padx=8, pady=3, cursor="hand2",
                  activebackground=ACCENT_PALE,
                  command=self._toggle_select_all).pack(side=tk.LEFT, padx=1)
        tk.Button(right_tools, text="反选", font=(FONT, 9),
                  bg=CARD_BG, fg=INK_SEC, relief="flat",
                  padx=8, pady=3, cursor="hand2",
                  activebackground=CARD_ALT,
                  command=self._invert_selection).pack(side=tk.LEFT, padx=1)

        # ═══ Canvas area ═══
        canvas_frame = tk.Frame(self, bg=PAGE_BG)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 4))

        self.canvas = tk.Canvas(canvas_frame, bg=PAGE_BG,
                                highlightthickness=0, relief="flat")
        v_scroll = tk.Scrollbar(canvas_frame, orient=tk.VERTICAL,
                                command=self.canvas.yview)
        h_scroll = tk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL,
                                command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=v_scroll.set,
                              xscrollcommand=h_scroll.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)

        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_drop)
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        # ═══ Guide bar ═══
        guide_bar = tk.Frame(self, bg=ACCENT_LIGHT, highlightbackground=ACCENT,
                             highlightthickness=1)
        guide_bar.pack(fill=tk.X, padx=12, pady=(0, 4))
        self._guide_label = tk.Label(guide_bar,
            text="💡  操作即时生效 — 选中页面 → 点击工具栏按钮 → 完成后「保存」",
            bg=ACCENT_LIGHT, fg=ACCENT_DEEP, font=(FONT, 9), anchor=tk.W,
            padx=10, pady=4)
        self._guide_label.pack(fill=tk.X)

        # ═══ Status bar ═══
        status_bar = tk.Frame(self, bg=CARD_BG, highlightbackground=BORDER,
                              highlightthickness=1)
        status_bar.pack(fill=tk.X, padx=12, pady=(0, 8))

        self._status_label = tk.Label(status_bar, text="就绪", bg=CARD_BG,
                                      fg=INK_SEC, font=(FONT, 9), anchor=tk.W,
                                      padx=10, pady=3)
        self._status_label.pack(fill=tk.X)

    # ── Responsive Layout ───────────────────────────────────

    def _calc_columns(self):
        """根据 Canvas 宽度计算合适的列数"""
        try:
            cw = self.canvas.winfo_width()
        except Exception:
            return 4
        if cw <= 1:
            return 4
        avail = cw - PADDING * 2
        tw = THUMB_BASE_W * self._thumb_scale + MIN_GAP
        cols = max(MIN_COLUMNS, min(MAX_COLUMNS, int(avail / tw)))
        return cols

    def _on_canvas_resize(self, event=None):
        new_cols = self._calc_columns()
        if new_cols != self._columns:
            self._columns = new_cols
            if self.editor.page_count > 0:
                self._render_thumbnails()

    def _get_thumb_size(self):
        w = int(THUMB_BASE_W * self._thumb_scale)
        h = int(THUMB_BASE_H * self._thumb_scale)
        return w, h

    def _get_thumb_pos(self, page_num):
        tw, th = self._get_thumb_size()
        gap = MIN_GAP
        col = page_num % self._columns
        row = page_num // self._columns
        x = PADDING + col * (tw + gap)
        y = PADDING + row * (th + TEXT_H + gap)
        return x, y

    # ── File Operations ──────────────────────────────────────

    def _get_last_dir(self, key):
        """获取上次使用的目录"""
        return USER_PREFS.get("pdf_editor", key, os.path.expanduser("~"))

    def _save_last_dir(self, key, path):
        """保存最后使用的目录"""
        if path and os.path.isdir(path):
            USER_PREFS.set("pdf_editor", key, path)
        elif path and os.path.isfile(path):
            USER_PREFS.set("pdf_editor", key, os.path.dirname(path))

    def _open_file(self):
        last_dir = self._get_last_dir("open")
        path = filedialog.askopenfilename(
            title="打开 PDF 文件",
            initialdir=last_dir,
            filetypes=[("PDF 文件", "*.pdf"), ("所有文件", "*.*")]
        )
        if not path:
            return
        self._save_last_dir("open", path)
        try:
            self.editor.open(path)
            self.selected.clear()
            self._last_clicked_page = None
            self._columns = self._calc_columns()
            self._render_thumbnails()
            self._update_status()
            self._info_label.config(text=os.path.basename(path), fg=INK)
            self._log(f"已打开: {path}")
        except RuntimeError as e:
            messagebox.showerror("打开失败", str(e))

    def _save_file(self):
        if not self.editor.page_count:
            return
        path = self.editor.file_path
        if path:
            try:
                self.editor.compact()
                self.editor.save(path)
                self._update_status()
                self._log(f"已保存: {path}")
            except RuntimeError as e:
                messagebox.showerror("保存失败", str(e))
        else:
            self._save_as()

    def _save_as(self):
        if not self.editor.page_count:
            return
        last_dir = self._get_last_dir("save")
        path = filedialog.asksaveasfilename(
            title="另存为",
            initialdir=last_dir,
            defaultextension=".pdf",
            filetypes=[("PDF 文件", "*.pdf"), ("所有文件", "*.*")]
        )
        if not path:
            return
        self._save_last_dir("save", path)
        try:
            self.editor.compact()
            self.editor.save(path)
            self._info_label.config(text=os.path.basename(path), fg=INK)
            self._update_status()
            self._log(f"已另存为: {path}")
        except RuntimeError as e:
            messagebox.showerror("保存失败", str(e))

    # ── Thumbnail Rendering ──────────────────────────────────

    def _render_thumbnails(self):
        self._render_gen += 1
        self.canvas.delete("thumb")
        self._thumb_refs = []
        self._page_items = {}
        self._item_to_page = {}

        n = self.editor.page_count
        if n == 0:
            self.canvas.config(scrollregion=(0, 0, 1, 1))
            return

        tw, th = self._get_thumb_size()
        gap = MIN_GAP
        rows = math.ceil(n / self._columns)
        total_w = self._columns * (tw + gap) + PADDING * 2
        total_h = rows * (th + TEXT_H + gap) + PADDING * 2

        for i in range(n):
            x, y = self._get_thumb_pos(i)

            # Shadow (subtle)
            self.canvas.create_rectangle(
                x + 2, y + 2, x + tw + 2, y + th + 2,
                fill=SHADOW, outline="", tags="thumb"
            )

            # Thumbnail background
            rect = self.canvas.create_rectangle(
                x, y, x + tw, y + th,
                fill=CARD_BG, outline=BORDER, width=1,
                tags="thumb"
            )

            # Page number label
            text = self.canvas.create_text(
                x + tw // 2, y + th + 8,
                text=f"第 {i + 1} 页",
                font=(FONT, 9), fill=INK_SEC,
                tags="thumb"
            )

            self._page_items[i] = {"rect": rect, "img": None, "text": text}
            self._item_to_page[rect] = i
            self._item_to_page[text] = i

        self.canvas.config(scrollregion=(0, 0, total_w, total_h))
        self._load_visible_thumbnails()

    def _load_thumbnails(self, start, end):
        gen = self._render_gen
        def _worker():
            for i in range(start, end + 1):
                try:
                    pil_img = self.editor.get_thumbnail(i)
                    if pil_img:
                        self.after(0, self._place_thumb, i, pil_img, gen)
                except Exception:
                    import traceback
                    traceback.print_exc()

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def _place_thumb(self, page_num, pil_img, gen=0):
        if gen != self._render_gen:
            return
        if page_num not in self._page_items:
            return
        items = self._page_items[page_num]
        if items["img"] is not None:
            self.canvas.delete(items["img"])

        # Scale image to fit thumbnail size
        tw, th = self._get_thumb_size()
        from PIL import Image as PILImage
        orig_w, orig_h = pil_img.size
        scale = min((tw - 4) / orig_w, (th - 4) / orig_h)
        new_w = max(1, int(orig_w * scale))
        new_h = max(1, int(orig_h * scale))
        pil_img = pil_img.resize((new_w, new_h), PILImage.LANCZOS)

        tk_img = ImageTk.PhotoImage(pil_img)
        x, y = self._get_thumb_pos(page_num)
        img_id = self.canvas.create_image(
            x + tw // 2, y + th // 2,
            image=tk_img, tags="thumb"
        )
        self._thumb_refs.append(tk_img)
        if len(self._thumb_refs) > self.editor.page_count * 2:
            self._thumb_refs = self._thumb_refs[-self.editor.page_count:]
        items["img"] = img_id
        self._item_to_page[img_id] = page_num
        if items["text"]:
            self.canvas.tag_lower(img_id, items["text"])

    def _load_visible_thumbnails(self):
        canvas = self.canvas
        left = canvas.canvasx(0)
        top = canvas.canvasy(0)
        right = canvas.canvasx(canvas.winfo_width())
        bottom = canvas.canvasy(canvas.winfo_height())
        if right <= left or bottom <= top:
            self._load_thumbnails(0, self.editor.page_count - 1)
            return
        n = self.editor.page_count
        start = None
        end = None
        for i in range(n):
            items = self._page_items.get(i)
            if not items:
                continue
            coords = self.canvas.coords(items["rect"])
            if not coords or len(coords) < 4:
                continue
            cx, cy = (coords[0] + coords[2]) / 2, (coords[1] + coords[3]) / 2
            if left <= cx <= right and top <= cy <= bottom:
                if start is None:
                    start = i
                end = i
        if start is not None:
            margin = 4
            start = max(0, start - margin)
            end = min(n - 1, end + margin)
            self._load_thumbnails(start, end)

    # ── Selection Handling ───────────────────────────────────

    def _find_page_at(self, cv_x, cv_y):
        for page_num, items in self._page_items.items():
            rect_id = items["rect"]
            coords = self.canvas.coords(rect_id)
            if coords and len(coords) == 4:
                x0, y0, x1, y1 = coords
                if x0 <= cv_x <= x1 and y0 <= cv_y <= y1:
                    return page_num
        return None

    def _on_click(self, event):
        cv_x = self.canvas.canvasx(event.x)
        cv_y = self.canvas.canvasy(event.y)
        page = self._find_page_at(cv_x, cv_y)
        if page is None:
            self.selected.clear()
            self._highlight_all()
            self._update_status()
            return

        ctrl = (event.state & 0x0004) != 0
        shift = (event.state & 0x0001) != 0
        was_selected = page in self.selected

        if ctrl:
            if page in self.selected:
                self.selected.discard(page)
            else:
                self.selected.add(page)
            self._last_clicked_page = page
        elif shift and self._last_clicked_page is not None:
            start = min(self._last_clicked_page, page)
            end = max(self._last_clicked_page, page)
            self.selected = set(range(start, end + 1))
        else:
            self.selected = {page}
            self._last_clicked_page = page

        if not ctrl and not shift and was_selected and len(self.selected) == 1:
            self.drag_data = {"page": page, "x": event.x_root, "y": event.y_root}

        self._highlight_all()
        self._update_status()

    def _highlight_all(self):
        for p in self._page_items:
            self._highlight_page(p)

    def _highlight_page(self, page_num):
        items = self._page_items.get(page_num)
        if not items:
            return
        selected = page_num in self.selected
        if selected:
            outline = ACCENT
            width = 3
        else:
            outline = BORDER
            width = 1
        self.canvas.itemconfig(items["rect"], outline=outline, width=width)

    # ── Drag & Drop Reordering ──────────────────────────────

    def _on_drag(self, event):
        pass

    def _on_drop(self, event):
        if self.drag_data is None:
            return
        src_page = self.drag_data["page"]
        self.drag_data = None

        cv_x = self.canvas.canvasx(event.x)
        cv_y = self.canvas.canvasy(event.y)
        target_page = self._find_page_at(cv_x, cv_y)
        if target_page is None or target_page == src_page:
            return

        n = self.editor.page_count
        new_order = list(range(n))
        new_order.remove(src_page)
        new_order.insert(target_page, src_page)

        if self.editor.reorder_pages(new_order):
            self.selected = {target_page}
            self._render_thumbnails()
            self._update_status()
            self._log(f"页面 {src_page + 1} 移动到 {target_page + 1}")

    # ── Toolbar Handlers ─────────────────────────────────────

    def _rotate_90(self):
        if not self.editor.page_count:
            return
        if not self.selected:
            messagebox.showinfo("提示", "请先选择要旋转的页面")
            return
        indices = sorted(self.selected)
        if self.editor.rotate_pages(indices, 90):
            self._render_thumbnails()
            self._update_status()
            self._log(f"已旋转 {len(indices)} 页")

    def _delete_selected(self):
        if not self.editor.page_count:
            return
        if not self.selected:
            messagebox.showinfo("提示", "请先选择要删除的页面")
            return
        if not messagebox.askyesno("确认删除", f"确定要删除选中的 {len(self.selected)} 页吗？"):
            return
        indices = sorted(self.selected)
        if self.editor.delete_pages(indices):
            self.selected.clear()
            self._render_thumbnails()
            self._update_status()
            self._log(f"已删除 {len(indices)} 页")

    def _insert_pdf(self):
        if not self.editor.page_count:
            return
        last_dir = self._get_last_dir("insert")
        path = filedialog.askopenfilename(
            title="插入 PDF 文件",
            initialdir=last_dir,
            filetypes=[("PDF 文件", "*.pdf"), ("所有文件", "*.*")]
        )
        if not path:
            return
        self._save_last_dir("insert", path)
        at = min(self.selected) if self.selected else self.editor.page_count
        if self.editor.insert_pdf(at, path):
            self._render_thumbnails()
            self._update_status()
            self._log(f"已在位置 {at + 1} 插入 PDF")

    def _insert_image(self):
        if not self.editor.page_count:
            return
        last_dir = self._get_last_dir("insert")
        path = filedialog.askopenfilename(
            title="插入图片",
            initialdir=last_dir,
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.bmp *.tiff *.webp"),
                       ("所有文件", "*.*")]
        )
        if not path:
            return
        self._save_last_dir("insert", path)
        at = min(self.selected) if self.selected else self.editor.page_count
        if self.editor.insert_image(at, path):
            self._render_thumbnails()
            self._update_status()
            self._log(f"已在位置 {at + 1} 插入图片")

    def _duplicate_selected(self):
        if not self.editor.page_count:
            return
        if not self.selected:
            messagebox.showinfo("提示", "请先选择要复制的页面")
            return
        indices = sorted(self.selected)
        at = max(indices) + 1
        if self.editor.duplicate_pages(indices, at):
            self.selected = set(range(at, at + len(indices)))
            self._render_thumbnails()
            self._update_status()
            self._log(f"已复制 {len(indices)} 页")

    def _insert_blank(self):
        if not self.editor.page_count:
            return
        at = min(self.selected) if self.selected else self.editor.page_count
        if self.editor.insert_blank(at):
            self._render_thumbnails()
            self._update_status()
            self._log(f"已在位置 {at + 1} 插入空白页")

    def _add_watermark(self):
        if not self.editor.page_count:
            return
        dialog = _WatermarkDialog(self)
        self.wait_window(dialog)
        if dialog.result:
            text, pos, opacity = dialog.result
            if self.editor.add_watermark(text, pos, opacity):
                self._render_thumbnails()
                self._update_status()
                self._log("已添加水印")

    def _add_page_numbers(self):
        if not self.editor.page_count:
            return
        dialog = _PageNumDialog(self)
        self.wait_window(dialog)
        if dialog.result:
            start, pos, fmt = dialog.result
            if self.editor.add_page_numbers(start, pos, fmt):
                self._render_thumbnails()
                self._update_status()
                self._log("已添加页码")

    def _edit_metadata(self):
        if not self.editor.page_count:
            return
        current = self.editor.metadata
        dialog = _MetadataDialog(self, current)
        self.wait_window(dialog)
        if dialog.result:
            if self.editor.set_metadata(dialog.result):
                self._update_status()
                self._log("元数据已更新")

    def _undo(self):
        if not self.editor.page_count:
            return
        if self.editor.undo():
            self.selected.clear()
            self._render_thumbnails()
            self._update_status()
            self._log("已撤销")

    def _toggle_select_all(self):
        if not self.editor.page_count:
            return
        n = self.editor.page_count
        if len(self.selected) == n:
            self.selected.clear()
        else:
            self.selected = set(range(n))
        self._highlight_all()
        self._update_status()

    def _invert_selection(self):
        if not self.editor.page_count:
            return
        n = self.editor.page_count
        self.selected = set(i for i in range(n) if i not in self.selected)
        self._highlight_all()
        self._update_status()

    # ── Status & Logging ─────────────────────────────────────

    def _update_status(self):
        n = self.editor.page_count
        if n == 0:
            self._status_label.config(text="就绪")
            return
        sel = len(self.selected)
        parts = [f"共 {n} 页"]
        if sel > 0:
            parts.append(f"选中 {sel} 页")
        if self.editor.modified:
            parts.append("● 未保存")
        self._status_label.config(text="  |  ".join(parts))

    def _log(self, msg, level="info"):
        if self.log_func:
            self.log_func(msg, level)

    # ── Public API ───────────────────────────────────────────

    def is_modified(self) -> bool:
        return self.editor.modified

    def is_open(self) -> bool:
        return self.editor.page_count > 0

    def cleanup(self):
        self.editor.close()
