"""Video panel — 视频格式转换面板（DI 化试点）。

把原 main.py:_p_video 的 UI 构建逻辑搬到 VideoPanel.build()，
状态从散落在 FormatMaster.self.v_xxx 迁移到独立的 VideoContext dataclass。

兼容策略：FormatMaster._p_video 改为薄代理，调用本类的 build() 后，
把 context 中的控件/变量以别名（self.v_fmt = context.fmt）回填到 self，
让 _go / _save_panel_prefs / _w / _disable_all_panels 等旧代码无感继续工作。
"""
from dataclasses import dataclass, field
from typing import Optional
import tkinter as tk
from tkinter import ttk

from app.context import AppContext, PanelContext
from gui.panels.base_panel import BasePanel
from utils.config import (
    SUPPORTED_VIDEO, VIDEO_CODECS, VIDEO_PRESETS, RESOLUTIONS,
)
from utils.presets import get_preset_names

# main 模块的 D/FT/XS/SM 是可变全局（暗色主题运行时改写 D[k]）。
# 本模块由 main._p_video 延迟导入，此时 main 已完整加载，import 安全。
import main as _main


@dataclass
class VideoContext(PanelContext):
    """视频面板状态。

    替代 _panel_attrs["video"] 中的 19 个 self.xxx 属性。
    字段类型与 main.py 原实现保持一致：
      - fmt/codec/preset/res/fps/br/hw_accel/preset_combo/out_dir_combo → ttk.Combobox 控件
      - copy_mode → tk.BooleanVar
      - out_dir_path → tk.StringVar
      - copy_hint/out_dir_label/out_dir_btn/pg/st/go/ca → tk 控件
    """
    panel_key: str = "video"

    # ttk.Combobox 控件（.get() 返回当前文本）
    fmt: Optional[ttk.Combobox] = None
    codec: Optional[ttk.Combobox] = None
    preset: Optional[ttk.Combobox] = None
    res: Optional[ttk.Combobox] = None
    fps: Optional[ttk.Combobox] = None
    br: Optional[ttk.Combobox] = None
    hw_accel: Optional[ttk.Combobox] = None
    preset_combo: Optional[ttk.Combobox] = None
    out_dir_combo: Optional[ttk.Combobox] = None

    # tk 变量
    copy_mode: Optional[tk.BooleanVar] = None
    out_dir_path: Optional[tk.StringVar] = None

    # tk 控件引用
    copy_hint: Optional[tk.Widget] = None
    out_dir_label: Optional[tk.Widget] = None
    out_dir_btn: Optional[tk.Widget] = None
    pg: Optional[tk.Widget] = None
    st: Optional[tk.Widget] = None
    go: Optional[tk.Widget] = None
    ca: Optional[tk.Widget] = None


