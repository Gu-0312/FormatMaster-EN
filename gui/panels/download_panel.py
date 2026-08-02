"""Download panel — 视频下载面板（DI 化，第 12 个迁移面板）。

最复杂的面板（UI 构建 ~120 行）：URL 输入 + 格式列表 + 设置区（3 行）+
保存目录 + 下载队列（Listbox + 操作按钮）+ 底部进度栏。

与 detect 面板同构的特殊面板：
  - go 按钮绑 _go_download（不是 _go("download")），走自己的下载流程
  - 无 collect_params（download 不经 _go 参数收集）
  - 12+ 个业务逻辑方法（_dl_parse_url/_dl_fetch_formats/_dl_add_url/
    _dl_batch_import/_dl_remove_selected/_dl_move_up/_dl_move_down/
    _dl_clear_queue/_dl_on_fmt_select/_dl_on_dbl_click/_go_download/
    _dl_cancel/_dl_toggle_audio）留在 main.py，通过 shim 访问 dl_ 控件
  - dl_queue/dl_formats 是 list，shim 指向同一对象
  - dl_obj 是 VideoDownloader 实例，在 _p_download 中创建后回填 shim

只迁移 UI 构建 + 偏好持久化（dl_dir 1 键）。
"""
from dataclasses import dataclass, field
from typing import Optional, List, Any
import os
import tkinter as tk
from tkinter import ttk

from app.context import AppContext, PanelContext
from gui.panels.base_panel import BasePanel

# main 模块的 D/FT/XS/SM/BODY 是可变全局（暗色主题运行时改写 D[k]）。
import main as _main


# 预置值（与 main.py:_p_download 原始值一致）
SPEED_VALUES = ["不限", "2", "5", "10", "20", "50"]
AUDIO_FMT_VALUES = ["mp3", "m4a", "flac", "wav", "opus"]


@dataclass
class DownloadContext(PanelContext):
    """视频下载面板状态。

    含 17 个控件 + 2 个 list（dl_queue/dl_formats）+ 1 个 VideoDownloader 实例。
    list/obj 用 default_factory 或 Optional 确保实例独立。
    """
    panel_key: str = "download"

    # URL 输入区
    url: Optional[tk.Text] = None              # URL 输入框
    fmt_info: Optional[tk.StringVar] = None    # 格式提示信息

    # 格式列表
    formats_list: Optional[tk.Listbox] = None  # 可选格式列表
    formats: List[Any] = field(default_factory=list)  # 解析到的格式数据

    # 设置区 row1: Cookie / 代理 / 限速
    cookie: Optional[tk.Entry] = None
    proxy: Optional[tk.Entry] = None
    speed: Optional[ttk.Combobox] = None

    # 设置区 row2: Header
    headers: Optional[tk.Entry] = None

    # 设置区 row3: 选项
    audio_only: Optional[tk.BooleanVar] = None
    audio_fmt: Optional[ttk.Combobox] = None
    subtitles: Optional[tk.BooleanVar] = None
    template: Optional[tk.Entry] = None

    # 保存目录
    dir: Optional[tk.StringVar] = None

    # 下载队列
    count_label: Optional[tk.Label] = None      # 任务计数标签
    queue_listbox: Optional[tk.Listbox] = None  # 队列列表
    queue: List[Any] = field(default_factory=list)  # 下载任务数据

    # VideoDownloader 实例（在 _p_download 中创建后回填 shim）
    obj: Any = None

    # 底部进度栏控件（_w("download") 通过 shim 命中）
    pg: Optional[ttk.Progressbar] = None
    st: Optional[tk.Label] = None
    go: Optional[tk.Widget] = None
    ca: Optional[tk.Widget] = None


