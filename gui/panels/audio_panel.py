"""Audio panel — 音频格式转换面板（DI 化，第 2 个迁移面板）。

按 video 模板执行：把 main.py:_p_audio 的 UI 构建逻辑搬到这里，
状态从 self.a_xxx 迁移到独立的 AudioContext dataclass。

按用户要求：长 UI 拆分为更细的内部方法（_build_header / _build_file_section
/ _build_output_settings / _build_bottom_bar），可读性优于 video 的单 build()。

兼容策略与 video 一致：FormatMaster._p_audio 改为薄代理，调用本类的 build() 后，
把 context 中的控件以别名（self.a_fmt = context.fmt）回填到 self，
让 _go / _save_panel_prefs / _w / _bar 等旧代码无感继续工作。
"""
from dataclasses import dataclass
from typing import Optional
import tkinter as tk
from tkinter import ttk

from app.context import AppContext, PanelContext
from gui.panels.base_panel import BasePanel
from utils.config import SUPPORTED_AUDIO

# main 模块的 D/FT/XS/SM/BODY 是可变全局（暗色主题运行时改写 D[k]）。
# 本模块由 main._p_audio 延迟导入，此时 main 已完整加载，import 安全。
import main as _main


# 音频格式 → FFmpeg 编码器映射（与 main.py:_run_task_general 的 audio 分支一致）
AUDIO_CODEC_MAP = {
    "MP3": "libmp3lame", "AAC": "aac", "FLAC": "flac", "WAV": "pcm_s16le",
    "WMA": "wmav2", "OGG": "libvorbis", "M4A": "aac",
    "AMR": "libopencore_amrnb", "OPUS": "libopus",
}


@dataclass
class AudioContext(PanelContext):
    """音频面板状态。

    替代 _panel_attrs["audio"] 中的 9 个属性 + _w/_bar 引用的 4 个进度控件。
    """
    panel_key: str = "audio"

    # ttk.Combobox 控件
    fmt: Optional[ttk.Combobox] = None
    br: Optional[ttk.Combobox] = None
    sr: Optional[ttk.Combobox] = None
    ch: Optional[ttk.Combobox] = None
    out_dir_combo: Optional[ttk.Combobox] = None

    # tk 控件
    vol: Optional[tk.Scale] = None
    out_dir_btn: Optional[tk.Widget] = None
    out_dir_label: Optional[tk.Widget] = None

    # tk 变量
    out_dir_path: Optional[tk.StringVar] = None

    # 底部进度栏控件（_w("audio") 通过 shim 命中）
    pg: Optional[ttk.Progressbar] = None
    st: Optional[tk.Label] = None
    go: Optional[tk.Widget] = None
    ca: Optional[tk.Widget] = None


