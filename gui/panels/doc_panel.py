"""Doc panel — 文档格式转换面板（DI 化，第 11 个迁移面板）。

doc 面板特点：
  - 目标格式通过"检测格式"按钮动态填充（_detect 业务逻辑留 main.py）
  - _detect 操作 d_tgt/d_st 控件，通过 shim 访问
  - collect_params 只返回 {target}（_go 入口用于计算 ext）
  - collect_prefs 只持久化 out_dir（不持久化 target，因 target 需重新检测）
"""
from dataclasses import dataclass
from typing import Optional
import tkinter as tk
from tkinter import ttk

from app.context import AppContext, PanelContext
from gui.panels.base_panel import BasePanel

# main 模块的 D/FT/XS/SM/BODY 是可变全局（暗色主题运行时改写 D[k]）。
import main as _main


@dataclass
class DocContext(PanelContext):
    """文档格式转换面板状态。"""
    panel_key: str = "doc"

    # 转换设置
    tgt: Optional[ttk.Combobox] = None  # 目标格式（通过"检测格式"动态填充）

    # 输出目录
    out_dir_combo: Optional[ttk.Combobox] = None
    out_dir_btn: Optional[tk.Widget] = None
    out_dir_path: Optional[tk.StringVar] = None
    out_dir_label: Optional[tk.Widget] = None

    # 底部进度栏控件（_w("doc") 通过 shim 命中）
    pg: Optional[ttk.Progressbar] = None
    st: Optional[tk.Label] = None
    go: Optional[tk.Widget] = None
    ca: Optional[tk.Widget] = None


class DocPanel(BasePanel):
    panel_key = "doc"
    context_cls = DocContext

    def build(self) -> tk.Widget:
        D = _main.D
        app = self.ctx._app

        p = tk.Frame(app.content, bg=D["page"])
        self.frame = p
        app.panels["doc"] = p

        c = DocContext()
        self.context = c

        self._build_header(p)
        self._build_file_section(p)
        s = self._build_settings_card(p, c, app)
        self._build_output_dir(s, c, app)
        self._build_bottom_bar(p, c, app)

        self.ctx.register_panel("doc", c)
        return p

    # ── UI 分区构建 ─────────────────────────────────
    def _build_header(self, parent: tk.Frame) -> None:
        app = self.ctx._app
        app._hdr(parent, "文档格式转换",
                 "PDF · Word · Excel · PPT · WPS · TXT · 图片 · Markdown · EPUB · RTF · ODT")

    def _build_file_section(self, parent: tk.Frame) -> None:
        """文档文件选择区，第三参数 True 启用 doc 面板独有的"检测格式"提示。"""
        app = self.ctx._app
        exts = ("*.pdf *.docx *.doc *.wps *.xlsx *.xls *.et *.csv *.pptx *.ppt *.dps "
                "*.txt *.html *.htm *.md *.epub *.rtf *.odt "
                "*.jpg *.jpeg *.png *.bmp *.tiff *.webp")
        app._file_sec(parent, "doc",
            [("文档文件", exts), ("所有文件", "*.*")], True)

    def _build_settings_card(self, parent: tk.Frame, c: DocContext, app) -> tk.Frame:
        """构建"转换设置"卡片：提示文字 + 目标格式 Combobox + 检测格式按钮。"""
        D = _main.D
        XS = _main.XS
        SM = _main.SM

        s = app._card(parent, "转换设置")
        # 提示文字
        tk.Label(s, text="添加文件后点击「检测格式」，系统将自动列出可转换的目标格式",
                 bg=D["card"], fg=D["ink_dis"], font=XS).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        # 目标格式
        tk.Label(s, text="目标格式", bg=D["card"], fg=D["ink"], font=SM).grid(
            row=1, column=0, sticky="w")
        c.tgt = ttk.Combobox(s, values=["请先添加文件"], state="readonly", width=22)
        c.tgt.set("请先添加文件")
        c.tgt.grid(row=1, column=1, sticky="ew", padx=(4, 10))
        c.tgt.bind("<<ComboboxSelected>>", lambda e: app._update_format_hint("doc"))
        # 检测格式按钮（绑定 _detect，业务逻辑留 main.py）
        app._btn(s, "检测格式", app._detect).grid(row=1, column=2, sticky="w")
        return s

    def _build_output_dir(self, card: tk.Frame, c: DocContext, app) -> None:
        D = _main.D
        SM = _main.SM
        XS = _main.XS

        out_frame = tk.Frame(card, bg=D["card"])
        out_frame.grid(row=2, column=0, columnspan=3, sticky="ew", padx=16, pady=(8, 10))
        tk.Label(out_frame, text="输出目录", bg=D["card"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(0, 8))
        c.out_dir_combo = ttk.Combobox(out_frame, values=["与源文件同目录", "自定义目录"],
                                       state="readonly", width=14)
        c.out_dir_combo.set("与源文件同目录")
        c.out_dir_combo.pack(side=tk.LEFT)
        c.out_dir_btn = app._btn(out_frame, "浏览",
                                  lambda: app._select_out_dir("doc"), style="secondary")
        c.out_dir_btn.pack(side=tk.LEFT, padx=(8, 0))
        c.out_dir_path = tk.StringVar(value="")
        c.out_dir_label = tk.Label(out_frame, textvariable=c.out_dir_path,
                                   bg=D["card"], fg=D["ink_dis"], font=XS)
        c.out_dir_label.pack(side=tk.LEFT, padx=(8, 0))

    def _build_bottom_bar(self, parent: tk.Frame, c: DocContext, app) -> None:
        c.pg, c.st, c.go, c.ca, _ = app._bar(parent)
        c.go.configure(command=lambda: app._go("doc"))
        c.ca.configure(command=lambda: app._stop("doc"))

    # ── 参数收集（供 _go 调度使用）──────────
    def collect_params(self) -> dict:
        """返回调度层期望的参数（1 键，与 main.py:_go 的 doc 分支一致）。

        target 用于 _go 入口计算输出扩展名；执行层不读此键。
        """
        return {"target": self.context.tgt.get()}

    # ── 偏好持久化 ──────────────────────────────────
    def collect_prefs(self) -> dict:
        """返回持久化偏好（与原 _save_panel_prefs 的 doc 分支一致，2 键）。

        注意：不持久化 target —— 目标格式需重新检测（依赖源文件类型）。
        """
        c = self.context
        return {
            "out_dir_combo": c.out_dir_combo.get(),
            "out_dir_path": c.out_dir_path.get(),
        }

    def apply_prefs(self, prefs: dict) -> None:
        """从持久化 prefs 恢复控件状态（与原 _load_panel_prefs 的 doc 分支一致）。"""
        c = self.context
        if prefs.get("out_dir_combo"): c.out_dir_combo.set(prefs["out_dir_combo"])
        if prefs.get("out_dir_path"):  c.out_dir_path.set(prefs["out_dir_path"])
