"""格式大师 - 主程序  ·  Editorial White 设计"""
import os, sys, ctypes, time, queue

try:
    import windnd
except ImportError:
    windnd = None

try:
    from utils.drag_drop_ctypes import register_drop as ctypes_register_drop, \
        SafeDropHandler, parse_dropped_files
except ImportError:
    ctypes_register_drop = None
    SafeDropHandler = None
    parse_dropped_files = None

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

if getattr(sys, 'frozen', False):
    base_dir = sys._MEIPASS
    sys.path.insert(0, base_dir)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, base_dir)

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading

from utils.config import *
from utils.ffmpeg_manager import FFmpegManager
from utils.presets import get_preset_names, get_preset_by_name
from core.video_converter import VideoConverter
from core.audio_converter import AudioConverter
from core.image_converter import ImageConverter
from core.doc_converter import DocumentConverter
from core.tools import pdf_merge, pdf_split, pdf_get_page_count, image_compress, batch_rename

# ═══════════════════════════════════════════════
#  Design Tokens
# ═══════════════════════════════════════════════
D = {
    "page":         "#f5f3ef",
    "card":         "#ffffff",
    "card_alt":     "#fafaf8",
    "sidebar":      "#fafaf8",
    "sidebar_sel":  "#f0eeea",
    "accent":       "#e8604c",
    "accent_soft":  "#f08878",
    "accent_pale":  "#fceeeb",
    "accent_deep":  "#c44a38",
    "ink":          "#2c2a28",
    "ink_sec":      "#787470",
    "ink_dis":      "#b5b0aa",
    "ink_inv":      "#ffffff",
    "border":       "#e8e5e0",
    "border_hi":    "#d5d0c8",
    "divider":      "#ebe8e3",
    "ok":           "#3a9d6a",
    "warn":         "#d4940a",
    "err":          "#d44a4a",
    "input_bg":     "#ffffff",
    "input_bd":     "#ddd8d0",
    "input_focus":  "#e8604c",
    "prog_trough":  "#eeece8",
    "prog_fill":    "#e8604c",
}

# 字体
FT  = "Microsoft YaHei UI"
DISPLAY = (FT, 22, "bold")
H2      = (FT, 14, "bold")
BODY    = (FT, 10)
BODY_B  = (FT, 10, "bold")
SM      = (FT, 9)
XS      = (FT, 8)
NAV     = (FT, 10)
NAV_B   = (FT, 10, "bold")
BTN     = (FT, 10, "bold")


