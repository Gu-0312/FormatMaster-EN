"""Image panel — 图片格式转换面板（DI 化，第 10 个迁移面板）。

按 compress/gif 模板执行：把 main.py:_p_image 的 UI 构建逻辑搬到这里，
状态从 self.i_xxx 迁移到独立的 ImageContext dataclass。
"""
from dataclasses import dataclass
from typing import Optional
import tkinter as tk
from tkinter import ttk

from app.context import AppContext, PanelContext
from gui.panels.base_panel import BasePanel
from utils.config import SUPPORTED_IMAGE

# main 模块的 D/FT/XS/SM/BODY 是可变全局（暗色主题运行时改写 D[k]）。
import main as _main


# 预置值（与 main.py:_p_image 原始值一致）
QUALITY_VALUES = ["100（无损）", "95（高质量）", "85（中等）", "70（低质量）", "50（压缩）"]
SIZE_VALUES = ["原始大小", "50%", "25%", "200%"]
ROTATE_VALUES = ["0°", "90°", "180°", "270°"]
CROP_VALUES = ["原始比例", "裁剪为正方形"]
WATERMARK_POS_VALUES = ["右下角", "左下角", "右上角", "左上角", "居中"]


@dataclass
class ImageContext(PanelContext):
    """图片格式转换面板状态。"""
    panel_key: str = "image"

    # 输出设置（卡片 row 0-2）
    fmt: Optional[ttk.Combobox] = None        # 目标格式
    q: Optional[ttk.Combobox] = None         # 质量
    sz: Optional[ttk.Combobox] = None        # 缩放
    rotate: Optional[ttk.Combobox] = None    # 旋转
    crop: Optional[ttk.Combobox] = None      # 裁剪
    grayscale: Optional[tk.BooleanVar] = None # 灰度

    # 水印处理（卡片 row 4-5）
    watermark: Optional[tk.Entry] = None          # 水印文字
    watermark_pos: Optional[ttk.Combobox] = None  # 水印位置

    # 输出目录
    out_dir_combo: Optional[ttk.Combobox] = None
    out_dir_btn: Optional[tk.Widget] = None
    out_dir_path: Optional[tk.StringVar] = None
    out_dir_label: Optional[tk.Widget] = None

    # 底部进度栏控件（_w("image") 通过 shim 命中）
    pg: Optional[ttk.Progressbar] = None
    st: Optional[tk.Label] = None
    go: Optional[tk.Widget] = None
    ca: Optional[tk.Widget] = None


