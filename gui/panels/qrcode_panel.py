"""QRCode panel — 二维码生成器面板（DI 化，第 15 个迁移面板）。

特殊面板（与 detect/download 同类）：
  - go 按钮绑 _qr_generate（不是 _go("qrcode")），走自己的生成流程
  - 无 collect_params（qrcode 不经 _go 参数收集）
  - 5 个业务逻辑方法（_qr_type_changed/_qr_toggle_eye/_qr_generate/
    _qr_cancel/_qr_save）留在 main.py，通过 shim 访问 qr_ 控件
  - 3 个非 UI 状态（_qr_eye_visible/_qr_photo/_qr_cancelled）是 self._qr_*
    私有属性，留 main.py，不迁移到 QrcodeContext
  - qr_status = qr_st（复用统一状态标签的别名），在 _build_bottom_bar 中设置

只迁移 UI 构建 + 偏好持久化（5 键）。
"""
from dataclasses import dataclass
from typing import Optional
import tkinter as tk
from tkinter import ttk

from app.context import AppContext, PanelContext
from gui.panels.base_panel import BasePanel

# main 模块的 D/FT/XS/SM/BODY 是可变全局（暗色主题运行时改写 D[k]）。
import main as _main

# 预置值（与 main.py:_p_qrcode 原始值一致）
TYPE_VALUES = ["文本", "网址", "WiFi", "名片"]
SIZE_VALUES = ["200", "300", "400", "500", "600"]
BORDER_VALUES = ["1", "2", "4", "6"]
DEFAULT_TYPE = "文本"
DEFAULT_SIZE = "400"
DEFAULT_BORDER = "4"
DEFAULT_FG = "#000000"
DEFAULT_BG = "#FFFFFF"
DEFAULT_TEXT = "Hello World"


@dataclass
class QrcodeContext(PanelContext):
    """二维码生成器面板状态。"""
    panel_key: str = "qrcode"

    # 内容设置
    type: Optional[ttk.Combobox] = None       # 内容类型
    text: Optional[tk.Text] = None            # 文本输入

    # WiFi 选项（默认隐藏，通过 _qr_type_changed 控制显隐）
    wifi_frame: Optional[tk.Frame] = None     # WiFi 选项容器
    wifi_ssid: Optional[tk.Entry] = None      # WiFi 名称
    wifi_pass: Optional[tk.Entry] = None      # WiFi 密码
    eye_btn: Optional[tk.Button] = None        # 密码显示/隐藏切换按钮

    # 外观设置
    size: Optional[ttk.Combobox] = None       # 尺寸
    border: Optional[ttk.Combobox] = None     # 边距
    fg: Optional[tk.StringVar] = None         # 前景色
    fg_entry: Optional[tk.Entry] = None       # 前景色输入框
    bg: Optional[tk.StringVar] = None         # 背景色
    bg_entry: Optional[tk.Entry] = None        # 背景色输入框

    # 预览区
    preview_label: Optional[tk.Label] = None  # 预览标签

    # 底部进度栏控件（_w("qrcode") 通过 shim 命中）
    pg: Optional[ttk.Progressbar] = None
    st: Optional[tk.Label] = None
    go: Optional[tk.Widget] = None
    ca: Optional[tk.Widget] = None
    status: Optional[tk.Label] = None  # qr_status = qr_st 复用别名