class FormatMaster:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        w = int(screen_w * 0.8)
        h = int(screen_h * 0.8)
        if w < 880: w = 880
        if h < 620: h = 620
        x = (screen_w - w) // 2
        y = (screen_h - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        
        self.root.minsize(880, 620)
        self.root.configure(bg=D["page"])
        try:
            ico = os.path.join(base_dir, "assets", "icon.ico")
            if os.path.exists(ico):
                self.root.iconbitmap(ico)
        except Exception:
            pass

        self.style = ttk.Style()
        self.style.theme_use("clam")
        self._ttk()

        self.panel_data = {}
        self.converting = False
        self.video_conv  = VideoConverter()
        self.audio_conv  = AudioConverter()
        self.image_conv  = ImageConverter()
        self.doc_conv    = DocumentConverter()
        self.ffmpeg_mgr  = FFmpegManager()
        self.current_tab = tk.StringVar(value="video")
        self._drop_handler = None

        self._ui()
        self.root.update_idletasks()
        self._setup_drag_drop()
        self._check_ffmpeg()

    # ── ttk 主题 ──────────────────────────────
    def _ttk(self):
        s = self.style
        s.configure("TFrame", background=D["page"])
        s.configure("TLabel", background=D["page"], foreground=D["ink"], font=BODY)
        s.configure("TCombobox",
                     fieldbackground=D["input_bg"], foreground="#000000",
                     selectbackground=D["accent_pale"], selectforeground="#000000",
                     font=BODY, padding=6)
        s.map("TCombobox",
               fieldbackground=[("readonly", D["input_bg"])],
               foreground=[("readonly", "#000000")],
               bordercolor=[("focus", D["input_focus"])])
        s.configure("Horizontal.TProgressbar",
                     troughcolor=D["prog_trough"], background=D["prog_fill"],
                     thickness=8, borderwidth=0)
        s.configure("AboutText.TButton",
                     font=("Segoe UI", 10),
                     foreground="#666666",
                     borderwidth=0,
                     padding=(12, 6))
        s.map("AboutText.TButton",
              foreground=[("active", "#333333")],
              background=[("pressed", "#e8e8e8"), ("active", "#f5f5f5")])
        self.root.option_add("*TCombobox*Listbox.background", D["input_bg"])
        self.root.option_add("*TCombobox*Listbox.foreground", D["ink"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", D["accent_pale"])

    # ── 按钮工厂 ──────────────────────────────
    def _btn(self, parent, text, cmd, style="secondary", **kw):
        presets = {
            "primary":   (D["accent"],    D["ink_inv"], D["accent_deep"], D["accent_soft"]),
            "secondary": (D["card"],      D["ink"],     D["border"],      D["border_hi"]),
            "ghost":     (D["page"],      D["ink_sec"], D["sidebar_sel"], D["border"]),
            "danger":    ("#fdf0f0",      D["err"],     "#f8dada",        "#f0c8c8"),
        }
        bg, fg, hover, active = presets[style]
        b = tk.Button(parent, text=text, command=cmd,
                      bg=bg, fg=fg, activebackground=active, activeforeground=fg,
                      font=BTN, bd=0, relief="flat", cursor="hand2",
                      padx=kw.pop("padx", 18), pady=kw.pop("pady", 8))
        b.bind("<Enter>", lambda e, w=b, c=hover:  w.configure(bg=c))
        b.bind("<Leave>", lambda e, w=b, c=bg:     w.configure(bg=c))
        if kw.get("state"): b.configure(state=kw["state"])
        return b

    # ── 主界面 ────────────────────────────────
    def _ui(self):
        # 顶部工具栏
        toolbar = tk.Frame(self.root, bg=D["page"], height=40)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        toolbar.pack_propagate(False)
        
        about_lbl = tk.Label(toolbar, text="关于", bg=D["page"], fg="#666666",
                             font=("Segoe UI", 10), cursor="hand2",
                             padx=12, pady=6)
        about_lbl.pack(side=tk.RIGHT, padx=16, pady=6)
        
        def on_about_enter(e):
            about_lbl.configure(bg=D["card_alt"], fg=D["ink"])
        
        def on_about_leave(e):
            about_lbl.configure(bg=D["page"], fg="#666666")
        
        about_lbl.bind("<Enter>", on_about_enter)
        about_lbl.bind("<Leave>", on_about_leave)
        about_lbl.bind("<Button-1>", lambda e: self._show_about())
        
        # 侧边栏
        sb = tk.Frame(self.root, bg=D["sidebar"], width=220,
                       highlightbackground=D["border"], highlightthickness=1)
        sb.pack(side=tk.LEFT, fill=tk.Y)
        sb.pack_propagate(False)

        # Logo
        logo_f = tk.Frame(sb, bg=D["sidebar"])
        logo_f.pack(fill=tk.X, padx=24, pady=(32, 8))
        tk.Label(logo_f, text="格式大师", bg=D["sidebar"], fg=D["accent"],
                 font=DISPLAY).pack(anchor=tk.W)
        tk.Label(logo_f, text=f"v{APP_VERSION}  ·  FormatMaster", bg=D["sidebar"],
                 fg=D["ink_dis"], font=XS).pack(anchor=tk.W, pady=(4, 0))

        tk.Frame(sb, bg=D["divider"], height=1).pack(fill=tk.X, padx=24, pady=(24, 18))

        # 导航
        self.nav = {}
        items = [
            ("video",    "▶  视频转换"),
            ("audio",    "♫  音频转换"),
            ("image",    "◆  图片转换"),
            ("doc",      "◇  文档转换"),
            ("gif",      "⊙  视频转GIF"),
            ("pdf",      "⊞  PDF合并拆分"),
            ("compress_img", "⊡  图片压缩"),
            ("rename",   "✏  批量重命名"),
            ("extract",  "↓  提取音频"),
            ("compress", "◈  视频压缩"),
            ("detect",   "🔍 格式检测"),
        ]
        for key, label in items:
            row = tk.Frame(sb, bg=D["sidebar"], cursor="hand2")
            row.pack(fill=tk.X, padx=12, pady=2)
            ind = tk.Frame(row, bg=D["sidebar"], width=4)
            ind.pack(side=tk.LEFT, fill=tk.Y, padx=(4, 10))
            lbl = tk.Label(row, text=label, bg=D["sidebar"], fg=D["ink_sec"],
                           font=NAV, anchor=tk.W, padx=10, pady=10)
            lbl.pack(fill=tk.X)
            for w in (row, ind, lbl):
                w.bind("<Button-1>", lambda e, k=key: self._switch(k))
                w.bind("<Enter>", lambda e, r=row: r.configure(bg=D["sidebar_sel"]))
                w.bind("<Leave>", lambda e, r=row, k=key:
                       r.configure(bg=D["sidebar_sel"] if self.current_tab.get() == k else D["sidebar"]))
            self.nav[key] = (row, ind, lbl)

        # 底部
        self.ff_lbl = tk.Label(sb, text="FFmpeg · 检测中…", bg=D["sidebar"],
                                fg=D["ink_dis"], font=XS, anchor=tk.W, padx=28)
        self.ff_lbl.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 20))

        # 主内容容器
        self.main_content = tk.Frame(self.root, bg=D["page"])
        self.main_content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 功能面板区
        self.content = tk.Frame(self.main_content, bg=D["page"])
        self.content.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.panels = {}
        self._p_video()
        self._p_audio()
        self._p_image()
        self._p_doc()
        self._p_gif()
        self._p_pdf()
        self._p_compress_img()
        self._p_rename()
        self._p_extract()
        self._p_compress()
        self._p_detect()
        self._switch("video")
        
        # 状态流面板
        self._status_stream = self._create_status_stream()
        
        self.status_queue = queue.Queue()
        self._process_status_queue()

    def _nav_update(self):
        cur = self.current_tab.get()
        for k, (row, ind, lbl) in self.nav.items():
            if k == cur:
                row.configure(bg=D["sidebar_sel"])
                ind.configure(bg=D["accent"])
                lbl.configure(bg=D["sidebar_sel"], fg=D["ink"], font=NAV_B)
            else:
                row.configure(bg=D["sidebar"])
                ind.configure(bg=D["sidebar"])
                lbl.configure(bg=D["sidebar"], fg=D["ink_sec"], font=NAV)
    
    def _create_status_stream(self):
        self.status_expanded = False
        self.log_line_count = 0
        self.MAX_LOG_LINES = 50
        
        frame = tk.Frame(self.main_content, bg="#ffffff", 
                         highlightbackground="#e0e0e0", highlightthickness=1)
        frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        header = tk.Frame(frame, bg="#ffffff")
        header.pack(fill=tk.X, padx=12, pady=(6, 4))
        
        tk.Label(header, text="状态流", bg="#ffffff", fg="#333333", 
                 font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        
        btn_frame = tk.Frame(header, bg="#ffffff")
        btn_frame.pack(side=tk.RIGHT)
        
        self.status_toggle_btn = tk.Button(btn_frame, text="▼", 
                                           command=self._toggle_status_stream,
                                           bg="#ffffff", fg="#666666", 
                                           font=("Segoe UI", 8),
                                           relief="flat", cursor="hand2", 
                                           padx=6, pady=1)
        self.status_toggle_btn.pack(side=tk.RIGHT, padx=(4, 0))
        
        self.status_clear_btn = tk.Button(btn_frame, text="清空", 
                                          command=self._clear_status_stream,
                                          bg="#ffffff", fg="#666666", 
                                          font=("Segoe UI", 8),
                                          relief="flat", cursor="hand2", 
                                          padx=8, pady=1)
        self.status_clear_btn.pack(side=tk.RIGHT, padx=(4, 0))
        
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.status_text = tk.Text(frame, height=2, wrap="word",
                                   bg="#ffffff", fg="#333333", 
                                   font=("Segoe UI", 9),
                                   bd=0, padx=12, pady=4,
                                   yscrollcommand=scrollbar.set,
                                   xscrollcommand=None,
                                   state=tk.DISABLED,
                                   insertwidth=0,
                                   selectbackground="#cce5ff",
                                   selectforeground="#000000")
        self.status_text.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.status_text.yview)
        
        self.status_text.tag_configure("success", foreground="#22c55e")
        self.status_text.tag_configure("error", foreground="#dc3545")
        self.status_text.tag_configure("warning", foreground="#f59e0b")
        self.status_text.tag_configure("info", foreground="#3b82f6")
        self.status_text.tag_configure("time", foreground="#999999", font=("Segoe UI", 8))
        
        self.status_text.bind("<Double-1>", self._copy_log_line)
        
        return frame
    
    def _toggle_status_stream(self):
        self.status_expanded = not self.status_expanded
        self.status_text.configure(height=6 if self.status_expanded else 2)
        self.status_toggle_btn.configure(text="▲" if self.status_expanded else "▼")
    
    def _clear_status_stream(self):
        self.status_text.configure(state=tk.NORMAL)
        self.status_text.delete(1.0, tk.END)
        self.status_text.configure(state=tk.DISABLED)
        self.log_line_count = 0
    
    def _copy_log_line(self, event):
        try:
            line_start = self.status_text.index("@%d,%d linestart" % (event.x, event.y))
            line_end = self.status_text.index("%s lineend" % line_start)
            line_text = self.status_text.get(line_start, line_end).strip()
            if line_text:
                ctypes.windll.user32.OpenClipboard(0)
                ctypes.windll.user32.EmptyClipboard()
                ctypes.windll.user32.SetClipboardTextW(line_text)
                ctypes.windll.user32.CloseClipboard()
        except Exception:
            pass
    
    def _log_status(self, message, level="info"):
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        self.status_queue.put((message, level, timestamp))
    
    def _process_status_queue(self):
        while not self.status_queue.empty():
            message, level, timestamp = self.status_queue.get()
            
            self.status_text.configure(state=tk.NORMAL)
            
            if self.status_text.index("end-1c") != "1.0":
                self.status_text.insert(tk.END, "\n")
            
            self.status_text.insert(tk.END, f"[{timestamp}]", "time")
            self.status_text.insert(tk.END, f" {message}", level)
            
            self.log_line_count += 1
            
            if self.log_line_count > self.MAX_LOG_LINES:
                self.status_text.delete(1.0, self.status_text.index("2.0"))
                self.log_line_count -= 1
            
            self.status_text.see(tk.END)
            self.status_text.configure(state=tk.DISABLED)
        
        self.root.after(100, self._process_status_queue)
    
    def _show_about(self):
        about_win = tk.Toplevel(self.root)
        about_win.title("关于")
        about_win.resizable(False, False)
        about_win.transient(self.root)
        about_win.grab_set()
        about_win.configure(bg="#f5f5f5")
        
        try:
            ico = os.path.join(base_dir, "assets", "icon.ico")
            if os.path.exists(ico):
                about_win.iconbitmap(ico)
        except Exception:
            pass
        
        frame = tk.Frame(about_win, bg="#f5f5f5")
        frame.pack(fill=tk.BOTH, expand=True, padx=24, pady=24)
        
        tk.Label(frame, text="格式大师", bg="#f5f5f5", fg="#333333",
                 font=("Segoe UI", 16, "bold")).pack(anchor=tk.W, pady=(0, 8))
        
        tk.Label(frame, text=f"版本 {APP_VERSION}", bg="#f5f5f5", fg="#666666",
                 font=("Segoe UI", 10)).pack(anchor=tk.W, pady=(0, 20))
        
        tk.Label(frame, text="一款功能强大的格式转换工具，支持视频、音频、图片、文档等多种格式的转换与处理。",
                 bg="#f5f5f5", fg="#666666", font=("Segoe UI", 9),
                 wraplength=340, justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 20))
        
        tk.Label(frame, text="GitHub:", bg="#f5f5f5", fg="#666666",
                 font=("Segoe UI", 9)).pack(anchor=tk.W)
        
        github_link = tk.Label(frame, 
                               text="https://github.com/2048895034qq/FormatMaster-EN",
                               bg="#f5f5f5", fg="#0d6efd",
                               font=("Segoe UI", 9, "underline"),
                               cursor="hand2",
                               wraplength=340, justify=tk.LEFT)
        github_link.pack(anchor=tk.W, pady=(4, 0))
        
        def open_github(event):
            import webbrowser
            webbrowser.open("https://github.com/2048895034qq/FormatMaster-EN")
        
        github_link.bind("<Button-1>", open_github)
        
        sep = tk.Frame(frame, bg="#e0e0e0", height=1)
        sep.pack(fill=tk.X, pady=(20, 16))
        
        disclaimer_text = """本软件仅供个人学习和研究使用。使用本软件进行格式转换时，请确保您拥有相关文件的合法使用权。
        
作者不对因使用本软件造成的任何数据损失或法律问题承担责任。请在使用前备份重要文件。"""
        
        tk.Label(frame, text=disclaimer_text, bg="#f5f5f5", fg="#999999",
                 font=("Segoe UI", 8), wraplength=340, justify=tk.LEFT).pack(anchor=tk.W)
        
        close_btn = tk.Button(frame, text="确定", command=about_win.destroy,
                              bg="#f5f5f5", fg="#333333",
                              font=("Segoe UI", 9),
                              relief="flat", cursor="hand2",
                              padx=16, pady=4)
        close_btn.pack(anchor=tk.CENTER, pady=(20, 0))
        
        about_win.update_idletasks()
        content_w = 400
        content_h = frame.winfo_reqheight() + 20
        about_win.geometry(f"{content_w}x{content_h}")
        
        screen_w = about_win.winfo_screenwidth()
        screen_h = about_win.winfo_screenheight()
        x = (screen_w - content_w) // 2
        y = (screen_h - content_h) // 2
        about_win.geometry(f"{content_w}x{content_h}+{x}+{y}")

    def _switch(self, tab):
        self.current_tab.set(tab)
        self._nav_update()
        for p in self.panels.values():
            p.pack_forget()
        self.panels[tab].pack(fill=tk.BOTH, expand=True, padx=32, pady=28)

    # ── 面板标题 ──────────────────────────────
    def _hdr(self, parent, title, sub):
        tk.Label(parent, text=title, bg=D["page"], fg=D["ink"],
                 font=H2).pack(anchor=tk.W)
        tk.Label(parent, text=sub, bg=D["page"], fg=D["ink_dis"],
                 font=XS).pack(anchor=tk.W, pady=(4, 18))

    # ── 文件选择区 ────────────────────────────
    def _file_sec(self, parent, key, fts, accept_all=False):
        self.panel_data[key] = {"files": [], "filetypes": fts, "listbox": None, "count": None, "accept_all": accept_all}
        d = self.panel_data[key]

        f = tk.Frame(parent, bg=D["page"])
        f.pack(fill=tk.BOTH, expand=True)

        # 按钮行
        br = tk.Frame(f, bg=D["page"])
        br.pack(fill=tk.X, pady=(0, 12))
        self._btn(br, "＋ 添加文件",  lambda k=key: self._add(k)).pack(side=tk.LEFT, padx=(0, 8))
        self._btn(br, "📁 文件夹",   lambda k=key: self._add_dir(k)).pack(side=tk.LEFT, padx=(0, 8))
        self._btn(br, "✕ 清空",      lambda k=key: self._clr(k), "ghost").pack(side=tk.LEFT)

        # 列表容器 — 白色圆角卡片感
        lo = tk.Frame(f, bg=D["border"], padx=1, pady=1)
        lo.pack(fill=tk.BOTH, expand=True)
        lb = tk.Listbox(lo, bg=D["input_bg"], fg=D["ink"],
                         font=(FT, 9), selectbackground=D["accent_pale"],
                         selectforeground=D["ink"],
                         bd=0, highlightthickness=1,
                         highlightbackground=D["input_bd"],
                         highlightcolor=D["accent"],
                         activestyle="none", relief="flat")
        scr = ttk.Scrollbar(lo, orient=tk.VERTICAL, command=lb.yview)
        lb.configure(yscrollcommand=scr.set)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scr.pack(side=tk.RIGHT, fill=tk.Y)

        d["listbox"] = lb
        d["count"] = tk.Label(f, text="0 个文件", bg=D["page"],
                               fg=D["ink_dis"], font=XS, anchor=tk.W)
        d["count"].pack(fill=tk.X, pady=(6, 0))
        return f

    def _add(self, key):
        d = self.panel_data[key]
        fs = filedialog.askopenfilenames(filetypes=d["filetypes"])
        for f in fs:
            if f not in d["files"]:
                d["files"].append(f)
                d["listbox"].insert(tk.END, f"  {os.path.basename(f)}")
        if fs: d["count"].configure(text=f"{len(d['files'])} 个文件")

    def _add_dir(self, key):
        d = self.panel_data[key]
        folder = filedialog.askdirectory()
        if not folder: return
        exts = {x[1:].lower() for ft in d["filetypes"] for x in ft[1].split() if x.startswith("*.")}
        for rd, _, fns in os.walk(folder):
            for fn in fns:
                fp = os.path.join(rd, fn)
                if any(fn.lower().endswith(e) for e in exts) and fp not in d["files"]:
                    d["files"].append(fp)
                    d["listbox"].insert(tk.END, f"  {fn}")
        d["count"].configure(text=f"{len(d['files'])} 个文件")

    def _clr(self, key):
        d = self.panel_data[key]
        d["files"].clear()
        d["listbox"].delete(0, tk.END)
        d["count"].configure(text="0 个文件")

    def _setup_drag_drop(self):
        hwnd = self.root.winfo_id()
        success = False
        
        if ctypes_register_drop and SafeDropHandler:
            try:
                self._drop_handler = SafeDropHandler(self.root)
                self._drop_handler.register_callback(self._handle_dropped_files)
                ctypes_register_drop(hwnd, self._drop_handler._enqueue_files)
                self._drop_handler.start()
                print("✅ 纯 ctypes 拖拽已启用（队列+after模式）")
                success = True
            except Exception as e:
                print(f"❌ 纯 ctypes 拖拽初始化失败: {e}")
        
        if not success and windnd:
            try:
                windnd.hook_dropfiles(hwnd, self._on_drop_windnd, force_unicode=True)
                print("✅ windnd 拖拽已启用")
                success = True
            except Exception as e:
                print(f"❌ windnd 初始化失败: {e}")
        
        if not success:
            print("❌ 拖拽功能不可用")

    def _handle_dropped_files(self, files):
        if not files:
            return
        
        if parse_dropped_files:
            files = parse_dropped_files(files)
        if not files:
            return
        
        try:
            if not hasattr(self, 'root') or not self.root.winfo_exists():
                return
            
            key = self.current_tab.get() if hasattr(self, 'current_tab') else None
            if not key:
                return
            
            d = self.panel_data.get(key) if hasattr(self, 'panel_data') else None
            if not d or d.get("listbox") is None:
                return
            
            accept_all = d.get("accept_all", False)
            exts = set()
            if not accept_all and d.get("filetypes"):
                for ft in d["filetypes"]:
                    if len(ft) > 1:
                        for pat in ft[1].split():
                            if pat.startswith("*."):
                                exts.add(pat[1:].lower())
            
            added = 0
            for f in files:
                try:
                    if not f or not os.path.isfile(f):
                        continue
                    
                    if d.get("files") is not None and f in d["files"]:
                        continue
                    
                    if not accept_all and exts:
                        file_ext = os.path.splitext(f)[1].lower()
                        if file_ext not in exts:
                            continue
                    
                    if d.get("files") is not None:
                        d["files"].append(f)
                    
                    try:
                        d["listbox"].insert(tk.END, f"  {os.path.basename(f)}")
                    except (tk.TclError, AttributeError):
                        continue
                    
                    added += 1
                except Exception:
                    continue
            
            if added > 0 and d.get("count") is not None:
                try:
                    d["count"].configure(text=f"{len(d['files'])} 个文件")
                except (tk.TclError, AttributeError):
                    pass
        except Exception:
            pass

    def _on_drop_windnd(self, files):
        if isinstance(files, (list, tuple)):
            self._handle_dropped_files(files)

    # ── 设置卡片（自适应网格布局）────────────────
    def _card(self, parent, title):
        outer = tk.Frame(parent, bg=D["card"], highlightbackground=D["border"],
                          highlightthickness=1)
        outer.pack(fill=tk.X, pady=(0, 16), expand=False)
        inner = tk.Frame(outer, bg=D["card"], padx=20, pady=16)
        inner.pack(fill=tk.BOTH, expand=True)
        tk.Label(inner, text=title, bg=D["card"], fg=D["ink_sec"],
                 font=(FT, 9, "bold")).pack(anchor=tk.W, pady=(0, 10))
        # 网格容器
        grid = tk.Frame(inner, bg=D["card"])
        grid.pack(fill=tk.X)
        grid._col_count = 0
        grid._max_cols = 3
        grid._widgets = []
        return grid

    def _row(self, parent, label, values, default, w=12):
        """往网格卡片里添加一项，自动换列/换行"""
        grid = parent
        # 计算当前位置
        idx = grid._col_count
        cols = grid._max_cols
        r, c = divmod(idx, cols)

        frame = tk.Frame(grid, bg=D["card"])
        frame.grid(row=r, column=c, padx=(0, 18), pady=5, sticky="ew")
        tk.Label(frame, text=label, bg=D["card"], fg=D["ink"],
                 font=SM).pack(anchor=tk.W)
        cb = ttk.Combobox(frame, values=values, state="readonly", width=w)
        cb.set(default)
        cb.pack(fill=tk.X, pady=(2, 0))

        # 让各列等宽
        for i in range(cols):
            grid.columnconfigure(i, weight=1)

        grid._col_count += 1
        grid._widgets.append(cb)
        return cb

    # ── 进度栏 ────────────────────────────────
    def _bar(self, parent):
        b = tk.Frame(parent, bg=D["page"])
        b.pack(fill=tk.X, pady=(18, 0))
        pg = ttk.Progressbar(b, style="Horizontal.TProgressbar")
        pg.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 16))
        st = tk.Label(b, text="就绪", bg=D["page"], fg=D["ink_dis"], font=XS)
        st.pack(side=tk.LEFT, padx=(0, 16))
        ca = self._btn(b, "取消", None, "danger", state=tk.DISABLED)
        ca.pack(side=tk.RIGHT)
        go = self._btn(b, "开始转换", None, "primary", padx=24)
        go.pack(side=tk.RIGHT, padx=(0, 10))
        return pg, st, go, ca

    # ══════════════════════════════════════════
    #  各面板
    # ══════════════════════════════════════════
    def _p_video(self):
        p = tk.Frame(self.content, bg=D["page"])
        self.panels["video"] = p
        self._hdr(p, "视频格式转换", "MP4 · AVI · MKV · WMV · MOV · FLV · WEBM 等主流格式互转")
        self._file_sec(p, "video",
            [("视频文件","*.mp4 *.avi *.mkv *.wmv *.mov *.flv *.webm *.ts *.mpeg *.3gp"),("所有文件","*.*")])
        
        preset_frame = tk.Frame(p, bg=D["page"])
        preset_frame.pack(fill=tk.X, pady=(0, 12))
        tk.Label(preset_frame, text="快速预设:", bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 8))
        video_presets = ["自定义"] + get_preset_names("video")
        self.v_preset_combo = ttk.Combobox(preset_frame, values=video_presets, state="readonly", width=12)
        self.v_preset_combo.set("自定义")
        self.v_preset_combo.pack(side=tk.LEFT)
        self.v_preset_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_video_preset())
        
        s = self._card(p, "输出设置")
        self.v_fmt     = self._row(s, "目标格式", list(SUPPORTED_VIDEO.keys()), "MP4")
        self.v_codec   = self._row(s, "视频编码", list(VIDEO_CODECS.keys()), "默认")
        self.v_preset  = self._row(s, "画质预设", list(VIDEO_PRESETS.keys()), "原始质量")
        self.v_res     = self._row(s, "分辨率",  list(RESOLUTIONS.keys()), "原始分辨率", 16)
        self.v_fps     = self._row(s, "帧率",    ["原始帧率","24","25","30","60"], "原始帧率")
        self.v_br      = self._row(s, "码率",    ["自动","1M","2M","5M","8M","10M","20M"], "自动")
        
        out_dir_frame = tk.Frame(p, bg=D["page"])
        out_dir_frame.pack(fill=tk.X, pady=(12, 0))
        tk.Label(out_dir_frame, text="输出目录:", bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 8))
        self.v_out_dir = tk.StringVar(value="与源文件同目录")
        self.v_out_dir_combo = ttk.Combobox(out_dir_frame, values=["与源文件同目录", "自定义目录"], state="readonly", width=14)
        self.v_out_dir_combo.set("与源文件同目录")
        self.v_out_dir_combo.pack(side=tk.LEFT)
        self.v_out_dir_btn = self._btn(out_dir_frame, "浏览", lambda: self._select_out_dir("video"), style="ghost")
        self.v_out_dir_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.v_out_dir_path = tk.StringVar(value="")
        self.v_out_dir_label = tk.Label(out_dir_frame, textvariable=self.v_out_dir_path, bg=D["page"], fg=D["ink_dis"], font=XS)
        self.v_out_dir_label.pack(side=tk.LEFT, padx=(8, 0))
        
        self.v_pg, self.v_st, self.v_go, self.v_ca = self._bar(p)
        self.v_go.configure(command=lambda: self._go("video"))
        self.v_ca.configure(command=lambda: self._stop("video"))

    def _apply_video_preset(self):
        name = self.v_preset_combo.get()
        if name == "自定义":
            return
        preset = get_preset_by_name("video", name)
        if preset:
            if preset.get("ext"):
                for k, v in SUPPORTED_VIDEO.items():
                    if v == preset["ext"]:
                        self.v_fmt.set(k)
                        break
            if preset.get("codec"):
                for k, v in VIDEO_CODECS.items():
                    if v == preset["codec"]:
                        self.v_codec.set(k)
                        break
            if preset.get("preset"):
                for k, v in VIDEO_PRESETS.items():
                    if v == preset["preset"]:
                        self.v_preset.set(k)
                        break
            if preset.get("resolution"):
                self.v_res.set(preset["resolution"])

    def _select_out_dir(self, panel_key):
        dir_path = filedialog.askdirectory()
        if dir_path:
            self.v_out_dir_path.set(dir_path)
            self.v_out_dir_combo.set("自定义目录")

    def _p_audio(self):
        p = tk.Frame(self.content, bg=D["page"])
        self.panels["audio"] = p
        self._hdr(p, "音频格式转换", "MP3 · WAV · WMA · AAC · FLAC · OGG · M4A 等格式互转")
        self._file_sec(p, "audio",
            [("音频文件","*.mp3 *.wav *.wma *.aac *.flac *.ogg *.m4a *.amr *.opus"),("所有文件","*.*")])
        s = self._card(p, "输出设置")
        self.a_fmt  = self._row(s, "目标格式", list(SUPPORTED_AUDIO.keys()), "MP3")
        self.a_br   = self._row(s, "比特率", ["128k","192k","256k","320k"], "192k")
        self.a_sr   = self._row(s, "采样率", ["原始","22050","44100","48000","96000"], "原始")
        self.a_ch   = self._row(s, "声道",   ["原始","单声道","立体声"], "原始")
        
        tk.Label(s, text="音量", bg=D["card"], fg=D["ink"], font=SM).grid(row=4, column=0, sticky="w")
        self.a_vol = tk.Scale(s, from_=20, to=200, orient=tk.HORIZONTAL,
                               bg=D["card"], fg=D["ink"], font=BODY,
                               highlightthickness=0, sliderlength=20,
                               troughcolor=D["input_bg"], relief="flat")
        self.a_vol.set(100)
        self.a_vol.grid(row=4, column=1, sticky="ew", padx=(4, 0))
        self.a_pg, self.a_st, self.a_go, self.a_ca = self._bar(p)
        self.a_go.configure(command=lambda: self._go("audio"))
        self.a_ca.configure(command=lambda: self._stop("audio"))

    def _p_image(self):
        p = tk.Frame(self.content, bg=D["page"])
        self.panels["image"] = p
        self._hdr(p, "图片格式转换", "JPG · PNG · BMP · GIF · TIFF · WEBP · ICO 格式互转")
        self._file_sec(p, "image",
            [("图片文件","*.jpg *.jpeg *.png *.bmp *.gif *.tiff *.webp *.ico *.tga"),("所有文件","*.*")])
        s = self._card(p, "输出设置")
        self.i_fmt  = self._row(s, "目标格式", list(SUPPORTED_IMAGE.keys()), "PNG")
        self.i_q    = self._row(s, "质量", ["100（无损）","95（高质量）","85（中等）","70（低质量）","50（压缩）"], "95（高质量）")
        self.i_sz   = self._row(s, "缩放", ["原始大小","50%","25%","200%"], "原始大小")
        
        tk.Label(s, text="水印文字", bg=D["card"], fg=D["ink"], font=SM).grid(row=3, column=0, sticky="w")
        self.i_watermark = tk.Entry(s, font=BODY, bg=D["input_bg"], fg="#000000",
                                     insertbackground="#000000", relief="flat",
                                     highlightthickness=1, highlightbackground=D["input_bd"],
                                     highlightcolor=D["accent"])
        self.i_watermark.grid(row=3, column=1, sticky="ew", padx=(4, 0))
        
        tk.Label(s, text="水印位置", bg=D["card"], fg=D["ink"], font=SM).grid(row=4, column=0, sticky="w")
        self.i_watermark_pos = self._row(s, "", ["右下角","左下角","右上角","左上角","居中"], "右下角")
        
        self.i_pg, self.i_st, self.i_go, self.i_ca = self._bar(p)
        self.i_go.configure(command=lambda: self._go("image"))
        self.i_ca.configure(command=lambda: self._stop("image"))

    def _p_doc(self):
        p = tk.Frame(self.content, bg=D["page"])
        self.panels["doc"] = p
        self._hdr(p, "文档格式转换", "PDF · Word · Excel · PPT · WPS · TXT · 图片 之间互相转换")
        exts = "*.pdf *.docx *.doc *.wps *.xlsx *.xls *.et *.csv *.pptx *.ppt *.dps *.txt *.html *.htm *.jpg *.jpeg *.png *.bmp *.tiff *.webp"
        self._file_sec(p, "doc", [("文档文件",exts),("所有文件","*.*")], True)
        s = self._card(p, "转换设置")
        tk.Label(s, text="添加文件后点击「检测格式」，系统将自动列出可转换的目标格式",
                 bg=D["card"], fg=D["ink_dis"], font=XS).grid(row=0, column=0, columnspan=3,
                                                              sticky="w", pady=(0, 8))
        tk.Label(s, text="目标格式", bg=D["card"], fg=D["ink"],
                 font=SM).grid(row=1, column=0, sticky="w")
        self.d_tgt = ttk.Combobox(s, values=["请先添加文件"], state="readonly", width=22)
        self.d_tgt.set("请先添加文件")
        self.d_tgt.grid(row=1, column=1, sticky="ew", padx=(4, 10))
        self._btn(s, "检测格式", self._detect).grid(row=1, column=2, sticky="w")
        self.d_pg, self.d_st, self.d_go, self.d_ca = self._bar(p)
        self.d_go.configure(command=lambda: self._go("doc"))
        self.d_ca.configure(command=lambda: self._stop("doc"))

    def _detect(self):
        data = self.panel_data.get("doc", {})
        files = data.get("files", [])
        if not files:
            messagebox.showinfo("提示", "请先添加文档文件"); return
        ext = os.path.splitext(files[0])[1].lower()
        src = DOC_READ_FORMATS.get(ext)
        if not src:
            messagebox.showwarning("提示", f"不支持的格式: {ext}"); return
        tgts = DOC_CONVERSION_MAP.get(src, [])
        if not tgts:
            messagebox.showinfo("提示", f"暂不支持从 {src} 转换"); return
        names = [f"{t}（{DOC_READ_FORMATS.get(t, t)}）" for t in tgts]
        self.d_tgt.configure(values=names)
        self.d_tgt.set(names[0])
        self.d_st.configure(text=f"已识别 {src}  ·  {len(files)} 个文件")

    def _p_extract(self):
        p = tk.Frame(self.content, bg=D["page"])
        self.panels["extract"] = p
        self._hdr(p, "从视频提取音频", "将视频中的音轨提取为独立音频文件")
        self._file_sec(p, "extract",
            [("视频文件","*.mp4 *.avi *.mkv *.wmv *.mov *.flv *.webm *.ts *.3gp"),("所有文件","*.*")])
        s = self._card(p, "输出设置")
        self.e_fmt = self._row(s, "音频格式", ["MP3","AAC","FLAC","WAV"], "MP3")
        self.e_br  = self._row(s, "比特率", ["128k","192k","256k","320k"], "192k")
        self.e_pg, self.e_st, self.e_go, self.e_ca = self._bar(p)
        self.e_go.configure(command=lambda: self._go("extract"))
        self.e_ca.configure(command=lambda: self._stop("extract"))

    def _p_compress(self):
        p = tk.Frame(self.content, bg=D["page"])
        self.panels["compress"] = p
        self._hdr(p, "视频压缩", "减小视频文件体积，便于存储和分享")
        self._file_sec(p, "compress",
            [("视频文件","*.mp4 *.avi *.mkv *.wmv *.mov *.flv *.webm *.ts *.3gp"),("所有文件","*.*")])
        s = self._card(p, "压缩设置")
        self.c_q   = self._row(s, "压缩质量", ["高质量（文件较大）","中等质量（推荐）","低质量（文件最小）"], "中等质量（推荐）", 20)
        self.c_res = self._row(s, "分辨率", list(RESOLUTIONS.keys()), "原始分辨率", 16)
        self.c_pg, self.c_st, self.c_go, self.c_ca = self._bar(p)
        self.c_go.configure(command=lambda: self._go("compress"))
        self.c_ca.configure(command=lambda: self._stop("compress"))

    # ── 格式检测 ──────────────────────────────
    def _p_detect(self):
        p = tk.Frame(self.content, bg=D["page"])
        self.panels["detect"] = p
        self._hdr(p, "格式检测", "批量检测文件夹中所有文件的格式，自动分类到对应功能面板")
        
        s = self._card(p, "检测设置")
        
        tk.Label(s, text="目标文件夹", bg=D["card"], fg=D["ink"], font=SM).grid(row=0, column=0, sticky="w")
        self.detect_path = tk.Entry(s, font=BODY, bg=D["input_bg"], fg="#000000",
                                     insertbackground="#000000", relief="flat",
                                     highlightthickness=1, highlightbackground=D["input_bd"],
                                     highlightcolor=D["accent"], width=40)
        self.detect_path.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self._btn(s, "浏览", self._detect_browse, style="ghost", padx=12, pady=2).grid(row=0, column=2, padx=(4, 0))
        
        self.detect_auto_add = tk.BooleanVar(value=True)
        tk.Checkbutton(s, text="自动添加到对应面板", variable=self.detect_auto_add,
                       bg=D["card"], fg=D["ink"], font=SM).grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))
        
        self.detect_results = tk.Text(p, height=8, bg=D["card"], fg=D["ink"], font=BODY,
                                       bd=0, relief="flat", padx=12, pady=8,
                                       state=tk.DISABLED)
        self.detect_results.pack(fill=tk.BOTH, expand=True, padx=16, pady=(12, 16))
        
        self.detect_results.tag_configure("video", foreground="#ef4444")
        self.detect_results.tag_configure("audio", foreground="#22c55e")
        self.detect_results.tag_configure("image", foreground="#3b82f6")
        self.detect_results.tag_configure("doc", foreground="#f59e0b")
        self.detect_results.tag_configure("pdf", foreground="#8b5cf6")
        self.detect_results.tag_configure("count", foreground=D["ink_dis"], font=XS)
        
        self.detect_pg, self.detect_st, self.detect_go, self.detect_ca = self._bar(p)
        self.detect_go.configure(command=self._detect_start)
        self.detect_ca.configure(command=self._detect_stop)
        self.detect_ca.configure(state=tk.DISABLED)
    
    def _detect_browse(self):
        path = filedialog.askdirectory(title="选择文件夹")
        if path:
            self.detect_path.delete(0, tk.END)
            self.detect_path.insert(0, path)
    
    def _detect_start(self):
        path = self.detect_path.get()
        if not path or not os.path.isdir(path):
            messagebox.showwarning("提示", "请选择有效的文件夹"); return
        
        self.detect_go.configure(state=tk.DISABLED)
        self.detect_ca.configure(state=tk.NORMAL)
        self.detect_results.configure(state=tk.NORMAL)
        self.detect_results.delete(1.0, tk.END)
        self.detect_results.configure(state=tk.DISABLED)
        
        threading.Thread(target=self._detect_run, args=(path,), daemon=True).start()
    
    def _detect_stop(self):
        self.detecting = False
    
    def _detect_run(self, path):
        self.detecting = True
        
        VIDEO_EXTS = {'.mp4', '.avi', '.mkv', '.wmv', '.mov', '.flv', '.webm', '.ts', '.3gp'}
        AUDIO_EXTS = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.amr', '.opus'}
        IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.svg'}
        DOC_EXTS = {'.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.rtf'}
        PDF_EXTS = {'.pdf'}
        
        detected = {
            'video': [], 'audio': [], 'image': [], 'doc': [], 'pdf': [], 'other': []
        }
        
        all_files = []
        for root, dirs, files in os.walk(path):
            for f in files:
                if not self.detecting:
                    self.root.after(0, lambda: self.detect_st.configure(text="检测已取消"))
                    return
                all_files.append(os.path.join(root, f))
        
        def update_status(msg):
            self.root.after(0, lambda: self.detect_st.configure(text=msg))
        
        update_status(f"正在检测 {len(all_files)} 个文件...")
        
        for i, fp in enumerate(all_files):
            if not self.detecting:
                update_status("检测已取消")
                return
            
            ext = os.path.splitext(fp)[1].lower()
            if ext in VIDEO_EXTS:
                detected['video'].append(fp)
            elif ext in AUDIO_EXTS:
                detected['audio'].append(fp)
            elif ext in IMAGE_EXTS:
                detected['image'].append(fp)
            elif ext in DOC_EXTS:
                detected['doc'].append(fp)
            elif ext in PDF_EXTS:
                detected['pdf'].append(fp)
            else:
                detected['other'].append(fp)
            
            if i % 20 == 0:
                update_status(f"已检测 {i+1}/{len(all_files)} 个文件")
        
        def show_results():
            self.detect_results.configure(state=tk.NORMAL)
            self.detect_results.delete(1.0, tk.END)
            
            type_names = {
                'video': ('视频文件', 'video'),
                'audio': ('音频文件', 'audio'),
                'image': ('图片文件', 'image'),
                'doc': ('文档文件', 'doc'),
                'pdf': ('PDF文件', 'pdf'),
                'other': ('其他文件', 'info')
            }
            
            total_found = 0
            for key, (name, tag) in type_names.items():
                count = len(detected[key])
                if count > 0:
                    total_found += count
                    self.detect_results.insert(tk.END, f"【{name}】{count} 个\n", tag)
                    for fp in detected[key][:5]:
                        self.detect_results.insert(tk.END, f"  └─ {os.path.basename(fp)}\n")
                    if count > 5:
                        self.detect_results.insert(tk.END, f"  ... 还有 {count-5} 个文件\n")
            
            self.detect_results.insert(tk.END, f"\n共检测到 {total_found} 个可处理文件", "count")
            self.detect_results.configure(state=tk.DISABLED)
            
            self.detect_st.configure(text=f"检测完成，共 {total_found} 个文件")
            self.detect_go.configure(state=tk.NORMAL)
            self.detect_ca.configure(state=tk.DISABLED)
            
            if self.detect_auto_add.get():
                for key, files in detected.items():
                    if files and key in self.panel_data:
                        self.panel_data[key]["files"] = list(set(self.panel_data[key].get("files", []) + files))
                        if hasattr(self, 'panel_data') and key in self.panel_data:
                            listbox = self.panel_data[key].get("listbox")
                            if listbox:
                                listbox.delete(0, tk.END)
                                for f in self.panel_data[key]["files"]:
                                    listbox.insert(tk.END, os.path.basename(f))
                
                self._log_status(f"格式检测完成，已自动分类 {total_found} 个文件", "success")
        
        self.root.after(0, show_results)

    # ── 视频转GIF ─────────────────────────────
    def _p_gif(self):
        p = tk.Frame(self.content, bg=D["page"])
        self.panels["gif"] = p
        self._hdr(p, "视频转GIF", "将视频片段转换为GIF动图，支持自定义分辨率和帧率")
        self._file_sec(p, "gif",
            [("视频文件","*.mp4 *.avi *.mkv *.mov *.flv *.webm *.ts"),("所有文件","*.*")])
        s = self._card(p, "GIF设置")
        self.gif_w     = self._row(s, "宽度", ["原始","640","480","320","240"], "480")
        self.gif_fps   = self._row(s, "帧率", ["10","15","20","24","30"], "15")
        self.gif_start = self._row(s, "开始(秒)", ["0"], "0")
        self.gif_dur   = self._row(s, "时长(秒)", ["5","10","15","30","60","全部"], "10")
        self.gif_pg, self.gif_st, self.gif_go, self.gif_ca = self._bar(p)
        self.gif_go.configure(command=lambda: self._go("gif"))
        self.gif_ca.configure(command=lambda: self._stop("gif"))

    # ── PDF合并拆分 ───────────────────────────
    def _p_pdf(self):
        p = tk.Frame(self.content, bg=D["page"])
        self.panels["pdf"] = p
        self._hdr(p, "PDF 合并 / 拆分", "多个PDF合并为一个，或将一个PDF按页码范围拆分")
        self._file_sec(p, "pdf", [("PDF文件","*.pdf"),("所有文件","*.*")])
        s = self._card(p, "操作设置")

        # 模式切换
        tk.Label(s, text="操作模式", bg=D["card"], fg=D["ink"],
                 font=SM).grid(row=0, column=0, sticky="w")
        self.pdf_mode = ttk.Combobox(s, values=["合并（多个→一个）", "拆分（一个→多个）"],
                                      state="readonly", width=20)
        self.pdf_mode.set("合并（多个→一个）")
        self.pdf_mode.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.pdf_mode.bind("<<ComboboxSelected>>", lambda e: self._pdf_mode_changed())

        # 拆分页码输入（仅拆分模式可见）
        self.pdf_range_frame = tk.Frame(s, bg=D["card"])
        self.pdf_range_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=5)
        tk.Label(self.pdf_range_frame, text="页码范围", bg=D["card"], fg=D["ink"],
                 font=SM).pack(side=tk.LEFT)
        self.pdf_range = tk.Entry(self.pdf_range_frame, font=BODY,
                                   bg=D["input_bg"], fg="#000000",
                                   insertbackground="#000000",
                                   relief="flat", highlightthickness=1,
                                   highlightbackground=D["input_bd"],
                                   highlightcolor=D["accent"])
        self.pdf_range.insert(0, "1-3,5,7-10")
        self.pdf_range.pack(side=tk.LEFT, padx=(6, 0), fill=tk.X, expand=True)
        self.pdf_range_frame.grid_remove()  # 默认隐藏

        self.pdf_pg, self.pdf_st, self.pdf_go, self.pdf_ca = self._bar(p)
        self.pdf_go.configure(command=lambda: self._go("pdf"))
        self.pdf_ca.configure(command=lambda: self._stop("pdf"))

    def _pdf_mode_changed(self):
        if "拆分" in self.pdf_mode.get():
            self.pdf_range_frame.grid()
        else:
            self.pdf_range_frame.grid_remove()

    # ── 图片压缩 ──────────────────────────────
    def _p_compress_img(self):
        p = tk.Frame(self.content, bg=D["page"])
        self.panels["compress_img"] = p
        self._hdr(p, "图片压缩", "批量压缩图片体积，保持格式不变，支持限制最大分辨率")
        self._file_sec(p, "compress_img",
            [("图片文件","*.jpg *.jpeg *.png *.bmp *.webp *.tiff"),("所有文件","*.*")])
        s = self._card(p, "压缩设置")
        self.ci_q  = self._row(s, "输出质量", ["95","85","75","60","50","40","30"], "75")
        self.ci_sz = self._row(s, "最大分辨率", ["不限制","1920x1080","1280x720","800x600"], "不限制")
        self.ci_pg, self.ci_st, self.ci_go, self.ci_ca = self._bar(p)
        self.ci_go.configure(command=lambda: self._go("compress_img"))
        self.ci_ca.configure(command=lambda: self._stop("compress_img"))

    # ── 批量重命名 ────────────────────────────
    def _p_rename(self):
        p = tk.Frame(self.content, bg=D["page"])
        self.panels["rename"] = p
        self._hdr(p, "批量重命名", "统一添加前缀/后缀、序号命名、替换文字等")
        self._file_sec(p, "rename", [("所有文件","*.*")])
        s = self._card(p, "命名规则")
        tk.Label(s, text="占位符：{n}=序号  {name}=原名  {ext}=扩展名  {date}=日期",
                 bg=D["card"], fg=D["ink_dis"], font=XS).grid(row=0, column=0, columnspan=3,
                                                              sticky="w", pady=(0, 8))
        self.rn_pattern = self._row(s, "命名模板", [], "文件_{n:03d}", 22)
        self.rn_pattern.configure(values=[
            "文件_{n:03d}",
            "{name}_压缩",
            "{name}_{date}",
            "{name}_new",
            "IMG_{n:04d}",
        ])
        self.rn_start = self._row(s, "起始序号", ["1","0","100"], "1")
        self.rn_pg, self.rn_st, self.rn_go, self.rn_ca = self._bar(p)
        self.rn_go.configure(command=lambda: self._go("rename"))
        self.rn_ca.configure(command=lambda: self._stop("rename"))

    # ══════════════════════════════════════════
    #  FFmpeg
    # ══════════════════════════════════════════
    def _check_ffmpeg(self):
        def cb(ok, _):
            self.root.after(0, lambda: self._ff(ok))
        self.ffmpeg_mgr.download_async(cb)

    def _ff(self, ok):
        if ok or self.ffmpeg_mgr.is_available():
            self.ff_lbl.configure(text="FFmpeg · 已就绪 ✓", fg=D["ok"])
        else:
            self.ff_lbl.configure(text="FFmpeg · 未安装 ✗", fg=D["err"])

    # ══════════════════════════════════════════
    #  转换调度
    # ══════════════════════════════════════════
    def _w(self, t):
        m = {
            "video":       (self.v_pg, self.v_st, self.v_go, self.v_ca),
            "audio":       (self.a_pg, self.a_st, self.a_go, self.a_ca),
            "image":       (self.i_pg, self.i_st, self.i_go, self.i_ca),
            "doc":         (self.d_pg, self.d_st, self.d_go, self.d_ca),
            "gif":         (self.gif_pg, self.gif_st, self.gif_go, self.gif_ca),
            "pdf":         (self.pdf_pg, self.pdf_st, self.pdf_go, self.pdf_ca),
            "compress_img":(self.ci_pg, self.ci_st, self.ci_go, self.ci_ca),
            "rename":      (self.rn_pg, self.rn_st, self.rn_go, self.rn_ca),
            "extract":     (self.e_pg, self.e_st, self.e_go, self.e_ca),
            "compress":    (self.c_pg, self.c_st, self.c_go, self.c_ca),
        }
        pg, st, go, ca = m[t]
        return {"pg": pg, "st": st, "go": go, "ca": ca}

    def _go(self, t):
        files = self.panel_data.get(t, {}).get("files", [])
        if not files:
            messagebox.showwarning("提示", "请先添加文件"); return
        if t in ("video","audio","extract","compress","gif") and not self.ffmpeg_mgr.is_available():
            messagebox.showwarning("提示", "FFmpeg 未就绪，请稍后重试"); return
        if t == "doc":
            tgt = self.d_tgt.get()
            if not tgt or tgt == "请先添加文件":
                messagebox.showwarning("提示", "请先点击「检测格式」"); return

        self.converting = True
        w = self._w(t)
        w["go"].configure(state=tk.DISABLED)
        w["ca"].configure(state=tk.NORMAL)
        w["pg"]["value"] = 0
        
        task_names = {
            "video": "视频转换", "audio": "音频转换", "image": "图片转换",
            "doc": "文档转换", "gif": "视频转GIF", "pdf": "PDF处理",
            "compress_img": "图片压缩", "rename": "批量重命名",
            "extract": "提取音频", "compress": "视频压缩"
        }
        
        self._log_status(f"开始 {task_names.get(t, t)}，共 {len(files)} 个文件", "info")
        self.root.attributes("-disabled", True)
        t = threading.Thread(target=self._run, args=(t,), daemon=True)
        t.start()

    def _stop(self, t):
        if t in ("video","compress","extract","gif"): self.video_conv.cancel()
        elif t == "audio":  self.audio_conv.cancel()
        elif t == "image":  self.image_conv.cancel()
        elif t == "doc":    self.doc_conv.cancel()
        self.converting = False

    def _run(self, t):
        w = self._w(t)
        files = self.panel_data[t]["files"]
        total = len(files)
        ok_n = 0
        start_time = time.time()
        
        def update_progress(pct, msg):
            elapsed = int(time.time() - start_time)
            elapsed_str = f"{elapsed}s" if elapsed < 60 else f"{elapsed//60}m{elapsed%60}s"
            
            def do_update():
                w["pg"].configure(value=max(0, pct))
                w["st"].configure(text=f"{msg} · {elapsed_str}")
                if "完成" in msg:
                    self._log_status(msg.replace("完成", "已完成"), "success")
                elif "失败" in msg:
                    self._log_status(msg.replace("失败", "失败"), "error")
                elif pct > 0:
                    self._log_status(msg, "info")
                self.root.update_idletasks()
            
            self.root.after(0, do_update)

        update_progress(0, "开始转换...")
        
        for i, fp in enumerate(files):
            if not self.converting: break
                
            fn = os.path.basename(fp)
            nm = os.path.splitext(fn)[0]
            od = os.path.dirname(fp)
            
            if t == "video" and hasattr(self, 'v_out_dir_combo'):
                if self.v_out_dir_combo.get() == "自定义目录" and hasattr(self, 'v_out_dir_path'):
                    custom_dir = self.v_out_dir_path.get()
                    if custom_dir:
                        od = custom_dir

            def prog(pct, msg, _i=i, _f=fn, _t=total):
                overall_pct = int((_i*100+max(0,pct))/_t)
                update_progress(overall_pct, f"[{_i+1}/{_t}] {_f}  {msg}")

            result = False
            error_msg = ""

            try:
                if t == "video":
                    ext = SUPPORTED_VIDEO[self.v_fmt.get()]
                    result = self.video_conv.convert(
                        fp, os.path.join(od, nm+ext), ext,
                        VIDEO_CODECS.get(self.v_codec.get()),
                        VIDEO_PRESETS.get(self.v_preset.get()),
                        RESOLUTIONS.get(self.v_res.get()),
                        None if self.v_br.get()=="自动" else self.v_br.get(),
                        None if self.v_fps.get()=="原始帧率" else int(self.v_fps.get()),
                        prog)

                elif t == "audio":
                    fmt = self.a_fmt.get()
                    ext = SUPPORTED_AUDIO[fmt]
                    cm = {"MP3":"libmp3lame","AAC":"aac","FLAC":"flac","WAV":"pcm_s16le",
                          "WMA":"wmav2","OGG":"libvorbis","M4A":"aac","AMR":"libopencore_amrnb","OPUS":"libopus"}
                    sr = self.a_sr.get(); ch = self.a_ch.get()
                    vol = self.a_vol.get()
                    result = self.audio_conv.convert(
                        fp, os.path.join(od, nm+ext), cm.get(fmt), self.a_br.get(),
                        None if sr=="原始" else int(sr),
                        None if ch=="原始" else (1 if ch=="单声道" else 2),
                        vol, prog)

                elif t == "image":
                    ext = SUPPORTED_IMAGE[self.i_fmt.get()]
                    watermark_text = self.i_watermark.get().strip()
                    watermark_pos = self.i_watermark_pos.get()
                    result = self.image_conv.convert(
                        fp, os.path.join(od, nm+ext),
                        int(self.i_q.get().split("（")[0]), None,
                        watermark_text, watermark_pos, prog)

                elif t == "doc":
                    tgt = self.d_tgt.get()
                    ext = tgt.split("（")[0]
                    result = self.doc_conv.convert(fp, os.path.join(od, nm+ext), prog)

                elif t == "extract":
                    em = {"MP3":".mp3","AAC":".aac","FLAC":".flac","WAV":".wav"}
                    cm = {"MP3":"mp3","AAC":"aac","FLAC":"flac","WAV":"wav"}
                    fmt = self.e_fmt.get()
                    result = self.video_conv.extract_audio(
                        fp, os.path.join(od, nm+em[fmt]), cm[fmt], self.e_br.get(), prog)

                elif t == "compress":
                    q = self.c_q.get()
                    pr = "high" if "高" in q else ("low" if "低" in q else "medium")
                    result = self.video_conv.convert(
                        fp, os.path.join(od, nm+"_compressed.mp4"), ".mp4", "libx264",
                        pr, RESOLUTIONS.get(self.c_res.get()), progress_callback=prog)

                elif t == "gif":
                    out = os.path.join(od, nm + ".gif")
                    w_val = self.gif_w.get()
                    fps = self.gif_fps.get()
                    start = self.gif_start.get()
                    dur = self.gif_dur.get()
                    ffmpeg = get_ffmpeg_path()
                    if ffmpeg:
                        import subprocess
                        cmd = [ffmpeg, "-y", "-progress", "pipe:1"]
                        if start != "0":
                            cmd += ["-ss", start]
                        cmd += ["-i", fp]
                        if dur != "全部":
                            cmd += ["-t", dur]
                        vf = f"fps={fps}"
                        if w_val != "原始":
                            vf += f",scale={w_val}:-1:flags=lanczos"
                        cmd += ["-vf", vf, "-loop", "0", out]
                        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                                text=True, creationflags=0x08000000 if os.name=='nt' else 0)
                        while proc.poll() is None and self.converting:
                            line = proc.stdout.readline()
                            if line:
                                if "out_time_ms=" in line:
                                    try:
                                        ms = int(line.split("=")[1].strip())
                                        total_ms = float('inf')
                                        if dur != "全部":
                                            try:
                                                total_ms = float(dur) * 1000000
                                            except:
                                                pass
                                        if total_ms != float('inf'):
                                            pct = min(100, int(ms / total_ms * 100))
                                        else:
                                            pct = 0
                                        prog(pct, f"正在生成 GIF... {ms//1000000}s")
                                    except:
                                        pass
                            time.sleep(0.1)
                        if not self.converting:
                            proc.kill()
                        else:
                            proc.wait()
                            result = proc.returncode == 0
                    prog(100, "GIF生成完成" if result else "GIF生成失败")

                elif t == "pdf":
                    mode = self.pdf_mode.get()
                    if "合并" in mode:
                        out = os.path.join(od, "merged.pdf")
                        result = pdf_merge(files, out, prog)
                    else:
                        range_str = self.pdf_range.get()
                        ranges = []
                        for part in range_str.split(","):
                            part = part.strip()
                            if "-" in part:
                                s, e = part.split("-", 1)
                                ranges.append((int(s.strip()), int(e.strip())))
                            else:
                                n = int(part)
                                ranges.append((n, n))
                        result = pdf_split(fp, od, ranges, prog)

                elif t == "compress_img":
                    q = int(self.ci_q.get())
                    sz_str = self.ci_sz.get()
                    max_sz = None
                    if sz_str != "不限制":
                        w, h = sz_str.split("x")
                        max_sz = (int(w), int(h))
                    out = os.path.join(od, nm + "_compressed" + os.path.splitext(fp)[1])
                    result = image_compress(fp, out, q, max_sz, prog)

                elif t == "rename":
                    pattern = self.rn_pattern.get()
                    start_num = int(self.rn_start.get())
                    renamed = batch_rename(files, pattern, start_num, prog)
                    result = len(renamed) > 0
            
            except Exception as ex:
                error_msg = str(ex)
                self._log_status(f"文件 {fn} 处理失败：{error_msg}", "error")
            
            if result: 
                ok_n += 1
            elif error_msg:
                self._log_status(f"跳过失败文件：{fn}", "warning")

        self.converting = False
        
        def cleanup():
            w["go"].configure(state=tk.NORMAL)
            w["ca"].configure(state=tk.DISABLED)
            self.root.attributes("-disabled", False)
            
            if ok_n == total:
                w["pg"].configure(value=100)
                w["st"].configure(text=f"全部完成  {ok_n}/{total}")
                self._log_status(f"转换完成，成功 {ok_n}/{total} 个文件", "success")
                messagebox.showinfo("完成", f"成功转换 {ok_n}/{total} 个文件")
            elif ok_n > 0:
                w["pg"].configure(value=100)
                w["st"].configure(text=f"部分完成  {ok_n}/{total}")
                self._log_status(f"转换完成，成功 {ok_n}/{total} 个文件（部分失败）", "warning")
                messagebox.showwarning("完成", f"成功 {ok_n}/{total} 个文件")
            else:
                w["pg"].configure(value=0)
                w["st"].configure(text="转换失败")
                self._log_status(f"转换失败，所有文件处理失败", "error")
                messagebox.showerror("失败", "所有文件转换失败")
        
        self.root.after(0, cleanup)

    def run(self):
        self.root.mainloop()


def main():
    FormatMaster().run()

if __name__ == "__main__":
    main()
