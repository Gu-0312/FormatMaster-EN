"""Detect panel — 格式检测面板（DI 化，第 9 个迁移面板）。

与前面面板不同，detect 是交互式文件检测器：
  - go 按钮绑定 _detect_start（不是 _go("detect")），走自己的检测流程
  - 无 collect_params（detect 不经 _go 参数收集）
  - 大量业务逻辑方法（_detect_start/_detect_stop/_detect_scan_thread/
    _detect_apply_results/_detect_clear/_detect_batch_convert/
    _detect_toggle_all/_detect_browse）留在 main.py，通过 shim 访问 detect_ 控件

本面板只迁移 UI 构建（Canvas 滚动结果区 + MouseWheel 绑定）+ 偏好持久化。
shim 别名让 main.py 中的业务逻辑方法无感继续工作。

shim 关键点：detect_file_list / detect_file_vars 是 list（非 tk 控件），
shim 别名指向同一 list 对象，main.py 中的 append/clear 操作直接作用于
DetectContext 中的 list —— 与 tk 控件 shim 同理，安全。
"""
from dataclasses import dataclass, field
from typing import Optional, List, Any
import tkinter as tk
from tkinter import ttk

from app.context import AppContext, PanelContext
from gui.panels.base_panel import BasePanel

# main 模块的 D/FT/XS/SM/BODY 是可变全局（暗色主题运行时改写 D[k]）。
import main as _main


@dataclass
class DetectContext(PanelContext):
    """格式检测面板状态。

    含 Canvas 滚动结果区 + 检测结果数据（file_list/file_vars）。
    detect_file_list / detect_file_vars 是 list，shim 别名指向同一对象。
    """
    panel_key: str = "detect"

    # 检测设置
    path: Optional[tk.Entry] = None           # 目标文件夹
    auto_add: Optional[tk.BooleanVar] = None  # 自动添加到对应面板

    # 可滚动结果区
    canvas: Optional[tk.Canvas] = None        # 滚动 Canvas
    rf: Optional[tk.Frame] = None             # 结果内层 Frame（results frame）

    # 底部进度栏控件（_w("detect") 通过 shim 命中）
    pg: Optional[ttk.Progressbar] = None
    st: Optional[tk.Label] = None
    go: Optional[tk.Widget] = None
    ca: Optional[tk.Widget] = None

    # 检测结果数据（list，shim 指向同一对象）
    # 用 default_factory 确保每个实例独立 list，避免 dataclass 可变默认值陷阱
    file_list: List[str] = field(default_factory=list)
    file_vars: List[Any] = field(default_factory=list)


class DetectPanel(BasePanel):
    panel_key = "detect"
    context_cls = DetectContext

    def build(self) -> tk.Widget:
        D = _main.D
        app = self.ctx._app

        p = tk.Frame(app.content, bg=D["page"])
        self.frame = p
        app.panels["detect"] = p

        c = DetectContext()
        self.context = c

        self._build_header(p)
        self._build_settings_card(p, c, app)
        self._build_scroll_area(p, c)
        self._build_bottom_bar(p, c, app)

        self.ctx.register_panel("detect", c)
        return p

    # ── UI 分区构建 ─────────────────────────────────
    def _build_header(self, parent: tk.Frame) -> None:
        app = self.ctx._app
        app._hdr(parent, "格式检测", "批量检测文件夹中所有文件的格式，支持按内容识别、文件详情预览和选择性批量转换")

    def _build_settings_card(self, parent: tk.Frame, c: DetectContext, app) -> None:
        """构建"检测设置"卡片：目标文件夹 Entry + 浏览按钮 + auto_add 复选框。"""
        D = _main.D
        BODY = _main.BODY
        SM = _main.SM

        s = app._card(parent, "检测设置")

        tk.Label(s, text="目标文件夹", bg=D["card"], fg=D["ink"], font=SM).grid(
            row=0, column=0, sticky="w")
        c.path = tk.Entry(s, font=BODY, bg=D["input_bg"], fg=D["ink"],
                          insertbackground=D["ink"], relief="flat",
                          highlightthickness=1, highlightbackground=D["input_bd"],
                          highlightcolor=D["accent"], width=40)
        c.path.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        app._btn(s, "浏览", app._detect_browse, style="secondary",
                padx=12, pady=2).grid(row=0, column=2, padx=(4, 0))

        c.auto_add = tk.BooleanVar(value=True)
        tk.Checkbutton(s, text="自动添加到对应面板", variable=c.auto_add,
                       bg=D["card"], fg=D["ink"], font=SM).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))

    def _build_scroll_area(self, parent: tk.Frame, c: DetectContext) -> None:
        """构建可滚动结果区：Canvas + Scrollbar + 内层 Frame + MouseWheel 绑定。

        MouseWheel 绑定/解绑逻辑从 main.py:_p_detect 的嵌套函数搬来：
        鼠标进入区域时 bind_all(<MouseWheel>)，离开时 unbind_all，
        避免检测面板的滚轮事件影响其他面板。
        """
        D = _main.D

        container = tk.Frame(parent, bg=D["card"])
        container.pack(fill=tk.BOTH, expand=True, padx=16, pady=(12, 0))

        c.canvas = tk.Canvas(container, bg=D["card"], highlightthickness=0)
        vbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=c.canvas.yview)
        c.rf = tk.Frame(c.canvas, bg=D["card"])

        c.rf.bind("<Configure>",
            lambda e: c.canvas.configure(scrollregion=c.canvas.bbox("all")))
        c.canvas.create_window((0, 0), window=c.rf, anchor="nw")
        c.canvas.configure(yscrollcommand=vbar.set)

        c.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)

        # MouseWheel 绑定（从 main.py 嵌套函数 _bind_mw/_unbind_mw 搬来）
        def _bind_mw(e):
            c.canvas.bind_all("<MouseWheel>",
                lambda ev: c.canvas.yview_scroll(int(-1*(ev.delta/120)), "units"))
        def _unbind_mw(e):
            c.canvas.unbind_all("<MouseWheel>")
        c.canvas.bind("<Enter>", _bind_mw)
        c.canvas.bind("<Leave>", _unbind_mw)
        c.rf.bind("<Enter>", _bind_mw)
        c.rf.bind("<Leave>", _unbind_mw)

    def _build_bottom_bar(self, parent: tk.Frame, c: DetectContext, app) -> None:
        """构建底部进度栏 + 操作按钮。

        detect 的 go 按钮绑定 _detect_start（不是 _go），text 改为"开始检测"；
        ca 按钮初始 DISABLED，绑定 _detect_stop。
        """
        c.pg, c.st, c.go, c.ca, _ = app._bar(parent)
        c.go.configure(text="开始检测", command=app._detect_start)
        c.ca.configure(command=app._detect_stop, state=tk.DISABLED)

    # ── 偏好持久化 ──────────────────────────────────
    def collect_prefs(self) -> dict:
        """返回持久化偏好（与原 _save_panel_prefs 的 detect 分支一致，2 键）。"""
        c = self.context
        return {
            "path": c.path.get(),
            "auto_add": c.auto_add.get(),
        }

    def apply_prefs(self, prefs: dict) -> None:
        """从持久化 prefs 恢复控件状态（与原 _load_panel_prefs 的 detect 分支一致）。

        path 是 Entry 控件，用 delete+insert 恢复（原逻辑）；
        auto_add 是 BooleanVar，用 set 恢复。
        """
        c = self.context
        if prefs.get("path"):
            c.path.delete(0, tk.END)
            c.path.insert(0, prefs["path"])
        if "auto_add" in prefs:
            c.auto_add.set(prefs["auto_add"])
