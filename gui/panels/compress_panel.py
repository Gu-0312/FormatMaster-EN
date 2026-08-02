"""Compress panel — 视频压缩面板（DI 化，第 5 个迁移面板）。

按 rename 模板执行：把 main.py:_p_compress 的 UI 构建逻辑搬到这里，
状态从 self.c_xxx 迁移到独立的 CompressContext dataclass，build 拆分为细分内部方法。

兼容策略与 rename 一致：FormatMaster._p_compress 改为薄代理，调用本类的 build() 后，
把 context 中的控件以别名（self.c_q = context.q）回填到 self，
让 _save_panel_prefs / _load_panel_prefs / _w / _go 等旧代码无感继续工作。
"""
from dataclasses import dataclass
from typing import Optional
import tkinter as tk
from tkinter import ttk

from app.context import AppContext, PanelContext
from gui.panels.base_panel import BasePanel
from utils.config import RESOLUTIONS

# main 模块的 D/FT/XS/SM/BODY 是可变全局（暗色主题运行时改写 D[k]）。
# 本模块由 main._p_compress 延迟导入，此时 main 已完整加载，import 安全。
import main as _main


# 压缩质量预置值（与 main.py:_p_compress 原始值一致）
# _run_task_general 的 compress 分支按"高/低"关键字识别 quality：
#   "高" → "high"，"低" → "low"，其余 → "medium"
QUALITY_VALUES = [
    "高质量（文件较大）",
    "中等质量（推荐）",
    "低质量（文件最小）",
]


@dataclass
class CompressContext(PanelContext):
    """视频压缩面板状态。

    替代 _panel_attrs["compress"] 中的 6 个属性 + _w/_bar 引用的 4 个进度控件。
    """
    panel_key: str = "compress"

    # 压缩设置
    q: Optional[ttk.Combobox] = None       # 压缩质量
    res: Optional[ttk.Combobox] = None     # 分辨率

    # 输出目录
    out_dir_combo: Optional[ttk.Combobox] = None
    out_dir_btn: Optional[tk.Widget] = None
    out_dir_path: Optional[tk.StringVar] = None
    out_dir_label: Optional[tk.Widget] = None

    # 底部进度栏控件（_w("compress") 通过 shim 命中）
    pg: Optional[ttk.Progressbar] = None
    st: Optional[tk.Label] = None
    go: Optional[tk.Widget] = None
    ca: Optional[tk.Widget] = None


class CompressPanel(BasePanel):
    panel_key = "compress"
    context_cls = CompressContext

    def build(self) -> tk.Widget:
        """构建视频压缩面板 UI。

        按 rename 模板：实例化 context，委托给细分的内部方法构建各区域，
        最后注册到 AppContext。
        """
        D = _main.D
        app = self.ctx._app  # FormatMaster 实例，用于复用 UI 原语与回调

        p = tk.Frame(app.content, bg=D["page"])
        self.frame = p
        app.panels["compress"] = p

        c = CompressContext()
        self.context = c

        self._build_header(p)
        self._build_file_section(p)
        self._build_settings_card(p, c, app)
        self._build_bottom_bar(p, c, app)

        self.ctx.register_panel("compress", c)
        return p

    # ── UI 分区构建（细分内部方法）─────────────────
    def _build_header(self, parent: tk.Frame) -> None:
        app = self.ctx._app
        app._hdr(parent, "视频压缩", "减小视频文件体积，便于存储和分享")

    def _build_file_section(self, parent: tk.Frame) -> None:
        app = self.ctx._app
        app._file_sec(parent, "compress", [
            ("视频文件", "*.mp4 *.avi *.mkv *.wmv *.mov *.flv *.webm *.ts *.3gp"),
            ("所有文件", "*.*"),
        ])

    def _build_settings_card(self, parent: tk.Frame, c: CompressContext, app) -> None:
        """构建"压缩设置"卡片：压缩质量 + 分辨率 + 输出目录。

        compress 的设置较少，单个卡片即可容纳，无需像 rename 那样再拆子方法。
        输出目录区由 _build_output_dir 构建，挂到同一卡片内。
        """
        s = app._card(parent, "压缩设置")
        c.q = app._row(s, "压缩质量", QUALITY_VALUES, "中等质量（推荐）", 20)
        c.res = app._row(s, "分辨率", list(RESOLUTIONS.keys()), "原始分辨率", 16)
        self._build_output_dir(s, c, app)

    def _build_output_dir(self, card: tk.Frame, c: CompressContext, app) -> None:
        """输出目录区（布局到卡片 row 2，与 rename 面板输出目录区结构一致）。"""
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
                                  lambda: app._select_out_dir("compress"), style="secondary")
        c.out_dir_btn.pack(side=tk.LEFT, padx=(8, 0))
        c.out_dir_path = tk.StringVar(value="")
        c.out_dir_label = tk.Label(out_frame, textvariable=c.out_dir_path,
                                   bg=D["card"], fg=D["ink_dis"], font=XS)
        c.out_dir_label.pack(side=tk.LEFT, padx=(8, 0))

    def _build_bottom_bar(self, parent: tk.Frame, c: CompressContext, app) -> None:
        """构建底部进度栏 + 操作按钮。

        compress 的 go 按钮保留 _bar 默认文案，仅绑定 _go("compress") 回调；
        ca 按钮绑定 _stop("compress")。
        """
        c.pg, c.st, c.go, c.ca, _ = app._bar(parent)
        c.go.configure(command=lambda: app._go("compress"))
        c.ca.configure(command=lambda: app._stop("compress"))

    # ── 参数收集（供 _go 调度使用）──────────
    def collect_params(self) -> dict:
        """返回调度层期望的参数（2 键，与 main.py:_go 的 compress 分支一致）。

        _run_task_general 的 compress 分支读 module_params.get("quality") /
        module_params.get("resolution")，故必须返回这两键。
        out_dir 不在此处收集（_go 通过 attr_map 单独处理输出目录）。
        """
        c = self.context
        return {
            "quality": c.q.get(),
            "resolution": c.res.get(),
        }

    # ── 偏好持久化 ──────────────────────────────────
    def collect_prefs(self) -> dict:
        """返回持久化偏好（与原 _save_panel_prefs 的 compress 分支一致，4 键）。"""
        c = self.context
        return {
            "quality": c.q.get(),
            "resolution": c.res.get(),
            "out_dir_combo": c.out_dir_combo.get(),
            "out_dir_path": c.out_dir_path.get(),
        }

    def apply_prefs(self, prefs: dict) -> None:
        """从持久化 prefs 恢复控件状态（与原 _load_panel_prefs 的 compress 分支一致）。

        原代码用 hasattr(self, 'c_q') 防御面板未构建的情况；委托后 apply_prefs
        在 CompressPanel 实例上调用，context 必然已初始化，无需 hasattr（与 rename 一致）。
        """
        c = self.context
        if prefs.get("quality"):       c.q.set(prefs["quality"])
        if prefs.get("resolution"):    c.res.set(prefs["resolution"])
        if prefs.get("out_dir_combo"): c.out_dir_combo.set(prefs["out_dir_combo"])
        if prefs.get("out_dir_path"):  c.out_dir_path.set(prefs["out_dir_path"])