class AudioPanel(BasePanel):
    panel_key = "audio"
    context_cls = AudioContext

    def build(self) -> tk.Widget:
        """构建音频面板 UI。

        按 video 模板：实例化 context，委托给细分的内部方法构建各区域，
        最后注册到 AppContext。
        """
        D = _main.D
        app = self.ctx._app  # FormatMaster 实例，用于复用 UI 原语与回调

        p = tk.Frame(app.content, bg=D["page"])
        self.frame = p
        app.panels["audio"] = p

        c = AudioContext()
        self.context = c

        self._build_header(p)
        self._build_file_section(p)
        settings_card = self._build_output_settings(p, c, app)
        self._build_bottom_bar(p, c, app)

        self.ctx.register_panel("audio", c)
        return p

    # ── UI 分区构建（细分内部方法）─────────────────
    def _build_header(self, parent: tk.Frame) -> None:
        app = self.ctx._app
        app._hdr(parent, "音频格式转换", "MP3 · WAV · WMA · AAC · FLAC · OGG · M4A 等格式互转")

    def _build_file_section(self, parent: tk.Frame) -> None:
        app = self.ctx._app
        app._file_sec(parent, "audio",
            [("音频文件", "*.mp3 *.wav *.wma *.aac *.flac *.ogg *.m4a *.amr *.opus"),
             ("所有文件", "*.*")])

    def _build_output_settings(self, parent: tk.Frame, c: AudioContext, app) -> tk.Frame:
        """构建输出设置卡片：格式/比特率/采样率/声道/音量/输出目录。"""
        D = _main.D
        SM = _main.SM
        BODY = _main.BODY
        XS = _main.XS

        s = app._card(parent, "输出设置")
        # 复用 _row 网格原语：自动布局到 card._col_count
        c.fmt = app._row(s, "目标格式", list(SUPPORTED_AUDIO.keys()), "MP3")
        c.fmt.bind("<<ComboboxSelected>>", lambda e: app._update_format_hint("audio"))
        c.br = app._row(s, "比特率", ["128k", "192k", "256k", "320k"], "192k")
        c.sr = app._row(s, "采样率", ["原始", "22050", "44100", "48000", "96000"], "原始")
        c.ch = app._row(s, "声道", ["原始", "单声道", "立体声"], "原始")

        # 音量滑块（_row 不支持 Scale，单独布局到第 4 行）
        tk.Label(s, text="音量", bg=D["card"], fg=D["ink"], font=SM).grid(
            row=4, column=0, sticky="w")
        c.vol = tk.Scale(s, from_=20, to=200, orient=tk.HORIZONTAL,
                         bg=D["card"], fg=D["ink"], font=BODY,
                         highlightthickness=0, sliderlength=20,
                         troughcolor=D["input_bg"], relief="flat")
        c.vol.set(100)
        c.vol.grid(row=4, column=1, sticky="ew", padx=(4, 0))

        # 输出目录（卡片内底部）
        out_frame = tk.Frame(s, bg=D["card"])
        out_frame.grid(row=5, column=0, columnspan=4, sticky="ew", padx=16, pady=(8, 10))
        tk.Label(out_frame, text="输出目录", bg=D["card"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(0, 8))
        c.out_dir_combo = ttk.Combobox(out_frame, values=["与源文件同目录", "自定义目录"],
                                       state="readonly", width=14)
        c.out_dir_combo.set("与源文件同目录")
        c.out_dir_combo.pack(side=tk.LEFT)
        c.out_dir_btn = app._btn(out_frame, "浏览",
                                  lambda: app._select_out_dir("audio"), style="secondary")
        c.out_dir_btn.pack(side=tk.LEFT, padx=(8, 0))
        c.out_dir_path = tk.StringVar(value="")
        c.out_dir_label = tk.Label(out_frame, textvariable=c.out_dir_path,
                                    bg=D["card"], fg=D["ink_dis"], font=XS)
        c.out_dir_label.pack(side=tk.LEFT, padx=(8, 0))
        return s

    def _build_bottom_bar(self, parent: tk.Frame, c: AudioContext, app) -> None:
        """构建底部进度栏 + 操作按钮。"""
        c.pg, c.st, c.go, c.ca, _ = app._bar(parent)
        c.go.configure(command=lambda: app._go("audio"))
        c.ca.configure(command=lambda: app._stop("audio"))

    # ── 参数收集（供 _go 调度使用）──────────────────
    def collect_params(self) -> dict:
        """返回调度层期望的参数（长名 key，含 codec 派生字段）。

        与 main.py:_go 的 audio 分支 + _run_task_general 的 audio 分支约定一致：
          fmt, codec, bitrate, sample_rate, channels, volume
        """
        c = self.context
        fmt = c.fmt.get()
        return {
            "fmt": fmt,
            "codec": AUDIO_CODEC_MAP.get(fmt),
            "bitrate": c.br.get(),
            "sample_rate": c.sr.get(),
            "channels": c.ch.get(),
            "volume": c.vol.get(),
        }

    # ── 偏好持久化 ──────────────────────────────────
    def collect_prefs(self) -> dict:
        """返回持久化偏好（短名 key，与原 _save_panel_prefs 的 audio 分支一致）。

        不含 codec（由 fmt 派生）、不含 volume（运行态可调，可选持久化；
        与原实现一致：原 _save_panel_prefs 不存 volume，这里保持兼容）。
        """
        c = self.context
        return {
            "fmt": c.fmt.get(),
            "br": c.br.get(),
            "sr": c.sr.get(),
            "ch": c.ch.get(),
            "out_dir_combo": c.out_dir_combo.get(),
            "out_dir_path": c.out_dir_path.get(),
        }

    def apply_prefs(self, prefs: dict) -> None:
        """从持久化 prefs 恢复控件状态（与原 _load_panel_prefs 的 audio 分支一致）。"""
        c = self.context
        if prefs.get("fmt"):           c.fmt.set(prefs["fmt"])
        if prefs.get("br"):            c.br.set(prefs["br"])
        if prefs.get("sr"):            c.sr.set(prefs["sr"])
        if prefs.get("ch"):            c.ch.set(prefs["ch"])
        if prefs.get("out_dir_combo"): c.out_dir_combo.set(prefs["out_dir_combo"])
        if prefs.get("out_dir_path"):  c.out_dir_path.set(prefs["out_dir_path"])