class ImagePanel(BasePanel):
    panel_key = "image"
    context_cls = ImageContext

    def build(self) -> tk.Widget:
        D = _main.D
        app = self.ctx._app

        p = tk.Frame(app.content, bg=D["page"])
        self.frame = p
        app.panels["image"] = p

        c = ImageContext()
        self.context = c

        self._build_header(p)
        self._build_file_section(p)
        s = self._build_settings_card(p, c, app)
        self._build_format_rows(s, c, app)
        self._build_watermark_section(s, c)
        self._build_output_dir(s, c, app)
        self._build_bottom_bar(p, c, app)

        self.ctx.register_panel("image", c)
        return p

    # ── UI 分区构建 ─────────────────────────────────
    def _build_header(self, parent: tk.Frame) -> None:
        app = self.ctx._app
        app._hdr(parent, "图片格式转换", "JPG · PNG · BMP · GIF · TIFF · WEBP · ICO 格式互转")

    def _build_file_section(self, parent: tk.Frame) -> None:
        app = self.ctx._app
        app._file_sec(parent, "image", [
            ("图片文件", "*.jpg *.jpeg *.png *.bmp *.gif *.tiff *.webp *.ico *.tga"),
            ("所有文件", "*.*"),
        ])

    def _build_settings_card(self, parent: tk.Frame, c: ImageContext, app) -> tk.Frame:
        """创建"输出设置"卡片，配置列权重，返回卡片 frame 供后续子区挂载。"""
        D = _main.D
        s = app._card(parent, "输出设置")
        s.columnconfigure(1, weight=1)
        s.columnconfigure(3, weight=1)
        return s

    def _build_format_rows(self, card: tk.Frame, c: ImageContext, app) -> None:
        """构建格式/质量/缩放/旋转/裁剪/灰度 6 个设置项（row 0-2，4 列网格）。"""
        D = _main.D
        SM = _main.SM

        # row 0: 目标格式 + 质量
        tk.Label(card, text="目标格式", bg=D["card"], fg=D["ink"], font=SM).grid(
            row=0, column=0, sticky="w", padx=(10, 8), pady=8)
        c.fmt = ttk.Combobox(card, values=list(SUPPORTED_IMAGE.keys()),
                             state="readonly", width=14)
        c.fmt.set("PNG")
        c.fmt.grid(row=0, column=1, sticky="ew", padx=(0, 16), pady=8)
        c.fmt.bind("<<ComboboxSelected>>", lambda e: app._update_format_hint("image"))

        tk.Label(card, text="质量", bg=D["card"], fg=D["ink"], font=SM).grid(
            row=0, column=2, sticky="w", padx=(10, 8), pady=8)
        c.q = ttk.Combobox(card, values=QUALITY_VALUES, state="readonly", width=14)
        c.q.set("95（高质量）")
        c.q.grid(row=0, column=3, sticky="ew", padx=(0, 10), pady=8)

        # row 1: 缩放 + 旋转
        tk.Label(card, text="缩放", bg=D["card"], fg=D["ink"], font=SM).grid(
            row=1, column=0, sticky="w", padx=(10, 8), pady=8)
        c.sz = ttk.Combobox(card, values=SIZE_VALUES, state="readonly", width=14)
        c.sz.set("原始大小")
        c.sz.grid(row=1, column=1, sticky="ew", padx=(0, 16), pady=8)

        tk.Label(card, text="旋转", bg=D["card"], fg=D["ink"], font=SM).grid(
            row=1, column=2, sticky="w", padx=(10, 8), pady=8)
        c.rotate = ttk.Combobox(card, values=ROTATE_VALUES, state="readonly", width=14)
        c.rotate.set("0°")
        c.rotate.grid(row=1, column=3, sticky="ew", padx=(0, 10), pady=8)

        # row 2: 裁剪 + 灰度
        tk.Label(card, text="裁剪", bg=D["card"], fg=D["ink"], font=SM).grid(
            row=2, column=0, sticky="w", padx=(10, 8), pady=8)
        c.crop = ttk.Combobox(card, values=CROP_VALUES, state="readonly", width=14)
        c.crop.set("原始比例")
        c.crop.grid(row=2, column=1, sticky="ew", padx=(0, 16), pady=8)

        c.grayscale = tk.BooleanVar(value=False)
        tk.Checkbutton(card, text="转为黑白（灰度）", variable=c.grayscale,
                       bg=D["card"], fg=D["ink"], font=SM).grid(
            row=2, column=2, columnspan=2, sticky="w", padx=10, pady=8)

    def _build_watermark_section(self, card: tk.Frame, c: ImageContext) -> None:
        """构建水印处理子区：分隔线 + 标题 + 水印文字 + 水印位置（row 3-5）。"""
        D = _main.D
        BODY = _main.BODY
        SM = _main.SM
        FT = _main.FT

        # 分隔线
        separator = tk.Frame(card, bg=D["border"], height=1)
        separator.grid(row=3, column=0, columnspan=4, sticky="ew", padx=10, pady=10)

        # 水印标题
        tk.Label(card, text="水印处理", bg=D["card"], fg=D["ink"],
                 font=(FT, 9, "bold")).grid(
            row=4, column=0, columnspan=4, sticky="w", padx=10, pady=(4, 4))

        # row 5: 水印文字 + 水印位置
        tk.Label(card, text="水印文字", bg=D["card"], fg=D["ink"], font=SM).grid(
            row=5, column=0, sticky="w", padx=(10, 8), pady=8)
        c.watermark = tk.Entry(card, font=BODY, bg=D["input_bg"], fg=D["ink"],
                               insertbackground=D["ink"], relief="flat",
                               highlightthickness=1, highlightbackground=D["input_bd"],
                               highlightcolor=D["accent"], width=16)
        c.watermark.grid(row=5, column=1, sticky="ew", padx=(0, 16), pady=8)

        tk.Label(card, text="水印位置", bg=D["card"], fg=D["ink"], font=SM).grid(
            row=5, column=2, sticky="w", padx=(10, 8), pady=8)
        c.watermark_pos = ttk.Combobox(card, values=WATERMARK_POS_VALUES,
                                       state="readonly", width=14)
        c.watermark_pos.set("右下角")
        c.watermark_pos.grid(row=5, column=3, sticky="ew", padx=(0, 10), pady=8)

    def _build_output_dir(self, card: tk.Frame, c: ImageContext, app) -> None:
        D = _main.D
        SM = _main.SM
        XS = _main.XS

        out_frame = tk.Frame(card, bg=D["card"])
        out_frame.grid(row=6, column=0, columnspan=4, sticky="ew", padx=10, pady=(8, 10))
        tk.Label(out_frame, text="输出目录", bg=D["card"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(0, 8))
        c.out_dir_combo = ttk.Combobox(out_frame, values=["与源文件同目录", "自定义目录"],
                                       state="readonly", width=14)
        c.out_dir_combo.set("与源文件同目录")
        c.out_dir_combo.pack(side=tk.LEFT)
        c.out_dir_btn = app._btn(out_frame, "浏览",
                                  lambda: app._select_out_dir("image"), style="secondary")
        c.out_dir_btn.pack(side=tk.LEFT, padx=(8, 0))
        c.out_dir_path = tk.StringVar(value="")
        c.out_dir_label = tk.Label(out_frame, textvariable=c.out_dir_path,
                                   bg=D["card"], fg=D["ink_dis"], font=XS)
        c.out_dir_label.pack(side=tk.LEFT, padx=(8, 0))

    def _build_bottom_bar(self, parent: tk.Frame, c: ImageContext, app) -> None:
        c.pg, c.st, c.go, c.ca, _ = app._bar(parent)
        c.go.configure(command=lambda: app._go("image"))
        c.ca.configure(command=lambda: app._stop("image"))

    # ── 参数收集（供 _go 调度使用）──────────
    def collect_params(self) -> dict:
        """返回调度层期望的参数（8 键，与 main.py:_go 的 image 分支一致）。

        _run_task_general 的 image 分支读 module_params.get() 取这 8 键。
        out_dir 不在此处收集（_go 通过 attr_map 单独处理输出目录）。
        """
        c = self.context
        return {
            "fmt": c.fmt.get(),
            "quality": c.q.get(),
            "size": c.sz.get(),
            "watermark": c.watermark.get(),
            "watermark_pos": c.watermark_pos.get(),
            "rotate": c.rotate.get(),
            "crop": c.crop.get(),
            "grayscale": c.grayscale.get(),
        }

    # ── 偏好持久化 ──────────────────────────────────
    def collect_prefs(self) -> dict:
        """返回持久化偏好（与原 _save_panel_prefs 的 image 分支一致，8 键）。"""
        c = self.context
        return {
            "fmt": c.fmt.get(),
            "quality": c.q.get(),
            "size": c.sz.get(),
            "rotate": c.rotate.get(),
            "crop": c.crop.get(),
            "grayscale": c.grayscale.get(),
            "out_dir_combo": c.out_dir_combo.get(),
            "out_dir_path": c.out_dir_path.get(),
        }

    def apply_prefs(self, prefs: dict) -> None:
        """从持久化 prefs 恢复控件状态（与原 _load_panel_prefs 的 image 分支一致）。"""
        c = self.context
        if prefs.get("fmt"):       c.fmt.set(prefs["fmt"])
        if prefs.get("quality"):   c.q.set(prefs["quality"])
        if prefs.get("size"):      c.sz.set(prefs["size"])
        if prefs.get("rotate"):    c.rotate.set(prefs["rotate"])
        if prefs.get("crop"):      c.crop.set(prefs["crop"])
        if "grayscale" in prefs:    c.grayscale.set(prefs["grayscale"])
        if prefs.get("out_dir_combo"): c.out_dir_combo.set(prefs["out_dir_combo"])
        if prefs.get("out_dir_path"):  c.out_dir_path.set(prefs["out_dir_path"])
