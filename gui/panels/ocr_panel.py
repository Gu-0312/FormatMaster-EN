"""OCR panel — OCR 文字识别面板（DI 化，第 14 个迁移面板）。

标准模板（与 compress/crop 同构），但含结果文本区 + 导出/复制按钮。
_ocr_export_txt / _ocr_copy 业务逻辑方法留 main.py，通过 shim 访问 ocr_text。
"""
from dataclasses import dataclass
from typing import Optional
import tkinter as tk
from tkinter import ttk

from app.context import AppContext, PanelContext
from gui.panels.base_panel import BasePanel

# main 模块的 D/FT/XS/SM/BODY 是可变全局（暗色主题运行时改写 D[k]）。
import main as _main

# 预置值（与 main.py:_p_ocr 原始值一致）
OCR_LANGS = ["chi_sim+eng", "chi_sim", "eng", "jpn", "kor", "chi_tra+eng", "chi_tra", "eng+chi_sim"]
DEFAULT_LANG = "chi_sim+eng"


@dataclass
class OcrContext(PanelContext):
    """OCR 文字识别面板状态。"""
    panel_key: str = "ocr"

    # 识别设置
    lang: Optional[ttk.Combobox] = None  # 识别语言

    # 结果文本区
    export_txt: Optional[tk.Button] = None   # 导出 TXT 按钮
    copy_btn: Optional[tk.Button] = None     # 复制到剪贴板按钮
    text: Optional[tk.Text] = None           # 识别结果显示区

    # 输出目录
    out_dir_combo: Optional[ttk.Combobox] = None
    out_dir_btn: Optional[tk.Widget] = None
    out_dir_path: Optional[tk.StringVar] = None
    out_dir_label: Optional[tk.Widget] = None

    # 底部进度栏控件（_w("ocr") 通过 shim 命中）
    pg: Optional[ttk.Progressbar] = None
    st: Optional[tk.Label] = None
    go: Optional[tk.Widget] = None
    ca: Optional[tk.Widget] = None


