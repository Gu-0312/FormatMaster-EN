"""CompressImg panel — 图片压缩面板（DI 化，第 8 个迁移面板）。

按 compress/gif 模板执行：把 main.py:_p_compress_img 的 UI 构建逻辑搬到这里，
状态从 self.ci_xxx 迁移到独立的 CompressImgContext dataclass。
"""
from dataclasses import dataclass
from typing import Optional
import tkinter as tk
from tkinter import ttk

from app.context import AppContext, PanelContext
from gui.panels.base_panel import BasePanel

# main 模块的 D/FT/XS/SM/BODY 是可变全局（暗色主题运行时改写 D[k]）。
import main as _main


# 预置值（与 main.py:_p_compress_img 原始值一致）
QUALITY_VALUES = ["95", "85", "75", "60", "50", "40", "30"]
SIZE_VALUES = ["不限制", "1920x1080", "1280x720", "800x600"]


@dataclass
class CompressImgContext(PanelContext):
    """图片压缩面板状态。"""
    panel_key: str = "compress_img"

    # 压缩设置
    q: Optional[ttk.Combobox] = None    # 输出质量
    sz: Optional[ttk.Combobox] = None   # 最大分辨率

    # 输出目录
    out_dir_combo: Optional[ttk.Combobox] = None
    out_dir_btn: Optional[tk.Widget] = None
    out_dir_path: Optional[tk.StringVar] = None
    out_dir_label: Optional[tk.Widget] = None

    # 底部进度栏控件（_w("compress_img") 通过 shim 命中）
    pg: Optional[ttk.Progressbar] = None
    st: Optional[tk.Label] = None
    go: Optional[tk.Widget] = None
    ca: Optional[tk.Widget] = None


class CompressImgPanel(BasePanel):
    panel_key = "compress_img"
    context_cls = CompressImgContext

    def build(self) -> tk.Widget:
        D = _main.D
        app = self.ctx._app

        p = tk.Frame(app.content, bg=D["page"])
        self.frame = p
        app.panels["compress_img"] = p

        c = CompressImgContext()
        self.context = c

        self._build_header(p)
        self._build_file_section(p)
        self._build_settings_card(p, c, app)
        self._build_bottom_bar(p, c, app)

        self.ctx.register_panel("compress_img", c)
        return p

    def _build_header(self, parent: tk.Frame) -> None:
        app = self.ctx._app
        app._hdr(parent, "图片压缩", "批量压缩图片体积，保持格式不变，支持限制最大分辨率")

    def _build_file_section(self, parent: tk.Frame) -> None:
        app = self.ctx._app
        app._file_sec(parent, "compress_img", [
            ("图片文件", "*.jpg *.jpeg *.png *.bmp *.webp *.tiff"),
            ("所有文件", "*.*"),
        ])

    def _build_settings_card(self, parent: tk.Frame, c: CompressImgContext, app) -> None:
        s = app._card(parent, "压缩设置")
        c.q = app._row(s, "输出质量", QUALITY_VALUES, "75")
        c.sz = app._row(s, "最大分辨率", SIZE_VALUES, "不限制")
        self._build_output_dir(s, c, app)

    def _build_output_dir(self, card: tk.Frame, c: CompressImgContext, app) -> None:
        D = _main.D
        SM = _main.SM
        XS = _main.XS

        out_frame = tk.Frame(card, bg=D["card"])
        out_frame.grid(row=2, column=0, columnspan=4, sticky="ew", padx=16, pady=(8, 10))
        tk.Label(out_frame, text="输出目录", bg=D["card"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(0, 8))
        c.out_dir_combo = ttk.Combobox(out_frame, values=["与源文件同目录", "自定义目录"],
                                       state="readonly", width=14)
        c.out_dir_combo.set("与源文件同目录")
        c.out_dir_combo.pack(side=tk.LEFT)
        c.out_dir_btn = app._btn(out_frame, "浏览",
                                  lambda: app._select_out_dir("compress_img"), style="secondary")
        c.out_dir_btn.pack(side=tk.LEFT, padx=(8, 0))
        c.out_dir_path = tk.StringVar(value="")
        c.out_dir_label = tk.Label(out_frame, textvariable=c.out_dir_path,
                                   bg=D["card"], fg=D["ink_dis"], font=XS)
        c.out_dir_label.pack(side=tk.LEFT, padx=(8, 0))

    def _build_bottom_bar(self, parent: tk.Frame, c: CompressImgContext, app) -> None:
        c.pg, c.st, c.go, c.ca, _ = app._bar(parent)
        c.go.configure(command=lambda: app._go("compress_img"))
        c.ca.configure(command=lambda: app._stop("compress_img"))

    # ── 参数收集（供 _go 调度使用）──────────
    def collect_params(self) -> dict:
        """返回调度层期望的参数（2 键，与 main.py:_go 的 compress_img 分支一致）。"""
        c = self.context
        return {
            "quality": c.q.get(),
            "size": c.sz.get(),
        }

    # ── 偏好持久化 ──────────────────────────────────
    def collect_prefs(self) -> dict:
        c = self.context
        return {
            "quality": c.q.get(),
            "size": c.sz.get(),
            "out_dir_combo": c.out_dir_combo.get(),
            "out_dir_path": c.out_dir_path.get(),
        }

    def apply_prefs(self, prefs: dict) -> None:
        c = self.context
        if prefs.get("quality"):       c.q.set(prefs["quality"])
        if prefs.get("size"):          c.sz.set(prefs["size"])
        if prefs.get("out_dir_combo"): c.out_dir_combo.set(prefs["out_dir_combo"])
        if prefs.get("out_dir_path"):  c.out_dir_path.set(prefs["out_dir_path"])
