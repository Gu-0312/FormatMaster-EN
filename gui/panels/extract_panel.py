"""Extract panel — 从视频提取音频面板（DI 化，第 3 个迁移面板）。

按 audio 模板执行：把 main.py:_p_extract 的 UI 构建逻辑搬到这里，
状态从 self.e_xxx 迁移到独立的 ExtractContext dataclass，build 拆分为细分内部方法。

兼容策略与 audio 一致：FormatMaster._p_extract 改为薄代理，调用本类的 build() 后，
把 context 中的控件以别名（self.e_fmt = context.fmt）回填到 self，
让 _go / _save_panel_prefs / _w / _bar 等旧代码无感继续工作。
"""
from dataclasses import dataclass
from typing import Optional
import tkinter as tk
from tkinter import ttk

from app.context import AppContext, PanelContext
from gui.panels.base_panel import BasePanel

# main 模块的 D/FT/XS/SM 是可变全局（暗色主题运行时改写 D[k]）。
# 本模块由 main._p_extract 延迟导入，此时 main 已完整加载，import 安全。
import main as _main

# 提取音频格式 → 文件扩展名映射（与 main.py:_go 的 extract 分支一致）
EXTRACT_FMT_EXT = {"MP3": ".mp3", "AAC": ".aac", "FLAC": ".flac", "WAV": ".wav"}


@dataclass
class ExtractContext(PanelContext):
    """提取音频面板状态。

    替代 _panel_attrs["extract"] 中的 6 个属性 + _w/_bar 引用的 4 个进度控件。
    """
    panel_key: str = "extract"

    # ttk.Combobox 控件
    fmt: Optional[ttk.Combobox] = None
    br: Optional[ttk.Combobox] = None
    out_dir_combo: Optional[ttk.Combobox] = None

    # tk 控件
    out_dir_btn: Optional[tk.Widget] = None
    out_dir_label: Optional[tk.Widget] = None

    # tk 变量
    out_dir_path: Optional[tk.StringVar] = None

    # 底部进度栏控件（_w("extract") 通过 shim 命中）
    pg: Optional[ttk.Progressbar] = None
    st: Optional[tk.Label] = None
    go: Optional[tk.Widget] = None
    ca: Optional[tk.Widget] = None


class ExtractPanel(BasePanel):
    panel_key = "extract"
    context_cls = ExtractContext

    def build(self) -> tk.Widget:
        """构建提取音频面板 UI。

        按 audio 模板：实例化 context，委托给细分的内部方法构建各区域，
        最后注册到 AppContext。
        """
        D = _main.D
        app = self.ctx._app  # FormatMaster 实例，用于复用 UI 原语与回调

        p = tk.Frame(app.content, bg=D["page"])
        self.frame = p
        app.panels["extract"] = p

        c = ExtractContext()
        self.context = c

        self._build_header(p)
        self._build_file_section(p)
        self._build_output_settings(p, c, app)
        self._build_bottom_bar(p, c, app)

        self.ctx.register_panel("extract", c)
        return p

    # ── UI 分区构建（细分内部方法）─────────────────
    def _build_header(self, parent: tk.Frame) -> None:
        app = self.ctx._app
        app._hdr(parent, "从视频提取音频", "将视频中的音轨提取为独立音频文件")

    def _build_file_section(self, parent: tk.Frame) -> None:
        app = self.ctx._app
        app._file_sec(parent, "extract",
            [("视频文件", "*.mp4 *.avi *.mkv *.wmv *.mov *.flv *.webm *.ts *.3gp"),
             ("所有文件", "*.*")])

    def _build_output_settings(self, parent: tk.Frame, c: ExtractContext, app) -> None:
        """构建输出设置卡片：音频格式/比特率/输出目录。"""
        D = _main.D
        SM = _main.SM
        XS = _main.XS

        s = app._card(parent, "输出设置")
        c.fmt = app._row(s, "音频格式", ["MP3", "AAC", "FLAC", "WAV"], "MP3")
        c.br = app._row(s, "比特率", ["128k", "192k", "256k", "320k"], "192k")

        # 输出目录（卡片内）
        out_frame = tk.Frame(s, bg=D["card"])
        out_frame.grid(row=2, column=0, columnspan=4, sticky="ew", padx=16, pady=(8, 10))
        tk.Label(out_frame, text="输出目录", bg=D["card"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(0, 8))
        c.out_dir_combo = ttk.Combobox(out_frame, values=["与源文件同目录", "自定义目录"],
                                       state="readonly", width=14)
        c.out_dir_combo.set("与源文件同目录")
        c.out_dir_combo.pack(side=tk.LEFT)
        c.out_dir_btn = app._btn(out_frame, "浏览",
                                  lambda: app._select_out_dir("extract"), style="secondary")
        c.out_dir_btn.pack(side=tk.LEFT, padx=(8, 0))
        c.out_dir_path = tk.StringVar(value="")
        c.out_dir_label = tk.Label(out_frame, textvariable=c.out_dir_path,
                                    bg=D["card"], fg=D["ink_dis"], font=XS)
        c.out_dir_label.pack(side=tk.LEFT, padx=(8, 0))

    def _build_bottom_bar(self, parent: tk.Frame, c: ExtractContext, app) -> None:
        """构建底部进度栏 + 操作按钮。"""
        c.pg, c.st, c.go, c.ca, _ = app._bar(parent)
        c.go.configure(command=lambda: app._go("extract"))
        c.ca.configure(command=lambda: app._stop("extract"))

    # ── 参数收集（供 _go 调度使用）──────────────────
    def collect_params(self) -> dict:
        """返回调度层期望的参数（与 main.py:_go 的 extract 分支构建的 dict 一致）。

        _run_task_general 的 extract 分支读 module_params.get("fmt") 和
        module_params.get("bitrate")，内部派生 codec {"MP3":"mp3",...}。
        故此处只返回 fmt + bitrate，不派生 codec（避免改变 _run_task_general 行为）。
        """
        c = self.context
        return {
            "fmt": c.fmt.get(),
            "bitrate": c.br.get(),
        }

    # ── 偏好持久化 ──────────────────────────────────
    def collect_prefs(self) -> dict:
        """返回持久化偏好（短名 key，与原 _save_panel_prefs 的 extract 分支一致）。"""
        c = self.context
        return {
            "fmt": c.fmt.get(),
            "br": c.br.get(),
            "out_dir_combo": c.out_dir_combo.get(),
            "out_dir_path": c.out_dir_path.get(),
        }

    def apply_prefs(self, prefs: dict) -> None:
        """从持久化 prefs 恢复控件状态（与原 _load_panel_prefs 的 extract 分支一致）。"""
        c = self.context
        if prefs.get("fmt"):           c.fmt.set(prefs["fmt"])
        if prefs.get("br"):            c.br.set(prefs["br"])
        if prefs.get("out_dir_combo"): c.out_dir_combo.set(prefs["out_dir_combo"])
        if prefs.get("out_dir_path"):  c.out_dir_path.set(prefs["out_dir_path"])