class QrcodePanel(BasePanel):
    panel_key = "qrcode"
    context_cls = QrcodeContext

    def build(self) -> tk.Widget:
        D = _main.D
        app = self.ctx._app

        p = tk.Frame(app.content, bg=D["page"])
        self.frame = p
        app.panels["qrcode"] = p

        c = QrcodeContext()
        self.context = c

        self._build_header(p, app)
        s = self._build_content_card(p, c, app)
        self._build_wifi_section(s, c, app)
        self._build_appearance_section(s, c)
        self._build_preview_section(p, c)
        self._build_bottom_bar(p, c, app)
        self._build_save_button(p, app)

        self.ctx.register_panel("qrcode", c)
        return p

    # ── UI 分区构建 ─────────────────────────────────
    def _build_header(self, parent: tk.Frame, app) -> None:
        app._hdr(parent, "二维码生成器", "将文本、链接、联系方式等生成二维码图片")

    def _build_content_card(self, parent: tk.Frame, c: QrcodeContext, app) -> tk.Frame:
        """构建"内容设置"卡片：内容类型 + 文本输入。"""
        D = _main.D
        SM = _main.SM
        BODY = _main.BODY

        s = app._card(parent, "内容设置")
        # 内容类型
        tk.Label(s, text="内容类型", bg=D["card"], fg=D["ink"], font=SM).grid(
            row=0, column=0, sticky="w")
        c.type = ttk.Combobox(s, values=TYPE_VALUES, state="readonly", width=12)
        c.type.set(DEFAULT_TYPE)
        c.type.grid(row=0, column=1, sticky="w", padx=(8, 0))
        c.type.bind("<<ComboboxSelected>>", lambda e: app._qr_type_changed())

        # 文本输入
        tk.Label(s, text="内容", bg=D["card"], fg=D["ink"], font=SM).grid(
            row=1, column=0, sticky="nw", pady=(8, 0))
        c.text = tk.Text(s, font=BODY, bg=D["input_bg"], fg=D["ink"],
                        relief="flat", highlightthickness=1, highlightbackground=D["input_bd"],
                        highlightcolor=D["accent"], height=3, width=40, wrap=tk.WORD)
        c.text.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=(8, 0))
        c.text.insert("1.0", DEFAULT_TEXT)
        return s

    def _build_wifi_section(self, card: tk.Frame, c: QrcodeContext, app) -> None:
        """WiFi 选项区（默认隐藏，通过 _qr_type_changed 控制显隐）。"""
        D = _main.D
        SM = _main.SM
        BODY = _main.BODY

        c.wifi_frame = tk.Frame(card, bg=D["card"])
        wifi_row = tk.Frame(c.wifi_frame, bg=D["card"])
        wifi_row.pack(fill=tk.X, pady=(4, 0))
        tk.Label(wifi_row, text="WiFi名称", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT)
        c.wifi_ssid = tk.Entry(wifi_row, font=BODY, bg=D["input_bg"], fg=D["ink"],
                               insertbackground=D["ink"], relief="flat", highlightthickness=1,
                               highlightbackground=D["input_bd"],
                               highlightcolor=D["accent"], width=20)
        c.wifi_ssid.pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(wifi_row, text="密码", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(16, 0))
        c.wifi_pass = tk.Entry(wifi_row, font=BODY, bg=D["input_bg"], fg=D["ink"],
                               insertbackground=D["ink"], relief="flat", highlightthickness=1,
                               highlightbackground=D["input_bd"], highlightcolor=D["accent"],
                               width=20, show="*")
        c.wifi_pass.pack(side=tk.LEFT, padx=(8, 0))
        # 密码显示/隐藏按钮（绑定 _qr_toggle_eye）
        c.eye_btn = tk.Button(wifi_row, text="👁", font=("Segoe UI Symbol", 10),
                              bg=D["card"], relief="flat", bd=0, cursor="hand2",
                              command=app._qr_toggle_eye)
        c.eye_btn.pack(side=tk.LEFT, padx=(2, 0))

    def _build_appearance_section(self, card: tk.Frame, c: QrcodeContext) -> None:
        """外观设置：尺寸 + 边距 + 前景色 + 背景色。"""
        D = _main.D
        SM = _main.SM
        BODY = _main.BODY

        qr_style = tk.Frame(card, bg=D["card"])
        qr_style.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        # 尺寸
        tk.Label(qr_style, text="尺寸", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT)
        c.size = ttk.Combobox(qr_style, values=SIZE_VALUES, state="readonly", width=8)
        c.size.set(DEFAULT_SIZE)
        c.size.pack(side=tk.LEFT, padx=(8, 0))
        # 边距
        tk.Label(qr_style, text="边距", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(16, 0))
        c.border = ttk.Combobox(qr_style, values=BORDER_VALUES, state="readonly", width=6)
        c.border.set(DEFAULT_BORDER)
        c.border.pack(side=tk.LEFT, padx=(8, 0))
        # 前景色
        tk.Label(qr_style, text="前景色", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(16, 0))
        c.fg = tk.StringVar(value=DEFAULT_FG)
        c.fg_entry = tk.Entry(qr_style, textvariable=c.fg, font=BODY, width=10,
                              bg=D["input_bg"], relief="flat", highlightthickness=1,
                              highlightbackground=D["input_bd"])
        c.fg_entry.pack(side=tk.LEFT, padx=(4, 0))
        # 背景色
        tk.Label(qr_style, text="背景色", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(16, 0))
        c.bg = tk.StringVar(value=DEFAULT_BG)
        c.bg_entry = tk.Entry(qr_style, textvariable=c.bg, font=BODY, width=10,
                              bg=D["input_bg"], relief="flat", highlightthickness=1,
                              highlightbackground=D["input_bd"])
        c.bg_entry.pack(side=tk.LEFT, padx=(4, 0))

    def _build_preview_section(self, parent: tk.Frame, c: QrcodeContext) -> None:
        """预览区：带边框的容器 + 预览标题 + 预览标签。"""
        D = _main.D
        FT = _main.FT
        BODY = _main.BODY

        preview_frame = tk.Frame(parent, bg=D["card"],
                                 highlightbackground=D["border"], highlightthickness=1)
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=(12, 0))
        tk.Label(preview_frame, text="预览", bg=D["card"], fg=D["ink_sec"],
                 font=(FT, 9, "bold")).pack(anchor=tk.W, padx=12, pady=(8, 4))
        c.preview_label = tk.Label(preview_frame, text="点击「生成二维码」预览",
                                   bg=D["card"], fg=D["ink_dis"], font=BODY)
        c.preview_label.pack(expand=True, pady=(0, 12))

    def _build_bottom_bar(self, parent: tk.Frame, c: QrcodeContext, app) -> None:
        """底部进度栏：go 绑 _qr_generate（不是 _go），ca 绑 _qr_cancel。"""
        c.pg, c.st, c.go, c.ca, _ = app._bar(parent)
        c.go.configure(text="生成二维码", command=app._qr_generate)
        c.ca.configure(command=app._qr_cancel, state=tk.DISABLED)
        c.status = c.st  # qr_status = qr_st 复用统一状态标签

    def _build_save_button(self, parent: tk.Frame, app) -> None:
        """底部保存按钮：保存为图片。"""
        D = _main.D
        bottom_bar = tk.Frame(parent, bg=D["page"])
        bottom_bar.pack(fill=tk.X, pady=(8, 0))
        app._btn(bottom_bar, "保存为图片", app._qr_save, "primary", padx=24).pack(side=tk.RIGHT)

    # ── 偏好持久化 ──────────────────────────────────
    def collect_prefs(self) -> dict:
        """返回持久化偏好（与原 _save_panel_prefs 的 qrcode 分支一致，5 键）。"""
        c = self.context
        return {
            "qr_type": c.type.get(),
            "qr_size": c.size.get(),
            "qr_border": c.border.get(),
            "qr_fg": c.fg.get(),
            "qr_bg": c.bg.get(),
        }

    def apply_prefs(self, prefs: dict) -> None:
        """从持久化 prefs 恢复控件状态（与原 _load_panel_prefs 的 qrcode 分支一致）。"""
        c = self.context
        if prefs.get("qr_type"):   c.type.set(prefs["qr_type"])
        if prefs.get("qr_size"):   c.size.set(prefs["qr_size"])
        if prefs.get("qr_border"): c.border.set(prefs["qr_border"])
        if prefs.get("qr_fg"):     c.fg.set(prefs["qr_fg"])
        if prefs.get("qr_bg"):     c.bg.set(prefs["qr_bg"])