class VideoPanel(BasePanel):
    panel_key = "video"
    context_cls = VideoContext

    def build(self) -> tk.Widget:
        D = _main.D   # 同一可变 dict 对象，跟随主题切换
        FT = _main.FT
        XS = _main.XS
        SM = _main.SM
        app = self.ctx._app  # FormatMaster 实例，用于复用 UI 原语与回调

        p = tk.Frame(app.content, bg=D["page"])
        self.frame = p
        app.panels["video"] = p
        app._hdr(p, "视频格式转换", "MP4 · AVI · MKV · WMV · MOV · FLV · WEBM 等主流格式互转")
        app._file_sec(p, "video",
            [("视频文件", "*.mp4 *.avi *.mkv *.wmv *.mov *.flv *.webm *.ts *.mpeg *.3gp"),
             ("所有文件", "*.*")])

        c = VideoContext()
        self.context = c

        settings_card = app._card(p, "输出设置")

        # ── 仅转封装 ──
        copy_row = tk.Frame(settings_card, bg=D["card"])
        copy_row.pack(fill=tk.X, padx=16, pady=(10, 8))
        c.copy_mode = tk.BooleanVar(value=False)
        check_bg = D["card"] if app._theme == "light" else "#6a6a7a"
        copy_cb = tk.Checkbutton(copy_row, text="⚡ 仅转封装（无损拷贝）", variable=c.copy_mode,
                                 bg=D["card"], selectcolor=check_bg,
                                 fg=D["accent"], activeforeground=D["accent"],
                                 font=(FT, 10, "bold"), bd=0, highlightthickness=0,
                                 command=app._toggle_copy_mode)
        copy_cb.pack(side=tk.LEFT)
        c.copy_hint = tk.Label(copy_row, text="无损转封装，速度极快", bg=D["card"], fg=D["ink_dis"], font=XS)
        c.copy_hint.pack(side=tk.LEFT, padx=(8, 0))
        c.copy_hint.pack_forget()
        tk.Label(copy_row, text="预计耗时 < 5秒", bg=D["card"], fg=D["accent"], font=XS).pack(side=tk.RIGHT)

        # ── 硬件加速 ──
        hw_accel_row = tk.Frame(settings_card, bg=D["card"])
        hw_accel_row.pack(fill=tk.X, padx=16, pady=(0, 8))
        tk.Label(hw_accel_row, text="硬件加速", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 8))
        c.hw_accel = ttk.Combobox(hw_accel_row, state="readonly", width=20)
        c.hw_accel.pack(side=tk.LEFT)
        # 直接为本面板的 combobox 填充选项（不依赖 main._update_hw_accel_options，
        # 因为该方法读 self.v_hw_accel，而 shim 在 build() 返回后才应用）
        self._populate_hw_accel_options(c.hw_accel)

        # ── 参数网格 ──
        grid_frame = tk.Frame(settings_card, bg=D["card"])
        grid_frame.pack(fill=tk.X, padx=16, pady=(0, 10))
        grid_frame.columnconfigure(0, weight=1)
        grid_frame.columnconfigure(1, weight=1)
        grid_frame.columnconfigure(2, weight=1)

        c.fmt = app._grid_row(grid_frame, "目标格式", list(SUPPORTED_VIDEO.keys()), "MP4", 0, 0)
        c.fmt.bind("<<ComboboxSelected>>", lambda e: app._update_format_hint("video"))
        c.codec = app._grid_row(grid_frame, "视频编码", list(VIDEO_CODECS.keys()), "默认", 0, 1)
        c.preset = app._grid_row(grid_frame, "画质预设", list(VIDEO_PRESETS.keys()), "原始质量", 0, 2)
        c.res = app._grid_row(grid_frame, "分辨率", list(RESOLUTIONS.keys()), "原始分辨率", 1, 0)
        c.fps = app._grid_row(grid_frame, "帧率", ["原始帧率", "24", "25", "30", "60"], "原始帧率", 1, 1)
        c.br = app._grid_row(grid_frame, "码率", ["自动", "1M", "2M", "5M", "8M", "10M", "20M"], "自动", 1, 2)

        # ── 快速预设 + 输出目录 ──
        preset_out_row = tk.Frame(settings_card, bg=D["card"])
        preset_out_row.pack(fill=tk.X, padx=16, pady=(0, 10))

        preset_frame = tk.Frame(preset_out_row, bg=D["card"])
        preset_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(preset_frame, text="快速预设", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 8))
        video_presets = ["自定义"] + get_preset_names("video")
        c.preset_combo = ttk.Combobox(preset_frame, values=video_presets, state="readonly", width=16)
        c.preset_combo.set("自定义")
        c.preset_combo.pack(side=tk.LEFT)
        c.preset_combo.bind("<<ComboboxSelected>>", lambda e: app._apply_video_preset())

        out_frame = tk.Frame(preset_out_row, bg=D["card"])
        out_frame.pack(side=tk.RIGHT)
        tk.Label(out_frame, text="输出目录", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 6))
        # v_out_dir (StringVar) 仅作内部桥接，保留以兼容 main.py 可能的引用
        app.v_out_dir = tk.StringVar(value="与源文件同目录")
        c.out_dir_combo = ttk.Combobox(out_frame, values=["与源文件同目录", "自定义目录"], state="readonly", width=12)
        c.out_dir_combo.set("与源文件同目录")
        c.out_dir_combo.pack(side=tk.LEFT)
        c.out_dir_btn = app._btn(out_frame, "浏览", lambda: app._select_out_dir("video"), style="secondary")
        c.out_dir_btn.pack(side=tk.LEFT, padx=(6, 0))
        c.out_dir_path = tk.StringVar(value="")
        c.out_dir_label = tk.Label(out_frame, textvariable=c.out_dir_path, bg=D["card"], fg=D["ink_dis"], font=XS)
        c.out_dir_label.pack(side=tk.LEFT, padx=(6, 0))

        # ── 底部进度栏 ──
        bottom_bar = tk.Frame(p, bg=D["page"])
        bottom_bar.pack(fill=tk.X, pady=(12, 0))

        c.pg = ttk.Progressbar(bottom_bar, style="Horizontal.TProgressbar")
        c.pg.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 16))

        c.st = tk.Label(bottom_bar, text="就绪", bg=D["page"], fg=D["ink_dis"], font=SM)
        c.st.pack(side=tk.LEFT, padx=(0, 12))

        app._btn(bottom_bar, "📁 打开输出文件夹", app._open_output_folder, "ghost", padx=8).pack(side=tk.RIGHT, padx=(0, 8))

        c.ca = app._btn(bottom_bar, "取消", None, "danger", state=tk.DISABLED)
        c.ca.pack(side=tk.RIGHT, padx=(0, 10))
        c.ca.configure(command=lambda: app._stop("video"))

        c.go = app._btn(bottom_bar, "开始转换", None, "primary", padx=24)
        c.go.pack(side=tk.RIGHT)
        c.go.configure(command=lambda: app._go("video"))

        # 注册到全局上下文
        self.ctx.register_panel("video", c)
        return p

    # ── 参数收集（供 _go 调度使用）──────────────────
    def _populate_hw_accel_options(self, combo: ttk.Combobox) -> None:
        """为本面板的硬件加速 combobox 填充可用选项。"""
        from utils.hardware_accel import detect_hardware_acceleration
        available = detect_hardware_acceleration()
        options = ["自动"]
        for accel in available:
            options.append(accel["name"])
        combo.configure(values=options)
        combo.set("自动")

    def collect_params(self) -> dict:
        c = self.context
        return {
            "fmt": c.fmt.get(),
            "codec": c.codec.get(),
            "preset": c.preset.get(),
            "res": c.res.get(),
            "fps": c.fps.get(),
            "br": c.br.get(),
            "copy_mode": c.copy_mode.get(),
            "out_dir_combo": c.out_dir_combo.get(),
            "out_dir_path": c.out_dir_path.get(),
            "hw_accel": self._resolve_hw_accel(),
        }

    def _resolve_hw_accel(self):
        """把硬件加速下拉显示名解析为内部 key（沿用原 _go 逻辑）。"""
        display = self.context.hw_accel.get() if self.context.hw_accel else "自动"
        if display == "自动":
            return None
        from utils.hardware_accel import HW_ACCEL_ENCODERS
        for key, info in HW_ACCEL_ENCODERS.items():
            if info["name"] == display:
                return key
        return None

    # ── 偏好持久化 ──────────────────────────────────
    def collect_prefs(self) -> dict:
        """仅持久化用户偏好（不含 copy_mode / hw_accel 等运行态选择）。
        与原 _save_panel_prefs 的 video 分支字段一致。"""
        c = self.context
        return {
            "fmt": c.fmt.get(),
            "codec": c.codec.get(),
            "preset": c.preset.get(),
            "res": c.res.get(),
            "fps": c.fps.get(),
            "br": c.br.get(),
            "out_dir_combo": c.out_dir_combo.get(),
            "out_dir_path": c.out_dir_path.get(),
        }

    def apply_prefs(self, prefs: dict) -> None:
        """从持久化 prefs 恢复控件状态。与原 _load_panel_prefs 的 video 分支一致。"""
        c = self.context
        if prefs.get("fmt"):      c.fmt.set(prefs["fmt"])
        if prefs.get("codec"):    c.codec.set(prefs["codec"])
        if prefs.get("preset"):   c.preset.set(prefs["preset"])
        if prefs.get("res"):      c.res.set(prefs["res"])
        if prefs.get("fps"):      c.fps.set(prefs["fps"])
        if prefs.get("br"):       c.br.set(prefs["br"])
        if prefs.get("out_dir_combo"): c.out_dir_combo.set(prefs["out_dir_combo"])
        if prefs.get("out_dir_path"):  c.out_dir_path.set(prefs["out_dir_path"])