class OcrPanel(BasePanel):
    panel_key = "ocr"
    context_cls = OcrContext

    def build(self) -> tk.Widget:
        D = _main.D
        app = self.ctx._app

        p = tk.Frame(app.content, bg=D["page"])
        self.frame = p
        app.panels["ocr"] = p

        c = OcrContext()
        self.context = c

        self._build_header(p, app)
        self._build_file_section(p, app)
        s = self._build_settings_card(p, c)
        self._build_result_section(p, c, app)
        self._build_output_dir(p, c, app)
        self._build_bottom_bar(p, c, app)

        self.ctx.register_panel("ocr", c)
        return p

    # ── UI 分区构建 ─────────────────────────────────
    def _build_header(self, parent: tk.Frame, app) -> None:
        app._hdr(parent, "OCR 文字识别", "从图片或PDF中识别文字，支持批量处理")

    def _build_file_section(self, parent: tk.Frame, app) -> None:
        app._file_sec(parent, "ocr",
            [("图片/PDF", "*.jpg *.jpeg *.png *.bmp *.webp *.tiff *.pdf"),
             ("所有文件", "*.*")])

    def _build_settings_card(self, parent: tk.Frame, c: OcrContext) -> tk.Frame:
        """构建"识别设置"卡片：识别语言 Combobox + 语言说明。"""
        D = _main.D
        SM = _main.SM
        XS = _main.XS

        s = self.ctx._app._card(parent, "识别设置")
        tk.Label(s, text="识别语言", bg=D["card"], fg=D["ink"], font=SM).grid(
            row=0, column=0, sticky="w")
        c.lang = ttk.Combobox(s, values=OCR_LANGS, state="readonly", width=20)
        c.lang.set(DEFAULT_LANG)
        c.lang.grid(row=0, column=1, sticky="w", padx=(8, 0))
        tk.Label(s, text="chi_sim=简体中文  eng=英文  jpn=日文  kor=韩文",
                 bg=D["card"], fg=D["ink_dis"], font=XS).grid(
            row=0, column=2, sticky="w", padx=(8, 0))
        return s

    def _build_result_section(self, parent: tk.Frame, c: OcrContext, app) -> None:
        """识别结果区：标题 + 导出/复制按钮 + 文本显示区（带滚动条）。"""
        D = _main.D
        FT = _main.FT
        SM = _main.SM

        result_frame = tk.Frame(parent, bg=D["card"])
        result_frame.pack(fill=tk.X, padx=16, pady=(12, 0))

        result_header = tk.Frame(result_frame, bg=D["card"])
        result_header.pack(fill=tk.X)
        tk.Label(result_header, text="识别结果", bg=D["card"], fg=D["ink_sec"],
                 font=(FT, 9, "bold")).pack(side=tk.LEFT)

        # 导出/复制按钮（绑定 main.py 业务逻辑方法）
        c.export_txt = tk.Button(result_header, text="导出 TXT", font=SM,
                                 bg=D["card"], fg=D["accent"], relief="flat",
                                 cursor="hand2", bd=0, command=app._ocr_export_txt)
        c.export_txt.pack(side=tk.RIGHT, padx=(8, 0))
        c.copy_btn = tk.Button(result_header, text="复制到剪贴板", font=SM,
                               bg=D["card"], fg=D["accent"], relief="flat",
                               cursor="hand2", bd=0, command=app._ocr_copy)
        c.copy_btn.pack(side=tk.RIGHT, padx=(8, 0))

        # 文本显示区
        text_container = tk.Frame(result_frame, bg=D["border"], padx=1, pady=1)
        text_container.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        c.text = tk.Text(text_container, font=("Microsoft YaHei UI", 10),
                        bg=D["input_bg"], fg=D["ink"],
                        relief="flat", bd=0, padx=8, pady=8,
                        height=6, wrap=tk.WORD)
        text_scroll = ttk.Scrollbar(text_container, orient=tk.VERTICAL,
                                    command=c.text.yview)
        c.text.configure(yscrollcommand=text_scroll.set)
        c.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        text_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_output_dir(self, parent: tk.Frame, c: OcrContext, app) -> None:
        D = _main.D
        SM = _main.SM
        XS = _main.XS

        out_dir_frame = tk.Frame(parent, bg=D["page"])
        out_dir_frame.pack(fill=tk.X, pady=(12, 0))
        tk.Label(out_dir_frame, text="输出目录", bg=D["page"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(0, 8))
        c.out_dir_combo = ttk.Combobox(out_dir_frame, values=["与源文件同目录", "自定义目录"],
                                       state="readonly", width=14)
        c.out_dir_combo.set("与源文件同目录")
        c.out_dir_combo.pack(side=tk.LEFT)
        c.out_dir_btn = app._btn(out_dir_frame, "浏览",
                                  lambda: app._select_out_dir("ocr"), style="secondary")
        c.out_dir_btn.pack(side=tk.LEFT, padx=(8, 0))
        c.out_dir_path = tk.StringVar(value="")
        c.out_dir_label = tk.Label(out_dir_frame, textvariable=c.out_dir_path,
                                   bg=D["page"], fg=D["ink_dis"], font=XS)
        c.out_dir_label.pack(side=tk.LEFT, padx=(8, 0))

    def _build_bottom_bar(self, parent: tk.Frame, c: OcrContext, app) -> None:
        c.pg, c.st, c.go, c.ca, _ = app._bar(parent)
        c.go.configure(text="开始识别", command=lambda: app._go("ocr"))
        c.ca.configure(command=lambda: app._stop("ocr"))

    # ── 参数收集（供 _go 调度使用）──────────
    def collect_params(self) -> dict:
        """返回调度层期望的参数（1 键，与 main.py:_go 的 ocr 分支一致）。"""
        return {"lang": self.context.lang.get()}

    # ── 偏好持久化 ──────────────────────────────────
    def collect_prefs(self) -> dict:
        """返回持久化偏好（与原 _save_panel_prefs 的 ocr 分支一致，3 键）。"""
        c = self.context
        return {
            "lang": c.lang.get(),
            "out_dir_combo": c.out_dir_combo.get(),
            "out_dir_path": c.out_dir_path.get(),
        }

    def apply_prefs(self, prefs: dict) -> None:
        """从持久化 prefs 恢复控件状态（与原 _load_panel_prefs 的 ocr 分支一致）。"""
        c = self.context
        if prefs.get("lang"):         c.lang.set(prefs["lang"])
        if prefs.get("out_dir_combo"): c.out_dir_combo.set(prefs["out_dir_combo"])
        if prefs.get("out_dir_path"):  c.out_dir_path.set(prefs["out_dir_path"])
