"""M3U8 panel — M3U8 视频下载面板（DI 化，第 16 个迁移面板）。

最复杂的面板之一（与 download 同构）：
  - go 按钮绑 _go_m3u8（不是 _go("m3u8")），走自己的下载流程
  - 无 collect_params（m3u8 不经 _go 参数收集）
  - 10+ 个业务逻辑方法（_m3u8_parse_url/_m3u8_quality_changed/_m3u8_batch_add/
    _m3u8_batch_import/_m3u8_move_up/_m3u8_move_down/_m3u8_remove_selected/
    _m3u8_clear_queue/_m3u8_show_favorites/_m3u8_show_history/_go_m3u8）留在 main.py，
    通过 shim 访问 m3u8_ 控件
  - m3u8_queue/m3u8_qualities 是 list，shim 指向同一对象
  - m3u8_dl 是 M3U8Downloader 实例，在 main.py __init__ (L283) 创建后回填 shim

只迁移 UI 构建 + 偏好持久化（10 键）。
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

# 预置值（与 main.py:_p_m3u8 原始值一致）
THREADS_VALUES = ["4", "8", "16", "24", "32", "48", "64"]
FORMAT_VALUES = ["mp4", "mkv", "avi", "mov", "ts"]
SPEED_VALUES = ["不限", "2", "5", "10", "20", "50"]
DEFAULT_THREADS = "16"
DEFAULT_FORMAT = "mp4"
DEFAULT_SPEED = "不限"
DEFAULT_OUT_DIR = os.path.expanduser("~/Downloads")


@dataclass
class M3u8Context(PanelContext):
    """M3U8 视频下载面板状态。

    含 19 个控件 + 2 个 list（queue/qualities）+ 1 个 M3U8Downloader 实例（dl）。
    list 用 default_factory 确保实例独立；dl 在 _p_m3u8 中回填 shim。
    """
    panel_key: str = "m3u8"

    # URL 输入
    url: Optional[tk.Text] = None

    # 画质选择
    quality: Optional[ttk.Combobox] = None
    quality_hint: Optional[tk.Label] = None

    # 文件名
    name: Optional[tk.Entry] = None

    # 保存目录
    out_dir: Optional[tk.StringVar] = None

    # 设置区：并发线程 + 输出格式 + 限速
    threads: Optional[ttk.Combobox] = None
    format: Optional[ttk.Combobox] = None
    speed: Optional[ttk.Combobox] = None

    # 高级设置：Cookie + 代理 + Header
    cookie: Optional[tk.Entry] = None
    proxy: Optional[tk.Entry] = None
    headers: Optional[tk.Entry] = None
    resume: Optional[tk.BooleanVar] = None  # 断点续传

    # 下载队列
    count_label: Optional[tk.Label] = None
    listbox: Optional[tk.Listbox] = None
    queue: List[Any] = field(default_factory=list)       # 下载任务数据
    qualities: List[Any] = field(default_factory=list)   # 解析到的画质数据

    # 选项
    download_sub: Optional[tk.BooleanVar] = None  # 同时下载字幕
    notify: Optional[tk.BooleanVar] = None        # 完成通知

    # 底部进度栏控件（_w("m3u8") 通过 shim 命中）
    pg: Optional[ttk.Progressbar] = None
    st: Optional[tk.Label] = None
    go: Optional[tk.Widget] = None
    ca: Optional[tk.Widget] = None

    # M3U8Downloader 实例（在 _p_m3u8 中回填 shim，不在 build 中创建）
    dl: Any = None


class M3u8Panel(BasePanel):
    panel_key = "m3u8"
    context_cls = M3u8Context

    def build(self) -> tk.Widget:
        D = _main.D
        app = self.ctx._app

        p = tk.Frame(app.content, bg=D["page"])
        self.frame = p
        app.panels["m3u8"] = p

        c = M3u8Context()
        self.context = c

        self._build_header(p, app)
        self._build_url_section(p, c, app)
        self._build_quality_section(p, c, app)
        self._build_name_section(p, c)
        self._build_out_dir_section(p, c, app)
        self._build_settings_section(p, c)
        self._build_adv_section(p, c)
        self._build_headers_section(p, c)
        self._build_notice(p)
        self._build_queue_section(p, c, app)
        self._build_options_section(p, c)
        self._build_bottom_bar(p, c, app)

        self.ctx.register_panel("m3u8", c)
        return p

    # ── UI 分区构建 ─────────────────────────────────
    def _build_header(self, parent: tk.Frame, app) -> None:
        app._hdr(parent, "M3U8 视频下载", "添加多个链接，支持画质选择，批量队列下载", badge="需联网")

    def _build_url_section(self, parent: tk.Frame, c: M3u8Context, app) -> None:
        """URL 输入区：标签 + Text + 操作按钮（解析画质/收藏/批量添加）。"""
        D = _main.D
        BODY = _main.BODY
        SM = _main.SM
        XS = _main.XS

        url_frame = tk.Frame(parent, bg=D["page"])
        url_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(url_frame, text="M3U8链接", bg=D["page"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(0, 8))
        c.url = tk.Text(url_frame, font=BODY, bg=D["input_bg"], fg=D["ink"],
                        relief="solid", bd=1, highlightthickness=0, height=3)
        c.url.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2)
        c.url.bind("<Control-v>", lambda e: app.root.after(100, lambda: app._m3u8_batch_add()))
        app._btn(url_frame, "解析画质", app._m3u8_parse_url, padx=12).pack(side=tk.RIGHT, padx=(8, 0))
        app._btn(url_frame, "⭐ 收藏", app._m3u8_add_to_favorites, "secondary", padx=8).pack(
            side=tk.RIGHT, padx=(4, 0))
        app._btn(url_frame, "批量添加", app._m3u8_batch_add, "primary", padx=12).pack(
            side=tk.RIGHT, padx=(8, 0))
        tk.Label(url_frame, text="每行一个链接，支持批量粘贴", bg=D["page"],
                 fg=D["ink_dis"], font=XS).pack(side=tk.BOTTOM, anchor=tk.W, pady=(2, 0))

    def _build_quality_section(self, parent: tk.Frame, c: M3u8Context, app) -> None:
        """画质选择区：Combobox + 提示标签。"""
        D = _main.D
        SM = _main.SM
        XS = _main.XS

        quality_frame = tk.Frame(parent, bg=D["page"])
        quality_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(quality_frame, text="画质", bg=D["page"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(0, 8))
        c.quality = ttk.Combobox(quality_frame, values=[""], state="readonly", width=30)
        c.quality.set("")
        c.quality.pack(side=tk.LEFT, fill=tk.X, expand=True)
        c.quality.bind("<<ComboboxSelected>>", app._m3u8_quality_changed)
        c.quality_hint = tk.Label(quality_frame, text="点击「解析画质」获取可选项",
                                 bg=D["page"], fg=D["ink_dis"], font=XS)
        c.quality_hint.pack(side=tk.LEFT, padx=(8, 0))

    def _build_name_section(self, parent: tk.Frame, c: M3u8Context) -> None:
        """文件名输入区。"""
        D = _main.D
        BODY = _main.BODY
        SM = _main.SM
        XS = _main.XS

        name_frame = tk.Frame(parent, bg=D["page"])
        name_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(name_frame, text="文件名", bg=D["page"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(0, 8))
        c.name = tk.Entry(name_frame, font=BODY, bg=D["input_bg"], fg=D["ink"],
                          relief="solid", bd=1, highlightthickness=0)
        c.name.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        tk.Label(name_frame, text="留空=自动命名", bg=D["page"], fg=D["ink_dis"],
                 font=XS).pack(side=tk.LEFT, padx=(8, 0))

    def _build_out_dir_section(self, parent: tk.Frame, c: M3u8Context, app) -> None:
        """保存目录区：标签 + 路径显示 + 浏览按钮。"""
        D = _main.D
        SM = _main.SM
        XS = _main.XS

        out_dir_frame = tk.Frame(parent, bg=D["page"])
        out_dir_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(out_dir_frame, text="保存到", bg=D["page"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(0, 8))
        c.out_dir = tk.StringVar(value=DEFAULT_OUT_DIR)
        tk.Label(out_dir_frame, textvariable=c.out_dir, bg=D["page"], fg=D["ink_dis"],
                 font=XS).pack(side=tk.LEFT, padx=(0, 8))
        app._btn(out_dir_frame, "浏览", app._select_m3u8_dir, "secondary").pack(side=tk.LEFT)

    def _build_settings_section(self, parent: tk.Frame, c: M3u8Context) -> None:
        """设置区：并发线程 + 输出格式 + 限速。"""
        D = _main.D
        SM = _main.SM

        settings_frame = tk.Frame(parent, bg=D["page"])
        settings_frame.pack(fill=tk.X, pady=(0, 8))
        # 并发线程
        tk.Label(settings_frame, text="并发线程", bg=D["page"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(0, 4))
        c.threads = ttk.Combobox(settings_frame, values=THREADS_VALUES,
                                 state="readonly", width=6)
        c.threads.set(DEFAULT_THREADS)
        c.threads.pack(side=tk.LEFT)
        # 输出格式
        tk.Label(settings_frame, text="输出格式", bg=D["page"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(12, 4))
        c.format = ttk.Combobox(settings_frame, values=FORMAT_VALUES,
                                state="readonly", width=6)
        c.format.set(DEFAULT_FORMAT)
        c.format.pack(side=tk.LEFT)
        # 限速
        tk.Label(settings_frame, text="限速 MB/s", bg=D["page"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(12, 4))
        c.speed = ttk.Combobox(settings_frame, values=SPEED_VALUES,
                              state="readonly", width=6)
        c.speed.set(DEFAULT_SPEED)
        c.speed.pack(side=tk.LEFT)

    def _build_adv_section(self, parent: tk.Frame, c: M3u8Context) -> None:
        """高级设置区：Cookie + 代理。"""
        D = _main.D
        BODY = _main.BODY
        SM = _main.SM
        XS = _main.XS

        adv_frame = tk.Frame(parent, bg=D["page"])
        adv_frame.pack(fill=tk.X, pady=(0, 8))
        # Cookie
        tk.Label(adv_frame, text="Cookie", bg=D["page"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(0, 4))
        c.cookie = tk.Entry(adv_frame, font=BODY, bg=D["input_bg"], fg=D["ink"],
                            relief="solid", bd=1, highlightthickness=0, width=25)
        c.cookie.pack(side=tk.LEFT, ipady=2)
        # 代理
        tk.Label(adv_frame, text="代理", bg=D["page"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(12, 4))
        c.proxy = tk.Entry(adv_frame, font=BODY, bg=D["input_bg"], fg=D["ink"],
                          relief="solid", bd=1, highlightthickness=0, width=18)
        c.proxy.pack(side=tk.LEFT, ipady=2)
        c.proxy.insert(0, "")
        tk.Label(adv_frame, text="如 http://127.0.0.1:7890", bg=D["page"],
                 fg=D["ink_dis"], font=XS).pack(side=tk.LEFT, padx=(4, 0))

    def _build_headers_section(self, parent: tk.Frame, c: M3u8Context) -> None:
        """Header + 断点续传区。"""
        D = _main.D
        BODY = _main.BODY
        SM = _main.SM
        XS = _main.XS

        hdr_frame = tk.Frame(parent, bg=D["page"])
        hdr_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(hdr_frame, text="自定义Header", bg=D["page"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(0, 4))
        c.headers = tk.Entry(hdr_frame, font=BODY, bg=D["input_bg"], fg=D["ink"],
                            relief="solid", bd=1, highlightthickness=0)
        c.headers.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2)
        tk.Label(hdr_frame, text="Key:Value,Key:Value", bg=D["page"], fg=D["ink_dis"],
                 font=XS).pack(side=tk.LEFT, padx=(4, 0))
        c.resume = tk.BooleanVar(value=True)
        tk.Checkbutton(hdr_frame, text="断点续传", variable=c.resume,
                       bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.RIGHT)

    def _build_notice(self, parent: tk.Frame) -> None:
        """速度提示条。"""
        D = _main.D
        SM = _main.SM
        notice_frame = tk.Frame(parent, bg=D["accent_pale"])
        notice_frame.pack(fill=tk.X, pady=(4, 0))
        tk.Label(notice_frame,
                 text="下载速度由服务器带宽决定，多线程只能在服务器允许范围内加速。速度慢可尝试切换画质或使用代理。",
                 bg=D["accent_pale"], fg=D["accent"], font=SM,
                 anchor=tk.CENTER, justify=tk.CENTER).pack(fill=tk.X, padx=4, pady=4)

    def _build_queue_section(self, parent: tk.Frame, c: M3u8Context, app) -> None:
        """下载队列卡片：标题+计数 + Listbox（带滚动条）+ 操作按钮（6 个）。"""
        D = _main.D
        FT = _main.FT
        XS = _main.XS

        queue_card = tk.Frame(parent, bg=D["border"], padx=1, pady=1)
        queue_card.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        queue_inner = tk.Frame(queue_card, bg=D["card"])
        queue_inner.pack(fill=tk.BOTH, expand=True)

        # 队列标题 + 计数
        q_header = tk.Frame(queue_inner, bg=D["card"])
        q_header.pack(fill=tk.X, padx=10, pady=(8, 4))
        tk.Label(q_header, text="下载队列", bg=D["card"], fg=D["ink"],
                 font=(FT, 9, "bold")).pack(side=tk.LEFT)
        c.count_label = tk.Label(q_header, text="0 个任务", bg=D["card"],
                                 fg=D["ink_dis"], font=XS)
        c.count_label.pack(side=tk.RIGHT)

        # 队列列表 + 滚动条
        q_list_frame = tk.Frame(queue_inner, bg=D["card"])
        q_list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 4))
        c.listbox = tk.Listbox(q_list_frame, font=(FT, 10), bg=D["card"], fg=D["ink"],
                               selectbackground=D["select_bg"], selectforeground=D["select_fg"],
                               bd=0, highlightthickness=0, activestyle="none",
                               selectborderwidth=0, height=6)
        q_scroll = ttk.Scrollbar(q_list_frame, orient=tk.VERTICAL,
                                 command=c.listbox.yview)
        c.listbox.configure(yscrollcommand=q_scroll.set)
        c.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        q_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 队列操作按钮（6 个）
        q_btn_frame = tk.Frame(queue_inner, bg=D["card"])
        q_btn_frame.pack(fill=tk.X, padx=10, pady=(0, 8))
        app._btn(q_btn_frame, "▲ 上移", app._m3u8_move_up, "ghost", padx=6).pack(side=tk.LEFT)
        app._btn(q_btn_frame, "▼ 下移", app._m3u8_move_down, "ghost", padx=6).pack(
            side=tk.LEFT, padx=(4, 0))
        app._btn(q_btn_frame, "✕ 移除选中", app._m3u8_remove_selected, "ghost", padx=8).pack(
            side=tk.LEFT, padx=(12, 0))
        app._btn(q_btn_frame, "清空队列", app._m3u8_clear_queue, "ghost", padx=8).pack(
            side=tk.LEFT, padx=(8, 0))
        app._btn(q_btn_frame, "📁 批量导入", app._m3u8_batch_import, "ghost", padx=8).pack(
            side=tk.LEFT, padx=(8, 0))
        app._btn(q_btn_frame, "⭐ 收藏链接", app._m3u8_show_favorites, "ghost", padx=8).pack(
            side=tk.LEFT, padx=(8, 0))
        app._btn(q_btn_frame, "📋 历史记录", app._m3u8_show_history, "ghost", padx=8).pack(
            side=tk.LEFT, padx=(8, 0))

    def _build_options_section(self, parent: tk.Frame, c: M3u8Context) -> None:
        """选项区：同时下载字幕 + 完成通知。"""
        D = _main.D
        SM = _main.SM

        opt_frame = tk.Frame(parent, bg=D["page"])
        opt_frame.pack(fill=tk.X, pady=(4, 0))
        c.download_sub = tk.BooleanVar(value=False)
        tk.Checkbutton(opt_frame, text="同时下载字幕", variable=c.download_sub,
                       bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.LEFT)
        c.notify = tk.BooleanVar(value=True)
        tk.Checkbutton(opt_frame, text="完成通知", variable=c.notify,
                       bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(16, 0))

    def _build_bottom_bar(self, parent: tk.Frame, c: M3u8Context, app) -> None:
        """底部操作栏：进度条 + 状态 + 打开文件夹/取消/开始下载按钮。

        注意：m3u8 的底部栏是自定义布局（不用 _bar），go 绑 _go_m3u8。
        """
        D = _main.D
        XS = _main.XS

        bottom_bar = tk.Frame(parent, bg=D["page"])
        bottom_bar.pack(fill=tk.X, pady=(8, 0))
        c.pg = ttk.Progressbar(bottom_bar, style="Horizontal.TProgressbar")
        c.pg.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        c.st = tk.Label(bottom_bar, text="就绪", bg=D["page"], fg=D["ink_dis"], font=XS)
        c.st.pack(side=tk.LEFT, padx=(0, 8))
        app._btn(bottom_bar, "📁 打开输出文件夹", app._open_output_folder, "ghost",
                 padx=8).pack(side=tk.RIGHT, padx=(0, 8))
        c.ca = app._btn(bottom_bar, "取消", None, "danger", padx=8, state=tk.DISABLED)
        c.ca.pack(side=tk.RIGHT, padx=(0, 4))
        c.ca.configure(command=lambda: app._stop("m3u8"))
        c.go = app._btn(bottom_bar, "开始下载", None, "primary", padx=16)
        c.go.pack(side=tk.RIGHT)
        c.go.configure(command=app._go_m3u8)

    # ── 偏好持久化 ──────────────────────────────────
    def collect_prefs(self) -> dict:
        """返回持久化偏好（与原 _save_panel_prefs 的 m3u8 分支一致，10 键）。

        注意：cookie/proxy/headers 是 Entry，用 .get()；其余是 Combobox/BooleanVar，用 .get()。
        """
        c = self.context
        return {
            "out_dir": c.out_dir.get(),
            "threads": c.threads.get(),
            "format": c.format.get(),
            "speed": c.speed.get(),
            "cookie": c.cookie.get(),
            "proxy": c.proxy.get(),
            "headers": c.headers.get(),
            "resume": c.resume.get(),
            "notify": c.notify.get(),
            "download_sub": c.download_sub.get(),
        }

    def apply_prefs(self, prefs: dict) -> None:
        """从持久化 prefs 恢复控件状态（与原 _load_panel_prefs 的 m3u8 分支一致，10 键）。

        注意：cookie/proxy/headers 是 Entry，用 delete+insert；其余用 set。
        resume/notify/download_sub 用 "in" 检查（允许 False 值）。
        """
        c = self.context
        if prefs.get("out_dir"): c.out_dir.set(prefs["out_dir"])
        if prefs.get("threads"): c.threads.set(prefs["threads"])
        if prefs.get("format"):  c.format.set(prefs["format"])
        if prefs.get("speed"):    c.speed.set(prefs["speed"])
        # Entry 类型：用 delete+insert
        if prefs.get("cookie"):
            c.cookie.delete(0, tk.END)
            c.cookie.insert(0, prefs["cookie"])
        if prefs.get("proxy"):
            c.proxy.delete(0, tk.END)
            c.proxy.insert(0, prefs["proxy"])
        if prefs.get("headers"):
            c.headers.delete(0, tk.END)
            c.headers.insert(0, prefs["headers"])
        # BooleanVar 类型：用 "in" 检查（允许 False 值）
        if "resume" in prefs:       c.resume.set(prefs["resume"])
        if "notify" in prefs:       c.notify.set(prefs["notify"])
        if "download_sub" in prefs: c.download_sub.set(prefs["download_sub"])