class DownloadPanel(BasePanel):
    panel_key = "download"
    context_cls = DownloadContext

    def build(self) -> tk.Widget:
        D = _main.D
        app = self.ctx._app

        p = tk.Frame(app.content, bg=D["page"])
        self.frame = p
        app.panels["download"] = p

        c = DownloadContext()
        self.context = c

        self._build_header(p, app)
        self._build_url_section(p, c, app)
        self._build_url_buttons(p, app)
        self._build_formats_section(p, c)
        self._build_settings_section(p, c, app)
        self._build_output_dir(p, c, app)
        self._build_queue_section(p, c, app)
        self._build_bottom_bar(p, c, app)

        self.ctx.register_panel("download", c)
        return p

    # ── UI 分区构建 ─────────────────────────────────
    def _build_header(self, parent: tk.Frame, app) -> None:
        app._hdr(parent, "视频下载",
                 "支持 B站 / YouTube / 微博 / Instagram 等数百个平台", badge="需联网")

    def _build_url_section(self, parent: tk.Frame, c: DownloadContext, app) -> None:
        """URL 输入框 + 格式提示信息标签。"""
        D = _main.D
        BODY = _main.BODY
        SM = _main.SM
        XS = _main.XS

        url_frame = tk.Frame(parent, bg=D["page"])
        url_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(url_frame, text="URL", bg=D["page"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(0, 8))
        c.url = tk.Text(url_frame, font=BODY, bg=D["input_bg"], fg=D["ink"],
                        relief="solid", bd=1, highlightthickness=0, height=3)
        c.url.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2)
        c.url.bind("<Control-v>", lambda e: app.root.after(100, app._dl_parse_url))
        c.fmt_info = tk.StringVar(value="")
        tk.Label(url_frame, textvariable=c.fmt_info, bg=D["page"], fg=D["ink_dis"],
                 font=XS).pack(side=tk.LEFT, padx=(8, 0))

    def _build_url_buttons(self, parent: tk.Frame, app) -> None:
        """URL 操作按钮：解析格式 / 添加链接 / 批量导入 / 历史 / 收藏 / 收藏夹。"""
        D = _main.D
        url_btn_frame = tk.Frame(parent, bg=D["page"])
        url_btn_frame.pack(fill=tk.X, pady=(0, 6))
        app._btn(url_btn_frame, "解析格式", app._dl_parse_url, padx=12).pack(side=tk.LEFT)
        app._btn(url_btn_frame, "添加链接", app._dl_add_url, "primary", padx=12).pack(
            side=tk.LEFT, padx=(8, 0))
        app._btn(url_btn_frame, "📁 批量导入", app._dl_batch_import, padx=8).pack(
            side=tk.LEFT, padx=(8, 0))
        app._btn(url_btn_frame, "⭐ 收藏", app._dl_add_favorite, padx=8).pack(
            side=tk.RIGHT, padx=(0, 0))
        app._btn(url_btn_frame, "📋 历史", app._dl_show_history, padx=8).pack(
            side=tk.RIGHT, padx=(8, 0))
        app._btn(url_btn_frame, "⭐ 收藏夹", app._dl_show_favorites, padx=8).pack(
            side=tk.RIGHT, padx=(8, 0))

    def _build_formats_section(self, parent: tk.Frame, c: DownloadContext) -> None:
        """格式列表区：选择格式 Label + Listbox。"""
        D = _main.D
        BODY = _main.BODY
        SM = _main.SM

        fmt_frame = tk.Frame(parent, bg=D["page"])
        fmt_frame.pack(fill=tk.X, pady=(0, 6))
        tk.Label(fmt_frame, text="选择格式", bg=D["page"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(0, 8))
        c.formats_list = tk.Listbox(fmt_frame, height=5, font=BODY, bg=D["input_bg"],
                                    relief="solid", bd=1, highlightthickness=0)
        c.formats_list.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2)

    def _build_settings_section(self, parent: tk.Frame, c: DownloadContext, app) -> None:
        """设置区 3 行：Cookie/代理/限速 | Header | 仅音频/字幕/模板。"""
        D = _main.D
        BODY = _main.BODY
        SM = _main.SM
        XS = _main.XS

        settings_frame = tk.Frame(parent, bg=D["page"])
        settings_frame.pack(fill=tk.X, pady=(0, 6))

        # row1: Cookie | 代理 | 限速
        row1 = tk.Frame(settings_frame, bg=D["page"])
        row1.pack(fill=tk.X, pady=(0, 4))
        tk.Label(row1, text="Cookie", bg=D["page"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(0, 4))
        c.cookie = tk.Entry(row1, font=BODY, bg=D["input_bg"], fg=D["ink"],
                            relief="solid", bd=1, highlightthickness=0, width=25)
        c.cookie.pack(side=tk.LEFT, ipady=2)
        tk.Label(row1, text="代理", bg=D["page"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(12, 4))
        c.proxy = tk.Entry(row1, font=BODY, bg=D["input_bg"], fg=D["ink"],
                           relief="solid", bd=1, highlightthickness=0, width=18)
        c.proxy.pack(side=tk.LEFT, ipady=2)
        tk.Label(row1, text="限速 MB/s", bg=D["page"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(12, 4))
        c.speed = ttk.Combobox(row1, values=SPEED_VALUES, state="readonly", width=6)
        c.speed.set("不限")
        c.speed.pack(side=tk.LEFT)

        # row2: Header
        row2 = tk.Frame(settings_frame, bg=D["page"])
        row2.pack(fill=tk.X, pady=(0, 4))
        tk.Label(row2, text="Header", bg=D["page"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(0, 4))
        c.headers = tk.Entry(row2, font=BODY, bg=D["input_bg"], fg=D["ink"],
                             relief="solid", bd=1, highlightthickness=0)
        c.headers.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2)
        tk.Label(row2, text="Key:Val,Key:Val", bg=D["page"], fg=D["ink_dis"],
                 font=XS).pack(side=tk.LEFT, padx=(4, 0))

        # row3: 仅音频 + 字幕 + 文件名模板
        row3 = tk.Frame(settings_frame, bg=D["page"])
        row3.pack(fill=tk.X)
        c.audio_only = tk.BooleanVar(value=False)
        tk.Checkbutton(row3, text="仅音频", variable=c.audio_only,
                       bg=D["page"], fg=D["ink"], font=SM,
                       command=app._dl_toggle_audio).pack(side=tk.LEFT)
        c.audio_fmt = ttk.Combobox(row3, values=AUDIO_FMT_VALUES,
                                   state="readonly", width=6)
        c.audio_fmt.set("mp3")
        c.audio_fmt.pack(side=tk.LEFT, padx=(4, 12))
        c.subtitles = tk.BooleanVar(value=False)
        tk.Checkbutton(row3, text="下载字幕", variable=c.subtitles,
                       bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.LEFT)
        tk.Label(row3, text="文件名模板", bg=D["page"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(16, 4))
        c.template = tk.Entry(row3, font=BODY, bg=D["input_bg"], fg=D["ink"],
                              relief="solid", bd=1, highlightthickness=0, width=24)
        c.template.pack(side=tk.LEFT, ipady=2)
        tk.Label(row3, text="留空=默认", bg=D["page"], fg=D["ink_dis"],
                 font=XS).pack(side=tk.LEFT, padx=(4, 0))

    def _build_output_dir(self, parent: tk.Frame, c: DownloadContext, app) -> None:
        D = _main.D
        SM = _main.SM
        XS = _main.XS

        out_frame = tk.Frame(parent, bg=D["page"])
        out_frame.pack(fill=tk.X, pady=(4, 0))
        tk.Label(out_frame, text="保存到", bg=D["page"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(0, 8))
        c.dir = tk.StringVar(value=os.path.expanduser("~/Downloads"))
        tk.Label(out_frame, textvariable=c.dir, bg=D["page"], fg=D["ink_dis"],
                 font=XS).pack(side=tk.LEFT, padx=(0, 8))
        # 浏览按钮（绑定 main.py 的 _select_dl_dir）
        app._btn(out_frame, "浏览", lambda: app._select_dl_dir(),
                 "secondary").pack(side=tk.LEFT)

    def _build_queue_section(self, parent: tk.Frame, c: DownloadContext, app) -> None:
        """下载队列卡片：标题 + 计数 + Listbox（带滚动条）+ 操作按钮。"""
        D = _main.D
        FT = _main.FT
        XS = _main.XS

        q_card = tk.Frame(parent, bg=D["border"], padx=1, pady=1)
        q_card.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        q_inner = tk.Frame(q_card, bg=D["card"])
        q_inner.pack(fill=tk.BOTH, expand=True)

        # 队列标题 + 计数
        q_hdr = tk.Frame(q_inner, bg=D["card"])
        q_hdr.pack(fill=tk.X, padx=10, pady=(6, 2))
        tk.Label(q_hdr, text="下载队列", bg=D["card"], fg=D["ink"],
                 font=(FT, 9, "bold")).pack(side=tk.LEFT)
        c.count_label = tk.Label(q_hdr, text="0 个任务", bg=D["card"],
                                 fg=D["ink_dis"], font=XS)
        c.count_label.pack(side=tk.RIGHT)

        # 队列列表 + 滚动条
        q_list = tk.Frame(q_inner, bg=D["card"])
        q_list.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 4))
        c.queue_listbox = tk.Listbox(q_list, font=(FT, 10), bg=D["card"], fg=D["ink"],
                                     selectbackground=D["select_bg"],
                                     selectforeground=D["select_fg"],
                                     bd=0, highlightthickness=0, activestyle="none",
                                     height=4)
        q_scroll = ttk.Scrollbar(q_list, orient=tk.VERTICAL,
                                 command=c.queue_listbox.yview)
        c.queue_listbox.configure(yscrollcommand=q_scroll.set)
        c.queue_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        q_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 队列操作按钮
        q_btns = tk.Frame(q_inner, bg=D["card"])
        q_btns.pack(fill=tk.X, padx=10, pady=(0, 6))
        app._btn(q_btns, "▲ 上移", app._dl_move_up, "ghost", padx=6).pack(side=tk.LEFT)
        app._btn(q_btns, "▼ 下移", app._dl_move_down, "ghost", padx=6).pack(
            side=tk.LEFT, padx=(4, 0))
        app._btn(q_btns, "✕ 移除选中", app._dl_remove_selected, "ghost", padx=8).pack(
            side=tk.LEFT, padx=(12, 0))
        app._btn(q_btns, "清空队列", app._dl_clear_queue, "ghost", padx=8).pack(
            side=tk.LEFT, padx=(8, 0))

    def _build_bottom_bar(self, parent: tk.Frame, c: DownloadContext, app) -> None:
        """底部进度栏：go 按钮绑 _go_download（不是 _go），ca 绑 _dl_cancel。"""
        c.pg, c.st, c.go, c.ca, _ = app._bar(parent)
        c.go.configure(text="开始下载", command=app._go_download)
        c.ca.configure(command=app._dl_cancel)

    # ── 偏好持久化 ──────────────────────────────────
    def collect_prefs(self) -> dict:
        """返回持久化偏好（与原 _save_panel_prefs 的 download 分支一致，1 键）。

        只持久化 dl_dir（保存目录）。其余设置（cookie/proxy/headers 等）不持久化。
        """
        return {"dl_dir": self.context.dir.get()}

    def apply_prefs(self, prefs: dict) -> None:
        """从持久化 prefs 恢复控件状态（与原 _load_panel_prefs 的 download 分支一致）。"""
        if prefs.get("dl_dir"):
            self.context.dir.set(prefs["dl_dir"])
