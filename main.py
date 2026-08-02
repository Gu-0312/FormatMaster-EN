"""格式大师 - 主程序  ·  Editorial White 设计"""
import os, sys, re, ctypes, time, queue, webbrowser, datetime
import warnings
warnings.filterwarnings("ignore", category=Warning, module="requests")

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
import subprocess

from utils.config import *
from utils.ffmpeg_manager import FFmpegManager
from utils.presets import get_preset_names, get_preset_by_name
from core.video_converter import VideoConverter
from core.audio_converter import AudioConverter
from core.image_converter import ImageConverter
from core.doc_converter import DocumentConverter
from core.tools import pdf_merge, pdf_split, pdf_get_page_count, image_compress, batch_rename, pdf_encrypt, pdf_decrypt, pdf_compress
from core.video_downloader import VideoDownloader
from core.image_cropper import PRESETS as CROP_PRESETS
from core.m3u8_downloader import M3U8Downloader
from gui.pdf_editor_panel import PdfEditorPanel
from utils.combobox_style import style_combobox


# ═══════════════════════════════════════════════
#  异常 → 中文提示映射
# ═══════════════════════════════════════════════
EX_HINT = {
    "FileNotFoundError": "找不到输入文件，请检查路径",
    "PermissionError": "没有访问权限，请检查文件/目录权限",
    "KeyError": "缺少必要参数，请检查设置",
    "ValueError": "参数值不合法，请检查输入",
    "OSError": "系统错误，文件可能被占用或路径无效",
    "IndexError": "索引越界，数据可能不完整",
    "TypeError": "类型错误，数据格式不匹配",
    "AttributeError": "功能暂不支持此操作",
    "subprocess.CalledProcessError": "子进程执行失败，请检查FFmpeg安装",
    "RuntimeError": "运行时错误，文件可能已损坏或不支持",
    "json.JSONDecodeError": "媒体信息解析失败，文件可能已损坏",
    "MemoryError": "内存不足，请关闭其他程序后重试",
    "TimeoutError": "操作超时，文件可能过大或已损坏",
    "ImportError": "缺少必要组件或依赖库，请重新安装",
    "ModuleNotFoundError": "缺少功能模块，请重新安装程序",
    "ConnectionError": "网络连接失败，请检查网络",
    "UnicodeDecodeError": "文件编码不兼容，请尝试其他格式",
    "UnicodeEncodeError": "文件名包含不兼容字符，请重命名",
    "requests.exceptions.ConnectionError": "网络连接失败，请检查网络",
    "pdfminer.pdfparser.PDFSyntaxError": "PDF文件语法错误，文件可能已损坏",
    "fitz.FileDataError": "PDF文件已损坏，无法打开",
    "fitz.EmptyFileError": "PDF文件为空",
    "PdfReadError": "PDF文件读取失败，文件可能已损坏或加密",
}

def _hint_ex(ex):
    """为常见异常生成中文说明，帮助用户理解错误原因"""
    en = type(ex).__name__
    for k, v in EX_HINT.items():
        if k in en:
            return v
    return None

# ═══════════════════════════════════════════════
#  Design Tokens - Modern Flat Style
# ═══════════════════════════════════════════════
D = {
    "page":         "#F5F6FA",
    "card":         "#FFFFFF",
    "card_alt":     "#FAFBFC",
    "sidebar":      "#FFFFFF",
    "sidebar_sel":  "#F0F1F5",
    "accent":       "#F05A42",
    "accent_soft":  "#FF7B69",
    "accent_pale":  "#FFF1EF",
    "accent_deep":  "#D04532",
    "ink":          "#1A1A2E",
    "ink_sec":      "#6B7280",
    "ink_dis":      "#9CA3AF",
    "ink_inv":      "#FFFFFF",
    "border":       "#E5E7EB",
    "border_hi":    "#D1D5DB",
    "divider":      "#F3F4F6",
    "ok":           "#10B981",
    "warn":         "#F59E0B",
    "err":          "#EF4444",
    "input_bg":     "#FFFFFF",
    "input_bd":     "#E5E7EB",
    "input_focus":  "#F05A42",
    "prog_trough":  "#E5E7EB",
    "prog_fill":    "#F05A42",
    "select_bg":    "#FDDBD6",
    "select_fg":    "#C0392B",
    "select_bold":  "#A83228",
}

D_LIGHT = dict(D)

D_DARK = {
    "page":         "#1E1E2E",
    "card":         "#2A2A3C",
    "card_alt":     "#323248",
    "sidebar":      "#252536",
    "sidebar_sel":  "#323248",
    "accent":       "#F05A42",
    "accent_soft":  "#FF7B69",
    "accent_pale":  "#3D2A28",
    "accent_deep":  "#D04532",
    "ink":          "#E4E4E7",
    "ink_sec":      "#A1A1AA",
    "ink_dis":      "#71717A",
    "ink_inv":      "#FFFFFF",
    "border":       "#3F3F50",
    "border_hi":    "#525266",
    "divider":      "#323248",
    "ok":           "#22C55E",
    "warn":         "#F59E0B",
    "err":          "#EF4444",
    "input_bg":     "#1A1A2E",
    "input_bd":     "#3F3F50",
    "input_focus":  "#F05A42",
    "prog_trough":  "#3F3F50",
    "prog_fill":    "#F05A42",
    "select_bg":    "#3D2A28",
    "select_fg":    "#FF7B69",
    "select_bold":  "#FF7B69",
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


def _extract_urls(text):
    """从文本中提取所有 http(s) URL"""
    return list(set(re.findall(r"https?://[^\s\u4e00-\u9fff\u3000-\u303f\uff00-\uffef<>\"']+", text)))


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
        self.root.bind("<Map>", self._fix_black_border)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        self._check_update()
        self._theme = USER_PREFS.get("global", "theme", "light")
        # 在构建UI前初始化D为已保存的主题，避免先以浅色创建再切换导致的映射碰撞bug
        if self._theme == "dark":
            for k, v in D_DARK.items():
                D[k] = v
        
        self._enable_double_buffering()
        self.root.after(100, self._force_redraw)
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
        self.panels_disabled = False
        self.last_output_dir = ""
        self.video_conv  = VideoConverter()
        self.audio_conv  = AudioConverter()
        self.image_conv  = ImageConverter()
        self.doc_conv    = DocumentConverter()
        self.ffmpeg_mgr  = FFmpegManager()
        self.m3u8_dl     = M3U8Downloader()
        self.current_tab = tk.StringVar(value="video")
        self._drop_handler = None
        
        self.task_queue = queue.Queue()
        self.tasks = []
        self.processing_task = False
        self.task_id_counter = 0

        self._ui()
        self.root.update_idletasks()
        self._setup_drag_drop()
        self._check_ffmpeg()
        self._check_ytdlp()
        self._apply_theme()

    # ── ttk 主题 ──────────────────────────────
    def _ttk(self):
        s = self.style
        
        s.configure("TFrame", background=D["page"])
        s.configure("TLabel", background=D["page"], foreground=D["ink"], font=BODY)
        
        # Combobox 样式优化
        s.configure("TCombobox",
                     fieldbackground=D["input_bg"], foreground=D["ink"],
                     selectbackground=D["accent"], selectforeground=D["ink_inv"],
                     font=BODY, padding=6, arrowcolor=D["ink_sec"])
        s.map("TCombobox",
               fieldbackground=[("readonly", D["input_bg"])],
               foreground=[("readonly", D["ink"]), ("!disabled", D["ink"])],
               selectbackground=[("!disabled", D["accent"])],
               selectforeground=[("!disabled", D["ink_inv"])],
               bordercolor=[("focus", D["input_focus"])],
               arrowcolor=[("active", D["ink"]), ("!disabled", D["ink_sec"])])
        
        s.configure("Horizontal.TProgressbar",
                     troughcolor=D["prog_trough"], background=D["prog_fill"],
                     thickness=12, borderwidth=0)
        
        s.configure("AboutText.TButton",
                     font=("Segoe UI", 10),
                     foreground=D["ink_sec"],
                     borderwidth=0,
                     padding=(12, 6))
        s.map("AboutText.TButton",
              foreground=[("active", D["ink"])],
              background=[("pressed", D["card_alt"]), ("active", D["card"])])
        
        s.configure("Treeview",
                     background=D["input_bg"], foreground=D["ink"],
                     font=BODY, rowheight=26,
                     fieldbackground=D["input_bg"],
                     borderwidth=0, relief="flat")
        s.configure("Treeview.Heading",
                     background=D["card_alt"], foreground=D["ink"],
                     font=(FT, 10, "bold"),
                     borderwidth=1, bordercolor=D["border"],
                     relief="flat", padding=6)
        s.map("Treeview",
              background=[("selected", D["accent_pale"])],
              foreground=[("selected", D["ink"])])
        s.map("Treeview.Heading",
              background=[("active", D["card_alt"])])

        s.configure("Flat.TButton",
                     font=BTN,
                     foreground=D["ink"],
                     background=D["card"],
                     borderwidth=1,
                     relief="solid",
                     bordercolor=D["border"],
                     padding=(16, 8))
        s.map("Flat.TButton",
              background=[("active", D["card_alt"])],
              foreground=[("active", D["ink"])],
              bordercolor=[("focus", D["input_focus"])])
        
        s.configure("Primary.TButton",
                     font=BTN,
                     foreground=D["ink_inv"],
                     background=D["accent"],
                     borderwidth=0,
                     relief="flat",
                     padding=(20, 8))
        s.map("Primary.TButton",
              background=[("active", D["accent_deep"]), ("pressed", D["accent_deep"])],
              foreground=[("active", D["ink_inv"])])
        
        s.layout("Primary.TButton",
                 [('Button.border', {'sticky': 'nswe', 'border': '0', 'children':
                   [('Button.focus', {'sticky': 'nswe', 'children':
                     [('Button.padding', {'sticky': 'nswe', 'children':
                       [('Button.label', {'sticky': 'nswe'})]
                      })]
                    })]
                  })])
        
        s.configure("Danger.TButton",
                     font=BTN,
                     foreground=D["err"],
                     background=D["accent_pale"],
                     borderwidth=1,
                     relief="solid",
                     bordercolor=D["err"],
                     padding=(16, 8))
        s.map("Danger.TButton",
              background=[("active", D["accent_pale"]), ("pressed", D["accent_pale"])],
              foreground=[("active", D["err"])])
        
        s.configure("Ghost.TButton",
                     font=BTN,
                     foreground=D["ink_sec"],
                     background=D["page"],
                     borderwidth=0,
                     relief="flat",
                     padding=(16, 8))
        s.map("Ghost.TButton",
              background=[("active", D["card_alt"])],
              foreground=[("active", D["ink"])])

    # ── 按钮工厂 ──────────────────────────────
    def _btn(self, parent, text, cmd, style="secondary", **kw):
        style_map = {
            "primary":   "Primary.TButton",
            "secondary": "Flat.TButton",
            "ghost":     "Ghost.TButton",
            "danger":    "Danger.TButton",
        }
        ttk_style = style_map.get(style, "Flat.TButton")
        
        b = ttk.Button(parent, text=text, command=cmd,
                       style=ttk_style, cursor="hand2")
        
        if kw.get("state"):
            b.configure(state=kw["state"])
        
        if kw.get("padx") or kw.get("pady"):
            padx = kw.get("padx", 16)
            pady = kw.get("pady", 8)
            current_style = self.style.lookup(ttk_style, "padding")
            if current_style:
                self.style.configure(ttk_style, padding=(padx, pady))
        
        return b

    # ── 主界面 ────────────────────────────────
    def _ui(self):
        # 顶部工具栏
        toolbar = tk.Frame(self.root, bg=D["page"], height=40)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        toolbar.pack_propagate(False)
        
        # 关于按钮（最右侧）
        about_lbl = tk.Label(toolbar, text="关于", bg=D["page"], fg=D["ink_sec"],
                             font=("Segoe UI", 10), cursor="hand2",
                             padx=12, pady=6)
        about_lbl.pack(side=tk.RIGHT, padx=(0, 16), pady=6)
        
        # 主题切换按钮
        self._theme_btn = tk.Button(toolbar, text="☾", font=("Segoe UI", 16),
                                    bg=D["page"], fg=D["ink_sec"], relief="flat",
                                    cursor="hand2", bd=0, padx=6,
                                    activebackground=D["card_alt"],
                                    command=self._toggle_theme)
        self._theme_btn.pack(side=tk.RIGHT, padx=(0, 4), pady=4)
        
        def on_about_enter(e):
            about_lbl.configure(bg=D["card_alt"], fg=D["ink"])
        
        def on_about_leave(e):
            about_lbl.configure(bg=D["page"], fg=D["ink_sec"])
        
        about_lbl.bind("<Enter>", on_about_enter)
        about_lbl.bind("<Leave>", on_about_leave)
        about_lbl.bind("<Button-1>", lambda e: self._show_about())
        
        # 侧边栏
        sb = tk.Frame(self.root, bg=D["sidebar"], width=230)
        sb.pack(side=tk.LEFT, fill=tk.Y)
        sb.pack_propagate(False)

        sep = tk.Frame(self.root, bg=D["border"], width=1)
        sep.pack(side=tk.LEFT, fill=tk.Y)

        # Logo
        logo_f = tk.Frame(sb, bg=D["sidebar"])
        logo_f.pack(fill=tk.X, padx=24, pady=(24, 4))
        tk.Label(logo_f, text="格式大师", bg=D["sidebar"], fg=D["accent"],
                 font=DISPLAY).pack(anchor=tk.W)
        tk.Label(logo_f, text=f"v{APP_VERSION}  FormatMaster", bg=D["sidebar"],
                 fg=D["ink_dis"], font=XS).pack(anchor=tk.W)

        tk.Frame(sb, bg=D["divider"], height=1).pack(fill=tk.X, padx=20, pady=(18, 12))

        # 导航
        self.nav = {}
        nav_items = [
            ("_media",     "媒体转换", [
                ("video",  "视"),
                ("audio",  "音"),
                ("image",  "图"),
                ("doc",    "文"),
                ("gif",    "动"),
            ]),
            ("_edit",      "编辑处理", [
                ("pdf",    "PDF"),
                ("compress_img", "压"),
                ("rename", "名"),
                ("extract","音"),
                ("compress","压"),
                ("crop",   "裁"),
            ]),
            ("_tool",      "工具箱", [
                ("detect", "检"),
                ("ocr",   "识"),
                ("qrcode","码"),
            ]),
            ("_net",       "网络工具", [
                ("download", "载"),
                ("m3u8",  "M8"),
            ]),
        ]
        for section_key, section_title, items in nav_items:
            sec_frame = tk.Frame(sb, bg=D["sidebar"])
            sec_frame.pack(fill=tk.X, padx=24, pady=(8, 2))
            tk.Label(sec_frame, text=section_title, bg=D["sidebar"],
                     fg=D["ink_dis"], font=XS).pack(anchor=tk.W)

            for key, marker in items:
                row = tk.Frame(sb, bg=D["sidebar"], cursor="hand2")
                row.pack(fill=tk.X, padx=8, pady=1)
                ind = tk.Frame(row, bg=D["sidebar"], width=5)
                ind.pack(side=tk.LEFT, fill=tk.Y, padx=(2, 8))
                badge = tk.Label(row, text=marker, bg=D["accent_pale"], fg=D["accent"],
                                 font=("Microsoft YaHei UI", 8, "bold"), width=4, height=1,
                                 anchor=tk.CENTER)
                badge.pack(side=tk.LEFT, padx=(0, 8))
                lbl = tk.Label(row, text=self._nav_label(key), bg=D["sidebar"], fg=D["ink_sec"],
                               font=NAV, anchor=tk.W, padx=4, pady=7)
                lbl.pack(fill=tk.X)
                for w in (row, ind, badge, lbl):
                    w.bind("<Button-1>", lambda e, k=key: self._switch(k))
                    def on_enter(e, r=row, i=ind, l=lbl, k=key):
                        if k != self.current_tab.get():
                            r.configure(bg=D["select_bg"])
                            i.configure(bg=D["accent_soft"])
                            l.configure(fg=D["select_fg"])
                    def on_leave(e, r=row, i=ind, l=lbl, k=key):
                        if k == self.current_tab.get():
                            r.configure(bg=D["select_bg"])
                            i.configure(bg=D["accent"])
                            l.configure(fg=D["select_bold"], font=NAV_B)
                        else:
                            r.configure(bg=D["sidebar"])
                            i.configure(bg=D["sidebar"])
                            l.configure(fg=D["ink_sec"], font=NAV)
                    w.bind("<Enter>", on_enter)
                    w.bind("<Leave>", on_leave)
                self.nav[key] = (row, ind, badge, lbl)

        # 底部状态
        self.status_frame = tk.Frame(sb, bg=D["sidebar"])
        self.status_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 16))
        tk.Frame(self.status_frame, bg=D["divider"], height=1).pack(fill=tk.X, padx=20, pady=(0, 12))
        self.yt_lbl = tk.Label(self.status_frame, text="yt-dlp · 检测中", bg=D["sidebar"],
                                fg=D["ink_dis"], font=XS, anchor=tk.W, padx=28, cursor="hand2")
        self.yt_lbl.pack(fill=tk.X)
        self.yt_lbl.bind("<Button-1>", lambda e: self._check_ytdlp())
        self.ff_lbl = tk.Label(self.status_frame, text="FFmpeg · 检测中", bg=D["sidebar"],
                                fg=D["ink_dis"], font=XS, anchor=tk.W, padx=28)
        self.ff_lbl.pack(fill=tk.X, pady=(6, 0))
        # 主内容容器
        self.main_content = tk.Frame(self.root, bg=D["page"])
        self.main_content.pack(side=tk.RIGHT, fill='both', expand=True)

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
        self._p_download()
        self._p_crop()
        self._p_m3u8()
        self._p_ocr()
        self._p_qrcode()
        self._switch("video")
        self._style_all_combos()

        # 底部面板 - 放在内容之后
        self._create_bottom_panel()

        self.status_queue = queue.Queue()
        self._process_status_queue()

        self._process_task_queue()

    def _style_all_combos(self):
        """遍历所有 Combobox，应用自定义下拉列表样式"""
        def _walk(widget):
            for child in widget.winfo_children():
                if isinstance(child, ttk.Combobox):
                    try:
                        style_combobox(child)
                    except Exception:
                        pass
                _walk(child)
        _walk(self.root)

    def _enable_double_buffering(self):
        self._set_title_bar_theme()
    
    def _set_title_bar_theme(self):
        try:
            hwnd = self.root.winfo_id()
            dark_mode = 1 if getattr(self, '_theme', 'light') == 'dark' else 0
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(ctypes.c_int(dark_mode)),
                ctypes.sizeof(ctypes.c_int)
            )
        except Exception:
            pass
    
    def _on_resize(self, event):
        pass
    
    def _fix_black_border(self, event):
        if event.widget == self.root:
            self.root.after(50, self._force_redraw)
            self.root.after(100, self._reapply_geometry)
    
    def _force_redraw(self):
        try:
            hwnd = self.root.winfo_id()
            RDW_INVALIDATE = 0x01
            RDW_ALLCHILDREN = 0x80
            RDW_UPDATENOW = 0x100
            ctypes.windll.user32.RedrawWindow(hwnd, None, None, RDW_INVALIDATE | RDW_ALLCHILDREN | RDW_UPDATENOW)
        except Exception:
            pass
        self.root.update_idletasks()
    
    def _reapply_geometry(self):
        try:
            hwnd = self.root.winfo_id()
            rect = ctypes.wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
            x, y = rect.left, rect.top
            ctypes.windll.user32.SetWindowPos(hwnd, None, x + 1, y, 0, 0, 0x0002 | 0x0001)
            ctypes.windll.user32.SetWindowPos(hwnd, None, x, y, 0, 0, 0x0002 | 0x0001)
        except Exception:
            pass
    
    def _nav_label(self, key):
        names = {
            "video": "视频转换", "audio": "音频转换", "image": "图片转换",
            "doc": "文档转换", "gif": "视频转GIF", "pdf": "PDF处理",
            "compress_img": "图片压缩", "rename": "批量重命名", "extract": "提取音频",
            "compress": "视频压缩", "detect": "格式检测", "download": "视频下载",
            "crop": "预设裁剪", "m3u8": "M3U8下载",
            "ocr": "OCR 识别", "qrcode": "二维码生成",
        }
        return names.get(key, key)

    def _toggle_theme(self):
        self._theme = "dark" if self._theme == "light" else "light"
        USER_PREFS.set("global", "theme", self._theme)
        self._apply_theme()

    def _apply_theme(self):
        colors = D_DARK if self._theme == "dark" else D_LIGHT
        for k, v in colors.items():
            D[k] = v

        self._ttk()

        self.root.configure(bg=D["page"])
        if hasattr(self, 'toolbar'):
            self.toolbar.configure(bg=D["page"])
        if hasattr(self, 'main_content'):
            self.main_content.configure(bg=D["page"])
        if hasattr(self, 'content'):
            self.content.configure(bg=D["page"])
        if hasattr(self, 'bottom_frame'):
            self.bottom_frame.configure(bg=D["card"])
            self._recolor_bottom_panel()

        self._set_title_bar_theme()
        self._recolor_sidebar()

        if hasattr(self, 'status_frame'):
            self._recolor_widget(self.status_frame)

        if hasattr(self, '_theme_btn'):
            self._theme_btn.configure(text="☀" if self._theme == "dark" else "☾")

        cur = self.current_tab.get() if hasattr(self, 'current_tab') else "video"
        if cur:
            self._switch(cur)

    def _recolor_bottom_panel(self):
        if not hasattr(self, 'bottom_frame'):
            return
        cmap = self._build_theme_color_map()
        self._recolor_widget_recursive(self.bottom_frame, cmap)
        # Reconfigure treeview tag colors
        if hasattr(self, 'task_tree'):
            try:
                self.task_tree.tag_configure("even", background=D["card"])
                self.task_tree.tag_configure("odd", background=D["card_alt"])
                self.task_tree.tag_configure("waiting", foreground=D["ink_sec"])
                self.task_tree.tag_configure("processing", foreground=D["accent"])
                self.task_tree.tag_configure("success", foreground=D["ok"])
                self.task_tree.tag_configure("failed", foreground=D["err"])
            except Exception:
                pass
        if hasattr(self, 'history_tree'):
            try:
                self.history_tree.tag_configure("success", foreground=D["ok"])
                self.history_tree.tag_configure("failed", foreground=D["err"])
            except Exception:
                pass
        # Reconfigure status text tags
        if hasattr(self, 'status_text'):
            try:
                self.status_text.configure(bg=D["card"], fg=D["ink"])
                self.status_text.tag_configure("info", foreground=D["ink_sec"])
                self.status_text.tag_configure("success", foreground=D["ok"])
                self.status_text.tag_configure("error", foreground=D["err"])
                self.status_text.tag_configure("warning", foreground=D["warn"])
                self.status_text.tag_configure("system", foreground=D["accent"])
                self.status_text.tag_configure("time", foreground=D["ink_dis"])
            except Exception:
                pass
        if hasattr(self, 'notebook'):
            try:
                self.notebook.configure()
            except Exception:
                pass

    def _build_theme_color_map(self):
        """Build per-attribute color map from both light and dark theme values.
        
        Returns {hex: {"fg": color, "bg": color}} so that ambiguous hex values
        (e.g. #FFFFFF used by both ink_inv as fg and card/sidebar/input_bg as bg)
        are correctly resolved based on the attribute being recolored.
        """
        # Classify D keys by their primary visual role
        fg_keys = {"ink", "ink_sec", "ink_dis", "ink_inv",
                    "select_fg", "select_bold", "ok", "warn", "err"}
        # All other keys are treated as bg-oriented
        bg_keys = set(D_LIGHT.keys()) - fg_keys

        def classify_hex(key, src_map):
            """Return ('fg', val) or ('bg', val) for a (key, source-theme) pair."""
            v = src_map[key].upper()
            grp = "fg" if key in fg_keys else "bg"
            return (v, grp, D[key])

        m = {}
        # Deterministic order: D_DARK first, then D_LIGHT
        for k in D_DARK:
            hex_val, grp, cur = classify_hex(k, D_DARK)
            if hex_val not in m:
                m[hex_val] = {"fg": cur, "bg": cur}
            else:
                m[hex_val][grp] = cur
        for k in D_LIGHT:
            hex_val, grp, cur = classify_hex(k, D_LIGHT)
            if hex_val not in m:
                m[hex_val] = {"fg": cur, "bg": cur}
            else:
                m[hex_val][grp] = cur

        # Extra colors used in UI that aren't in theme dicts
        extras = {
            "#E8E8EE": D["border"],
            "#666666": D["ink_sec"],
            "#F0F1F5": D["sidebar_sel"],
            "#333333": D["ink"],
            "#E0E0E0": D["border"],
            "#999999": D["ink_dis"],
            "#CCCCCC": D["ink_dis"],
            "#6B7280": D["ink_sec"],
            "#374151": D["ink"],
        }
        for src, dst in extras.items():
            h = src.upper()
            m[h] = {"fg": dst, "bg": dst}
        return m

    def _recolor_sidebar(self):
        cmap = self._build_theme_color_map()
        for widget in self.root.winfo_children():
            self._recolor_widget_recursive(widget, cmap)

    def _recolor_widget(self, widget):
        cmap = self._build_theme_color_map()
        self._recolor_widget_recursive(widget, cmap)

    def _recolor_widget_recursive(self, widget, color_map):
        fg_attrs = {"fg", "foreground", "activeforeground", "selectforeground", "disabledforeground"}
        bg_attrs = {"bg", "background", "highlightbackground", "highlightcolor",
                     "activebackground", "selectbackground", "troughcolor",
                     "fieldbackground"}
        for attr in ["fg", "bg", "highlightbackground", "highlightcolor",
                     "activebackground", "activeforeground",
                     "selectbackground", "selectforeground",
                     "disabledforeground", "troughcolor"]:
            try:
                val = widget.cget(attr)
                if val:
                    key = val.upper() if val.startswith("#") else val
                    if key in color_map:
                        grp = "fg" if attr in fg_attrs else "bg"
                        widget.configure(**{attr: color_map[key][grp]})
            except Exception:
                pass
        try:
            for child in widget.winfo_children():
                self._recolor_widget_recursive(child, color_map)
        except Exception:
            pass

    def _nav_update(self):
        cur = self.current_tab.get()
        for k, (row, ind, badge, lbl) in self.nav.items():
            if k == cur:
                # 选中状态：背景加深 + 左侧指示条加宽 + 文字加粗变色
                row.configure(bg=D["select_bg"])
                ind.configure(bg=D["accent"], width=6)
                badge.configure(bg=D["accent"], fg=D["ink_inv"])
                lbl.configure(bg=D["select_bg"], fg=D["select_bold"], font=NAV_B)
            else:
                # 默认状态
                row.configure(bg=D["sidebar"])
                ind.configure(bg=D["sidebar"], width=5)
                badge.configure(bg=D["accent_pale"], fg=D["accent"])
                lbl.configure(bg=D["sidebar"], fg=D["ink_sec"], font=NAV)
    
    def _create_bottom_panel(self):
        self.bottom_frame = tk.Frame(self.main_content, bg=D["card"],
                                      highlightbackground=D["border"], highlightthickness=1)
        self.bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(4, 0))
        self.bottom_frame.pack_propagate(False)
        self.bottom_frame.grid_propagate(False)
        self.bottom_frame.configure(height=550)

        self.notebook = ttk.Notebook(self.bottom_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        self._create_task_tab()
        self._create_log_tab()
        self._create_history_tab()
    
    def _create_task_tab(self):
        task_tab = tk.Frame(self.notebook, bg=D["card"])
        task_tab.columnconfigure(0, weight=1)
        task_tab.rowconfigure(1, weight=1)
        
        header = tk.Frame(task_tab, bg=D["card"])
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(6, 4))
        header.columnconfigure(0, weight=1)
        
        tk.Label(header, text="📋 任务进度", bg=D["card"], fg=D["ink"], 
                 font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")
        
        self.task_count_label = tk.Label(header, text="0 个任务", bg=D["card"], fg=D["ink_dis"], 
                                         font=("Segoe UI", 8))
        self.task_count_label.grid(row=0, column=1, sticky="e", padx=(0, 8))
        
        self.task_clear_btn = tk.Button(header, text="清空", 
                                        command=self._clear_task_list,
                                        bg=D["card"], fg=D["ink_sec"], 
                                        font=("Segoe UI", 8),
                                        relief="flat", cursor="hand2", 
                                        padx=8, pady=1)
        self.task_clear_btn.grid(row=0, column=2, sticky="e")
        
        inner_frame = tk.Frame(task_tab, bg=D["card"])
        inner_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        inner_frame.columnconfigure(0, weight=1)
        inner_frame.rowconfigure(0, weight=1)
        
        self.task_tree = ttk.Treeview(inner_frame, columns=("name", "status", "progress"), 
                                       show="headings", height=12)
        self.task_tree.heading("name", text="任务名称")
        self.task_tree.heading("status", text="状态")
        self.task_tree.heading("progress", text="进度")
        
        self.task_tree.column("name", width=350, stretch=True)
        self.task_tree.column("status", width=80, stretch=False, anchor="center")
        self.task_tree.column("progress", width=80, stretch=False, anchor="center")
        
        scrollbar = ttk.Scrollbar(inner_frame, orient=tk.VERTICAL, command=self.task_tree.yview)
        self.task_tree.configure(yscrollcommand=scrollbar.set)
        
        self.task_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        
        self.task_empty_label = tk.Label(inner_frame, text="暂无正在处理的任务", 
                                         bg=D["card"], fg=D["ink_dis"], 
                                         font=("Segoe UI", 10))
        self.task_empty_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        self.task_tree.tag_configure("waiting", foreground=D["ink_sec"])
        self.task_tree.tag_configure("processing", foreground=D["accent"])
        self.task_tree.tag_configure("success", foreground=D["ok"])
        self.task_tree.tag_configure("failed", foreground=D["err"])
        
        self.task_tree.tag_configure("even", background=D["card"])
        self.task_tree.tag_configure("odd", background=D["card_alt"])
        
        self.notebook.add(task_tab, text="📋 任务进度")
    
    def _create_log_tab(self):
        self.log_line_count = 0
        self.MAX_LOG_LINES = 50
        
        log_tab = tk.Frame(self.notebook, bg=D["card"])
        log_tab.columnconfigure(0, weight=1)
        log_tab.rowconfigure(1, weight=1)
        
        header = tk.Frame(log_tab, bg=D["card"])
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(6, 4))
        header.columnconfigure(0, weight=1)
        
        tk.Label(header, text="📝 运行日志", bg=D["card"], fg=D["ink"], 
                 font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")
        
        self.status_clear_btn = tk.Button(header, text="清空", 
                                          command=self._clear_status_stream,
                                          bg=D["card"], fg=D["ink_sec"], 
                                          font=("Segoe UI", 8),
                                          relief="flat", cursor="hand2", 
                                          padx=8, pady=1)
        self.status_clear_btn.grid(row=0, column=1, sticky="e")
        
        inner_frame = tk.Frame(log_tab, bg=D["card"])
        inner_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        inner_frame.columnconfigure(0, weight=1)
        inner_frame.rowconfigure(0, weight=1)
        
        scrollbar = ttk.Scrollbar(inner_frame, orient=tk.VERTICAL)
        scrollbar.grid(row=0, column=1, sticky="ns")
        
        self.status_text = tk.Text(inner_frame, wrap="word",
                                   bg=D["card"], fg=D["ink"], 
                                   font=("Segoe UI", 11),
                                   bd=0, padx=10, pady=6,
                                   yscrollcommand=scrollbar.set,
                                   xscrollcommand=None,
                                   state=tk.DISABLED,
                                   insertwidth=0,
                                   selectbackground=D["select_bg"],
                                   selectforeground=D["select_fg"])
        self.status_text.grid(row=0, column=0, sticky="nsew")
        scrollbar.config(command=self.status_text.yview)
        
        self.status_text.tag_configure("success", foreground=D["ok"])
        self.status_text.tag_configure("error", foreground=D["err"])
        self.status_text.tag_configure("warning", foreground=D["warn"])
        self.status_text.tag_configure("info", foreground=D["ink_sec"])
        self.status_text.tag_configure("time", foreground=D["ink_dis"], font=("Segoe UI", 9))
        
        self.status_text.bind("<Double-1>", self._copy_log_line)
        
        self.notebook.add(log_tab, text="📝 运行日志")
    
    def _create_history_tab(self):
        self.history_tab = tk.Frame(self.notebook, bg=D["card"])
        self.history_tab.columnconfigure(0, weight=1)
        self.history_tab.rowconfigure(1, weight=1)

        header = tk.Frame(self.history_tab, bg=D["card"])
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(6, 4))
        header.columnconfigure(0, weight=1)

        tk.Label(header, text="📜 转换历史", bg=D["card"], fg=D["ink"],
                 font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")

        self.history_count_label = tk.Label(header, text="0 条记录", bg=D["card"], fg=D["ink_dis"],
                                            font=("Segoe UI", 8))
        self.history_count_label.grid(row=0, column=1, sticky="e", padx=(0, 8))

        self.history_clear_btn = tk.Button(header, text="清空历史",
                                           command=self._clear_history,
                                           bg=D["card"], fg=D["ink_sec"],
                                           font=("Segoe UI", 8),
                                           relief="flat", cursor="hand2",
                                           padx=8, pady=1)
        self.history_clear_btn.grid(row=0, column=2, sticky="e")

        inner_frame = tk.Frame(self.history_tab, bg=D["card"])
        inner_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        inner_frame.columnconfigure(0, weight=1)
        inner_frame.rowconfigure(0, weight=1)

        columns = ("time", "type", "source", "target", "status")
        self.history_tree = ttk.Treeview(inner_frame, columns=columns,
                                          show="headings", height=12)
        self.history_tree.heading("time", text="时间")
        self.history_tree.heading("type", text="类型")
        self.history_tree.heading("source", text="源文件")
        self.history_tree.heading("target", text="目标")
        self.history_tree.heading("status", text="状态")

        self.history_tree.column("time", width=150, minwidth=130)
        self.history_tree.column("type", width=90, minwidth=70, anchor="center")
        self.history_tree.column("source", width=250, minwidth=100)
        self.history_tree.column("target", width=160, minwidth=80)
        self.history_tree.column("status", width=70, minwidth=50, anchor="center")

        scrollbar = ttk.Scrollbar(inner_frame, orient=tk.VERTICAL, command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=scrollbar.set)

        self.history_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.history_tree.tag_configure("success", foreground=D["ok"])
        self.history_tree.tag_configure("failed", foreground=D["err"])

        self.history_empty_label = tk.Label(inner_frame, text="暂无转换记录",
                                            bg=D["card"], fg=D["ink_dis"],
                                            font=("Segoe UI", 10))
        self.history_empty_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        self.notebook.add(self.history_tab, text="📜 转换历史")

        # 窗口初始化完成后再加载历史记录
        self.root.after(200, self._refresh_history_view)

    def _refresh_history_view(self):
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        records = CONV_HISTORY.get_all()
        for i, rec in enumerate(records):
            tag = "success" if rec.get("status") == "success" else "failed"
            self.history_tree.insert("", tk.END, values=(
                rec.get("time", ""),
                rec.get("type", ""),
                rec.get("source", ""),
                rec.get("target", ""),
                "✅" if rec.get("status") == "success" else "❌"
            ), tags=(tag,))
        self.history_count_label.configure(text=f"{len(records)} 条记录")
        if records:
            self.history_empty_label.place_forget()
        else:
            self.history_empty_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

    def _clear_history(self):
        if messagebox.askyesno("确认", "确定清空所有转换历史记录吗？"):
            CONV_HISTORY.clear()
            self._refresh_history_view()

    def _clear_task_list(self):
        for item in self.task_tree.get_children():
            self.task_tree.delete(item)
        self.tasks.clear()
        self.task_count_label.configure(text="0 个任务")
        self.task_empty_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
    
    def _add_task(self, name, task_type, params):
        file_path = params.get("file_path", "")
        if file_path:
            for existing_task in self.tasks:
                if existing_task["status"] in ["waiting", "processing"]:
                    existing_params = existing_task.get("params", {})
                    if existing_params.get("file_path") == file_path:
                        return None
        
        if not file_path:
            for existing_task in self.tasks:
                if existing_task["status"] in ["waiting", "processing"]:
                    if existing_task["name"] == name:
                        # 对于下载类任务，URL 不同也算不同任务
                        if task_type in ("download", "m3u8"):
                            old_url = existing_task.get("params", {}).get("params", {}).get("url", "")
                            new_url = params.get("params", {}).get("url", "")
                            if old_url != new_url:
                                continue
                        return None
        
        self.task_id_counter += 1
        task_id = self.task_id_counter
        
        params["task_id"] = task_id
        
        task = {
            "id": task_id,
            "name": name,
            "type": task_type,
            "params": params,
            "status": "waiting",
            "progress": 0,
            "tree_id": None
        }
        
        self.tasks.append(task)
        row_idx = len(self.tasks) - 1
        zebra_tag = "even" if row_idx % 2 == 0 else "odd"
        
        if len(self.tasks) == 1:
            self.task_empty_label.place_forget()
        
        tree_id = self.task_tree.insert("", tk.END, values=(name, "⏳", "0%"), tags=("waiting", zebra_tag))
        task["tree_id"] = tree_id
        
        self.task_queue.put(task)
        self.task_count_label.configure(text=f"{len(self.tasks)} 个任务")
        
        return task_id
    
    def _update_task_status(self, task_id, status, progress=0):
        for task in self.tasks:
            if task["id"] == task_id:
                task["status"] = status
                task["progress"] = progress
                
                status_emoji = {
                    "waiting": "⏳",
                    "processing": "🔄",
                    "success": "✅",
                    "failed": "❌"
                }.get(status, "❓")
                
                progress_text = f"{progress}%"
                
                current_tags = self.task_tree.item(task["tree_id"], "tags")
                zebra_tag = "even"
                for t in current_tags:
                    if t in ["even", "odd"]:
                        zebra_tag = t
                        break
                
                self.task_tree.item(task["tree_id"], 
                                    values=(task["name"], status_emoji, progress_text),
                                    tags=(status, zebra_tag))
                
                if status in ["success", "failed"]:
                    self.task_count_label.configure(text=f"{len(self.tasks)} 个任务")
                break
    
    def _process_task_queue(self):
        if not self.processing_task and not self.task_queue.empty():
            task = self.task_queue.get()
            self.processing_task = True
            self._update_task_status(task["id"], "processing")
            
            task_type = task["type"]
            params = task["params"]
            
            def on_task_complete(success):
                self.root.after(0, lambda: self._on_task_complete_main(task, params, task_type, success))
            
            if task_type == "video":
                threading.Thread(target=self._run_task_video, args=(params, on_task_complete), daemon=True).start()
            elif task_type in ["audio", "image", "doc", "gif", "pdf", "compress_img", "rename", "extract", "compress", "crop", "m3u8", "ocr", "download"]:
                threading.Thread(target=self._run_task_general, args=(task_type, params, on_task_complete), daemon=True).start()
        
        self.root.after(500, self._process_task_queue)

    def _on_task_complete_main(self, task, params, task_type, success):
        self.processing_task = False

        target = ""
        try:
            fn = os.path.basename(params.get("file_path", ""))
            module_params = params.get("params", {})
            if task_type == "video":
                target = module_params.get("fmt", "")
            elif task_type == "audio":
                target = module_params.get("fmt", "")
            elif task_type == "image":
                target = module_params.get("fmt", "")
            elif task_type == "doc":
                target = module_params.get("target", "")
            elif task_type == "pdf":
                target = module_params.get("mode", "")
            elif task_type == "extract":
                target = module_params.get("fmt", "")
            elif task_type == "compress":
                target = "压缩"
            elif task_type == "gif":
                target = "GIF"
            elif task_type == "compress_img":
                target = "图片压缩"
            elif task_type == "rename":
                target = "重命名"
            elif task_type == "crop":
                target = module_params.get("preset", "")
            elif task_type == "m3u8":
                target = "M3U8下载"
            elif task_type == "download":
                target = "视频下载"
            elif task_type == "ocr":
                target = "OCR"
            type_names = {
                "video": "视频转换", "audio": "音频转换", "image": "图片转换",
                "doc": "文档转换", "pdf": "PDF处理", "extract": "提取音频",
                "compress": "视频压缩", "gif": "视频转GIF", "compress_img": "图片压缩",
                "rename": "批量重命名", "crop": "图像裁剪", "m3u8": "M3U8下载",
                "ocr": "OCR识别", "download": "视频下载",
            }
            CONV_HISTORY.add({
                "type": type_names.get(task_type, task_type),
                "source": fn or task.get("name", ""),
                "target": str(target),
                "status": "success" if success else "failed",
                "output_path": params.get("output_path", ""),
            })
        except Exception:
            pass

        self._update_task_status(task["id"], "success" if success else "failed", 100)
        self._refresh_history_view()

        all_done = True
        success_count = 0
        failed_count = 0
        for t in self.tasks:
            if t["status"] in ["waiting", "processing"]:
                all_done = False
                break
            if t["status"] == "success":
                success_count += 1
            elif t["status"] == "failed":
                failed_count += 1

        if all_done:
            self.converting = False
            self._disable_all_panels(disable=False)

            panel_name = params.get("panel_name", task_type)
            w = self._w(panel_name)
            if w and "pg" in w:
                w["pg"].configure(value=0)
            if w and "st" in w:
                w["st"].configure(text="")

            total = success_count + failed_count
            if task_type == "rename" and success_count > 0:
                cnt = getattr(self, '_rn_file_count', 0)
                self._log_status(f"共重命名了 {cnt} 个文件", "success")
                self.root.after(100, lambda: messagebox.showinfo("完成", f"成功重命名 {cnt} 个文件"))
                self._rn_file_count = 0
            elif failed_count == 0:
                self._log_status(f"全部完成，成功 {total} 个任务", "success")
                self.root.after(100, lambda: messagebox.showinfo("完成", f"成功处理 {total} 个文件"))
            elif success_count > 0:
                self._log_status(f"部分完成，成功 {success_count}/{total}", "warning")
                self.root.after(100, lambda: messagebox.showwarning("完成", f"成功 {success_count}/{total} 个文件，失败 {failed_count} 个"))
            else:
                self._log_status(f"全部失败，{total} 个任务均未通过", "error")
                self.root.after(100, lambda: messagebox.showerror("失败", f"全部 {total} 个文件处理失败"))

    def _run_task_video(self, params, callback):
        file_path = params.get("file_path", "")
        output_path = params.get("output_path", "")
        video_params = params.get("params", {})
        task_id = params.get("task_id", 0)
        panel_name = params.get("panel_name", "video")
        
        w = self._w(panel_name)
        start_time_total = time.time()
        
        def update_progress(pct, msg):
            elapsed = int(time.time() - start_time_total)
            elapsed_str = f"{elapsed}s" if elapsed < 60 else f"{elapsed//60}m{elapsed%60}s"
            
            def do_update():
                if w and "pg" in w:
                    w["pg"].configure(value=max(0, pct))
                if w and "st" in w:
                    w["st"].configure(text=f"{msg} · {elapsed_str}")
                if "完成" in msg:
                    self._log_status(msg.replace("完成", "已完成"), "success")
                elif "失败" in msg:
                    self._log_status(msg.replace("失败", "失败"), "error")
                elif pct > 0:
                    self._log_status(msg, "info")
                self._update_task_status(task_id, "processing", pct)
            
            self.root.after(0, do_update)
        
        fn = os.path.basename(file_path)
        nm = os.path.splitext(fn)[0]
        
        def prog(pct, msg):
            if not self.converting:
                raise Exception("已取消")
            update_progress(pct, f"{fn}  {msg}")
        
        try:
            ext = SUPPORTED_VIDEO[video_params.get("fmt", "MP4")]
            copy_mode = video_params.get("copy_mode", False)
            selected_streams = getattr(self, 'v_selected_streams', None)
            result = self.video_conv.convert(
                file_path, output_path, ext,
                VIDEO_CODECS.get(video_params.get("codec", "默认")),
                VIDEO_PRESETS.get(video_params.get("preset", "原始质量")),
                RESOLUTIONS.get(video_params.get("res", "原始分辨率")),
                None if video_params.get("br", "自动")=="自动" else video_params.get("br"),
                None if video_params.get("fps", "原始帧率")=="原始帧率" else int(video_params.get("fps", 30)),
                prog,
                copy_mode=copy_mode,
                selected_streams=selected_streams)
            
            callback(result)
            if w and "pg" in w:
                w["pg"].configure(value=0)
            if w and "st" in w:
                w["st"].configure(text="")
        except Exception as ex:
            if w and "pg" in w:
                w["pg"].configure(value=0)
            if w and "st" in w:
                w["st"].configure(text="")
            err_msg = str(ex)
            if err_msg == "已取消":
                self._log_status(f"文件 {fn} 已取消", "info")
            else:
                self._log_status(f"文件 {fn} 处理失败：{err_msg}", "error")
            callback(False)
    
    def _run_task_general(self, task_type, params, callback):
        file_path = params.get("file_path", "")
        output_path = params.get("output_path", "")
        module_params = params.get("params", {})
        task_id = params.get("task_id", 0)
        panel_name = params.get("panel_name", task_type)
        
        fn = os.path.basename(file_path)
        nm = os.path.splitext(fn)[0]
        
        w = self._w(panel_name)
        
        def update_progress(pct, msg):
            def do_update():
                if w and "pg" in w:
                    w["pg"].configure(value=max(0, pct))
                if w and "st" in w:
                    w["st"].configure(text=msg)
                if "完成" in msg:
                    self._log_status(msg.replace("完成", "已完成"), "success")
                elif "失败" in msg:
                    self._log_status(msg.replace("失败", "失败"), "error")
                elif pct > 0:
                    self._log_status(msg, "info")
                self._update_task_status(task_id, "processing", pct)
            
            self.root.after(0, do_update)
        
        self._prog_heartbeat_id = None
        self._prog_last_pct = 0
        self._prog_last_time = 0
        
        def _heartbeat():
            if self._prog_heartbeat_id is None:
                return
            elapsed = time.time() - self._prog_last_time
            if elapsed > 2.0 and 0 < self._prog_last_pct < 95:
                self._prog_last_pct += 1
                self._prog_last_time = time.time()
                update_progress(self._prog_last_pct, f"{fn}  处理中...")
            self._prog_heartbeat_id = self.root.after(1000, _heartbeat)
        
        def prog(pct, msg):
            if not self.converting:
                raise Exception("已取消")
            if pct >= 0:
                self._prog_last_pct = pct
                self._prog_last_time = time.time()
            update_progress(pct, f"{fn}  {msg}")
            if pct >= 100 or pct < 0:
                if self._prog_heartbeat_id:
                    self.root.after_cancel(self._prog_heartbeat_id)
                    self._prog_heartbeat_id = None
        
        self._prog_heartbeat_id = self.root.after(1000, _heartbeat)
        
        try:
            result = False
            
            if task_type == "audio":
                fmt = module_params.get("fmt", "MP3")
                ext = SUPPORTED_AUDIO[fmt]
                cm = {"MP3":"libmp3lame","AAC":"aac","FLAC":"flac","WAV":"pcm_s16le",
                      "WMA":"wmav2","OGG":"libvorbis","M4A":"aac","AMR":"libopencore_amrnb","OPUS":"libopus"}
                sr = module_params.get("sample_rate", "原始")
                ch = module_params.get("channels", "原始")
                vol = module_params.get("volume", 100)
                result = self.audio_conv.convert(
                    file_path, output_path, cm.get(fmt), module_params.get("bitrate"),
                    None if sr=="原始" else int(sr),
                    None if ch=="原始" else (1 if ch=="单声道" else 2),
                    vol, prog)
            
            elif task_type == "image":
                watermark_text = module_params.get("watermark", "").strip()
                watermark_pos = module_params.get("watermark_pos", "右下角")
                rotate_val = int(module_params.get("rotate", "0°").replace("°", ""))
                crop_val = module_params.get("crop", "原始比例")
                grayscale_val = module_params.get("grayscale", False)
                sz_str = module_params.get("size", "原始大小")
                resize_factor = 1.0
                max_sz = None
                if sz_str == "50%":
                    resize_factor = 0.5
                elif sz_str == "25%":
                    resize_factor = 0.25
                elif sz_str == "200%":
                    resize_factor = 2.0
                elif sz_str != "原始大小" and "x" in sz_str:
                    try:
                        w, h = sz_str.split("x")
                        max_sz = (int(w), int(h))
                    except:
                        pass
                result = self.image_conv.convert(
                    file_path, output_path,
                    int(module_params.get("quality", "95（高质量）").split("（")[0]), max_sz,
                    watermark_text, watermark_pos,
                    rotate=rotate_val, crop_mode=crop_val, grayscale=grayscale_val,
                    resize_factor=resize_factor,
                    progress_callback=prog)
            
            elif task_type == "doc":
                result = self.doc_conv.convert(file_path, output_path, prog)
            
            elif task_type == "extract":
                fmt = module_params.get("fmt", "MP3")
                cm = {"MP3":"mp3","AAC":"aac","FLAC":"flac","WAV":"wav"}
                result = self.video_conv.extract_audio(
                    file_path, output_path, cm[fmt], module_params.get("bitrate"), prog)
            
            elif task_type == "compress":
                q = module_params.get("quality", "中等质量")
                pr = "high" if "高" in q else ("low" if "低" in q else "medium")
                result = self.video_conv.convert(
                    file_path, output_path, ".mp4", "libx264",
                    pr, RESOLUTIONS.get(module_params.get("resolution", "原始分辨率")),
                    None, None, prog)
            
            elif task_type == "gif":
                ffmpeg = get_ffmpeg_path()
                if ffmpeg:
                    import subprocess
                    cmd = [ffmpeg, "-y", "-progress", "pipe:1"]
                    start = module_params.get("start", "0")
                    dur = module_params.get("duration", "全部")
                    fps = module_params.get("fps", "10")
                    w_val = module_params.get("width", "原始")
                    if start != "0":
                        cmd += ["-ss", start]
                    cmd += ["-i", file_path]
                    if dur != "全部":
                        cmd += ["-t", dur]
                    vf = f"fps={fps}"
                    if w_val != "原始":
                        vf += f",scale={w_val}:-1:flags=lanczos"
                    cmd += ["-vf", vf, "-loop", "0", output_path]
                    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            text=True, encoding='utf-8', errors='replace', creationflags=0x08000000 if os.name=='nt' else 0)
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
                                    prog(pct, "正在转换...")
                                except:
                                    pass
                    result = proc.returncode == 0
            
            elif task_type == "pdf":
                mode = module_params.get("mode", "合并（多个→一个）")
                files_list = params.get("files", [file_path])
                if "合并" in mode:
                    result = pdf_merge(files_list, output_path, prog)
                elif "拆分" in mode:
                    range_str = module_params.get("range", "")
                    ranges = []
                    for part in range_str.split(","):
                        part = part.strip()
                        if "-" in part:
                            s, e = part.split("-", 1)
                            ranges.append((int(s.strip()), int(e.strip())))
                        else:
                            ranges.append((int(part), int(part)))
                    result = pdf_split(file_path, output_path, ranges, prog)
                elif "加密" in mode:
                    open_pwd = module_params.get("open_pwd", "")
                    owner_pwd = module_params.get("owner_pwd", "")
                    result = pdf_encrypt(file_path, output_path,
                                         open_pwd, owner_pwd,
                                         module_params.get("encrypt_method", "AES-256"), prog)
                    if result:
                        self._save_pwd_history(open_pwd, owner_pwd)
                elif "解密" in mode:
                    result = pdf_decrypt(file_path, output_path,
                                         module_params.get("decrypt_pwd", ""), prog)
                elif "压缩" in mode:
                    dpi = int(module_params.get("compress_dpi", "150").replace("dpi", ""))
                    quality = int(module_params.get("compress_quality", "80"))
                    result = pdf_compress(file_path, output_path, dpi, quality, prog)
                elif "水印" in mode:
                    wm_text = module_params.get("wm_text", "")
                    if not wm_text:
                        if prog: prog(-1, "水印文字不能为空")
                        result = False
                    else:
                        from core.tools import pdf_add_watermark
                        result = pdf_add_watermark(
                            file_path, output_path,
                            text=wm_text,
                            pos=module_params.get("wm_pos", "居中"),
                            opacity=module_params.get("wm_opacity", 0.3),
                            rotation=module_params.get("wm_rotate", 0),
                            progress_cb=prog,
                        )
                elif "页码" in mode:
                    from core.tools import pdf_add_page_numbers
                    result = pdf_add_page_numbers(
                        file_path, output_path,
                        start=module_params.get("pn_start", 1),
                        pos=module_params.get("pn_pos", "底部居中"),
                        fmt=module_params.get("pn_fmt", "{n}"),
                        progress_cb=prog,
                    )
            
            elif task_type == "compress_img":
                q = int(module_params.get("quality", "75"))
                sz_str = module_params.get("size", "不限制")
                max_sz = None
                if sz_str != "不限制":
                    w, h = sz_str.split("x")
                    max_sz = (int(w), int(h))
                result = image_compress(file_path, output_path, q, max_sz, prog)
            
            elif task_type == "rename":
                pattern = module_params.get("pattern", "文件_{n:03d}")
                start_num = int(module_params.get("start", "1"))
                search_text = module_params.get("search", "")
                replace_text = module_params.get("replace", "")
                case = module_params.get("case", "none")
                regex_pattern = module_params.get("regex_pattern", "")
                regex_replace = module_params.get("regex_replace", "")
                renamed_files = batch_rename(params.get("files", [file_path]), pattern, start_num, prog,
                                             output_dir=output_path, search_text=search_text,
                                             replace_text=replace_text, case=case,
                                             regex_pattern=regex_pattern, regex_replace=regex_replace)
                result = len(renamed_files) > 0

            elif task_type == "crop":
                import core.image_cropper as ic
                preset_key = module_params.get("preset", "")
                sz = ic.PRESETS.get(preset_key)
                if not sz:
                    prog(-1, f"未知预设：{preset_key}")
                    result = False
                else:
                    crp_mode = module_params.get("crop_mode", "cover")
                    files_all = params.get("files", [])
                    cnt = ic.batch_crop(files_all, output_path, sz, crp_mode, prog)
                    result = cnt > 0

            elif task_type == "m3u8":
                url = module_params.get("url", "")
                threads = module_params.get("threads", 16)
                cookie = module_params.get("cookie")
                headers = module_params.get("headers")
                proxy = module_params.get("proxy")
                speed_limit = module_params.get("speed_limit", 0)
                resume = module_params.get("resume", True)
                output_format = module_params.get("output_format", "mp4")
                download_sub = module_params.get("download_sub", False)
                notify = module_params.get("notify", True)
                result = self.m3u8_dl.download(url, output_path, prog,
                                               threads=threads, cookie=cookie,
                                               headers=headers, proxy=proxy,
                                               speed_limit=speed_limit, resume=resume,
                                               output_format=output_format)
                if result and download_sub:
                    try:
                        master_url = module_params.get("master_url", url)
                        subs = self.m3u8_dl.get_subtitles(master_url, headers=headers, cookie=cookie, proxy=proxy)
                        if subs:
                            for sub in subs:
                                sub_url = sub["url"]
                                sub_lang = sub.get("lang", "und")
                                sub_ext = ".vtt" if ".vtt" in sub_url.lower() else (".srt" if ".srt" in sub_url.lower() else ".vtt")
                                sub_output = os.path.splitext(output_path)[0] + f".{sub_lang}{sub_ext}"
                                ok = self.m3u8_dl.download_subtitle(sub_url, sub_output, cookie=cookie, headers=headers, proxy=proxy)
                                if ok: prog(-1, f"字幕已保存: {os.path.basename(sub_output)}")
                                else: prog(-1, f"字幕下载失败: {os.path.basename(sub_output)}")
                        else: prog(-1, "未找到字幕轨道（该视频可能没有字幕）")
                    except Exception as e: prog(-1, f"字幕下载出错: {e}")
                if result and notify:
                    try: import winsound; winsound.MessageBeep(winsound.MB_OK)
                    except: pass

            elif task_type == "download":
                url = module_params.get("url", "")
                vd = getattr(self, 'dl_obj', None)
                if not vd:
                    from core.video_downloader import VideoDownloader
                    vd = VideoDownloader()
                    self.dl_obj = vd
                dl_params = {}
                if module_params.get("cookie"): dl_params["cookie"] = module_params["cookie"]
                if module_params.get("headers"): dl_params["headers"] = module_params["headers"]
                if module_params.get("proxy"): dl_params["proxy"] = module_params["proxy"]
                sl = module_params.get("speed_limit", 0)
                if sl > 0: dl_params["speed_limit"] = sl
                if module_params.get("audio_only"): dl_params["audio_only"] = True
                if module_params.get("audio_format"): dl_params["audio_format"] = module_params["audio_format"]
                if module_params.get("subtitles"): dl_params["subtitles"] = True
                if module_params.get("output_template"): dl_params["output_template"] = module_params["output_template"]
                result = vd.download(url, output_path, progress_callback=prog, **dl_params)

            elif task_type == "ocr":
                from core.ocr_tool import ocr_image
                text = ocr_image(file_path, module_params.get("lang", "chi_sim+eng"), prog)
                if text:
                    def show_result(t=text):
                        self.ocr_text.delete(1.0, tk.END)
                        self.ocr_text.insert(1.0, t)
                        self._log_status(f"识别完成：{len(t)} 字符", "success")
                    self.root.after(0, show_result)
                    result = True
                else:
                    prog(-1, "识别失败，未提取到文字")
                    result = False

            callback(result)
        except Exception as ex:
            if self._prog_heartbeat_id:
                self.root.after_cancel(self._prog_heartbeat_id)
                self._prog_heartbeat_id = None
            if w and "pg" in w:
                w["pg"].configure(value=0)
            if w and "st" in w:
                w["st"].configure(text="")
            err_msg = str(ex)
            if err_msg == "已取消":
                self._log_status(f"文件 {fn} 已取消", "info")
            else:
                self._log_status(f"文件 {fn} 处理失败：{err_msg}", "error")
            callback(False)
    
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
        about_win.configure(bg="#f8f9fa")

        try:
            ico = os.path.join(base_dir, "assets", "icon.ico")
            if os.path.exists(ico):
                about_win.iconbitmap(ico)
        except Exception:
            pass

        header_frame = tk.Frame(about_win, bg="#f8f9fa")
        header_frame.pack(fill=tk.X, padx=28, pady=(28, 12))

        title_lbl = tk.Label(header_frame, text="格式大师", bg="#f8f9fa", fg="#1A1A2E",
                             font=("Segoe UI", 20, "bold"))
        title_lbl.pack(side=tk.LEFT)

        version_frame = tk.Frame(header_frame, bg="#f8f9fa")
        version_frame.pack(side=tk.RIGHT)

        tk.Label(version_frame, text=f"版本 {APP_VERSION}", bg="#f8f9fa", fg="#6B7280",
                 font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(0, 8))

        update_btn = tk.Label(version_frame, text="[检查更新]", bg="#f8f9fa", fg="#1971C2",
                              font=("Segoe UI", 10, "underline"), cursor="hand2")
        update_btn.pack(side=tk.LEFT)

        def on_check_update(e):
            def manual_check():
                try:
                    if self._check_for_updates():
                        pass
                    else:
                        self.root.after(0, lambda: messagebox.showinfo("检查更新", "当前已是最新版本。"))
                except Exception:
                    self.root.after(0, lambda: messagebox.showerror("错误", "网络异常，检查更新失败。"))
            threading.Thread(target=manual_check, daemon=True).start()

        update_btn.bind("<Button-1>", on_check_update)

        tk.Label(about_win, text="一款功能强大的格式转换工具，支持视频、音频、图片、文档等多种格式的转换与处理。",
                 bg="#f8f9fa", fg="#333333", font=("Segoe UI", 10),
                 wraplength=380, justify=tk.LEFT).pack(anchor=tk.W, padx=28, pady=(0, 12))

        github_frame = tk.Frame(about_win, bg="#f8f9fa")
        github_frame.pack(anchor=tk.W, padx=28, pady=(0, 16))

        tk.Label(github_frame, text="GitHub: ", bg="#f8f9fa", fg="#333333", font=("Segoe UI", 10)).pack(side=tk.LEFT)

        github_link = tk.Label(github_frame,
                               text="github.com/Gu-0312/FormatMaster-EN",
                               bg="#f8f9fa", fg="#0d6efd", font=("Segoe UI", 10, "underline"),
                               cursor="hand2")
        github_link.pack(side=tk.LEFT)

        github_link.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/Gu-0312/FormatMaster-EN"))

        sep = tk.Frame(about_win, bg="#E5E7EB", height=1)
        sep.pack(fill=tk.X, padx=28, pady=(16, 12))

        disclaimer_text = """本软件仅供个人学习和研究使用。使用本软件进行格式转换时，请确保您拥有相关文件的合法使用权。

作者不对因使用本软件造成的任何数据损失或法律问题承担责任。请在使用前备份重要文件。"""

        tk.Label(about_win, text=disclaimer_text, bg="#f8f9fa", fg="#9CA3AF",
                 font=("Segoe UI", 8), wraplength=380, justify=tk.LEFT).pack(anchor=tk.W, padx=28, pady=(0, 12))

        close_btn = tk.Button(about_win, text="确定", command=about_win.destroy,
                              bg="#f8f9fa", fg="#1A1A2E", relief="flat",
                              font=("Segoe UI", 10), cursor="hand2",
                              activebackground="#E5E7EB", padx=12, pady=4)
        close_btn.pack(anchor=tk.CENTER, pady=(8, 24))

        about_win.update_idletasks()
        content_w = about_win.winfo_reqwidth() + 20
        content_h = about_win.winfo_reqheight() + 20
        about_win.geometry(f"{content_w}x{content_h}")

        screen_w = about_win.winfo_screenwidth()
        screen_h = about_win.winfo_screenheight()
        x = (screen_w - content_w) // 2
        y = (screen_h - content_h) // 2
        about_win.geometry(f"{content_w}x{content_h}+{x}+{y}")

    def _check_for_updates(self):
        """手动检查更新，返回布尔值：True=有新版本，False=无新版本或检查失败"""
        import urllib.request
        import urllib.error
        import json
        import socket
        GITHUB_REPO = "Gu-0312/FormatMaster-EN"
        try:
            socket.setdefaulttimeout(5)
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            req = urllib.request.Request(url, headers={
                "User-Agent": "FormatMaster",
                "Accept": "application/vnd.github+json"
            })
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                latest_version = (data.get("tag_name") or "").lstrip("vV")
                if latest_version and self._version_gt(latest_version, APP_VERSION):
                    USER_PREFS.set("global", "new_version", latest_version)
                    USER_PREFS.set("global", "update_url",
                                   data.get("html_url") or
                                   f"https://github.com/{GITHUB_REPO}/releases/latest")
                    self.root.after(0, self._show_update_notification)
                    return True
            return False
        except urllib.error.URLError:
            return False
        except socket.timeout:
            return False
        except Exception:
            return False

    def _save_panel_prefs(self, panel):
        prefs = {}
        if panel == "video":
            prefs = {
                "fmt": self.v_fmt.get(),
                "codec": self.v_codec.get(),
                "preset": self.v_preset.get(),
                "res": self.v_res.get(),
                "fps": self.v_fps.get(),
                "br": self.v_br.get(),
                "out_dir_combo": self.v_out_dir_combo.get(),
                "out_dir_path": self.v_out_dir_path.get() if hasattr(self, 'v_out_dir_path') else "",
            }
        elif panel == "audio":
            prefs = {
                "fmt": self.a_fmt.get(),
                "br": self.a_br.get(),
                "sr": self.a_sr.get(),
                "ch": self.a_ch.get(),
                "out_dir_combo": self.a_out_dir_combo.get() if hasattr(self, 'a_out_dir_combo') else "与源文件同目录",
                "out_dir_path": self.a_out_dir_path.get() if hasattr(self, 'a_out_dir_path') else "",
            }
        elif panel == "image":
            prefs = {
                "fmt": self.i_fmt.get(),
                "quality": self.i_q.get(),
                "size": self.i_sz.get(),
                "rotate": self.i_rotate.get(),
                "crop": self.i_crop.get(),
                "grayscale": self.i_grayscale.get(),
                "out_dir_combo": self.i_out_dir_combo.get() if hasattr(self, 'i_out_dir_combo') else "与源文件同目录",
                "out_dir_path": self.i_out_dir_path.get() if hasattr(self, 'i_out_dir_path') else "",
            }
        elif panel == "doc":
            prefs = {
                "out_dir_combo": self.d_out_dir_combo.get() if hasattr(self, 'd_out_dir_combo') else "与源文件同目录",
                "out_dir_path": self.d_out_dir_path.get() if hasattr(self, 'd_out_dir_path') else "",
            }
        elif panel == "extract":
            prefs = {
                "fmt": self.e_fmt.get(),
                "br": self.e_br.get(),
                "out_dir_combo": self.e_out_dir_combo.get() if hasattr(self, 'e_out_dir_combo') else "与源文件同目录",
                "out_dir_path": self.e_out_dir_path.get() if hasattr(self, 'e_out_dir_path') else "",
            }
        elif panel == "compress":
            prefs = {
                "quality": self.c_q.get(),
                "resolution": self.c_res.get(),
                "out_dir_combo": self.c_out_dir_combo.get() if hasattr(self, 'c_out_dir_combo') else "与源文件同目录",
                "out_dir_path": self.c_out_dir_path.get() if hasattr(self, 'c_out_dir_path') else "",
            }
        elif panel == "gif":
            prefs = {
                "width": self.gif_w.get(),
                "fps": self.gif_fps.get(),
                "start": self.gif_start.get(),
                "duration": self.gif_dur.get(),
                "out_dir_combo": self.gif_out_dir_combo.get() if hasattr(self, 'gif_out_dir_combo') else "与源文件同目录",
                "out_dir_path": self.gif_out_dir_path.get() if hasattr(self, 'gif_out_dir_path') else "",
            }
        elif panel == "pdf":
            prefs = {
                "mode": self.pdf_mode.get(),
                "out_dir_combo": self.pdf_out_dir_combo.get() if hasattr(self, 'pdf_out_dir_combo') else "与源文件同目录",
                "out_dir_path": self.pdf_out_dir_path.get() if hasattr(self, 'pdf_out_dir_path') else "",
            }
        elif panel == "compress_img":
            prefs = {
                "quality": self.ci_q.get(),
                "size": self.ci_sz.get(),
                "out_dir_combo": self.ci_out_dir_combo.get() if hasattr(self, 'ci_out_dir_combo') else "与源文件同目录",
                "out_dir_path": self.ci_out_dir_path.get() if hasattr(self, 'ci_out_dir_path') else "",
            }
        elif panel == "rename":
            prefs = {
                "pattern": self.rn_pattern.get(),
                "start": self.rn_start.get(),
                "search": self.rn_search.get() if hasattr(self, 'rn_search') else "",
                "replace": self.rn_replace.get() if hasattr(self, 'rn_replace') else "",
                "case": self.rn_case.get() if hasattr(self, 'rn_case') else "不转换",
                "out_dir_combo": self.rn_out_dir_combo.get() if hasattr(self, 'rn_out_dir_combo') else "与源文件同目录",
                "out_dir_path": self.rn_out_dir_path.get() if hasattr(self, 'rn_out_dir_path') else "",
            }
        elif panel == "crop":
            prefs = {
                "preset": self.crp_preset.get(),
                "mode": self.crp_mode.get(),
                "out_dir_combo": self.crp_out_dir_combo.get() if hasattr(self, 'crp_out_dir_combo') else "与源文件同目录",
                "out_dir_path": self.crp_out_dir_path.get() if hasattr(self, 'crp_out_dir_path') else "",
            }
        elif panel == "ocr":
            prefs = {
                "lang": self.ocr_lang.get(),
                "out_dir_combo": self.ocr_out_dir_combo.get() if hasattr(self, 'ocr_out_dir_combo') else "与源文件同目录",
                "out_dir_path": self.ocr_out_dir_path.get() if hasattr(self, 'ocr_out_dir_path') else "",
            }
        elif panel == "download":
            prefs = {
                "dl_dir": self.dl_dir.get(),
            }
        elif panel == "m3u8":
            prefs = {
                "out_dir": self.m3u8_out_dir.get(),
                "threads": self.m3u8_threads.get(),
                "format": self.m3u8_format.get(),
                "speed": self.m3u8_speed.get(),
                "cookie": self.m3u8_cookie.get(),
                "proxy": self.m3u8_proxy.get(),
                "headers": self.m3u8_headers.get(),
                "resume": self.m3u8_resume.get(),
                "notify": self.m3u8_notify.get(),
                "download_sub": self.m3u8_download_sub.get(),
            }
        if prefs:
            USER_PREFS.save_panel(panel, prefs)

    def _save_pwd_history(self, open_pwd, owner_pwd):
        import time as tm
        hist = USER_PREFS.get("pwd_history", "pdf", {})
        MAX = 10
        def push(lst, val):
            if not val:
                return lst
            migrated = []
            for v in lst:
                if isinstance(v, str):
                    continue
                migrated.append(v)
            lst = [v for v in migrated if v.get("pwd") != val]
            lst.insert(0, {"pwd": val, "time": tm.strftime("%Y-%m-%d %H:%M:%S")})
            return lst[:MAX]
        hist["open_pwd"] = push(hist.get("open_pwd", []), open_pwd)
        hist["owner_pwd"] = push(hist.get("owner_pwd", []), owner_pwd)
        USER_PREFS.set("pwd_history", "pdf", hist)

    def _show_pwd_history(self):
        hist = USER_PREFS.get("pwd_history", "pdf", {})
        win = tk.Toplevel(self.root)
        win.title("密码历史记录")
        win.configure(bg=D["page"])
        win.geometry("780x450")
        win.minsize(600, 350)
        win.transient(self.root)
        win.grab_set()
        win.update_idletasks()
        pw = self.root.winfo_width()
        ph = self.root.winfo_height()
        px = self.root.winfo_x()
        py = self.root.winfo_y()
        ww = win.winfo_width()
        wh = win.winfo_height()
        win.geometry(f"+{px + (pw - ww)//2}+{py + (ph - wh)//2}")

        def make_section(parent, label, key, target_entry):
            f = tk.Frame(parent, bg=D["card"], bd=1, relief="solid",
                         highlightbackground=D["border"], highlightthickness=1)
            tk.Label(f, text=label, bg=D["card"], fg=D["ink"], font=("Microsoft YaHei UI", 10, "bold")
                     ).pack(anchor=tk.W, padx=10, pady=(8, 4))
            items = [v for v in hist.get(key, []) if isinstance(v, dict)]
            if not items:
                tk.Label(f, text="暂无记录", bg=D["card"], fg=D["ink_dis"],
                         font=("Microsoft YaHei UI", 9)).pack(pady=16)
                return f
            lb_frame = tk.Frame(f, bg=D["card"])
            lb_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 8))
            lb = tk.Listbox(lb_frame, font=("Consolas", 9), bg=D["input_bg"],
                            fg=D["ink"], relief="flat", highlightthickness=1,
                            highlightbackground=D["border"], selectbackground=D["select_bg"],
                            selectforeground=D["select_fg"])
            lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scroll = tk.Scrollbar(lb_frame, orient="vertical", command=lb.yview)
            scroll.pack(side=tk.RIGHT, fill=tk.Y)
            lb.configure(yscrollcommand=scroll.set)
            for entry in items:
                lb.insert(tk.END, f"{entry['time']}  |  {entry['pwd']}")
            btn_frame = tk.Frame(f, bg=D["card"])
            btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
            def use_selected():
                sel = lb.curselection()
                if sel:
                    text = lb.get(sel[0])
                    pwd = text.split("  |  ", 1)[-1]
                    target_entry.delete(0, tk.END)
                    target_entry.insert(0, pwd)
                    win.destroy()
            tk.Button(btn_frame, text="使用选中密码", font=("Microsoft YaHei UI", 9),
                      bg=D["accent"], fg="white", relief="flat", padx=12, pady=2,
                      activebackground=D["accent_deep"], activeforeground="white",
                      cursor="hand2", command=use_selected).pack(side=tk.LEFT)
            def delete_selected():
                sel = lb.curselection()
                if not sel:
                    return
                items.pop(sel[0])
                USER_PREFS.set("pwd_history", "pdf", hist)
                win.destroy()
                self._show_pwd_history()
            tk.Button(btn_frame, text="删除", font=("Microsoft YaHei UI", 9),
                      bg=D["card"], fg=D["err"], relief="flat", padx=12, pady=2,
                      activebackground=D["card_alt"], cursor="hand2",
                       command=delete_selected).pack(side=tk.LEFT, padx=(8, 0))
            return f

        top = tk.Frame(win, bg=D["page"])
        top.pack(fill=tk.BOTH, expand=True, pady=16, padx=12)
        top.columnconfigure(0, weight=1, uniform="col")
        top.columnconfigure(1, weight=1, uniform="col")
        top.rowconfigure(0, weight=1)
        make_section(top, "打开密码", "open_pwd", self.pdf_open_pwd).grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        make_section(top, "权限密码", "owner_pwd", self.pdf_owner_pwd).grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        tk.Button(win, text="关闭", font=("Microsoft YaHei UI", 9),
                  bg=D["card"], fg=D["ink"], relief="flat", padx=24, pady=4,
                  activebackground=D["card_alt"], cursor="hand2",
                  command=win.destroy).pack(pady=(0, 12))

    def _load_panel_prefs(self, panel):
        prefs = USER_PREFS.get_panel(panel)
        if not prefs:
            return

        if panel == "video":
            if prefs.get("fmt") and hasattr(self, 'v_fmt'):
                self.v_fmt.set(prefs["fmt"])
            if prefs.get("codec") and hasattr(self, 'v_codec'):
                self.v_codec.set(prefs["codec"])
            if prefs.get("preset") and hasattr(self, 'v_preset'):
                self.v_preset.set(prefs["preset"])
            if prefs.get("res") and hasattr(self, 'v_res'):
                self.v_res.set(prefs["res"])
            if prefs.get("fps") and hasattr(self, 'v_fps'):
                self.v_fps.set(prefs["fps"])
            if prefs.get("br") and hasattr(self, 'v_br'):
                self.v_br.set(prefs["br"])
            if prefs.get("out_dir_combo") and hasattr(self, 'v_out_dir_combo'):
                self.v_out_dir_combo.set(prefs["out_dir_combo"])
            if prefs.get("out_dir_path") and hasattr(self, 'v_out_dir_path'):
                self.v_out_dir_path.set(prefs["out_dir_path"])
        elif panel == "audio":
            if prefs.get("fmt") and hasattr(self, 'a_fmt'):
                self.a_fmt.set(prefs["fmt"])
            if prefs.get("br") and hasattr(self, 'a_br'):
                self.a_br.set(prefs["br"])
            if prefs.get("sr") and hasattr(self, 'a_sr'):
                self.a_sr.set(prefs["sr"])
            if prefs.get("ch") and hasattr(self, 'a_ch'):
                self.a_ch.set(prefs["ch"])
            if prefs.get("out_dir_combo") and hasattr(self, 'a_out_dir_combo'):
                self.a_out_dir_combo.set(prefs["out_dir_combo"])
            if prefs.get("out_dir_path") and hasattr(self, 'a_out_dir_path'):
                self.a_out_dir_path.set(prefs["out_dir_path"])
        elif panel == "image":
            if prefs.get("fmt") and hasattr(self, 'i_fmt'):
                self.i_fmt.set(prefs["fmt"])
            if prefs.get("quality") and hasattr(self, 'i_q'):
                self.i_q.set(prefs["quality"])
            if prefs.get("size") and hasattr(self, 'i_sz'):
                self.i_sz.set(prefs["size"])
            if prefs.get("rotate") and hasattr(self, 'i_rotate'):
                self.i_rotate.set(prefs["rotate"])
            if prefs.get("crop") and hasattr(self, 'i_crop'):
                self.i_crop.set(prefs["crop"])
            if "grayscale" in prefs and hasattr(self, 'i_grayscale'):
                self.i_grayscale.set(prefs["grayscale"])
            if prefs.get("out_dir_combo") and hasattr(self, 'i_out_dir_combo'):
                self.i_out_dir_combo.set(prefs["out_dir_combo"])
            if prefs.get("out_dir_path") and hasattr(self, 'i_out_dir_path'):
                self.i_out_dir_path.set(prefs["out_dir_path"])
        elif panel == "doc":
            if prefs.get("out_dir_combo") and hasattr(self, 'd_out_dir_combo'):
                self.d_out_dir_combo.set(prefs["out_dir_combo"])
            if prefs.get("out_dir_path") and hasattr(self, 'd_out_dir_path'):
                self.d_out_dir_path.set(prefs["out_dir_path"])
        elif panel == "extract":
            if prefs.get("fmt") and hasattr(self, 'e_fmt'):
                self.e_fmt.set(prefs["fmt"])
            if prefs.get("br") and hasattr(self, 'e_br'):
                self.e_br.set(prefs["br"])
            if prefs.get("out_dir_combo") and hasattr(self, 'e_out_dir_combo'):
                self.e_out_dir_combo.set(prefs["out_dir_combo"])
            if prefs.get("out_dir_path") and hasattr(self, 'e_out_dir_path'):
                self.e_out_dir_path.set(prefs["out_dir_path"])
        elif panel == "compress":
            if prefs.get("quality") and hasattr(self, 'c_q'):
                self.c_q.set(prefs["quality"])
            if prefs.get("resolution") and hasattr(self, 'c_res'):
                self.c_res.set(prefs["resolution"])
            if prefs.get("out_dir_combo") and hasattr(self, 'c_out_dir_combo'):
                self.c_out_dir_combo.set(prefs["out_dir_combo"])
            if prefs.get("out_dir_path") and hasattr(self, 'c_out_dir_path'):
                self.c_out_dir_path.set(prefs["out_dir_path"])
        elif panel == "gif":
            if prefs.get("width") and hasattr(self, 'gif_w'):
                self.gif_w.set(prefs["width"])
            if prefs.get("fps") and hasattr(self, 'gif_fps'):
                self.gif_fps.set(prefs["fps"])
            if prefs.get("start") and hasattr(self, 'gif_start'):
                self.gif_start.set(prefs["start"])
            if prefs.get("duration") and hasattr(self, 'gif_dur'):
                self.gif_dur.set(prefs["duration"])
            if prefs.get("out_dir_combo") and hasattr(self, 'gif_out_dir_combo'):
                self.gif_out_dir_combo.set(prefs["out_dir_combo"])
            if prefs.get("out_dir_path") and hasattr(self, 'gif_out_dir_path'):
                self.gif_out_dir_path.set(prefs["out_dir_path"])
        elif panel == "pdf":
            if prefs.get("mode") and hasattr(self, 'pdf_mode'):
                self.pdf_mode.set(prefs["mode"])
                self._pdf_mode_changed()
            if prefs.get("out_dir_combo") and hasattr(self, 'pdf_out_dir_combo'):
                self.pdf_out_dir_combo.set(prefs["out_dir_combo"])
            if prefs.get("out_dir_path") and hasattr(self, 'pdf_out_dir_path'):
                self.pdf_out_dir_path.set(prefs["out_dir_path"])
        elif panel == "compress_img":
            if prefs.get("quality") and hasattr(self, 'ci_q'):
                self.ci_q.set(prefs["quality"])
            if prefs.get("size") and hasattr(self, 'ci_sz'):
                self.ci_sz.set(prefs["size"])
            if prefs.get("out_dir_combo") and hasattr(self, 'ci_out_dir_combo'):
                self.ci_out_dir_combo.set(prefs["out_dir_combo"])
            if prefs.get("out_dir_path") and hasattr(self, 'ci_out_dir_path'):
                self.ci_out_dir_path.set(prefs["out_dir_path"])
        elif panel == "rename":
            if prefs.get("pattern") and hasattr(self, 'rn_pattern'):
                self.rn_pattern.set(prefs["pattern"])
            if prefs.get("start") and hasattr(self, 'rn_start'):
                self.rn_start.set(prefs["start"])
            if prefs.get("search") and hasattr(self, 'rn_search'):
                self.rn_search.delete(0, tk.END)
                self.rn_search.insert(0, prefs["search"])
            if prefs.get("replace") and hasattr(self, 'rn_replace'):
                self.rn_replace.delete(0, tk.END)
                self.rn_replace.insert(0, prefs["replace"])
            if prefs.get("case") and hasattr(self, 'rn_case'):
                self.rn_case.set(prefs["case"])
            if prefs.get("out_dir_combo") and hasattr(self, 'rn_out_dir_combo'):
                self.rn_out_dir_combo.set(prefs["out_dir_combo"])
            if prefs.get("out_dir_path") and hasattr(self, 'rn_out_dir_path'):
                self.rn_out_dir_path.set(prefs["out_dir_path"])
        elif panel == "crop":
            if prefs.get("preset") and hasattr(self, 'crp_preset'):
                self.crp_preset.set(prefs["preset"])
            if prefs.get("mode") and hasattr(self, 'crp_mode'):
                self.crp_mode.set(prefs["mode"])
            if prefs.get("out_dir_combo") and hasattr(self, 'crp_out_dir_combo'):
                self.crp_out_dir_combo.set(prefs["out_dir_combo"])
            if prefs.get("out_dir_path") and hasattr(self, 'crp_out_dir_path'):
                self.crp_out_dir_path.set(prefs["out_dir_path"])
        elif panel == "ocr":
            if prefs.get("lang") and hasattr(self, 'ocr_lang'):
                self.ocr_lang.set(prefs["lang"])
            if prefs.get("out_dir_combo") and hasattr(self, 'ocr_out_dir_combo'):
                self.ocr_out_dir_combo.set(prefs["out_dir_combo"])
            if prefs.get("out_dir_path") and hasattr(self, 'ocr_out_dir_path'):
                self.ocr_out_dir_path.set(prefs["out_dir_path"])
        elif panel == "download":
            if prefs.get("dl_dir") and hasattr(self, 'dl_dir'):
                self.dl_dir.set(prefs["dl_dir"])
        elif panel == "m3u8":
            if prefs.get("out_dir") and hasattr(self, 'm3u8_out_dir'):
                self.m3u8_out_dir.set(prefs["out_dir"])
            if prefs.get("threads") and hasattr(self, 'm3u8_threads'):
                self.m3u8_threads.set(prefs["threads"])
            if prefs.get("format") and hasattr(self, 'm3u8_format'):
                self.m3u8_format.set(prefs["format"])
            if prefs.get("speed") and hasattr(self, 'm3u8_speed'):
                self.m3u8_speed.set(prefs["speed"])
            if prefs.get("cookie") and hasattr(self, 'm3u8_cookie'):
                self.m3u8_cookie.delete(0, tk.END)
                self.m3u8_cookie.insert(0, prefs["cookie"])
            if prefs.get("proxy") and hasattr(self, 'm3u8_proxy'):
                self.m3u8_proxy.delete(0, tk.END)
                self.m3u8_proxy.insert(0, prefs["proxy"])
            if prefs.get("headers") and hasattr(self, 'm3u8_headers'):
                self.m3u8_headers.delete(0, tk.END)
                self.m3u8_headers.insert(0, prefs["headers"])
            if "resume" in prefs and hasattr(self, 'm3u8_resume'):
                self.m3u8_resume.set(prefs["resume"])
            if "notify" in prefs and hasattr(self, 'm3u8_notify'):
                self.m3u8_notify.set(prefs["notify"])
            if "download_sub" in prefs and hasattr(self, 'm3u8_download_sub'):
                self.m3u8_download_sub.set(prefs["download_sub"])
    def _switch(self, tab):
        if getattr(self, 'panels_disabled', False):
            return
        if hasattr(self, 'current_tab') and self.current_tab.get():
            self._save_panel_prefs(self.current_tab.get())
        self.current_tab.set(tab)
        self._nav_update()
        for p in self.panels.values():
            p.pack_forget()
        self.panels[tab].pack(fill=tk.BOTH, expand=True, padx=20, pady=12)
        self._load_panel_prefs(tab)

    # ── 面板标题 ──────────────────────────────
    def _hdr(self, parent, title, sub, badge=""):
        row = tk.Frame(parent, bg=D["page"])
        row.pack(anchor=tk.W, fill=tk.X)
        tk.Label(row, text=title, bg=D["page"], fg=D["ink"],
                 font=H2).pack(side=tk.LEFT)
        if badge:
            tk.Label(row, text=badge, bg=D["accent_pale"], fg=D["accent"],
                     font=("Microsoft YaHei UI", 9), padx=6, pady=1).pack(side=tk.LEFT, padx=(10, 0))
        tk.Label(parent, text=sub, bg=D["page"], fg=D["ink_dis"],
                 font=XS).pack(anchor=tk.W, pady=(2, 8))

    # ── 文件选择区 ────────────────────────────
    def _file_sec(self, parent, key, fts, accept_all=False):
        self.panel_data[key] = {"files": [], "filetypes": fts, "listbox": None, "count": None, "accept_all": accept_all}
        d = self.panel_data[key]

        f = tk.Frame(parent, bg=D["page"])
        f.pack(fill=tk.BOTH, expand=True)

        # 按钮行
        br = tk.Frame(f, bg=D["page"])
        br.pack(fill=tk.X, pady=(0, 6))
        self._btn(br, "＋ 添加文件",  lambda k=key: self._add(k)).pack(side=tk.LEFT, padx=(0, 8))
        self._btn(br, "📁 文件夹",   lambda k=key: self._add_dir(k)).pack(side=tk.LEFT, padx=(0, 8))
        self._btn(br, "✕ 清空",      lambda k=key: self._clr(k), "ghost").pack(side=tk.LEFT)

        if key in ["video", "audio", "image", "doc"]:
            hint_var = tk.StringVar(value="请先添加文件")
            hint_frame = tk.Frame(f, bg=D["page"])
            hint_frame.pack(fill=tk.X, pady=(4, 0))
            hint_label = tk.Label(hint_frame, textvariable=hint_var, bg=D["page"], fg=D["ink_sec"],
                                  font=XS, anchor=tk.W)
            hint_label.pack(side=tk.LEFT)
            d["format_hint_var"] = hint_var
            d["format_hint_label"] = hint_label

        # 列表容器 — 白色卡片
        lo = tk.Frame(f, bg=D["border"], padx=1, pady=1)
        lo.pack(fill=tk.BOTH, expand=True)
        lb = tk.Listbox(lo, bg=D["card"], fg=D["ink"],
                         font=(FT, 10), selectbackground=D["select_bg"],
                         selectforeground=D["ink"],
                         bd=0, highlightthickness=0,
                         activestyle="none", relief="flat",
                         selectborderwidth=0)
        scr = ttk.Scrollbar(lo, orient=tk.VERTICAL, command=lb.yview)
        lb.configure(yscrollcommand=scr.set)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scr.pack(side=tk.RIGHT, fill=tk.Y)

        d["listbox"] = lb
        d["count"] = tk.Label(f, text="0 个文件", bg=D["page"],
                               fg=D["ink_dis"], font=XS, anchor=tk.W)
        d["count"].pack(fill=tk.X, pady=(6, 0))

        # 文件属性预览面板
        props_frame = tk.Frame(f, bg=D["card"], highlightbackground=D["border"], highlightthickness=1)
        props_frame.pack(fill=tk.X, pady=(8, 0), padx=1, ipady=8)
        
        props_label = tk.Label(props_frame, text="文件属性", bg=D["card"], fg=D["ink"], font=SM)
        props_label.pack(anchor=tk.W, padx=12, pady=(0, 4))
        
        props_content = tk.Frame(props_frame, bg=D["card"])
        props_content.pack(fill=tk.X, padx=12)
        
        d["props_labels"] = {}
        for i, label_text in enumerate(["文件名", "文件大小", "时长", "分辨率", "编码格式"]):
            tk.Label(props_content, text=f"{label_text}:", bg=D["card"], fg=D["ink_dis"], font=XS).grid(row=0, column=i*2, sticky="w")
            val_label = tk.Label(props_content, text="-", bg=D["card"], fg=D["ink"], font=XS)
            val_label.grid(row=0, column=i*2+1, sticky="w", padx=(4, 16))
            d["props_labels"][label_text] = val_label

        lb.bind("<<ListboxSelect>>", lambda e, k=key: self._on_file_select(k))

        return f

    def _get_last_dir(self, panel_key):
        """获取面板上次使用的目录"""
        return USER_PREFS.get("last_dirs", panel_key, os.path.expanduser("~"))

    def _save_last_dir(self, panel_key, path):
        """保存面板最后使用的目录"""
        if path and os.path.isdir(path):
            USER_PREFS.set("last_dirs", panel_key, path)
        elif path and os.path.isfile(path):
            USER_PREFS.set("last_dirs", panel_key, os.path.dirname(path))

    def _add(self, key):
        d = self.panel_data[key]
        last_dir = self._get_last_dir(key)
        fs = filedialog.askopenfilenames(initialdir=last_dir, filetypes=d["filetypes"])
        if fs:
            self._save_last_dir(key, fs[0])
        for f in fs:
            if f not in d["files"]:
                d["files"].append(f)
                d["listbox"].insert(tk.END, f"  {os.path.basename(f)}")
        if fs: 
            d["count"].configure(text=f"{len(d['files'])} 个文件")
            self._update_format_hint(key)
            if key == "doc":
                self._detect()

    def _add_dir(self, key):
        d = self.panel_data[key]
        last_dir = self._get_last_dir(key)
        folder = filedialog.askdirectory(initialdir=last_dir)
        if not folder: return
        self._save_last_dir(key, folder)
        exts = {x[1:].lower() for ft in d["filetypes"] for x in ft[1].split() if x.startswith("*.")}
        for rd, _, fns in os.walk(folder):
            for fn in fns:
                fp = os.path.join(rd, fn)
                if any(fn.lower().endswith(e) for e in exts) and fp not in d["files"]:
                    d["files"].append(fp)
                    d["listbox"].insert(tk.END, f"  {fn}")
        d["count"].configure(text=f"{len(d['files'])} 个文件")
        self._update_format_hint(key)
        if key == "doc" and d["files"]:
            self._detect()

    def _clr(self, key):
        d = self.panel_data[key]
        d["files"].clear()
        d["listbox"].delete(0, tk.END)
        d["count"].configure(text="0 个文件")
        if "props_labels" in d:
            for label in d["props_labels"].values():
                label.configure(text="-")
        self._update_format_hint(key)

    def _on_file_select(self, key):
        d = self.panel_data[key]
        selection = d["listbox"].curselection()
        if not selection:
            if "props_labels" in d:
                for label in d["props_labels"].values():
                    label.configure(text="-")
            return
        
        idx = selection[0]
        if idx < len(d["files"]):
            filepath = d["files"][idx]
            self._update_file_props(key, filepath)

    def _update_file_props(self, key, filepath):
        d = self.panel_data[key]
        if "props_labels" not in d:
            return
        
        file_size = self._format_size(os.path.getsize(filepath))
        file_name = os.path.basename(filepath)
        
        d["props_labels"]["文件名"].configure(text=file_name)
        d["props_labels"]["文件大小"].configure(text=file_size)
        d["props_labels"]["时长"].configure(text="-")
        d["props_labels"]["分辨率"].configure(text="-")
        d["props_labels"]["编码格式"].configure(text="-")
        
        ext = os.path.splitext(filepath)[1].lower()
        if ext in [".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv"]:
            self._get_video_info(filepath, key)
        elif ext in [".mp3", ".wav", ".flac", ".m4a", ".ogg"]:
            self._get_audio_info(filepath, key)
        elif ext in [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"]:
            self._get_image_info(filepath, key)

    def _format_size(self, size):
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.1f} GB"

    def _get_video_info(self, filepath, key):
        def get_info():
            try:
                from core.ffmpeg_executor import get_ffprobe_info
                info = get_ffprobe_info(filepath)
                if info:
                    duration = info.get("duration", "-")
                    resolution = info.get("resolution", "-")
                    codec = info.get("codec", "-")
                    self.root.after(0, lambda: self._set_props(key, duration, resolution, codec))
            except Exception:
                pass
        threading.Thread(target=get_info, daemon=True).start()

    def _get_audio_info(self, filepath, key):
        def get_info():
            try:
                from core.ffmpeg_executor import get_ffprobe_info
                info = get_ffprobe_info(filepath)
                if info:
                    duration = info.get("duration", "-")
                    codec = info.get("codec", "-")
                    self.root.after(0, lambda: self._set_props(key, duration, "-", codec))
            except Exception:
                pass
        threading.Thread(target=get_info, daemon=True).start()

    def _get_image_info(self, filepath, key):
        # 风险规避：图片元数据读取也可能在大图时较慢，使用线程 + 超时保护
        def get_info():
            try:
                from PIL import Image
                # PIL 默认懒加载：Image.open() 仅读取头部，img.size 和 img.format 不需要完整解码
                with Image.open(filepath) as img:
                    width, height = img.size
                    resolution = f"{width}×{height}"
                    img_format = img.format or "-"
                    self.root.after(0, lambda: self._set_props(key, "-", resolution, img_format))
            except Exception:
                # 失败时保持 "-"，绝不抛出到主线程
                pass
        threading.Thread(target=get_info, daemon=True).start()

    def _set_props(self, key, duration, resolution, codec):
        d = self.panel_data[key]
        if "props_labels" in d:
            d["props_labels"]["时长"].configure(text=duration)
            d["props_labels"]["分辨率"].configure(text=resolution)
            d["props_labels"]["编码格式"].configure(text=codec)
        
        self._update_format_hint(key)

    def _update_format_hint(self, key):
        """更新格式兼容性提示
        
        状态1：同格式转换 → 蓝色提示
        状态2：正常跨格式转换 → 灰色提示
        状态3：格式不兼容 → 红色警告
        状态4：未选择文件 → 灰色提示
        """
        d = self.panel_data.get(key, {})
        if "format_hint_var" not in d:
            return
        
        files = d.get("files", [])
        if not files:
            d["format_hint_var"].set("请先添加文件")
            d["format_hint_label"].configure(fg=D["ink_sec"])
            return
        
        selected_idx = d.get("listbox", tk.Listbox()).curselection()
        if not selected_idx:
            selected_idx = (0,)
        
        filepath = files[selected_idx[0]] if selected_idx else ""
        if not filepath:
            d["format_hint_var"].set("请先添加文件")
            d["format_hint_label"].configure(fg=D["ink_sec"])
            return
        
        src_ext = os.path.splitext(filepath)[1].lower()
        
        if key == "video":
            target_fmt = self.v_fmt.get() if hasattr(self, 'v_fmt') else "MP4"
            target_ext = SUPPORTED_VIDEO.get(target_fmt, ".mp4").lower()
            supported_exts = [v.lower() for v in SUPPORTED_VIDEO.values()]
            lossless_hint = "（建议勾选「仅转封装」以获得极速转换）" if target_ext == ".mp4" else ""
        elif key == "audio":
            target_fmt = self.a_fmt.get() if hasattr(self, 'a_fmt') else "MP3"
            target_ext = SUPPORTED_AUDIO.get(target_fmt, ".mp3").lower()
            supported_exts = [v.lower() for v in SUPPORTED_AUDIO.values()]
            lossless_hint = ""
        elif key == "image":
            target_fmt = self.i_fmt.get() if hasattr(self, 'i_fmt') else "PNG"
            target_ext = SUPPORTED_IMAGE.get(target_fmt, ".png").lower()
            supported_exts = [v.lower() for v in SUPPORTED_IMAGE.values()]
            lossless_hint = ""
        elif key == "doc":
            target_fmt = self.d_tgt.get() if hasattr(self, 'd_tgt') else ""
            if target_fmt == "请先添加文件":
                d["format_hint_var"].set("请先添加文件并点击「检测格式」")
                d["format_hint_label"].configure(fg=D["ink_sec"])
                return
            import re
            target_ext = "." + re.sub(r'[^a-zA-Z0-9]', '', target_fmt.lower())
            supported_exts = [".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".txt", ".html", ".jpg", ".png",
                              ".wps", ".et", ".csv", ".dps", ".bmp", ".tiff", ".webp", ".md", ".epub", ".rtf", ".odt"]
            lossless_hint = ""
        else:
            return
        
        if src_ext == target_ext:
            d["format_hint_var"].set(f"提示：源格式与目标格式一致{lossless_hint}")
            d["format_hint_label"].configure(fg=D["accent"])
        elif src_ext in supported_exts:
            d["format_hint_var"].set("当前配置正常，准备转换为指定格式")
            d["format_hint_label"].configure(fg=D["ink"])
        else:
            d["format_hint_var"].set("警告：当前文件可能无法转换为该目标格式，请检查源文件编码")
            d["format_hint_label"].configure(fg=D["err"])

    def _setup_drag_drop(self):
        hwnd = self.root.winfo_id()
        success = False
        
        if ctypes_register_drop and SafeDropHandler:
            try:
                self._drop_handler = SafeDropHandler(self.root)
                self._drop_handler.register_callback(self._handle_dropped_files)
                ctypes_register_drop(hwnd, self._drop_handler._enqueue_files)
                self._drop_handler.start()
                print("[drag_drop] ctypes 拖拽已启用")
                success = True
            except Exception as e:
                print("[drag_drop] ctypes 拖拽初始化失败: {}".format(e))
        
        if not success and windnd:
            try:
                windnd.hook_dropfiles(hwnd, self._on_drop_windnd, force_unicode=True)
                print("[drag_drop] windnd 拖拽已启用")
                success = True
            except Exception as e:
                print("[drag_drop] windnd 初始化失败: {}".format(e))
        
        if not success:
            print("[drag_drop] 拖拽功能不可用")

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
            if added > 0 and key:
                self._update_format_hint(key)
                if key == "doc":
                    self._detect()
        except Exception:
            pass

    def _on_drop_windnd(self, files):
        if isinstance(files, (list, tuple)):
            self._handle_dropped_files(files)

    # ── 设置卡片（自适应网格布局）────────────────
    def _card(self, parent, title):
        outer = tk.Frame(parent, bg=D["border"], padx=1, pady=1)
        outer.pack(fill=tk.X, pady=(0, 10), expand=False)

        card = tk.Frame(outer, bg=D["card"])
        card.pack(fill=tk.BOTH, expand=True)

        header = tk.Frame(card, bg=D["card"])
        header.pack(fill=tk.X, padx=16, pady=(10, 0))
        tk.Label(header, text=title, bg=D["card"], fg=D["ink_sec"],
                 font=(FT, 9, "bold")).pack(anchor=tk.W)

        content = tk.Frame(card, bg=D["card"])
        content.pack(fill=tk.BOTH, expand=True, padx=16, pady=(8, 12))

        content._col_count = 0
        content._max_cols = 3
        content._widgets = []
        return content

    def _row(self, parent, label, values, default, w=12, row=None):
        """往网格卡片里添加一项，自动换列/换行"""
        grid = parent
        if row is None:
            idx = grid._col_count
            cols = grid._max_cols
            r, c = divmod(idx, cols)
        else:
            idx = grid._col_count
            cols = grid._max_cols
            r = row
            c = idx % cols

        frame = tk.Frame(grid, bg=D["card"])
        frame.grid(row=r, column=c, padx=(0, 18), pady=5, sticky="w")
        tk.Label(frame, text=label, bg=D["card"], fg=D["ink"],
                 font=SM).pack(anchor=tk.W)
        cb = ttk.Combobox(frame, values=values, state="readonly", width=w)
        cb.set(default)
        cb.pack(fill=tk.X, pady=(4, 0), padx=5)

        if not hasattr(grid, '_cols_configured'):
            for i in range(cols):
                grid.columnconfigure(i, weight=1)
            grid._cols_configured = True

        grid._col_count += 1
        grid._widgets.append(cb)
        return cb

    def _grid_row(self, parent, label, values, default, row, col):
        frame = tk.Frame(parent, bg=D["card"])
        frame.grid(row=row, column=col, padx=(0, 8), pady=4, sticky="ew")
        tk.Label(frame, text=label, bg=D["card"], fg=D["ink"],
                 font=SM).pack(anchor=tk.W)
        cb = ttk.Combobox(frame, values=values, state="readonly", width=12)
        cb.set(default)
        cb.pack(fill=tk.X, pady=(4, 0), padx=5)
        return cb

    # ── 进度栏 ────────────────────────────────
    def _bar(self, parent):
        b = tk.Frame(parent, bg=D["page"])
        b.pack(fill=tk.X, pady=(10, 0))
        pg = ttk.Progressbar(b, style="Horizontal.TProgressbar")
        pg.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 16))
        st = tk.Label(b, text="就绪", bg=D["page"], fg=D["ink_dis"], font=SM)
        st.pack(side=tk.LEFT, padx=(0, 16))
        open_folder_btn = self._btn(b, "📁 打开输出文件夹", self._open_output_folder, "ghost", padx=8)
        open_folder_btn.pack(side=tk.RIGHT, padx=(0, 8))
        ca = self._btn(b, "取消", None, "danger", state=tk.DISABLED)
        ca.pack(side=tk.RIGHT)
        go = self._btn(b, "开始转换", None, "primary", padx=24)
        go.pack(side=tk.RIGHT, padx=(0, 10))
        return pg, st, go, ca, open_folder_btn

    def _open_output_folder(self):
        if self.last_output_dir and os.path.exists(self.last_output_dir):
            os.startfile(self.last_output_dir)
        else:
            messagebox.showinfo("提示", "尚未进行转换，暂无输出目录")

    # ══════════════════════════════════════════
    #  各面板
    # ══════════════════════════════════════════
    def _p_video(self):
        p = tk.Frame(self.content, bg=D["page"])
        self.panels["video"] = p
        self._hdr(p, "视频格式转换", "MP4 · AVI · MKV · WMV · MOV · FLV · WEBM 等主流格式互转")
        self._file_sec(p, "video",
            [("视频文件","*.mp4 *.avi *.mkv *.wmv *.mov *.flv *.webm *.ts *.mpeg *.3gp"),("所有文件","*.*")])

        settings_card = self._card(p, "输出设置")

        copy_row = tk.Frame(settings_card, bg=D["card"])
        copy_row.pack(fill=tk.X, padx=16, pady=(10, 8))
        self.v_copy_mode = tk.BooleanVar(value=False)
        check_bg = D["card"] if self._theme == "light" else "#6a6a7a"
        copy_cb = tk.Checkbutton(copy_row, text="⚡ 仅转封装（无损拷贝）", variable=self.v_copy_mode,
                                  bg=D["card"], selectcolor=check_bg,
                                  fg=D["accent"], activeforeground=D["accent"],
                                  font=(FT, 10, "bold"), bd=0, highlightthickness=0,
                                  command=self._toggle_copy_mode)
        copy_cb.pack(side=tk.LEFT)
        self.v_copy_hint = tk.Label(copy_row, text="无损转封装，速度极快", bg=D["card"], fg=D["ink_dis"], font=XS)
        self.v_copy_hint.pack(side=tk.LEFT, padx=(8, 0))
        self.v_copy_hint.pack_forget()
        tk.Label(copy_row, text="预计耗时 < 5秒", bg=D["card"], fg=D["accent"], font=XS).pack(side=tk.RIGHT)

        grid_frame = tk.Frame(settings_card, bg=D["card"])
        grid_frame.pack(fill=tk.X, padx=16, pady=(0, 10))
        grid_frame.columnconfigure(0, weight=1)
        grid_frame.columnconfigure(1, weight=1)
        grid_frame.columnconfigure(2, weight=1)

        self.v_fmt = self._grid_row(grid_frame, "目标格式", list(SUPPORTED_VIDEO.keys()), "MP4", 0, 0)
        self.v_fmt.bind("<<ComboboxSelected>>", lambda e: self._update_format_hint("video"))
        self.v_codec = self._grid_row(grid_frame, "视频编码", list(VIDEO_CODECS.keys()), "默认", 0, 1)
        self.v_preset = self._grid_row(grid_frame, "画质预设", list(VIDEO_PRESETS.keys()), "原始质量", 0, 2)
        self.v_res = self._grid_row(grid_frame, "分辨率", list(RESOLUTIONS.keys()), "原始分辨率", 1, 0)
        self.v_fps = self._grid_row(grid_frame, "帧率", ["原始帧率","24","25","30","60"], "原始帧率", 1, 1)
        self.v_br = self._grid_row(grid_frame, "码率", ["自动","1M","2M","5M","8M","10M","20M"], "自动", 1, 2)

        # 快速预设 + 输出目录 合并为一行
        preset_out_row = tk.Frame(settings_card, bg=D["card"])
        preset_out_row.pack(fill=tk.X, padx=16, pady=(0, 10))

        # 快速预设（左侧）
        preset_frame = tk.Frame(preset_out_row, bg=D["card"])
        preset_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(preset_frame, text="快速预设", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 8))
        video_presets = ["自定义"] + get_preset_names("video")
        self.v_preset_combo = ttk.Combobox(preset_frame, values=video_presets, state="readonly", width=16)
        self.v_preset_combo.set("自定义")
        self.v_preset_combo.pack(side=tk.LEFT)
        self.v_preset_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_video_preset())

        # 输出目录（右侧）
        out_frame = tk.Frame(preset_out_row, bg=D["card"])
        out_frame.pack(side=tk.RIGHT)
        tk.Label(out_frame, text="输出目录", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 6))
        self.v_out_dir = tk.StringVar(value="与源文件同目录")
        self.v_out_dir_combo = ttk.Combobox(out_frame, values=["与源文件同目录", "自定义目录"], state="readonly", width=12)
        self.v_out_dir_combo.set("与源文件同目录")
        self.v_out_dir_combo.pack(side=tk.LEFT)
        self.v_out_dir_btn = self._btn(out_frame, "浏览", lambda: self._select_out_dir("video"), style="secondary")
        self.v_out_dir_btn.pack(side=tk.LEFT, padx=(6, 0))
        self.v_out_dir_path = tk.StringVar(value="")
        self.v_out_dir_label = tk.Label(out_frame, textvariable=self.v_out_dir_path, bg=D["card"], fg=D["ink_dis"], font=XS)
        self.v_out_dir_label.pack(side=tk.LEFT, padx=(6, 0))

        bottom_bar = tk.Frame(p, bg=D["page"])
        bottom_bar.pack(fill=tk.X, pady=(12, 0))

        self.v_pg = ttk.Progressbar(bottom_bar, style="Horizontal.TProgressbar")
        self.v_pg.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 16))

        self.v_st = tk.Label(bottom_bar, text="就绪", bg=D["page"], fg=D["ink_dis"], font=SM)
        self.v_st.pack(side=tk.LEFT, padx=(0, 12))

        self._btn(bottom_bar, "📁 打开输出文件夹", self._open_output_folder, "ghost", padx=8).pack(side=tk.RIGHT, padx=(0, 8))

        self.v_ca = self._btn(bottom_bar, "取消", None, "danger", state=tk.DISABLED)
        self.v_ca.pack(side=tk.RIGHT, padx=(0, 10))
        self.v_ca.configure(command=lambda: self._stop("video"))

        self.v_go = self._btn(bottom_bar, "开始转换", None, "primary", padx=24)
        self.v_go.pack(side=tk.RIGHT)
        self.v_go.configure(command=lambda: self._go("video"))

    def _toggle_copy_mode(self):
        copy_mode = self.v_copy_mode.get()
        has_video_files = len(self.panel_data.get("video", {}).get("files", [])) > 0
        
        if copy_mode:
            self.v_fmt.configure(values=["MP4", "MKV", "TS", "FLV", "MOV"])
            current_fmt = self.v_fmt.get()
            if current_fmt not in ["MP4", "MKV", "TS", "FLV", "MOV"]:
                self.v_fmt.set("MP4")
            
            for widget in [self.v_codec, self.v_preset, self.v_res, self.v_fps, self.v_br]:
                widget.configure(state="disabled")
            
            self.v_copy_hint.pack(side=tk.LEFT, padx=(8, 0))
            self._validate_copy_compatibility()
        else:
            self.v_fmt.configure(values=list(SUPPORTED_VIDEO.keys()))
            
            for widget in [self.v_codec, self.v_preset, self.v_res, self.v_fps, self.v_br]:
                widget.configure(state="readonly")
            
            self.v_copy_hint.pack_forget()

    def _validate_copy_compatibility(self):
        files = self.panel_data.get("video", {}).get("files", [])
        if not files:
            return
        
        info = self.video_conv.get_media_info(files[0])
        if not info:
            return
        
        streams = info.get("streams", [])
        v_codec = None
        for s in streams:
            if s.get("codec_type") == "video":
                v_codec = s.get("codec_name")
                break
        
        fmt = self.v_fmt.get()
        ext = SUPPORTED_VIDEO[fmt]
        
        incompatible = False
        reason = ""
        
        if v_codec:
            if v_codec in ["hevc", "h265"] and ext == ".flv":
                incompatible = True
                reason = "H.265 编码不兼容 FLV 容器"
            elif v_codec in ["vp9", "av1"] and ext in [".flv", ".wmv"]:
                incompatible = True
                reason = f"{v_codec.upper()} 编码不兼容 {fmt} 容器"
        
        if incompatible:
            self.v_copy_mode.set(False)
            self._toggle_copy_mode()
            messagebox.showwarning("不兼容", f"无法使用转封装模式：{reason}")

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
        attr_map = {
            "video": ("v_out_dir_combo", "v_out_dir_path"),
            "audio": ("a_out_dir_combo", "a_out_dir_path"),
            "image": ("i_out_dir_combo", "i_out_dir_path"),
            "doc": ("d_out_dir_combo", "d_out_dir_path"),
            "extract": ("e_out_dir_combo", "e_out_dir_path"),
            "compress": ("c_out_dir_combo", "c_out_dir_path"),
            "gif": ("gif_out_dir_combo", "gif_out_dir_path"),
            "pdf": ("pdf_out_dir_combo", "pdf_out_dir_path"),
            "compress_img": ("ci_out_dir_combo", "ci_out_dir_path"),
            "rename": ("rn_out_dir_combo", "rn_out_dir_path"),
            "crop": ("crp_out_dir_combo", "crp_out_dir_path"),
            "ocr": ("ocr_out_dir_combo", "ocr_out_dir_path"),
        }

        last_dir = self._get_last_dir(panel_key)
        dir_path = filedialog.askdirectory(initialdir=last_dir)
        if not dir_path:
            return

        self._save_last_dir(panel_key, dir_path)

        if panel_key in attr_map:
            combo_attr, path_attr = attr_map[panel_key]
            if hasattr(self, combo_attr) and hasattr(self, path_attr):
                getattr(self, path_attr).set(dir_path)
                getattr(self, combo_attr).set("自定义目录")

    def _p_audio(self):
        p = tk.Frame(self.content, bg=D["page"])
        self.panels["audio"] = p
        self._hdr(p, "音频格式转换", "MP3 · WAV · WMA · AAC · FLAC · OGG · M4A 等格式互转")
        self._file_sec(p, "audio",
            [("音频文件","*.mp3 *.wav *.wma *.aac *.flac *.ogg *.m4a *.amr *.opus"),("所有文件","*.*")])
        s = self._card(p, "输出设置")
        self.a_fmt  = self._row(s, "目标格式", list(SUPPORTED_AUDIO.keys()), "MP3")
        self.a_fmt.bind("<<ComboboxSelected>>", lambda e: self._update_format_hint("audio"))
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

        # 输出目录（卡片内底部）
        out_frame = tk.Frame(s, bg=D["card"])
        out_frame.grid(row=5, column=0, columnspan=4, sticky="ew", padx=16, pady=(8, 10))
        tk.Label(out_frame, text="输出目录", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 8))
        self.a_out_dir_combo = ttk.Combobox(out_frame, values=["与源文件同目录", "自定义目录"], state="readonly", width=14)
        self.a_out_dir_combo.set("与源文件同目录")
        self.a_out_dir_combo.pack(side=tk.LEFT)
        self.a_out_dir_btn = self._btn(out_frame, "浏览", lambda: self._select_out_dir("audio"), style="secondary")
        self.a_out_dir_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.a_out_dir_path = tk.StringVar(value="")
        self.a_out_dir_label = tk.Label(out_frame, textvariable=self.a_out_dir_path, bg=D["card"], fg=D["ink_dis"], font=XS)
        self.a_out_dir_label.pack(side=tk.LEFT, padx=(8, 0))

        self.a_pg, self.a_st, self.a_go, self.a_ca, _ = self._bar(p)
        self.a_go.configure(command=lambda: self._go("audio"))
        self.a_ca.configure(command=lambda: self._stop("audio"))

    def _p_image(self):
        p = tk.Frame(self.content, bg=D["page"])
        self.panels["image"] = p
        self._hdr(p, "图片格式转换", "JPG · PNG · BMP · GIF · TIFF · WEBP · ICO 格式互转")
        self._file_sec(p, "image",
            [("图片文件","*.jpg *.jpeg *.png *.bmp *.gif *.tiff *.webp *.ico *.tga"),("所有文件","*.*")])
        s = self._card(p, "输出设置")
        
        s.columnconfigure(1, weight=1)
        s.columnconfigure(3, weight=1)
        
        tk.Label(s, text="目标格式", bg=D["card"], fg=D["ink"], font=SM).grid(row=0, column=0, sticky="w", padx=(10, 8), pady=8)
        self.i_fmt = ttk.Combobox(s, values=list(SUPPORTED_IMAGE.keys()), state="readonly", width=14)
        self.i_fmt.set("PNG")
        self.i_fmt.grid(row=0, column=1, sticky="ew", padx=(0, 16), pady=8)
        self.i_fmt.bind("<<ComboboxSelected>>", lambda e: self._update_format_hint("image"))
        
        tk.Label(s, text="质量", bg=D["card"], fg=D["ink"], font=SM).grid(row=0, column=2, sticky="w", padx=(10, 8), pady=8)
        self.i_q = ttk.Combobox(s, values=["100（无损）","95（高质量）","85（中等）","70（低质量）","50（压缩）"], state="readonly", width=14)
        self.i_q.set("95（高质量）")
        self.i_q.grid(row=0, column=3, sticky="ew", padx=(0, 10), pady=8)
        
        tk.Label(s, text="缩放", bg=D["card"], fg=D["ink"], font=SM).grid(row=1, column=0, sticky="w", padx=(10, 8), pady=8)
        self.i_sz = ttk.Combobox(s, values=["原始大小","50%","25%","200%"], state="readonly", width=14)
        self.i_sz.set("原始大小")
        self.i_sz.grid(row=1, column=1, sticky="ew", padx=(0, 16), pady=8)
        
        tk.Label(s, text="旋转", bg=D["card"], fg=D["ink"], font=SM).grid(row=1, column=2, sticky="w", padx=(10, 8), pady=8)
        self.i_rotate = ttk.Combobox(s, values=["0°","90°","180°","270°"], state="readonly", width=14)
        self.i_rotate.set("0°")
        self.i_rotate.grid(row=1, column=3, sticky="ew", padx=(0, 10), pady=8)
        
        tk.Label(s, text="裁剪", bg=D["card"], fg=D["ink"], font=SM).grid(row=2, column=0, sticky="w", padx=(10, 8), pady=8)
        self.i_crop = ttk.Combobox(s, values=["原始比例","裁剪为正方形"], state="readonly", width=14)
        self.i_crop.set("原始比例")
        self.i_crop.grid(row=2, column=1, sticky="ew", padx=(0, 16), pady=8)
        
        self.i_grayscale = tk.BooleanVar(value=False)
        grayscale_cb = tk.Checkbutton(s, text="转为黑白（灰度）", variable=self.i_grayscale,
                                       bg=D["card"], fg=D["ink"], font=SM)
        grayscale_cb.grid(row=2, column=2, columnspan=2, sticky="w", padx=10, pady=8)
        
        separator = tk.Frame(s, bg=D["border"], height=1)
        separator.grid(row=3, column=0, columnspan=4, sticky="ew", padx=10, pady=10)
        
        tk.Label(s, text="水印处理", bg=D["card"], fg=D["ink"], font=(FT, 9, "bold")).grid(row=4, column=0, columnspan=4, sticky="w", padx=10, pady=(4, 4))
        
        tk.Label(s, text="水印文字", bg=D["card"], fg=D["ink"], font=SM).grid(row=5, column=0, sticky="w", padx=(10, 8), pady=8)
        self.i_watermark = tk.Entry(s, font=BODY, bg=D["input_bg"], fg=D["ink"],
                                     insertbackground=D["ink"], relief="flat",
                                     highlightthickness=1, highlightbackground=D["input_bd"],
                                     highlightcolor=D["accent"], width=16)
        self.i_watermark.grid(row=5, column=1, sticky="ew", padx=(0, 16), pady=8)
        
        tk.Label(s, text="水印位置", bg=D["card"], fg=D["ink"], font=SM).grid(row=5, column=2, sticky="w", padx=(10, 8), pady=8)
        self.i_watermark_pos = ttk.Combobox(s, values=["右下角","左下角","右上角","左上角","居中"], state="readonly", width=14)
        self.i_watermark_pos.set("右下角")
        self.i_watermark_pos.grid(row=5, column=3, sticky="ew", padx=(0, 10), pady=8)

        # 输出目录（卡片内底部）
        out_frame = tk.Frame(s, bg=D["card"])
        out_frame.grid(row=6, column=0, columnspan=4, sticky="ew", padx=10, pady=(8, 10))
        tk.Label(out_frame, text="输出目录", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 8))
        self.i_out_dir_combo = ttk.Combobox(out_frame, values=["与源文件同目录", "自定义目录"], state="readonly", width=14)
        self.i_out_dir_combo.set("与源文件同目录")
        self.i_out_dir_combo.pack(side=tk.LEFT)
        self.i_out_dir_btn = self._btn(out_frame, "浏览", lambda: self._select_out_dir("image"), style="secondary")
        self.i_out_dir_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.i_out_dir_path = tk.StringVar(value="")
        self.i_out_dir_label = tk.Label(out_frame, textvariable=self.i_out_dir_path, bg=D["card"], fg=D["ink_dis"], font=XS)
        self.i_out_dir_label.pack(side=tk.LEFT, padx=(8, 0))

        self.i_pg, self.i_st, self.i_go, self.i_ca, _ = self._bar(p)
        self.i_go.configure(command=lambda: self._go("image"))
        self.i_ca.configure(command=lambda: self._stop("image"))

    def _p_doc(self):
        p = tk.Frame(self.content, bg=D["page"])
        self.panels["doc"] = p
        self._hdr(p, "文档格式转换", "PDF · Word · Excel · PPT · WPS · TXT · 图片 · Markdown · EPUB · RTF · ODT")
        exts = "*.pdf *.docx *.doc *.wps *.xlsx *.xls *.et *.csv *.pptx *.ppt *.dps *.txt *.html *.htm *.md *.epub *.rtf *.odt *.jpg *.jpeg *.png *.bmp *.tiff *.webp"
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
        self.d_tgt.bind("<<ComboboxSelected>>", lambda e: self._update_format_hint("doc"))
        self._btn(s, "检测格式", self._detect).grid(row=1, column=2, sticky="w")

        # 输出目录（卡片内）
        out_frame = tk.Frame(s, bg=D["card"])
        out_frame.grid(row=2, column=0, columnspan=3, sticky="ew", padx=16, pady=(8, 10))
        tk.Label(out_frame, text="输出目录", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 8))
        self.d_out_dir_combo = ttk.Combobox(out_frame, values=["与源文件同目录", "自定义目录"], state="readonly", width=14)
        self.d_out_dir_combo.set("与源文件同目录")
        self.d_out_dir_combo.pack(side=tk.LEFT)
        self.d_out_dir_btn = self._btn(out_frame, "浏览", lambda: self._select_out_dir("doc"), style="secondary")
        self.d_out_dir_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.d_out_dir_path = tk.StringVar(value="")
        self.d_out_dir_label = tk.Label(out_frame, textvariable=self.d_out_dir_path, bg=D["card"], fg=D["ink_dis"], font=XS)
        self.d_out_dir_label.pack(side=tk.LEFT, padx=(8, 0))

        self.d_pg, self.d_st, self.d_go, self.d_ca, _ = self._bar(p)
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

        # 输出目录（卡片内）
        out_frame = tk.Frame(s, bg=D["card"])
        out_frame.grid(row=2, column=0, columnspan=4, sticky="ew", padx=16, pady=(8, 10))
        tk.Label(out_frame, text="输出目录", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 8))
        self.e_out_dir_combo = ttk.Combobox(out_frame, values=["与源文件同目录", "自定义目录"], state="readonly", width=14)
        self.e_out_dir_combo.set("与源文件同目录")
        self.e_out_dir_combo.pack(side=tk.LEFT)
        self.e_out_dir_btn = self._btn(out_frame, "浏览", lambda: self._select_out_dir("extract"), style="secondary")
        self.e_out_dir_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.e_out_dir_path = tk.StringVar(value="")
        self.e_out_dir_label = tk.Label(out_frame, textvariable=self.e_out_dir_path, bg=D["card"], fg=D["ink_dis"], font=XS)
        self.e_out_dir_label.pack(side=tk.LEFT, padx=(8, 0))

        self.e_pg, self.e_st, self.e_go, self.e_ca, _ = self._bar(p)
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

        # 输出目录（卡片内）
        out_frame = tk.Frame(s, bg=D["card"])
        out_frame.grid(row=2, column=0, columnspan=4, sticky="ew", padx=16, pady=(8, 10))
        tk.Label(out_frame, text="输出目录", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 8))
        self.c_out_dir_combo = ttk.Combobox(out_frame, values=["与源文件同目录", "自定义目录"], state="readonly", width=14)
        self.c_out_dir_combo.set("与源文件同目录")
        self.c_out_dir_combo.pack(side=tk.LEFT)
        self.c_out_dir_btn = self._btn(out_frame, "浏览", lambda: self._select_out_dir("compress"), style="secondary")
        self.c_out_dir_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.c_out_dir_path = tk.StringVar(value="")
        self.c_out_dir_label = tk.Label(out_frame, textvariable=self.c_out_dir_path, bg=D["card"], fg=D["ink_dis"], font=XS)
        self.c_out_dir_label.pack(side=tk.LEFT, padx=(8, 0))

        self.c_pg, self.c_st, self.c_go, self.c_ca, _ = self._bar(p)
        self.c_go.configure(command=lambda: self._go("compress"))
        self.c_ca.configure(command=lambda: self._stop("compress"))

    # ── 格式检测 ──────────────────────────────
    def _p_detect(self):
        p = tk.Frame(self.content, bg=D["page"])
        self.panels["detect"] = p
        self._hdr(p, "格式检测", "批量检测文件夹中所有文件的格式，支持按内容识别、文件详情预览和选择性批量转换")
        
        s = self._card(p, "检测设置")
        
        tk.Label(s, text="目标文件夹", bg=D["card"], fg=D["ink"], font=SM).grid(row=0, column=0, sticky="w")
        self.detect_path = tk.Entry(s, font=BODY, bg=D["input_bg"], fg=D["ink"],
                                     insertbackground=D["ink"], relief="flat",
                                     highlightthickness=1, highlightbackground=D["input_bd"],
                                     highlightcolor=D["accent"], width=40)
        self.detect_path.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self._btn(s, "浏览", self._detect_browse, style="secondary", padx=12, pady=2).grid(row=0, column=2, padx=(4, 0))
        
        self.detect_auto_add = tk.BooleanVar(value=True)
        tk.Checkbutton(s, text="自动添加到对应面板", variable=self.detect_auto_add,
                       bg=D["card"], fg=D["ink"], font=SM).grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))
        
        # 可滚动结果区域（Canvas + Frame + Scrollbar）
        container = tk.Frame(p, bg=D["card"])
        container.pack(fill=tk.BOTH, expand=True, padx=16, pady=(12, 0))
        
        self.detect_canvas = tk.Canvas(container, bg=D["card"], highlightthickness=0)
        vbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.detect_canvas.yview)
        self.detect_rf = tk.Frame(self.detect_canvas, bg=D["card"])
        
        self.detect_rf.bind("<Configure>",
            lambda e: self.detect_canvas.configure(scrollregion=self.detect_canvas.bbox("all")))
        self.detect_canvas.create_window((0, 0), window=self.detect_rf, anchor="nw")
        self.detect_canvas.configure(yscrollcommand=vbar.set)
        
        self.detect_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        def _bind_mw(e):
            self.detect_canvas.bind_all("<MouseWheel>",
                lambda ev: self.detect_canvas.yview_scroll(int(-1*(ev.delta/120)), "units"))
        def _unbind_mw(e):
            self.detect_canvas.unbind_all("<MouseWheel>")
        self.detect_canvas.bind("<Enter>", _bind_mw)
        self.detect_canvas.bind("<Leave>", _unbind_mw)
        
        self.detect_pg, self.detect_st, self.detect_go, self.detect_ca, _ = self._bar(p)
        self.detect_go.configure(text="开始检测", command=self._detect_start)
        self.detect_ca.configure(command=self._detect_stop, state=tk.DISABLED)
        
        self.detect_file_list = []
        self.detect_file_vars = []

    def _detect_browse(self):
        last_dir = self._get_last_dir("detect")
        path = filedialog.askdirectory(title="选择文件夹", initialdir=last_dir)
        if path:
            self._save_last_dir("detect", path)
            self.detect_path.delete(0, tk.END)
            self.detect_path.insert(0, path)
    
    def _detect_start(self):
        path = self.detect_path.get()
        if not path or not os.path.isdir(path):
            messagebox.showwarning("提示", "请选择有效的文件夹"); return
        
        self.detect_go.configure(state=tk.DISABLED)
        self.detect_ca.configure(state=tk.NORMAL)
        self.detect_pg["value"] = 0
        
        for w in self.detect_rf.winfo_children():
            w.destroy()
        self.detect_file_list.clear()
        self.detect_file_vars.clear()
        self.detect_st.configure(text="正在扫描文件夹...")
        
        threading.Thread(target=self._detect_run, args=(path,), daemon=True).start()
    
    def _detect_stop(self):
        self.detecting = False
    
    def _detect_format_by_content(self, fp):
        """通过文件头魔数检测文件实际格式"""
        try:
            with open(fp, 'rb') as f:
                header = f.read(16)
        except Exception:
            return None
        if not header or len(header) < 4:
            return None
        if header[:4] == b'%PDF': return 'pdf'
        if header[:2] == b'\xff\xd8': return 'image'
        if header[:8] == b'\x89PNG\r\n\x1a\n': return 'image'
        if header[:3] == b'GIF': return 'image'
        if header[:2] == b'BM': return 'image'
        if header[:4] == b'RIFF' and len(header) >= 12:
            if header[8:12] == b'WEBP': return 'image'
            if header[8:12] == b'AVI ': return 'video'
            if header[8:12] == b'WAVE': return 'audio'
        if header[:4] in (b'II*\x00', b'MM\x00*'): return 'image'
        if header[:4] == b'ftyp': return 'video'
        if header[:4] == b'\x1aE\xdf\xa3': return 'video'
        if header[:4] == b'\x30\x26\xb2\x75':
            ext = os.path.splitext(fp)[1].lower()
            return 'audio' if ext in ('.wma',) else 'video'
        if header[:3] == b'\x00\x00\x00' and len(header) > 3 and header[3] in (0x18, 0x1C, 0x20):
            return 'video'
        if header[:3] == b'ID3': return 'audio'
        if header[:4] == b'fLaC': return 'audio'
        if header[:4] == b'OggS': return 'audio'
        if header[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1': return 'doc'
        if header[:4] == b'PK\x03\x04':
            low = fp.lower()
            if any(low.endswith(e) for e in ('.docx','.xlsx','.pptx','.docm','.xlsm','.pptm')):
                return 'doc'
            return 'other'
        return None
    
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
        
        total = len(all_files)
        if total == 0:
            self.root.after(0, lambda: self.detect_st.configure(text="文件夹为空，未检测到文件"))
            self.root.after(0, lambda: self.detect_go.configure(state=tk.NORMAL,
                text="开始检测", command=self._detect_start))
            self.root.after(0, lambda: self.detect_ca.configure(state=tk.DISABLED))
            return
        
        self.root.after(0, lambda: self.detect_st.configure(text=f"正在检测 {total} 个文件..."))
        self.root.after(0, lambda: self.detect_pg.configure(maximum=total, value=0))
        
        file_info = []  # [(fp, category, size_str, content_type)]
        
        for i, fp in enumerate(all_files):
            if not self.detecting:
                self.root.after(0, lambda: self.detect_st.configure(text="检测已取消"))
                return
            
            ext = os.path.splitext(fp)[1].lower()
            if ext in VIDEO_EXTS:
                cat = 'video'
            elif ext in AUDIO_EXTS:
                cat = 'audio'
            elif ext in IMAGE_EXTS:
                cat = 'image'
            elif ext in DOC_EXTS:
                cat = 'doc'
            elif ext in PDF_EXTS:
                cat = 'pdf'
            else:
                cat = 'other'
            
            detected[cat].append(fp)
            
            content_type = self._detect_format_by_content(fp)
            size_str = self._format_size(os.path.getsize(fp))
            file_info.append((fp, cat, size_str, content_type))
            
            if (i + 1) % 20 == 0 or i == total - 1:
                cur = i + 1
                self.root.after(0, lambda v=cur: self.detect_pg.configure(value=v))
                self.root.after(0, lambda v=cur, t=total: self.detect_st.configure(
                    text=f"正在检测 {v}/{t} 个文件"))
        
        self.root.after(0, self._show_detect_results, detected, file_info)

    def _batch_convert_from_detect(self, detected):
        task_names = {
            "video": "视频转换", "audio": "音频转换", "image": "图片转换",
            "doc": "文档转换", "pdf": "PDF处理",
        }
        
        task_counts = {
            "video": 0, "audio": 0, "image": 0, "doc": 0, "pdf": 0
        }
        
        for key, files in detected.items():
            if key not in task_counts:
                continue
            
            if key == "pdf":
                mode = self.pdf_mode.get() if hasattr(self, 'pdf_mode') else "合并（多个→一个）"
                if "合并" in mode and files:
                    output_path = os.path.join(os.path.dirname(files[0]), "merged.pdf")
                    task_name = f"PDF合并 - {len(files)}个文件"
                    task_id = self._add_task(task_name, "pdf", {
                        "file_path": "",
                        "output_path": output_path,
                        "files": files,
                        "task_type": "pdf",
                        "panel_name": "pdf",
                        "params": {"mode": mode, "range": self.pdf_range.get() if hasattr(self, 'pdf_range') else ""}
                    })
                    if task_id:
                        task_counts["pdf"] += 1
                    continue
            
            for fp in files:
                fn = os.path.basename(fp)
                nm = os.path.splitext(fn)[0]
                od = os.path.dirname(fp)
                
                output_path = ""
                module_params = {}
                
                if key == "video":
                    fmt = self.v_fmt.get() if hasattr(self, 'v_fmt') else "MP4"
                    ext = SUPPORTED_VIDEO.get(fmt, ".mp4")
                    output_path = os.path.join(od, nm + ext)
                    module_params = {
                        "fmt": fmt,
                        "codec": self.v_codec.get() if hasattr(self, 'v_codec') else "默认",
                        "preset": self.v_preset.get() if hasattr(self, 'v_preset') else "原始质量",
                        "res": self.v_res.get() if hasattr(self, 'v_res') else "原始分辨率",
                        "fps": self.v_fps.get() if hasattr(self, 'v_fps') else "原始帧率",
                        "br": self.v_br.get() if hasattr(self, 'v_br') else "自动",
                        "copy": self.v_copy_mode.get() if hasattr(self, 'v_copy_mode') else False,
                        "out_dir_combo": "与源文件同目录",
                        "out_dir_path": ""
                    }
                    task_type = "video"
                elif key == "audio":
                    fmt = self.a_fmt.get() if hasattr(self, 'a_fmt') else "MP3"
                    ext = SUPPORTED_AUDIO.get(fmt, ".mp3")
                    output_path = os.path.join(od, nm + ext)
                    module_params = {
                        "fmt": fmt,
                        "bitrate": self.a_br.get() if hasattr(self, 'a_br') else "192k",
                        "sample_rate": self.a_sr.get() if hasattr(self, 'a_sr') else "原始",
                        "channels": self.a_ch.get() if hasattr(self, 'a_ch') else "原始",
                        "volume": self.a_vol.get() if hasattr(self, 'a_vol') else 100
                    }
                    task_type = "audio"
                elif key == "image":
                    fmt = self.i_fmt.get() if hasattr(self, 'i_fmt') else "PNG"
                    ext = SUPPORTED_IMAGE.get(fmt, ".png")
                    output_path = os.path.join(od, nm + ext)
                    module_params = {
                        "fmt": fmt,
                        "quality": self.i_q.get() if hasattr(self, 'i_q') else "95（高质量）",
                        "size": self.i_sz.get() if hasattr(self, 'i_sz') else "原始大小",
                        "rotate": self.i_rotate.get() if hasattr(self, 'i_rotate') else "0°",
                        "crop": self.i_crop.get() if hasattr(self, 'i_crop') else "原始比例",
                        "grayscale": self.i_grayscale.get() if hasattr(self, 'i_grayscale') else False,
                        "watermark": "",
                        "watermark_pos": "右下角"
                    }
                    task_type = "image"
                elif key == "doc":
                    tgt = self.d_tgt.get() if hasattr(self, 'd_tgt') else ""
                    if tgt == "请先添加文件":
                        tgt = "PDF"
                    ext = "." + tgt.split("（")[0].lower()
                    output_path = os.path.join(od, nm + ext)
                    module_params = {"target": tgt}
                    task_type = "doc"
                elif key == "pdf":
                    mode = self.pdf_mode.get() if hasattr(self, 'pdf_mode') else "合并（多个→一个）"
                    if "拆分" in mode:
                        output_path = os.path.join(od, nm + "_split")
                        os.makedirs(output_path, exist_ok=True)
                    elif "加密" in mode:
                        output_path = os.path.join(od, nm + "_encrypted.pdf")
                    elif "解密" in mode:
                        output_path = os.path.join(od, nm + "_decrypted.pdf")
                    elif "压缩" in mode:
                        output_path = os.path.join(od, nm + "_compressed.pdf")
                    else:
                        output_path = os.path.join(od, nm + ".pdf")
                    module_params = {"mode": mode}
                    task_type = "pdf"
                else:
                    continue
                
                if output_path and output_path.lower() == fp.lower():
                    base_ext = os.path.splitext(output_path)
                    output_path = base_ext[0] + "_1" + base_ext[1]
                
                if output_path and os.path.exists(output_path):
                    base_ext = os.path.splitext(output_path)
                    counter = 1
                    while os.path.exists(f"{base_ext[0]}_{counter}{base_ext[1]}"):
                        counter += 1
                    output_path = f"{base_ext[0]}_{counter}{base_ext[1]}"
                
                task_name = f"{task_names.get(task_type, task_type)} - {fn}"
                task_id = self._add_task(task_name, task_type, {
                    "file_path": fp,
                    "output_path": output_path,
                    "files": [fp],
                    "task_type": task_type,
                    "panel_name": task_type,
                    "params": module_params
                })
                
                if task_id:
                    task_counts[key] += 1
        
        summary_parts = []
        for k, v in task_counts.items():
            if v > 0:
                summary_parts.append(f"{v} 个{task_names.get(k, k)}任务")
        
        if summary_parts:
            summary_msg = "一键批量转换已触发，共添加 " + "，".join(summary_parts)
            self._log_status(summary_msg, "success")
        else:
            self._log_status("未检测到可批量转换的文件", "info")

    def _show_detect_results(self, detected, file_info):
        for w in self.detect_rf.winfo_children():
            w.destroy()
        self.detect_file_list.clear()
        self.detect_file_vars.clear()

        type_order = ['video', 'audio', 'image', 'doc', 'pdf', 'other']
        type_icons = {'video': '🎬', 'audio': '🎵', 'image': '🖼️', 'doc': '📄', 'pdf': '📕', 'other': '📁'}
        type_names = {'video': '视频文件', 'audio': '音频文件', 'image': '图片文件', 'doc': '文档文件', 'pdf': 'PDF文件', 'other': '其他文件'}

        processable = {k: v for k, v in detected.items() if k != 'other'}
        total_found = sum(len(v) for v in processable.values())
        total_all = sum(len(v) for v in detected.values())

        row = 0

        if total_all > 0:
            cf = tk.Frame(self.detect_rf, bg=D["card"])
            cf.grid(row=row, column=0, columnspan=4, sticky="ew", padx=8, pady=(4, 4))
            cf.columnconfigure(0, weight=1)
            row += 1
            tk.Label(cf, text=f"共检测到 {total_found} 个可处理文件（共 {total_all} 个），勾选要转换的文件：",
                     bg=D["card"], fg=D["ink"], font=SM).grid(row=0, column=0, sticky="w")
            sa = tk.Button(cf, text="全选", font=SM, bg=D["card"], fg=D["accent"],
                           relief="flat", cursor="hand2", bd=0,
                           activebackground=D["card_alt"], command=self._detect_select_all)
            sa.grid(row=0, column=1, sticky="e", padx=(0, 4))
            da = tk.Button(cf, text="取消全选", font=SM, bg=D["card"], fg=D["ink_sec"],
                           relief="flat", cursor="hand2", bd=0,
                           activebackground=D["card_alt"], command=self._detect_deselect_all)
            da.grid(row=0, column=2, sticky="e")
            reset_btn = tk.Button(cf, text="🔄 重新检测", font=SM, bg=D["card"], fg=D["ink_sec"],
                                  relief="flat", cursor="hand2", bd=0,
                                  activebackground=D["card_alt"], command=self._detect_reset)
            reset_btn.grid(row=0, column=3, sticky="e", padx=(8, 0))

        for cat in type_order:
            files = detected[cat]
            if not files:
                continue

            hdr = tk.Label(self.detect_rf, text=f"{type_icons[cat]} {type_names[cat]} ({len(files)}个)",
                           bg=D["card"], fg=D["ink_sec"], font=(FT, 10, "bold"), anchor=tk.W)
            hdr.grid(row=row, column=0, columnspan=4, sticky="ew", pady=(8, 2), padx=8)
            row += 1

            for fp in files:
                matching = [fi for fi in file_info if fi[0] == fp]
                if matching:
                    _, _, size_str, content_type = matching[0]
                else:
                    size_str = self._format_size(os.path.getsize(fp))
                    content_type = None

                fn = os.path.basename(fp)
                var = tk.BooleanVar(value=True)
                self.detect_file_list.append(fp)
                self.detect_file_vars.append(var)

                rf = tk.Frame(self.detect_rf, bg=D["card"])
                rf.grid(row=row, column=0, columnspan=4, sticky="ew", pady=1, padx=(4, 8))
                rf.columnconfigure(1, weight=1)

                cb = tk.Checkbutton(rf, variable=var, bg=D["card"], fg=D["ink"],
                                     activebackground=D["card"], bd=0)
                cb.grid(row=0, column=0, sticky="w")

                if content_type and content_type != cat:
                    display = f"{fn}  ⚠️ (内容检测: {type_names.get(content_type, content_type)})"
                    fg_c = D["warn"]
                else:
                    display = fn
                    fg_c = D["ink"]

                tk.Label(rf, text=display, bg=D["card"], fg=fg_c,
                         font=BODY, anchor=tk.W).grid(row=0, column=1, sticky="ew", padx=(4, 8))
                tk.Label(rf, text=size_str, bg=D["card"], fg=D["ink_dis"],
                         font=XS, anchor=tk.E, width=10).grid(row=0, column=2, sticky="e")

                ext_str = os.path.splitext(fp)[1].upper() or "?"
                tk.Label(rf, text=ext_str, bg=D["card"], fg=D["ink_sec"],
                         font=XS, anchor=tk.E, width=8).grid(row=0, column=3, sticky="e")
                row += 1

        if total_found > 0:
            sep = tk.Frame(self.detect_rf, bg=D["border"], height=1)
            sep.grid(row=row, column=0, columnspan=4, sticky="ew", pady=(8, 4), padx=8)
            row += 1
            tk.Label(self.detect_rf, text=f"共检测到 {total_found} 个可处理文件",
                     bg=D["card"], fg=D["ink_dis"], font=XS).grid(row=row, column=0, columnspan=4, sticky="w", padx=8)
            row += 1

        self.detect_go.configure(
            text=f"批量转换选中 ({total_found})",
            command=self._detect_batch,
            state=tk.NORMAL
        )
        self.detect_ca.configure(state=tk.DISABLED)
        self.detect_st.configure(text=f"检测完成，共 {total_found} 个文件")
        self.detect_pg["value"] = 0

        if self.detect_auto_add.get():
            for key, files in processable.items():
                if key in self.panel_data:
                    self.panel_data[key]["files"] = list(set(self.panel_data[key].get("files", []) + files))
                    listbox = self.panel_data[key].get("listbox")
                    if listbox:
                        listbox.delete(0, tk.END)
                        for f in self.panel_data[key]["files"]:
                            listbox.insert(tk.END, os.path.basename(f))

    def _detect_select_all(self):
        for var in self.detect_file_vars:
            var.set(True)
        count = len(self.detect_file_vars)
        self.detect_go.configure(text=f"批量转换选中 ({count})")

    def _detect_deselect_all(self):
        for var in self.detect_file_vars:
            var.set(False)
        self.detect_go.configure(text="批量转换选中 (0)")

    def _detect_reset(self):
        for w in self.detect_rf.winfo_children():
            w.destroy()
        self.detect_file_list.clear()
        self.detect_file_vars.clear()
        self.detect_st.configure(text="就绪")
        self.detect_pg["value"] = 0
        self.detect_go.configure(text="开始检测", command=self._detect_start, state=tk.NORMAL)
        self.detect_ca.configure(state=tk.DISABLED)

    def _detect_batch(self):
        selected = [fp for fp, var in zip(self.detect_file_list, self.detect_file_vars) if var.get()]
        if not selected:
            messagebox.showinfo("提示", "请先勾选需要转换的文件"); return

        VIDEO_EXTS = {'.mp4', '.avi', '.mkv', '.wmv', '.mov', '.flv', '.webm', '.ts', '.3gp'}
        AUDIO_EXTS = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.amr', '.opus'}
        IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.svg'}
        DOC_EXTS = {'.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.rtf'}
        PDF_EXTS = {'.pdf'}

        detected = {'video': [], 'audio': [], 'image': [], 'doc': [], 'pdf': [], 'other': []}
        for fp in selected:
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

        self._batch_convert_from_detect(detected)
        self.detect_go.configure(text="开始检测", command=self._detect_start)
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

        # 输出目录（卡片内）
        out_frame = tk.Frame(s, bg=D["card"])
        out_frame.grid(row=2, column=0, columnspan=4, sticky="ew", padx=16, pady=(8, 10))
        tk.Label(out_frame, text="输出目录", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 8))
        self.gif_out_dir_combo = ttk.Combobox(out_frame, values=["与源文件同目录", "自定义目录"], state="readonly", width=14)
        self.gif_out_dir_combo.set("与源文件同目录")
        self.gif_out_dir_combo.pack(side=tk.LEFT)
        self.gif_out_dir_btn = self._btn(out_frame, "浏览", lambda: self._select_out_dir("gif"), style="secondary")
        self.gif_out_dir_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.gif_out_dir_path = tk.StringVar(value="")
        self.gif_out_dir_label = tk.Label(out_frame, textvariable=self.gif_out_dir_path, bg=D["card"], fg=D["ink_dis"], font=XS)
        self.gif_out_dir_label.pack(side=tk.LEFT, padx=(8, 0))

        self.gif_pg, self.gif_st, self.gif_go, self.gif_ca, _ = self._bar(p)
        self.gif_go.configure(command=lambda: self._go("gif"))
        self.gif_ca.configure(command=lambda: self._stop("gif"))

    # ── PDF合并拆分 ───────────────────────────
    def _p_pdf(self):
        p = tk.Frame(self.content, bg=D["page"])
        self.panels["pdf"] = p
        self._hdr(p, "PDF 工具", "合并、拆分、加密、解密、压缩")
        self._file_sec(p, "pdf", [("PDF文件","*.pdf"),("所有文件","*.*")])
        s = self._card(p, "操作设置")

        # 模式切换行
        mode_row = tk.Frame(s, bg=D["card"])
        mode_row.pack(fill=tk.X, pady=(0, 12))

        tk.Label(mode_row, text="操作模式", bg=D["card"], fg=D["ink"],
                  font=BODY).pack(side=tk.LEFT, padx=(0, 8))
        self.pdf_mode = ttk.Combobox(mode_row, values=["合并（多个→一个）", "拆分（一个→多个）",
                                                        "加密（设置密码）", "解密（移除密码）", "压缩",
                                                        "添加水印", "添加页码"],
                                      state="readonly", width=22)
        self.pdf_mode.set("合并（多个→一个）")
        self.pdf_mode.pack(side=tk.LEFT)
        self.pdf_mode.bind("<<ComboboxSelected>>", lambda e: self._pdf_mode_changed())

        # 编辑按钮 - 靠右
        edit_btn = tk.Button(mode_row, text="✏️ 编辑器", font=(BODY[0], BODY[1], "bold"),
                             bg=D["accent"], fg=D["ink_inv"], relief="flat",
                             padx=12, pady=3, cursor="hand2",
                             activebackground=D["accent_deep"],
                             command=self._open_pdf_editor)
        edit_btn.pack(side=tk.RIGHT)

        # ── 拆分设置 ──
        self.pdf_range_frame = tk.Frame(s, bg=D["card"])
        tk.Label(self.pdf_range_frame, text="页码范围", bg=D["card"], fg=D["ink"],
                 font=BODY).pack(side=tk.LEFT, padx=(0, 8))
        self.pdf_range = tk.Entry(self.pdf_range_frame, font=BODY,
                                   bg=D["input_bg"], fg=D["ink"],
                                   insertbackground=D["ink"],
                                   relief="flat", highlightthickness=1,
                                   highlightbackground=D["input_bd"],
                                   highlightcolor=D["accent"])
        self.pdf_range.insert(0, "1-3,5,7-10")
        self.pdf_range.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(self.pdf_range_frame, text="示例: 1-3,5,7-10", bg=D["card"],
                 fg=D["ink_dis"], font=XS).pack(side=tk.LEFT, padx=(8, 0))
        self.pdf_range_frame.pack_forget()

        # ── 加密设置 ──
        self.pdf_encrypt_frame = tk.Frame(s, bg=D["card"])

        # 密码行
        pwd_row = tk.Frame(self.pdf_encrypt_frame, bg=D["card"])
        pwd_row.pack(fill=tk.X, pady=(0, 8))

        def make_pwd_field(parent, label, attr_name):
            f = tk.Frame(parent, bg=D["card"])
            f.pack(side=tk.LEFT, padx=(0, 16))
            tk.Label(f, text=label, bg=D["card"], fg=D["ink"], font=BODY).pack(side=tk.LEFT, padx=(0, 4))
            entry = tk.Entry(f, font=BODY, bg=D["input_bg"], fg=D["ink"],
                             insertbackground=D["ink"], relief="flat", highlightthickness=1,
                             highlightbackground=D["input_bd"], highlightcolor=D["accent"],
                             show="•", width=16)
            entry.pack(side=tk.LEFT)
            def toggle_show(e=entry):
                e.configure(show="" if e.cget("show") else "•")
            tk.Button(f, text="👁", font=("Segoe UI Symbol", 10),
                      bg=D["card"], relief="flat", cursor="hand2",
                      activebackground=D["card_alt"], bd=0,
                      command=toggle_show).pack(side=tk.LEFT, padx=(2, 0))
            setattr(self, attr_name, entry)
            return entry

        self.pdf_open_pwd = make_pwd_field(pwd_row, "打开密码", "pdf_open_pwd")
        self.pdf_owner_pwd = make_pwd_field(pwd_row, "权限密码", "pdf_owner_pwd")

        # 加密方式行
        method_row = tk.Frame(self.pdf_encrypt_frame, bg=D["card"])
        method_row.pack(fill=tk.X, pady=(0, 6))
        tk.Label(method_row, text="加密方式", bg=D["card"], fg=D["ink"], font=BODY).pack(side=tk.LEFT)
        self.pdf_encrypt_method = ttk.Combobox(method_row, values=["AES-256", "AES-128"],
                                                 state="readonly", width=10)
        self.pdf_encrypt_method.set("AES-256")
        self.pdf_encrypt_method.pack(side=tk.LEFT, padx=(8, 16))

        tk.Button(method_row, text="📋 密码历史", font=BODY,
                  bg=D["card"], fg=D["accent"], relief="flat", cursor="hand2",
                  activebackground=D["card_alt"],
                  command=self._show_pwd_history).pack(side=tk.LEFT)

        self.pdf_encrypt_frame.pack_forget()

        # ── 解密设置 ──
        self.pdf_decrypt_frame = tk.Frame(s, bg=D["card"])
        tk.Label(self.pdf_decrypt_frame, text="输入密码", bg=D["card"], fg=D["ink"],
                 font=BODY).pack(side=tk.LEFT, padx=(0, 8))
        self.pdf_decrypt_pwd = tk.Entry(self.pdf_decrypt_frame, font=BODY, bg=D["input_bg"], fg=D["ink"],
                                          insertbackground=D["ink"], relief="flat", highlightthickness=1,
                                          highlightbackground=D["input_bd"], highlightcolor=D["accent"],
                                          show="•", width=30)
        self.pdf_decrypt_pwd.pack(side=tk.LEFT)
        def toggle_decrypt_show():
            e = self.pdf_decrypt_pwd
            e.configure(show="" if e.cget("show") else "•")
        tk.Button(self.pdf_decrypt_frame, text="👁", font=("Segoe UI Symbol", 10),
                  bg=D["card"], relief="flat", cursor="hand2",
                  activebackground=D["card_alt"], bd=0,
                  command=toggle_decrypt_show).pack(side=tk.LEFT, padx=(4, 0))
        self.pdf_decrypt_frame.pack_forget()

        # ── 压缩设置 ──
        self.pdf_compress_frame = tk.Frame(s, bg=D["card"])
        compress_row = tk.Frame(self.pdf_compress_frame, bg=D["card"])
        compress_row.pack(fill=tk.X)
        tk.Label(compress_row, text="目标分辨率", bg=D["card"], fg=D["ink"], font=BODY).pack(side=tk.LEFT)
        self.pdf_compress_dpi = ttk.Combobox(compress_row, values=["72dpi", "100dpi", "150dpi", "200dpi"],
                                               state="readonly", width=10)
        self.pdf_compress_dpi.set("150dpi")
        self.pdf_compress_dpi.pack(side=tk.LEFT, padx=(8, 16))
        tk.Label(compress_row, text="图片质量", bg=D["card"], fg=D["ink"], font=BODY).pack(side=tk.LEFT)
        self.pdf_compress_quality = ttk.Combobox(compress_row, values=["60", "70", "80", "90"],
                                                  state="readonly", width=8)
        self.pdf_compress_quality.set("80")
        self.pdf_compress_quality.pack(side=tk.LEFT, padx=(8, 0))
        self.pdf_compress_frame.pack_forget()

        # ── 水印设置 ──
        self.pdf_wm_frame = tk.Frame(s, bg=D["card"])
        wm_row1 = tk.Frame(self.pdf_wm_frame, bg=D["card"])
        wm_row1.pack(fill=tk.X, pady=(0, 6))
        tk.Label(wm_row1, text="水印文字", bg=D["card"], fg=D["ink"], font=BODY).pack(side=tk.LEFT, padx=(0, 6))
        self.pdf_wm_text = tk.Entry(wm_row1, font=BODY, bg=D["input_bg"], fg=D["ink"],
                                     insertbackground=D["ink"], relief="flat", highlightthickness=1,
                                     highlightbackground=D["input_bd"], width=20)
        self.pdf_wm_text.insert(0, "机密")
        self.pdf_wm_text.pack(side=tk.LEFT)

        wm_row2 = tk.Frame(self.pdf_wm_frame, bg=D["card"])
        wm_row2.pack(fill=tk.X, pady=(2, 0))
        tk.Label(wm_row2, text="位置", bg=D["card"], fg=D["ink"], font=BODY).pack(side=tk.LEFT, padx=(0, 6))
        self.pdf_wm_pos = ttk.Combobox(wm_row2, values=["左上角","右上角","左下角","右下角","居中"],
                                        state="readonly", width=8)
        self.pdf_wm_pos.set("居中")
        self.pdf_wm_pos.pack(side=tk.LEFT, padx=(0, 16))
        tk.Label(wm_row2, text="透明度", bg=D["card"], fg=D["ink"], font=BODY).pack(side=tk.LEFT)
        self.pdf_wm_opacity = ttk.Combobox(wm_row2, values=["0.1","0.2","0.3","0.5","0.7","0.9"],
                                            state="readonly", width=6)
        self.pdf_wm_opacity.set("0.3")
        self.pdf_wm_opacity.pack(side=tk.LEFT, padx=(8, 16))
        tk.Label(wm_row2, text="旋转", bg=D["card"], fg=D["ink"], font=BODY).pack(side=tk.LEFT)
        self.pdf_wm_rotate = ttk.Combobox(wm_row2, values=["0°","45°","90°"],
                                           state="readonly", width=6)
        self.pdf_wm_rotate.set("0°")
        self.pdf_wm_rotate.pack(side=tk.LEFT, padx=(8, 0))
        self.pdf_wm_frame.pack_forget()

        # ── 页码设置 ──
        self.pdf_pn_frame = tk.Frame(s, bg=D["card"])
        pn_row = tk.Frame(self.pdf_pn_frame, bg=D["card"])
        pn_row.pack(fill=tk.X)
        tk.Label(pn_row, text="起始页码", bg=D["card"], fg=D["ink"], font=BODY).pack(side=tk.LEFT, padx=(0, 6))
        self.pdf_pn_start = tk.Entry(pn_row, font=BODY, bg=D["input_bg"], fg=D["ink"],
                                      insertbackground=D["ink"], relief="flat", highlightthickness=1,
                                      highlightbackground=D["input_bd"], width=6)
        self.pdf_pn_start.insert(0, "1")
        self.pdf_pn_start.pack(side=tk.LEFT, padx=(0, 16))
        tk.Label(pn_row, text="位置", bg=D["card"], fg=D["ink"], font=BODY).pack(side=tk.LEFT)
        self.pdf_pn_pos = ttk.Combobox(pn_row, values=["底部居中","底部左对齐","底部右对齐","顶部居中"],
                                        state="readonly", width=12)
        self.pdf_pn_pos.set("底部居中")
        self.pdf_pn_pos.pack(side=tk.LEFT, padx=(8, 16))
        tk.Label(pn_row, text="格式", bg=D["card"], fg=D["ink"], font=BODY).pack(side=tk.LEFT)
        self.pdf_pn_fmt = tk.Entry(pn_row, font=BODY, bg=D["input_bg"], fg=D["ink"],
                                    insertbackground=D["ink"], relief="flat", highlightthickness=1,
                                    highlightbackground=D["input_bd"], width=12)
        self.pdf_pn_fmt.insert(0, "第{n}页")
        self.pdf_pn_fmt.pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(pn_row, text="{n}=页码", bg=D["card"], fg=D["ink_dis"], font=XS).pack(side=tk.LEFT, padx=(6, 0))
        self.pdf_pn_frame.pack_forget()

        # ── 输出目录（卡片内） ──
        out_frame = tk.Frame(s, bg=D["card"])
        out_frame.pack(fill=tk.X, padx=16, pady=(8, 10))
        tk.Label(out_frame, text="输出目录", bg=D["card"], fg=D["ink"], font=BODY).pack(side=tk.LEFT, padx=(0, 8))
        self.pdf_out_dir_combo = ttk.Combobox(out_frame, values=["与源文件同目录", "自定义目录"], state="readonly", width=14)
        self.pdf_out_dir_combo.set("与源文件同目录")
        self.pdf_out_dir_combo.pack(side=tk.LEFT)
        self.pdf_out_dir_btn = self._btn(out_frame, "浏览", lambda: self._select_out_dir("pdf"), style="secondary")
        self.pdf_out_dir_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.pdf_out_dir_path = tk.StringVar(value="")
        self.pdf_out_dir_label = tk.Label(out_frame, textvariable=self.pdf_out_dir_path, bg=D["card"], fg=D["ink_dis"], font=XS)
        self.pdf_out_dir_label.pack(side=tk.LEFT, padx=(8, 0))

        self.pdf_pg, self.pdf_st, self.pdf_go, self.pdf_ca, _ = self._bar(p)
        self.pdf_go.configure(command=lambda: self._go("pdf"))
        self.pdf_ca.configure(command=lambda: self._stop("pdf"))

    def _pdf_mode_changed(self):
        self.pdf_range_frame.pack_forget()
        self.pdf_encrypt_frame.pack_forget()
        self.pdf_decrypt_frame.pack_forget()
        self.pdf_compress_frame.pack_forget()
        self.pdf_wm_frame.pack_forget()
        self.pdf_pn_frame.pack_forget()

        mode = self.pdf_mode.get()
        if "拆分" in mode:
            self.pdf_range_frame.pack(fill=tk.X, pady=(8, 0))
        elif "加密" in mode:
            self.pdf_encrypt_frame.pack(fill=tk.X, pady=(8, 0))
        elif "解密" in mode:
            self.pdf_decrypt_frame.pack(fill=tk.X, pady=(8, 0))
        elif "压缩" in mode:
            self.pdf_compress_frame.pack(fill=tk.X, pady=(8, 0))
        elif "水印" in mode:
            self.pdf_wm_frame.pack(fill=tk.X, pady=(8, 0))
        elif "页码" in mode:
            self.pdf_pn_frame.pack(fill=tk.X, pady=(8, 0))

    def _open_pdf_editor(self):
        w = tk.Toplevel(self.root)
        w.title("PDF 可视化编辑")

        # 适配屏幕并居中
        screen_w = w.winfo_screenwidth()
        screen_h = w.winfo_screenheight()
        win_w = int(screen_w * 0.75)
        win_h = int(screen_h * 0.75)
        if win_w < 800: win_w = 800
        if win_h < 560: win_h = 560
        x = (screen_w - win_w) // 2
        y = (screen_h - win_h) // 2
        w.geometry(f"{win_w}x{win_h}+{x}+{y}")
        w.minsize(640, 480)
        w.transient(self.root)
        w.grab_set()
        w.configure(bg=D["page"])
        panel = PdfEditorPanel(w, log_func=lambda msg, level="info": self._log_status(msg, level))
        panel.pack(fill=tk.BOTH, expand=True)
        def on_close():
            if panel.is_modified() and not messagebox.askyesno("未保存", 
                "编辑器中有未保存的修改，确定要关闭吗？"):
                return
            panel.cleanup()
            w.destroy()
        w.protocol("WM_DELETE_WINDOW", on_close)

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

        # 输出目录（卡片内）
        out_frame = tk.Frame(s, bg=D["card"])
        out_frame.grid(row=2, column=0, columnspan=4, sticky="ew", padx=16, pady=(8, 10))
        tk.Label(out_frame, text="输出目录", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 8))
        self.ci_out_dir_combo = ttk.Combobox(out_frame, values=["与源文件同目录", "自定义目录"], state="readonly", width=14)
        self.ci_out_dir_combo.set("与源文件同目录")
        self.ci_out_dir_combo.pack(side=tk.LEFT)
        self.ci_out_dir_btn = self._btn(out_frame, "浏览", lambda: self._select_out_dir("compress_img"), style="secondary")
        self.ci_out_dir_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.ci_out_dir_path = tk.StringVar(value="")
        self.ci_out_dir_label = tk.Label(out_frame, textvariable=self.ci_out_dir_path, bg=D["card"], fg=D["ink_dis"], font=XS)
        self.ci_out_dir_label.pack(side=tk.LEFT, padx=(8, 0))

        self.ci_pg, self.ci_st, self.ci_go, self.ci_ca, _ = self._bar(p)
        self.ci_go.configure(command=lambda: self._go("compress_img"))
        self.ci_ca.configure(command=lambda: self._stop("compress_img"))

    # ── 批量重命名 ────────────────────────────
    def _p_rename(self):
        p = tk.Frame(self.content, bg=D["page"])
        self.panels["rename"] = p
        self._hdr(p, "批量重命名", "统一添加前缀/后缀、序号命名、正则替换等")
        self._file_sec(p, "rename", [("所有文件","*.*")])

        s = self._card(p, "命名规则")
        tk.Label(s, text="占位符：{n}=序号  {name}=原名  {ext}=扩展名  {date}=日期  {time}=时间  {folder}=文件夹",
                 bg=D["card"], fg=D["ink_dis"], font=XS).grid(row=0, column=0, columnspan=3,
                                                              sticky="w", pady=(0, 8))
        self.rn_pattern = self._row(s, "命名模板", [], "文件_{n:03d}", 22)
        self.rn_pattern.configure(values=[
            "文件_{n:03d}",
            "{name}_压缩",
            "{name}_{date}",
            "{name}_{time}",
            "{folder}_{name}",
            "{name}_new",
            "IMG_{n:04d}",
            "{date}_{name}",
        ])
        self.rn_start = self._row(s, "起始序号", ["1","0","100"], "1")

        # Search & Replace
        opt_card = tk.Frame(s, bg=D["card"])
        opt_card.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        s.columnconfigure(0, weight=1)

        tk.Label(opt_card, text="查找替换", bg=D["card"], fg=D["ink_sec"],
                 font=(FT, 9, "bold")).pack(anchor=tk.W, padx=5, pady=(4, 4))

        sr_row = tk.Frame(opt_card, bg=D["card"])
        sr_row.pack(fill=tk.X, padx=5)
        tk.Label(sr_row, text="查找", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 4))
        self.rn_search = tk.Entry(sr_row, font=BODY, bg=D["input_bg"], fg=D["ink"],
                                  relief="flat", highlightthickness=1,
                                  highlightbackground=D["input_bd"], width=14)
        self.rn_search.pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(sr_row, text="替换为", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 4))
        self.rn_replace = tk.Entry(sr_row, font=BODY, bg=D["input_bg"], fg=D["ink"],
                                   relief="flat", highlightthickness=1,
                                   highlightbackground=D["input_bd"], width=14)
        self.rn_replace.pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(sr_row, text="大小写", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(8, 4))
        self.rn_case = ttk.Combobox(sr_row, values=["不转换", "全大写", "全小写", "首字母大写"],
                                    state="readonly", width=10)
        self.rn_case.set("不转换")
        self.rn_case.pack(side=tk.LEFT)

        # 高级替换（正则）
        tk.Frame(opt_card, bg=D["border"], height=1).pack(fill=tk.X, padx=5, pady=(8, 6))
        tk.Label(opt_card, text="高级替换（正则）", bg=D["card"], fg=D["ink_sec"],
                 font=(FT, 9, "bold")).pack(anchor=tk.W, padx=5, pady=(0, 4))

        adv_row = tk.Frame(opt_card, bg=D["card"])
        adv_row.pack(fill=tk.X, padx=5)
        tk.Label(adv_row, text="查找内容", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT)
        self.rn_regex = tk.Entry(adv_row, font=("Consolas", 10), bg=D["input_bg"], fg=D["ink"],
                                 relief="flat", highlightthickness=1,
                                 highlightbackground=D["input_bd"], width=14)
        self.rn_regex.pack(side=tk.LEFT, padx=(4, 8))

        tk.Label(adv_row, text="替换为", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT)
        self.rn_regex_replace = tk.Entry(adv_row, font=("Consolas", 10), bg=D["input_bg"], fg=D["ink"],
                                         relief="flat", highlightthickness=1,
                                         highlightbackground=D["input_bd"], width=14)
        self.rn_regex_replace.pack(side=tk.LEFT, padx=(4, 8))

        # 输出目录（卡片内）
        out_frame = tk.Frame(s, bg=D["card"])
        out_frame.grid(row=3, column=0, columnspan=3, sticky="ew", padx=16, pady=(8, 10))
        tk.Label(out_frame, text="输出目录", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 8))
        self.rn_out_dir_combo = ttk.Combobox(out_frame, values=["与源文件同目录", "自定义目录"], state="readonly", width=14)
        self.rn_out_dir_combo.set("与源文件同目录")
        self.rn_out_dir_combo.pack(side=tk.LEFT)
        self.rn_out_dir_btn = self._btn(out_frame, "浏览", lambda: self._select_out_dir("rename"), style="secondary")
        self.rn_out_dir_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.rn_out_dir_path = tk.StringVar(value="")
        self.rn_out_dir_label = tk.Label(out_frame, textvariable=self.rn_out_dir_path, bg=D["card"], fg=D["ink_dis"], font=XS)
        self.rn_out_dir_label.pack(side=tk.LEFT, padx=(8, 0))

        self.rn_pg, self.rn_st, self.rn_go, self.rn_ca, _ = self._bar(p)
        self.rn_go.configure(text="开始重命名", command=self._rn_start)
        self.rn_ca.configure(command=lambda: self._stop("rename"))

    def _rn_calc_name(self, fp, name, ext, idx):
        pattern = self.rn_pattern.get()
        start = int(self.rn_start.get()) if self.rn_start.get().isdigit() else 1
        search = self.rn_search.get() if hasattr(self, 'rn_search') else ""
        replace = self.rn_replace.get() if hasattr(self, 'rn_replace') else ""
        case_map = {"不转换": "none", "全大写": "upper", "全小写": "lower", "首字母大写": "title"}
        case = case_map.get(self.rn_case.get() if hasattr(self, 'rn_case') else "不转换", "none")
        regex_pat = self.rn_regex.get() if hasattr(self, 'rn_regex') else ""
        regex_rep = self.rn_regex_replace.get() if hasattr(self, 'rn_regex_replace') else ""

        date_str = ""
        time_str = ""
        try:
            mtime = os.path.getmtime(fp)
            date_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y%m%d")
            time_str = datetime.datetime.fromtimestamp(mtime).strftime("%H%M%S")
        except Exception:
            date_str = "00000000"
            time_str = "000000"
        folder_str = os.path.basename(os.path.dirname(fp))

        n = start + idx
        new_name = pattern.replace("{name}", name).replace("{ext}", ext)
        new_name = new_name.replace("{date}", date_str).replace("{time}", time_str).replace("{folder}", folder_str)
        def _fmt_n(m):
            # 捕获组形如 ":04d"，format() 需要不含前导冒号的 format_spec（"04d"）
            spec = m.group(1)[1:] if m.group(1) else ""
            return format(n, spec) if spec else str(n)
        new_name = re.sub(r'\{n(:.*?)?\}', _fmt_n, new_name)
        new_name = new_name + ext if not new_name.endswith(ext) else new_name

        if search:
            new_name = new_name.replace(search, replace)

        if regex_pat:
            try:
                new_name = re.sub(regex_pat, regex_rep, new_name)
            except re.error:
                pass

        if case == "upper":
            new_name = new_name.upper()
        elif case == "lower":
            new_name = new_name.lower()
        elif case == "title":
            new_name = new_name.title()

        return new_name

    def _rn_start(self):
        files = self.panel_data.get("rename", {}).get("files", [])
        if not files:
            self._log_status("没有待重命名的文件", "warn")
            return

        fp0 = files[0]
        name0 = os.path.splitext(os.path.basename(fp0))[0]
        ext0 = os.path.splitext(fp0)[1]
        new_name0 = self._rn_calc_name(fp0, name0, ext0, 0)
        total = len(files)
        msg = f"即将对 {total} 个文件进行重命名。示例：{os.path.basename(fp0)} -> {new_name0}。是否确认开始？"
        if not messagebox.askyesno("确认重命名", msg):
            return
        self._rn_file_count = total
        self._go("rename")

    # ══════════════════════════════════════════
    #  视频下载
    # ══════════════════════════════════════════
    def _p_download(self):
        p = tk.Frame(self.content, bg=D["page"])
        self.panels["download"] = p
        self._hdr(p, "视频下载", "支持 B站 / YouTube / 微博 / Instagram 等数百个平台", badge="需联网")
        self.dl_queue = []
        from core.video_downloader import VideoDownloader
        self.dl_obj = VideoDownloader()

        # URL 输入
        url_frame = tk.Frame(p, bg=D["page"])
        url_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(url_frame, text="URL", bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 8))
        self.dl_url = tk.Text(url_frame, font=BODY, bg=D["input_bg"], fg=D["ink"],
                               relief="solid", bd=1, highlightthickness=0, height=3)
        self.dl_url.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2)
        self.dl_url.bind("<Control-v>", lambda e: self.root.after(100, self._dl_parse_url))
        self.dl_fmt_info = tk.StringVar(value="")
        tk.Label(url_frame, textvariable=self.dl_fmt_info, bg=D["page"], fg=D["ink_dis"], font=XS).pack(side=tk.LEFT, padx=(8, 0))
        url_btn_frame = tk.Frame(p, bg=D["page"])
        url_btn_frame.pack(fill=tk.X, pady=(0, 6))
        self._btn(url_btn_frame, "解析格式", self._dl_parse_url, padx=12).pack(side=tk.LEFT)
        self._btn(url_btn_frame, "添加链接", self._dl_add_url, "primary", padx=12).pack(side=tk.LEFT, padx=(8, 0))
        self._btn(url_btn_frame, "📁 批量导入", self._dl_batch_import, padx=8).pack(side=tk.LEFT, padx=(8, 0))
        self._btn(url_btn_frame, "⭐ 收藏", self._dl_add_favorite, padx=8).pack(side=tk.RIGHT, padx=(0, 0))
        self._btn(url_btn_frame, "📋 历史", self._dl_show_history, padx=8).pack(side=tk.RIGHT, padx=(8, 0))
        self._btn(url_btn_frame, "⭐ 收藏夹", self._dl_show_favorites, padx=8).pack(side=tk.RIGHT, padx=(8, 0))

        # 格式 + 画质
        fmt_frame = tk.Frame(p, bg=D["page"])
        fmt_frame.pack(fill=tk.X, pady=(0, 6))
        tk.Label(fmt_frame, text="选择格式", bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 8))
        self.dl_formats_list = tk.Listbox(fmt_frame, height=5, font=BODY, bg=D["input_bg"],
                                           relief="solid", bd=1, highlightthickness=0)
        self.dl_formats_list.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2)
        self.dl_formats = []

        # 设置区域
        settings_frame = tk.Frame(p, bg=D["page"])
        settings_frame.pack(fill=tk.X, pady=(0, 6))

        # 第一行：Cookie | 代理
        row1 = tk.Frame(settings_frame, bg=D["page"])
        row1.pack(fill=tk.X, pady=(0, 4))
        tk.Label(row1, text="Cookie", bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 4))
        self.dl_cookie = tk.Entry(row1, font=BODY, bg=D["input_bg"], fg=D["ink"],
                                   relief="solid", bd=1, highlightthickness=0, width=25)
        self.dl_cookie.pack(side=tk.LEFT, ipady=2)
        tk.Label(row1, text="代理", bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(12, 4))
        self.dl_proxy = tk.Entry(row1, font=BODY, bg=D["input_bg"], fg=D["ink"],
                                  relief="solid", bd=1, highlightthickness=0, width=18)
        self.dl_proxy.pack(side=tk.LEFT, ipady=2)
        tk.Label(row1, text="限速 MB/s", bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(12, 4))
        self.dl_speed = ttk.Combobox(row1, values=["不限","2","5","10","20","50"], state="readonly", width=6)
        self.dl_speed.set("不限")
        self.dl_speed.pack(side=tk.LEFT)

        # 第二行：Header | 文件名模板
        row2 = tk.Frame(settings_frame, bg=D["page"])
        row2.pack(fill=tk.X, pady=(0, 4))
        tk.Label(row2, text="Header", bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 4))
        self.dl_headers = tk.Entry(row2, font=BODY, bg=D["input_bg"], fg=D["ink"],
                                    relief="solid", bd=1, highlightthickness=0)
        self.dl_headers.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2)
        tk.Label(row2, text="Key:Val,Key:Val", bg=D["page"], fg=D["ink_dis"], font=XS).pack(side=tk.LEFT, padx=(4, 0))

        # 第三行：选项
        row3 = tk.Frame(settings_frame, bg=D["page"])
        row3.pack(fill=tk.X)
        self.dl_audio_only = tk.BooleanVar(value=False)
        tk.Checkbutton(row3, text="仅音频", variable=self.dl_audio_only, bg=D["page"], fg=D["ink"], font=SM,
                       command=self._dl_toggle_audio).pack(side=tk.LEFT)
        self.dl_audio_fmt = ttk.Combobox(row3, values=["mp3","m4a","flac","wav","opus"], state="readonly", width=6)
        self.dl_audio_fmt.set("mp3")
        self.dl_audio_fmt.pack(side=tk.LEFT, padx=(4, 12))
        self.dl_subtitles = tk.BooleanVar(value=False)
        tk.Checkbutton(row3, text="下载字幕", variable=self.dl_subtitles, bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.LEFT)
        tk.Label(row3, text="文件名模板", bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(16, 4))
        self.dl_template = tk.Entry(row3, font=BODY, bg=D["input_bg"], fg=D["ink"],
                                     relief="solid", bd=1, highlightthickness=0, width=24)
        self.dl_template.pack(side=tk.LEFT, ipady=2)
        tk.Label(row3, text="留空=默认", bg=D["page"], fg=D["ink_dis"], font=XS).pack(side=tk.LEFT, padx=(4, 0))

        # 保存目录
        out_frame = tk.Frame(p, bg=D["page"])
        out_frame.pack(fill=tk.X, pady=(4, 0))
        tk.Label(out_frame, text="保存到", bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 8))
        self.dl_dir = tk.StringVar(value=os.path.expanduser("~/Downloads"))
        tk.Label(out_frame, textvariable=self.dl_dir, bg=D["page"], fg=D["ink_dis"], font=XS).pack(side=tk.LEFT, padx=(0, 8))
        self._btn(out_frame, "浏览", lambda: self._select_dl_dir(), "secondary").pack(side=tk.LEFT)

        # 下载队列
        q_card = tk.Frame(p, bg=D["border"], padx=1, pady=1)
        q_card.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        q_inner = tk.Frame(q_card, bg=D["card"])
        q_inner.pack(fill=tk.BOTH, expand=True)
        q_hdr = tk.Frame(q_inner, bg=D["card"])
        q_hdr.pack(fill=tk.X, padx=10, pady=(6, 2))
        tk.Label(q_hdr, text="下载队列", bg=D["card"], fg=D["ink"], font=(FT, 9, "bold")).pack(side=tk.LEFT)
        self.dl_count_label = tk.Label(q_hdr, text="0 个任务", bg=D["card"], fg=D["ink_dis"], font=XS)
        self.dl_count_label.pack(side=tk.RIGHT)
        q_list = tk.Frame(q_inner, bg=D["card"])
        q_list.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 4))
        self.dl_queue_listbox = tk.Listbox(q_list, font=(FT, 10), bg=D["card"], fg=D["ink"],
                                            selectbackground=D["select_bg"], selectforeground=D["select_fg"],
                                            bd=0, highlightthickness=0, activestyle="none", height=4)
        q_scroll = ttk.Scrollbar(q_list, orient=tk.VERTICAL, command=self.dl_queue_listbox.yview)
        self.dl_queue_listbox.configure(yscrollcommand=q_scroll.set)
        self.dl_queue_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        q_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        q_btns = tk.Frame(q_inner, bg=D["card"])
        q_btns.pack(fill=tk.X, padx=10, pady=(0, 6))
        self._btn(q_btns, "▲ 上移", self._dl_move_up, "ghost", padx=6).pack(side=tk.LEFT)
        self._btn(q_btns, "▼ 下移", self._dl_move_down, "ghost", padx=6).pack(side=tk.LEFT, padx=(4, 0))
        self._btn(q_btns, "✕ 移除选中", self._dl_remove_selected, "ghost", padx=8).pack(side=tk.LEFT, padx=(12, 0))
        self._btn(q_btns, "清空队列", self._dl_clear_queue, "ghost", padx=8).pack(side=tk.LEFT, padx=(8, 0))

        # 操作栏
        self.dl_pg, self.dl_st, self.dl_go, self.dl_ca, _ = self._bar(p)
        self.dl_go.configure(text="开始下载", command=self._go_download)
        self.dl_ca.configure(command=self._dl_cancel)

    def _select_dl_dir(self):
        last_dir = self._get_last_dir("download")
        d = filedialog.askdirectory(title="选择下载目录", initialdir=last_dir)
        if d:
            self._save_last_dir("download", d)
            self.dl_dir.set(d)

    def _dl_toggle_audio(self):
        if self.dl_audio_only.get():
            self.dl_audio_fmt.configure(state="readonly")
        else:
            self.dl_audio_fmt.configure(state="disabled")

    def _dl_parse_url(self):
        raw = self.dl_url.get("1.0", tk.END).strip()
        url = self._clean_url(raw)
        if not url:
            messagebox.showinfo("提示", "未检测到有效URL"); return
        self.dl_url.delete("1.0", tk.END); self.dl_url.insert("1.0", url)
        if "douyin" in url.lower() or "tiktok" in url.lower():
            self._log_status("抖音/TikTok 受平台限制无法直接下载", "warn")
        self.dl_go.configure(state=tk.DISABLED, text="获取中...")
        self.dl_st.configure(text="正在获取格式信息...")
        self.dl_formats_list.delete(0, tk.END)
        from core.video_downloader import VideoDownloader
        def work():
            try:
                dl = VideoDownloader()
                cookie = self.dl_cookie.get().strip() or None
                proxy = self.dl_proxy.get().strip() or None
                dl._last_error = ""
                fmts, title, _ = dl.get_formats(url)
                # 检查是否为播放列表
                playlist = None
                try:
                    pl = dl.get_playlist_info(url)
                    if pl and pl.get("count", 0) > 1:
                        playlist = pl
                except Exception:
                    pass
                self.root.after(0, lambda: self._dl_show_formats(fmts, title, playlist))
            except Exception as e:
                self.root.after(0, lambda e=e: self._dl_parse_fail(str(e)))
        threading.Thread(target=work, daemon=True).start()

    def _dl_parse_fail(self, err):
        self.dl_st.configure(text=f"获取失败：{err}")
        self.dl_go.configure(state=tk.NORMAL, text="开始下载")

    def _dl_show_formats(self, fmts, title, playlist=None):
        self.dl_formats = fmts
        self.dl_formats_list.delete(0, tk.END)
        for f in fmts:
            sz = f"{f['filesize']/1024/1024:.0f}MB" if f['filesize'] else "?"
            label = f"[{f['format_id']}] {f['ext']}  {f['resolution']}  {sz}"
            self.dl_formats_list.insert(tk.END, label)
        self._dl_title = title
        info = f"已识别：{title[:60]}"
        if playlist:
            info += f"  |  播放列表: {playlist['title']} ({playlist['count']}个视频)"
        self.dl_st.configure(text=info)
        self.dl_go.configure(state=tk.NORMAL, text="开始下载")

    def _dl_add_url(self):
        raw = self.dl_url.get("1.0", tk.END).strip()
        urls = [self._clean_url(u) for u in raw.split("\n") if self._clean_url(u)]
        if not urls:
            messagebox.showwarning("提示", "请输入有效URL"); return
        for url in urls:
            if any(q["url"] == url for q in self.dl_queue):
                continue
            name = "video"
            if hasattr(self, '_dl_title'):
                name = self._dl_title
            self.dl_queue.append({"url": url, "name": name, "status": "等待", "fmt_id": None})
            display = f"  {name[:30]}  —  {url[:50]}"
            self.dl_queue_listbox.insert(tk.END, display)
        self.dl_count_label.configure(text=f"{len(self.dl_queue)} 个任务")
        self.dl_url.delete("1.0", tk.END)
        if len(urls) == 1:
            self._log_status(f"已添加 1 个链接到队列", "info")
        else:
            self._log_status(f"已添加 {len(urls)} 个链接到队列", "info")

    def _dl_batch_import(self):
        path = filedialog.askopenfilename(title="选择链接文件",
            filetypes=[("文本文件","*.txt"),("所有文件","*.*")])
        if not path: return
        try:
            with open(path, "r", encoding="utf-8") as f: lines = f.readlines()
        except:
            with open(path, "r", encoding="gbk") as f: lines = f.readlines()
        added = 0
        for line in lines:
            url = self._clean_url(line)
            if not url: continue
            if any(q["url"] == url for q in self.dl_queue): continue
            self.dl_queue.append({"url": url, "name": "批量导入", "status": "等待", "fmt_id": None})
            self.dl_queue_listbox.insert(tk.END, f"  {url[:60]}")
            added += 1
        self.dl_count_label.configure(text=f"{len(self.dl_queue)} 个任务")
        if added: messagebox.showinfo("导入完成", f"成功导入 {added} 个链接")
        else: messagebox.showwarning("提示", "未找到有效链接")

    def _dl_remove_selected(self):
        sel = self.dl_queue_listbox.curselection()
        if not sel: return
        for i in reversed(sel):
            self.dl_queue_listbox.delete(i)
            self.dl_queue.pop(i)
        self.dl_count_label.configure(text=f"{len(self.dl_queue)} 个任务")

    def _dl_move_up(self):
        sel = self.dl_queue_listbox.curselection()
        if not sel or sel[0] == 0: return
        i = sel[0]
        self.dl_queue[i], self.dl_queue[i-1] = self.dl_queue[i-1], self.dl_queue[i]
        a = self.dl_queue_listbox.get(i); b = self.dl_queue_listbox.get(i-1)
        self.dl_queue_listbox.delete(i-1, i)
        self.dl_queue_listbox.insert(i-1, a); self.dl_queue_listbox.insert(i, b)
        self.dl_queue_listbox.selection_set(i-1)

    def _dl_move_down(self):
        sel = self.dl_queue_listbox.curselection()
        if not sel or sel[0] >= self.dl_queue_listbox.size()-1: return
        i = sel[0]
        self.dl_queue[i], self.dl_queue[i+1] = self.dl_queue[i+1], self.dl_queue[i]
        a = self.dl_queue_listbox.get(i); b = self.dl_queue_listbox.get(i+1)
        self.dl_queue_listbox.delete(i, i+1)
        self.dl_queue_listbox.insert(i, b); self.dl_queue_listbox.insert(i+1, a)
        self.dl_queue_listbox.selection_set(i+1)

    def _dl_clear_queue(self):
        self.dl_queue_listbox.delete(0, tk.END)
        self.dl_queue.clear()
        self.dl_count_label.configure(text="0 个任务")

    def _dl_add_favorite(self):
        url = self._clean_url(self.dl_url.get("1.0", tk.END).strip())
        if not url: return
        name = getattr(self, '_dl_title', "未命名")
        win = tk.Toplevel(self.root)
        win.title("收藏链接"); win.configure(bg=D["page"]); win.minsize(400, 180)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = min(int(sw*0.4),500), min(int(sh*0.25),220)
        win.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        win.transient(self.root); win.grab_set()
        tk.Label(win, text="添加备注（可选）", bg=D["page"], fg=D["ink"], font=H2).pack(anchor=tk.W, padx=20, pady=(16,8))
        nf = tk.Frame(win, bg=D["page"]); nf.pack(fill=tk.X, padx=20, pady=(0,8))
        tk.Label(nf, text="名称", bg=D["page"], fg=D["ink"], font=SM, width=6, anchor="w").pack(side=tk.LEFT)
        ne = tk.Entry(nf, font=BODY, bg=D["input_bg"], fg=D["ink"], relief="solid", bd=1, highlightthickness=0)
        ne.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3); ne.insert(0, name)
        ntf = tk.Frame(win, bg=D["page"]); ntf.pack(fill=tk.X, padx=20, pady=(0,12))
        tk.Label(ntf, text="备注", bg=D["page"], fg=D["ink"], font=SM, width=6, anchor="w").pack(side=tk.LEFT)
        nte = tk.Entry(ntf, font=BODY, bg=D["input_bg"], fg=D["ink"], relief="solid", bd=1, highlightthickness=0)
        nte.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)
        def do_save():
            from core.m3u8_downloader import M3U8Store
            M3U8Store().add_favorite(url, name=ne.get().strip(), note=nte.get().strip())
            win.destroy(); messagebox.showinfo("收藏成功", f"已收藏: {ne.get().strip()}")
        bf = tk.Frame(win, bg=D["page"]); bf.pack(fill=tk.X, padx=20, pady=(0,12))
        self._btn(bf, "保存", do_save, "primary", padx=16).pack(side=tk.LEFT)
        self._btn(bf, "取消", win.destroy, padx=16).pack(side=tk.LEFT, padx=(8,0))

    def _dl_show_favorites(self):
        from core.m3u8_downloader import M3U8Store
        favs = M3U8Store().get_favorites()
        self._show_dl_fav_hist_win("收藏链接", favs, lambda: M3U8Store().get_favorites(),
                                   lambda url, name: self.dl_queue.append({"url":url, "name":name, "status":"等待", "fmt_id":None}) or self.dl_queue_listbox.insert(tk.END, f"  {name[:30]}  —  {url[:50]}") or self.dl_count_label.configure(text=f"{len(self.dl_queue)} 个任务"))

    def _dl_show_history(self):
        from core.m3u8_downloader import M3U8Store
        history = M3U8Store().get_history()
        self._show_dl_fav_hist_win("下载历史", history, lambda: M3U8Store().get_history(),
                                   lambda url, name: setattr(self, '_dl_title', name) or self.dl_url.delete("1.0", tk.END) or self.dl_url.insert("1.0", url))

    def _show_dl_fav_hist_win(self, title, items, refresh_fn, use_fn):
        win = tk.Toplevel(self.root)
        win.title(title); win.configure(bg=D["page"]); win.minsize(600, 400)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = min(int(sw*0.55),850), min(int(sh*0.6),550)
        win.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        win.transient(self.root); win.grab_set()
        tk.Label(win, text=title, bg=D["page"], fg=D["ink"], font=H2).pack(anchor=tk.W, padx=16, pady=(16,8))
        lf = tk.Frame(win, bg=D["card"]); lf.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0,8))
        lb = tk.Listbox(lf, font=(FT,10), bg=D["card"], fg=D["ink"],
                        selectbackground=D["select_bg"], selectforeground=D["select_fg"],
                        bd=0, highlightthickness=0, activestyle="none")
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scr = ttk.Scrollbar(lf, orient=tk.VERTICAL, command=lb.yview)
        lb.configure(yscrollcommand=scr.set); scr.pack(side=tk.RIGHT, fill=tk.Y)
        def refresh():
            items = refresh_fn()
            lb.delete(0, tk.END)
            for item in items:
                nm = item.get("name","?")
                sz = f"{item.get('size',0)/1024/1024:.0f}MB" if item.get("size",0) else ""
                tm = item.get("time","")
                lb.insert(tk.END, f"  {nm}  {sz}  {tm}")
        refresh()
        def use_sel():
            sel = lb.curselection()
            if not sel: return
            items = refresh_fn()
            item = items[sel[0]]
            use_fn(item.get("url",""), item.get("name",""))
            win.destroy()
        bf = tk.Frame(win, bg=D["page"]); bf.pack(fill=tk.X, padx=16, pady=(0,12))
        self._btn(bf, "使用", use_sel, "primary", padx=12).pack(side=tk.LEFT)
        self._btn(bf, "关闭", win.destroy, padx=12).pack(side=tk.RIGHT)

    def _clean_url(self, raw):
        raw = raw.strip()
        m = re.search(r"https?://[^\s\u4e00-\u9fff\u3000-\u303f\uff00-\uffef<>\"']+", raw)
        if m:
            return m.group(0).rstrip(".,;:!?)")
        return re.sub(r"[^\x00-\x7f]", "", raw).strip()

    def _go_download(self):
        if not self.dl_queue:
            messagebox.showwarning("提示", "请先添加下载链接"); return
        out_dir = self.dl_dir.get()
        os.makedirs(out_dir, exist_ok=True); self.last_output_dir = out_dir
        self.dl_go.configure(state=tk.DISABLED)
        self.dl_ca.configure(state=tk.NORMAL)
        self.dl_pg["value"] = 0
        self.converting = True; self._disable_all_panels(); self._clear_task_list()
        cookie = self.dl_cookie.get().strip() or None
        proxy = self.dl_proxy.get().strip() or None
        speed_str = self.dl_speed.get()
        speed_limit = 0 if speed_str == "不限" else int(speed_str)
        audio_only = self.dl_audio_only.get()
        audio_fmt = self.dl_audio_fmt.get()
        subtitles = self.dl_subtitles.get()
        tmpl = self.dl_template.get().strip() or None
        custom_headers = {}
        hdr_str = self.dl_headers.get().strip()
        if hdr_str:
            for pair in hdr_str.split(","):
                if ":" in pair:
                    k, v = pair.split(":", 1)
                    custom_headers[k.strip()] = v.strip()
        for item in self.dl_queue:
            url = item["url"]
            name = item["name"]
            ext = audio_fmt if audio_only else "mp4"
            output_path = os.path.join(out_dir, f"{name}.{ext}")
            if os.path.exists(output_path):
                base, ext2 = os.path.splitext(output_path); c = 1
                while os.path.exists(f"{base}_{c}{ext2}"): c += 1
                output_path = f"{base}_{c}{ext2}"
            self._add_task(f"下载 - {name}", "download", {
                "file_path": "", "output_path": output_path, "files": [],
                "task_type": "download", "panel_name": "download",
                "params": {"url": url, "cookie": cookie, "headers": custom_headers,
                           "proxy": proxy, "speed_limit": speed_limit,
                           "audio_only": audio_only, "audio_format": audio_fmt,
                           "subtitles": subtitles, "output_template": tmpl}
            })
        self._log_status(f"共添加 {len(self.dl_queue)} 个下载任务", "success")

    def _dl_cancel(self):
        if hasattr(self, 'dl_obj'):
            self.dl_obj.cancel()

    # ══════════════════════════════════════════
    #  预设裁剪
    # ══════════════════════════════════════════
    def _p_crop(self):
        p = tk.Frame(self.content, bg=D["page"])
        self.panels["crop"] = p
        self._hdr(p, "图像预设裁剪", "按社交媒体尺寸批量裁剪图片")
        self._file_sec(p, "crop", [("图片文件","*.jpg *.jpeg *.png *.bmp *.webp"),("所有文件","*.*")])
        s = self._card(p, "裁剪设置")
        tk.Label(s, text="预设尺寸", bg=D["card"], fg=D["ink"], font=SM).grid(row=0, column=0, sticky="w")
        self.crp_preset = ttk.Combobox(s, values=list(CROP_PRESETS.keys()), state="readonly", width=28)
        self.crp_preset.set("1:1 正方形 (1080×1080)")
        self.crp_preset.grid(row=0, column=1, sticky="w", padx=(8, 0))
        tk.Label(s, text="裁剪模式", bg=D["card"], fg=D["ink"], font=SM).grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.crp_mode = ttk.Combobox(s, values=["cover（裁剪填充）","fit（等比适应）"], state="readonly", width=20)
        self.crp_mode.set("cover（裁剪填充）")
        self.crp_mode.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(8, 0))

        # 输出目录（卡片内）
        out_frame = tk.Frame(s, bg=D["card"])
        out_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(8, 10))
        tk.Label(out_frame, text="输出目录", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 8))
        self.crp_out_dir_combo = ttk.Combobox(out_frame, values=["与源文件同目录", "自定义目录"], state="readonly", width=14)
        self.crp_out_dir_combo.set("与源文件同目录")
        self.crp_out_dir_combo.pack(side=tk.LEFT)
        self.crp_out_dir_btn = self._btn(out_frame, "浏览", lambda: self._select_out_dir("crop"), style="secondary")
        self.crp_out_dir_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.crp_out_dir_path = tk.StringVar(value="")
        self.crp_out_dir_label = tk.Label(out_frame, textvariable=self.crp_out_dir_path, bg=D["card"], fg=D["ink_dis"], font=XS)
        self.crp_out_dir_label.pack(side=tk.LEFT, padx=(8, 0))

        self.crp_pg, self.crp_st, self.crp_go, self.crp_ca, _ = self._bar(p)
        self.crp_go.configure(command=lambda: self._go("crop"))
        self.crp_ca.configure(command=lambda: self._stop("crop"), state=tk.DISABLED)

    # ══════════════════════════════════════════
    #  M3U8 下载
    # ══════════════════════════════════════════
    def _p_m3u8(self):
        p = tk.Frame(self.content, bg=D["page"])
        self.panels["m3u8"] = p
        self._hdr(p, "M3U8 视频下载", "添加多个链接，支持画质选择，批量队列下载", badge="需联网")
        self.m3u8_queue = []
        self.m3u8_qualities = []

        # URL 输入
        url_frame = tk.Frame(p, bg=D["page"])
        url_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(url_frame, text="M3U8链接", bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 8))
        self.m3u8_url = tk.Text(url_frame, font=BODY, bg=D["input_bg"], fg=D["ink"],
                                relief="solid", bd=1, highlightthickness=0, height=3)
        self.m3u8_url.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2)
        self.m3u8_url.bind("<Control-v>", lambda e: self.root.after(100, lambda: self._m3u8_batch_add()))
        self._btn(url_frame, "解析画质", self._m3u8_parse_url, padx=12).pack(side=tk.RIGHT, padx=(8, 0))
        self._btn(url_frame, "⭐ 收藏", self._m3u8_add_to_favorites, "secondary", padx=8).pack(side=tk.RIGHT, padx=(4, 0))
        self._btn(url_frame, "批量添加", self._m3u8_batch_add, "primary", padx=12).pack(side=tk.RIGHT, padx=(8, 0))
        tk.Label(url_frame, text="每行一个链接，支持批量粘贴", bg=D["page"], fg=D["ink_dis"], font=XS).pack(side=tk.BOTTOM, anchor=tk.W, pady=(2, 0))

        # 画质选择
        quality_frame = tk.Frame(p, bg=D["page"])
        quality_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(quality_frame, text="画质", bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 8))
        self.m3u8_quality = ttk.Combobox(quality_frame, values=[""], state="readonly", width=30)
        self.m3u8_quality.set("")
        self.m3u8_quality.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.m3u8_quality.bind("<<ComboboxSelected>>", self._m3u8_quality_changed)
        self.m3u8_quality_hint = tk.Label(quality_frame, text="点击「解析画质」获取可选项", bg=D["page"], fg=D["ink_dis"], font=XS)
        self.m3u8_quality_hint.pack(side=tk.LEFT, padx=(8, 0))

        # 文件名
        name_frame = tk.Frame(p, bg=D["page"])
        name_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(name_frame, text="文件名", bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 8))
        self.m3u8_name = tk.Entry(name_frame, font=BODY, bg=D["input_bg"], fg=D["ink"], relief="solid", bd=1, highlightthickness=0)
        self.m3u8_name.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        tk.Label(name_frame, text="留空=自动命名", bg=D["page"], fg=D["ink_dis"], font=XS).pack(side=tk.LEFT, padx=(8, 0))

        # 保存目录
        out_dir_frame = tk.Frame(p, bg=D["page"])
        out_dir_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(out_dir_frame, text="保存到", bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 8))
        self.m3u8_out_dir = tk.StringVar(value=os.path.expanduser("~/Downloads"))
        tk.Label(out_dir_frame, textvariable=self.m3u8_out_dir, bg=D["page"], fg=D["ink_dis"], font=XS).pack(side=tk.LEFT, padx=(0, 8))
        self._btn(out_dir_frame, "浏览", self._select_m3u8_dir, "secondary").pack(side=tk.LEFT)

        # 线程数 + 输出格式 + 限速
        settings_frame = tk.Frame(p, bg=D["page"])
        settings_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(settings_frame, text="并发线程", bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 4))
        self.m3u8_threads = ttk.Combobox(settings_frame, values=["4","8","16","24","32","48","64"], state="readonly", width=6)
        self.m3u8_threads.set("16")
        self.m3u8_threads.pack(side=tk.LEFT)
        tk.Label(settings_frame, text="输出格式", bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(12, 4))
        self.m3u8_format = ttk.Combobox(settings_frame, values=["mp4","mkv","avi","mov","ts"], state="readonly", width=6)
        self.m3u8_format.set("mp4")
        self.m3u8_format.pack(side=tk.LEFT)
        tk.Label(settings_frame, text="限速(MB/s)", bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(12, 4))
        self.m3u8_speed = ttk.Combobox(settings_frame, values=["不限","2","5","10","20","50"], state="readonly", width=6)
        self.m3u8_speed.set("不限")
        self.m3u8_speed.pack(side=tk.LEFT)

        # Cookie/Header/Proxy
        adv_frame = tk.Frame(p, bg=D["page"])
        adv_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(adv_frame, text="Cookie", bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 4))
        self.m3u8_cookie = tk.Entry(adv_frame, font=BODY, bg=D["input_bg"], fg=D["ink"], relief="solid", bd=1, highlightthickness=0, width=25)
        self.m3u8_cookie.pack(side=tk.LEFT, ipady=2)
        tk.Label(adv_frame, text="代理", bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(12, 4))
        self.m3u8_proxy = tk.Entry(adv_frame, font=BODY, bg=D["input_bg"], fg=D["ink"], relief="solid", bd=1, highlightthickness=0, width=18)
        self.m3u8_proxy.pack(side=tk.LEFT, ipady=2)
        self.m3u8_proxy.insert(0, "")
        tk.Label(adv_frame, text="如 http://127.0.0.1:7890", bg=D["page"], fg=D["ink_dis"], font=XS).pack(side=tk.LEFT, padx=(4, 0))

        # Header + 断点续传
        hdr_frame = tk.Frame(p, bg=D["page"])
        hdr_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(hdr_frame, text="自定义Header", bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 4))
        self.m3u8_headers = tk.Entry(hdr_frame, font=BODY, bg=D["input_bg"], fg=D["ink"], relief="solid", bd=1, highlightthickness=0)
        self.m3u8_headers.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2)
        tk.Label(hdr_frame, text="Key:Value,Key:Value", bg=D["page"], fg=D["ink_dis"], font=XS).pack(side=tk.LEFT, padx=(4, 0))
        self.m3u8_resume = tk.BooleanVar(value=True)
        tk.Checkbutton(hdr_frame, text="断点续传", variable=self.m3u8_resume, bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.RIGHT)

        # 速度提示
        notice_frame = tk.Frame(p, bg=D["accent_pale"])
        notice_frame.pack(fill=tk.X, pady=(4, 0))
        tk.Label(notice_frame, text="下载速度由服务器带宽决定，多线程只能在服务器允许范围内加速。速度慢可尝试切换画质或使用代理。",
                 bg=D["accent_pale"], fg=D["accent"], font=SM, anchor=tk.CENTER, justify=tk.CENTER).pack(fill=tk.X, padx=4, pady=4)

        # 下载队列
        queue_card = tk.Frame(p, bg=D["border"], padx=1, pady=1)
        queue_card.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        queue_inner = tk.Frame(queue_card, bg=D["card"])
        queue_inner.pack(fill=tk.BOTH, expand=True)
        q_header = tk.Frame(queue_inner, bg=D["card"])
        q_header.pack(fill=tk.X, padx=10, pady=(8, 4))
        tk.Label(q_header, text="下载队列", bg=D["card"], fg=D["ink"], font=(FT, 9, "bold")).pack(side=tk.LEFT)
        self.m3u8_count_label = tk.Label(q_header, text="0 个任务", bg=D["card"], fg=D["ink_dis"], font=XS)
        self.m3u8_count_label.pack(side=tk.RIGHT)

        q_list_frame = tk.Frame(queue_inner, bg=D["card"])
        q_list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 4))
        self.m3u8_listbox = tk.Listbox(q_list_frame, font=(FT, 10), bg=D["card"], fg=D["ink"],
                                        selectbackground=D["select_bg"], selectforeground=D["select_fg"],
                                        bd=0, highlightthickness=0, activestyle="none", selectborderwidth=0, height=6)
        q_scroll = ttk.Scrollbar(q_list_frame, orient=tk.VERTICAL, command=self.m3u8_listbox.yview)
        self.m3u8_listbox.configure(yscrollcommand=q_scroll.set)
        self.m3u8_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        q_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        q_btn_frame = tk.Frame(queue_inner, bg=D["card"])
        q_btn_frame.pack(fill=tk.X, padx=10, pady=(0, 8))
        self._btn(q_btn_frame, "▲ 上移", self._m3u8_move_up, "ghost", padx=6).pack(side=tk.LEFT)
        self._btn(q_btn_frame, "▼ 下移", self._m3u8_move_down, "ghost", padx=6).pack(side=tk.LEFT, padx=(4, 0))
        self._btn(q_btn_frame, "✕ 移除选中", self._m3u8_remove_selected, "ghost", padx=8).pack(side=tk.LEFT, padx=(12, 0))
        self._btn(q_btn_frame, "清空队列", self._m3u8_clear_queue, "ghost", padx=8).pack(side=tk.LEFT, padx=(8, 0))
        self._btn(q_btn_frame, "📁 批量导入", self._m3u8_batch_import, "ghost", padx=8).pack(side=tk.LEFT, padx=(8, 0))
        self._btn(q_btn_frame, "⭐ 收藏链接", self._m3u8_show_favorites, "ghost", padx=8).pack(side=tk.LEFT, padx=(8, 0))
        self._btn(q_btn_frame, "📋 历史记录", self._m3u8_show_history, "ghost", padx=8).pack(side=tk.LEFT, padx=(8, 0))

        # 字幕 + 通知
        opt_frame = tk.Frame(p, bg=D["page"])
        opt_frame.pack(fill=tk.X, pady=(4, 0))
        self.m3u8_download_sub = tk.BooleanVar(value=False)
        tk.Checkbutton(opt_frame, text="同时下载字幕", variable=self.m3u8_download_sub, bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.LEFT)
        self.m3u8_notify = tk.BooleanVar(value=True)
        tk.Checkbutton(opt_frame, text="完成通知", variable=self.m3u8_notify, bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(16, 0))

        # 底部操作栏
        bottom_bar = tk.Frame(p, bg=D["page"])
        bottom_bar.pack(fill=tk.X, pady=(8, 0))
        self.m3u8_pg = ttk.Progressbar(bottom_bar, style="Horizontal.TProgressbar")
        self.m3u8_pg.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.m3u8_st = tk.Label(bottom_bar, text="就绪", bg=D["page"], fg=D["ink_dis"], font=XS)
        self.m3u8_st.pack(side=tk.LEFT, padx=(0, 8))
        self._btn(bottom_bar, "📁 打开输出文件夹", self._open_output_folder, "ghost", padx=8).pack(side=tk.RIGHT, padx=(0, 8))
        self.m3u8_ca = self._btn(bottom_bar, "取消", None, "danger", padx=8, state=tk.DISABLED)
        self.m3u8_ca.pack(side=tk.RIGHT, padx=(0, 4))
        self.m3u8_ca.configure(command=lambda: self._stop("m3u8"))
        self.m3u8_go = self._btn(bottom_bar, "开始下载", None, "primary", padx=16)
        self.m3u8_go.pack(side=tk.RIGHT)
        self.m3u8_go.configure(command=self._go_m3u8)

    # ══════════════════════════════════════════
    def _p_ocr(self):
        p = tk.Frame(self.content, bg=D["page"])
        self.panels["ocr"] = p
        self._hdr(p, "OCR 文字识别", "从图片或PDF中识别文字，支持批量处理")
        self._file_sec(p, "ocr",
            [("图片/PDF", "*.jpg *.jpeg *.png *.bmp *.webp *.tiff *.pdf"), ("所有文件", "*.*")])
        
        s = self._card(p, "识别设置")
        
        ocr_langs = ["chi_sim+eng", "chi_sim", "eng", "jpn", "kor", "chi_tra+eng", "chi_tra", "eng+chi_sim"]
        tk.Label(s, text="识别语言", bg=D["card"], fg=D["ink"], font=SM).grid(row=0, column=0, sticky="w")
        self.ocr_lang = ttk.Combobox(s, values=ocr_langs, state="readonly", width=20)
        self.ocr_lang.set("chi_sim+eng")
        self.ocr_lang.grid(row=0, column=1, sticky="w", padx=(8, 0))
        tk.Label(s, text="chi_sim=简体中文  eng=英文  jpn=日文  kor=韩文",
                 bg=D["card"], fg=D["ink_dis"], font=XS).grid(row=0, column=2, sticky="w", padx=(8, 0))
        
        # 结果文本区
        result_frame = tk.Frame(p, bg=D["card"])
        result_frame.pack(fill=tk.X, padx=16, pady=(12, 0))
        
        result_header = tk.Frame(result_frame, bg=D["card"])
        result_header.pack(fill=tk.X)
        tk.Label(result_header, text="识别结果", bg=D["card"], fg=D["ink_sec"],
                 font=(FT, 9, "bold")).pack(side=tk.LEFT)
        
        self.ocr_export_txt = tk.Button(result_header, text="导出 TXT", font=SM,
                                        bg=D["card"], fg=D["accent"], relief="flat",
                                        cursor="hand2", bd=0,
                                        command=self._ocr_export_txt)
        self.ocr_export_txt.pack(side=tk.RIGHT, padx=(8, 0))
        
        self.ocr_copy_btn = tk.Button(result_header, text="复制到剪贴板", font=SM,
                                      bg=D["card"], fg=D["accent"], relief="flat",
                                      cursor="hand2", bd=0,
                                      command=self._ocr_copy)
        self.ocr_copy_btn.pack(side=tk.RIGHT, padx=(8, 0))
        
        # 文本显示区
        text_container = tk.Frame(result_frame, bg=D["border"], padx=1, pady=1)
        text_container.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        
        self.ocr_text = tk.Text(text_container, font=("Microsoft YaHei UI", 10),
                                bg=D["input_bg"], fg=D["ink"],
                                relief="flat", bd=0, padx=8, pady=8,
                                height=6, wrap=tk.WORD)
        text_scroll = ttk.Scrollbar(text_container, orient=tk.VERTICAL, command=self.ocr_text.yview)
        self.ocr_text.configure(yscrollcommand=text_scroll.set)
        self.ocr_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        text_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        out_dir_frame = tk.Frame(p, bg=D["page"])
        out_dir_frame.pack(fill=tk.X, pady=(12, 0))
        tk.Label(out_dir_frame, text="输出目录", bg=D["page"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(0, 8))
        self.ocr_out_dir_combo = ttk.Combobox(out_dir_frame, values=["与源文件同目录", "自定义目录"], state="readonly", width=14)
        self.ocr_out_dir_combo.set("与源文件同目录")
        self.ocr_out_dir_combo.pack(side=tk.LEFT)
        self.ocr_out_dir_btn = self._btn(out_dir_frame, "浏览", lambda: self._select_out_dir("ocr"), style="secondary")
        self.ocr_out_dir_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.ocr_out_dir_path = tk.StringVar(value="")
        self.ocr_out_dir_label = tk.Label(out_dir_frame, textvariable=self.ocr_out_dir_path, bg=D["page"], fg=D["ink_dis"], font=XS)
        self.ocr_out_dir_label.pack(side=tk.LEFT, padx=(8, 0))
        
        self.ocr_pg, self.ocr_st, self.ocr_go, self.ocr_ca, _ = self._bar(p)
        self.ocr_go.configure(text="开始识别", command=lambda: self._go("ocr"))
        self.ocr_ca.configure(command=lambda: self._stop("ocr"))

    def _ocr_export_txt(self):
        text = self.ocr_text.get(1.0, tk.END).strip()
        if not text:
            messagebox.showinfo("提示", "没有可导出的文字"); return
        path = filedialog.asksaveasfilename(defaultextension=".txt",
            filetypes=[("文本文件", "*.txt")])
        if not path: return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)
            self._log_status(f"已导出至：{os.path.basename(path)}", "success")
        except Exception as e:
            messagebox.showerror("失败", f"导出失败：{e}")

    def _ocr_copy(self):
        text = self.ocr_text.get(1.0, tk.END).strip()
        if not text:
            messagebox.showinfo("提示", "没有可复制的文字"); return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._log_status(f"已复制 {len(text)} 字符到剪贴板", "success")

    # ══════════════════════════════════════════
    #  二维码生成器
    # ══════════════════════════════════════════
    def _p_qrcode(self):
        p = tk.Frame(self.content, bg=D["page"])
        self.panels["qrcode"] = p
        self._hdr(p, "二维码生成器", "将文本、链接、联系方式等生成二维码图片")

        # 输入区
        s = self._card(p, "内容设置")
        tk.Label(s, text="内容类型", bg=D["card"], fg=D["ink"], font=SM).grid(row=0, column=0, sticky="w")
        self.qr_type = ttk.Combobox(s, values=["文本", "网址", "WiFi", "名片"], state="readonly", width=12)
        self.qr_type.set("文本")
        self.qr_type.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.qr_type.bind("<<ComboboxSelected>>", lambda e: self._qr_type_changed())

        # 文本输入
        tk.Label(s, text="内容", bg=D["card"], fg=D["ink"], font=SM).grid(row=1, column=0, sticky="nw", pady=(8, 0))
        self.qr_text = tk.Text(s, font=BODY, bg=D["input_bg"], fg=D["ink"],
                               relief="flat", highlightthickness=1, highlightbackground=D["input_bd"],
                               highlightcolor=D["accent"], height=3, width=40, wrap=tk.WORD)
        self.qr_text.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=(8, 0))
        self.qr_text.insert("1.0", "Hello World")

        # WiFi 选项（默认隐藏）
        self.qr_wifi_frame = tk.Frame(s, bg=D["card"])
        wifi_row = tk.Frame(self.qr_wifi_frame, bg=D["card"])
        wifi_row.pack(fill=tk.X, pady=(4, 0))
        tk.Label(wifi_row, text="WiFi名称", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT)
        self.qr_wifi_ssid = tk.Entry(wifi_row, font=BODY, bg=D["input_bg"], fg=D["ink"],
                                      insertbackground=D["ink"], relief="flat", highlightthickness=1,
                                      highlightbackground=D["input_bd"],
                                      highlightcolor=D["accent"], width=20)
        self.qr_wifi_ssid.pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(wifi_row, text="密码", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(16, 0))
        self.qr_wifi_pass = tk.Entry(wifi_row, font=BODY, bg=D["input_bg"], fg=D["ink"],
                                      insertbackground=D["ink"], relief="flat", highlightthickness=1,
                                      highlightbackground=D["input_bd"], highlightcolor=D["accent"],
                                      width=20, show="*")
        self.qr_wifi_pass.pack(side=tk.LEFT, padx=(8, 0))
        self._qr_eye_visible = False
        self.qr_eye_btn = tk.Button(wifi_row, text="👁", font=("Segoe UI Symbol", 10),
                                     bg=D["card"], relief="flat", bd=0, cursor="hand2",
                                     command=self._qr_toggle_eye)
        self.qr_eye_btn.pack(side=tk.LEFT, padx=(2, 0))

        # 外观设置
        qr_style = tk.Frame(s, bg=D["card"])
        qr_style.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        tk.Label(qr_style, text="尺寸", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT)
        self.qr_size = ttk.Combobox(qr_style, values=["200", "300", "400", "500", "600"], state="readonly", width=8)
        self.qr_size.set("400")
        self.qr_size.pack(side=tk.LEFT, padx=(8, 0))

        tk.Label(qr_style, text="边距", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(16, 0))
        self.qr_border = ttk.Combobox(qr_style, values=["1", "2", "4", "6"], state="readonly", width=6)
        self.qr_border.set("4")
        self.qr_border.pack(side=tk.LEFT, padx=(8, 0))

        tk.Label(qr_style, text="前景色", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(16, 0))
        self.qr_fg = tk.StringVar(value="#000000")
        self.qr_fg_entry = tk.Entry(qr_style, textvariable=self.qr_fg, font=BODY, width=10,
                                     bg=D["input_bg"], relief="flat", highlightthickness=1,
                                     highlightbackground=D["input_bd"])
        self.qr_fg_entry.pack(side=tk.LEFT, padx=(4, 0))

        tk.Label(qr_style, text="背景色", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT, padx=(16, 0))
        self.qr_bg = tk.StringVar(value="#FFFFFF")
        self.qr_bg_entry = tk.Entry(qr_style, textvariable=self.qr_bg, font=BODY, width=10,
                                     bg=D["input_bg"], relief="flat", highlightthickness=1,
                                     highlightbackground=D["input_bd"])
        self.qr_bg_entry.pack(side=tk.LEFT, padx=(4, 0))

        # 预览区
        preview_frame = tk.Frame(p, bg=D["card"], highlightbackground=D["border"], highlightthickness=1)
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=(12, 0))
        tk.Label(preview_frame, text="预览", bg=D["card"], fg=D["ink_sec"],
                 font=(FT, 9, "bold")).pack(anchor=tk.W, padx=12, pady=(8, 4))

        self.qr_preview_label = tk.Label(preview_frame, text="点击「生成二维码」预览", bg=D["card"],
                                          fg=D["ink_dis"], font=BODY)
        self.qr_preview_label.pack(expand=True, pady=(0, 12))

        # 底部按钮
        bottom_bar = tk.Frame(p, bg=D["page"])
        bottom_bar.pack(fill=tk.X, pady=(12, 0))
        self._btn(bottom_bar, "保存为图片", self._qr_save, "primary", padx=24).pack(side=tk.RIGHT)
        self._btn(bottom_bar, "生成二维码", self._qr_generate, "primary", padx=24).pack(side=tk.RIGHT, padx=(0, 8))
        self.qr_status = tk.Label(bottom_bar, text="", bg=D["page"], fg=D["ink_dis"], font=SM)
        self.qr_status.pack(side=tk.LEFT, padx=(8, 0))

        self._qr_photo = None  # 保持引用防止GC

    # ── 压缩包密码恢复 ──────────────────────────
    def _qr_type_changed(self):
        t = self.qr_type.get()
        if t == "WiFi":
            self.qr_wifi_frame.grid(row=2, column=0, columnspan=3, sticky="ew", padx=16, pady=(8, 0))
            self.qr_text.delete("1.0", tk.END)
            self.qr_text.insert("1.0", "↓ 在下方填写WiFi名称和密码")
            self.qr_text.configure(state=tk.DISABLED, height=1)
            self.root.after(100, lambda: self.qr_wifi_ssid.focus_set())
        else:
            self.qr_wifi_frame.grid_forget()
            self.qr_text.configure(state=tk.NORMAL, height=3)
            if t == "网址":
                self.qr_text.delete("1.0", tk.END)
                self.qr_text.insert("1.0", "https://")
            elif t == "名片":
                self.qr_text.delete("1.0", tk.END)
                self.qr_text.insert("1.0", "BEGIN:VCARD\nFN:姓名\nTEL:13800138000\nEMAIL:email@example.com\nEND:VCARD")
            else:
                self.qr_text.delete("1.0", tk.END)
                self.qr_text.insert("1.0", "Hello World")

    def _qr_toggle_eye(self):
        self._qr_eye_visible = not self._qr_eye_visible
        if self._qr_eye_visible:
            self.qr_wifi_pass.configure(show="")
            self.qr_eye_btn.configure(text="🙈")
        else:
            self.qr_wifi_pass.configure(show="*")
            self.qr_eye_btn.configure(text="👁")

    def _qr_generate(self):
        try:
            import qrcode
        except ImportError:
            messagebox.showerror("缺少依赖", "请先安装 qrcode 库：\npip install qrcode[pil]")
            return

        t = self.qr_type.get()
        if t == "WiFi":
            ssid = self.qr_wifi_ssid.get().strip()
            pwd = self.qr_wifi_pass.get().strip()
            if not ssid:
                messagebox.showwarning("提示", "请输入WiFi名称")
                return
            content = f"WIFI:T:WPA;S:{ssid};P:{pwd};;"
        else:
            content = self.qr_text.get("1.0", tk.END).strip()
            if not content:
                messagebox.showwarning("提示", "请输入内容")
                return

        try:
            fg = self.qr_fg.get().strip()
            bg = self.qr_bg.get().strip()
            size = int(self.qr_size.get())
            border = int(self.qr_border.get())

            qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_H,
                                box_size=10, border=border)
            qr.add_data(content)
            qr.make(fit=True)
            img = qr.make_image(fill_color=fg, back_color=bg).convert("RGB")
            img = img.resize((size, size), resample=0)

            from PIL import ImageTk
            self._qr_photo = ImageTk.PhotoImage(img)
            self.qr_preview_label.configure(image=self._qr_photo, text="")
            self.qr_status.configure(text=f"已生成 {size}×{size} 二维码", fg=D["ok"])

            # 保存到临时变量供复制/保存使用
            self._qr_img = img

        except Exception as e:
            messagebox.showerror("生成失败", str(e))

    def _qr_save(self):
        if not hasattr(self, '_qr_img') or self._qr_img is None:
            messagebox.showwarning("提示", "请先生成二维码")
            return
        path = filedialog.asksaveasfilename(defaultextension=".png",
            initialfile="qrcode.png",
            filetypes=[("PNG 图片", "*.png"), ("JPEG 图片", "*.jpg"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            self._qr_img.save(path)
            self.qr_status.configure(text=f"已保存: {os.path.basename(path)}", fg=D["ok"])
            self._log_status(f"二维码已保存: {path}", "success")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))


    def _select_m3u8_dir(self):
        last_dir = self._get_last_dir("m3u8")
        d = filedialog.askdirectory(title="选择保存目录", initialdir=last_dir)
        if d:
            self._save_last_dir("m3u8", d)
            self.m3u8_out_dir.set(d)

    def _m3u8_parse_url(self):
        urls = _extract_urls(self.m3u8_url.get("1.0", tk.END))
        if not urls:
            messagebox.showwarning("提示", "请先输入M3U8链接")
            return
        url = urls[0]
        self.m3u8_quality.set("正在解析...")
        self.m3u8_quality_hint.configure(text="正在解析画质...")
        cookie = self.m3u8_cookie.get().strip() or None
        proxy = self.m3u8_proxy.get().strip() or None
        custom_headers = {}
        hdr_str = self.m3u8_headers.get().strip()
        if hdr_str:
            for pair in hdr_str.split(","):
                if ":" in pair:
                    k, v = pair.split(":", 1)
                    custom_headers[k.strip()] = v.strip()

        def work():
            try:
                qualities = self.m3u8_dl.get_qualities(url, headers=custom_headers, cookie=cookie, proxy=proxy)
                subs = self.m3u8_dl.get_subtitles(url, headers=custom_headers, cookie=cookie, proxy=proxy)
                self.root.after(0, lambda: self._m3u8_show_qualities(qualities, subs))
            except Exception as e:
                self.root.after(0, lambda: self._m3u8_parse_fail(str(e)))
        threading.Thread(target=work, daemon=True).start()

    def _m3u8_show_qualities(self, qualities, subs=None):
        self.m3u8_qualities = qualities
        if not qualities:
            self.m3u8_quality["values"] = ["仅有一个画质"]
            self.m3u8_quality.set("仅有一个画质")
            hint = "该链接没有多码率选项，将使用默认画质"
        else:
            labels = [q["display"] for q in qualities]
            self.m3u8_quality["values"] = labels
            self.m3u8_quality.set(labels[0])
            hint = f"找到 {len(qualities)} 个画质，最高: {qualities[0]['label']}"
        if subs is not None:
            if subs:
                sub_names = ", ".join([s["name"] for s in subs])
                hint += f"  |  字幕: {len(subs)}个 ({sub_names})"
                self._log_status(f"检测到 {len(subs)} 个字幕轨道: {sub_names}", "info")
            else:
                hint += "  |  字幕: 无"
                self._log_status("该视频没有字幕轨道", "info")
        self.m3u8_quality_hint.configure(text=hint)

    def _m3u8_parse_fail(self, err):
        self.m3u8_quality["values"] = ["解析失败"]
        self.m3u8_quality.set("解析失败")
        self.m3u8_quality_hint.configure(text=f"解析失败：{err[:50]}")

    def _m3u8_quality_changed(self, event=None):
        sel = self.m3u8_quality.current()
        if sel >= 0 and sel < len(self.m3u8_qualities):
            q = self.m3u8_qualities[sel]
            hint = f"已选: {q['label']}"
            if q.get("resolution"): hint += f"  {q['resolution']}"
            if q.get("bandwidth_str"): hint += f"  {q['bandwidth_str']}"
            self.m3u8_quality_hint.configure(text=hint)

    def _m3u8_batch_add(self):
        raw = self.m3u8_url.get("1.0", tk.END)
        urls = _extract_urls(raw)
        if not urls:
            messagebox.showwarning("提示", "请先输入有效的M3U8链接")
            return
        added = 0
        for url in urls:
            if self.m3u8_dl.store.is_downloaded(url):
                if not messagebox.askyesno("提示", f"链接已下载过，是否重新添加？\n{url[:60]}"):
                    continue
            name = self._m3u8_gen_name(url)
            quality_url = url
            if self.m3u8_qualities:
                sel = self.m3u8_quality.current()
                if sel >= 0 and sel < len(self.m3u8_qualities):
                    quality_url = self.m3u8_qualities[sel]["url"]
            self.m3u8_queue.append({"url": quality_url, "master_url": url, "name": name, "status": "等待"})
            quality_label = ""
            if self.m3u8_qualities:
                sel = self.m3u8_quality.current()
                if sel >= 0 and sel < len(self.m3u8_qualities):
                    quality_label = f"  [{self.m3u8_qualities[sel]['label']}]"
            display = f"  {name}{quality_label}  —  {url[:50]}{'...' if len(url) > 50 else ''}"
            self.m3u8_listbox.insert(tk.END, display)
            added += 1
        self.m3u8_count_label.configure(text=f"{len(self.m3u8_queue)} 个任务")
        self.m3u8_url.delete("1.0", tk.END)
        self.m3u8_name.delete(0, tk.END)
        self._log_status(f"已添加 {added} 个链接到队列", "info")

    def _m3u8_gen_name(self, url):
        name = self.m3u8_name.get().strip()
        if name: return name
        import hashlib
        from urllib.parse import urlparse, unquote
        parsed = urlparse(url)
        path_part = parsed.path.rstrip("/")
        base = unquote(os.path.basename(path_part))
        if "." in base:
            base = os.path.splitext(base)[0]
        if base and 2 <= len(base) <= 30:
            return base
        return hashlib.md5(url.encode()).hexdigest()[:12]

    def _m3u8_add_to_favorites(self):
        urls = _extract_urls(self.m3u8_url.get("1.0", tk.END))
        if not urls:
            messagebox.showwarning("提示", "请先输入链接")
            return
        url = urls[0]
        from urllib.parse import urlparse, unquote
        path_parts = urlparse(url).path
        name = unquote(path_parts.split("/")[-1].split("?")[0])
        if not name or name.endswith(".m3u8"):
            name = self.m3u8_name.get().strip() or url[:40]
        win = tk.Toplevel(self.root)
        win.title("收藏链接")
        win.configure(bg=D["page"])
        win.minsize(400, 180)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = min(int(sw*0.4), 500), min(int(sh*0.25), 220)
        win.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        win.transient(self.root)
        win.grab_set()
        tk.Label(win, text="添加备注（可选）", bg=D["page"], fg=D["ink"], font=H2).pack(anchor=tk.W, padx=20, pady=(16, 8))
        nf = tk.Frame(win, bg=D["page"]); nf.pack(fill=tk.X, padx=20, pady=(0, 8))
        tk.Label(nf, text="名称", bg=D["page"], fg=D["ink"], font=SM, width=6, anchor="w").pack(side=tk.LEFT)
        name_e = tk.Entry(nf, font=BODY, bg=D["input_bg"], fg=D["ink"], relief="solid", bd=1, highlightthickness=0)
        name_e.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3); name_e.insert(0, name)
        ntf = tk.Frame(win, bg=D["page"]); ntf.pack(fill=tk.X, padx=20, pady=(0, 12))
        tk.Label(ntf, text="备注", bg=D["page"], fg=D["ink"], font=SM, width=6, anchor="w").pack(side=tk.LEFT)
        note_e = tk.Entry(ntf, font=BODY, bg=D["input_bg"], fg=D["ink"], relief="solid", bd=1, highlightthickness=0)
        note_e.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)
        tk.Label(ntf, text="如：第一集、电影名等", bg=D["page"], fg=D["ink_dis"], font=XS).pack(side=tk.LEFT, padx=(8, 0))
        def do_save():
            name_val = name_e.get().strip()
            note_val = note_e.get().strip()
            self.m3u8_dl.store.add_favorite(url, name_val, note_val)
            win.destroy()
            messagebox.showinfo("收藏成功", f"已收藏: {name_val}")
        bf = tk.Frame(win, bg=D["page"]); bf.pack(fill=tk.X, padx=20, pady=(0, 12))
        self._btn(bf, "保存", do_save, "primary", padx=16).pack(side=tk.LEFT)
        self._btn(bf, "取消", win.destroy, "ghost", padx=16).pack(side=tk.LEFT, padx=(8, 0))

    def _m3u8_remove_selected(self):
        sel = self.m3u8_listbox.curselection()
        if not sel: return
        for i in reversed(sel):
            self.m3u8_listbox.delete(i)
            self.m3u8_queue.pop(i)
        self.m3u8_count_label.configure(text=f"{len(self.m3u8_queue)} 个任务")

    def _m3u8_move_up(self):
        sel = self.m3u8_listbox.curselection()
        if not sel or sel[0] == 0: return
        i = sel[0]
        self.m3u8_queue[i], self.m3u8_queue[i-1] = self.m3u8_queue[i-1], self.m3u8_queue[i]
        a = self.m3u8_listbox.get(i); b = self.m3u8_listbox.get(i-1)
        self.m3u8_listbox.delete(i-1, i)
        self.m3u8_listbox.insert(i-1, a); self.m3u8_listbox.insert(i, b)
        self.m3u8_listbox.selection_set(i-1)

    def _m3u8_move_down(self):
        sel = self.m3u8_listbox.curselection()
        if not sel or sel[0] >= self.m3u8_listbox.size()-1: return
        i = sel[0]
        self.m3u8_queue[i], self.m3u8_queue[i+1] = self.m3u8_queue[i+1], self.m3u8_queue[i]
        a = self.m3u8_listbox.get(i); b = self.m3u8_listbox.get(i+1)
        self.m3u8_listbox.delete(i, i+1)
        self.m3u8_listbox.insert(i, b); self.m3u8_listbox.insert(i+1, a)
        self.m3u8_listbox.selection_set(i+1)

    def _m3u8_clear_queue(self):
        self.m3u8_listbox.delete(0, tk.END)
        self.m3u8_queue.clear()
        self.m3u8_count_label.configure(text="0 个任务")

    def _m3u8_batch_import(self):
        last_dir = self._get_last_dir("m3u8")
        path = filedialog.askopenfilename(title="选择链接文件", initialdir=last_dir,
                                          filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if not path: return
        self._save_last_dir("m3u8", path)
        try:
            with open(path, "r", encoding="utf-8") as f: lines = f.readlines()
        except:
            with open(path, "r", encoding="gbk") as f: lines = f.readlines()
        added = 0
        for line in lines:
            url = line.strip()
            if not url or url.startswith("#") or not url.lower().startswith(("http://", "https://")): continue
            if any(q["url"] == url for q in self.m3u8_queue): continue
            import hashlib
            from urllib.parse import urlparse, unquote
            parsed = urlparse(url)
            base = unquote(os.path.basename(parsed.path.rstrip("/")))
            if "." in base: base = os.path.splitext(base)[0]
            name = base if base and 2 <= len(base) <= 30 and base.isalnum() else hashlib.md5(url.encode()).hexdigest()[:12]
            self.m3u8_queue.append({"url": url, "master_url": url, "name": name, "status": "等待"})
            self.m3u8_listbox.insert(tk.END, f"  {name}  —  {url[:50]}")
            added += 1
        self.m3u8_count_label.configure(text=f"{len(self.m3u8_queue)} 个任务")
        if added > 0: messagebox.showinfo("导入完成", f"成功导入 {added} 个链接")
        else: messagebox.showwarning("提示", "未找到有效链接")

    def _m3u8_show_favorites(self):
        favs = self.m3u8_dl.store.get_favorites()
        win = tk.Toplevel(self.root)
        win.title("收藏链接")
        win.configure(bg=D["page"])
        win.minsize(600, 400)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = min(int(sw*0.55), 850), min(int(sh*0.6), 550)
        win.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        win.transient(self.root)
        win.grab_set()
        tk.Label(win, text="我的收藏", bg=D["page"], fg=D["ink"], font=H2).pack(anchor=tk.W, padx=16, pady=(16, 8))
        lf = tk.Frame(win, bg=D["card"]); lf.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))
        lb = tk.Listbox(lf, font=(FT, 10), bg=D["card"], fg=D["ink"], selectbackground=D["select_bg"], selectforeground=D["select_fg"], bd=0, highlightthickness=0, activestyle="none")
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scr = ttk.Scrollbar(lf, orient=tk.VERTICAL, command=lb.yview)
        lb.configure(yscrollcommand=scr.set); scr.pack(side=tk.RIGHT, fill=tk.Y)

        def refresh():
            nonlocal favs
            favs = self.m3u8_dl.store.get_favorites()
            lb.delete(0, tk.END)
            for fav in favs:
                note = fav.get("note", "")
                display = f"  {fav['name']}"
                if note: display += f"  [{note}]"
                display += f"  —  {fav['url'][:50]}"
                lb.insert(tk.END, display)
            if not favs:
                lb.insert(tk.END, "  暂无收藏，请先输入链接后点击「收藏」按钮")
                lb.configure(fg=D["ink_dis"])
            else: lb.configure(fg=D["ink"])
        refresh()

        def edit_sel():
            sel = lb.curselection()
            if not sel: return
            fav = favs[sel[0]]
            ew = tk.Toplevel(win); ew.title("编辑收藏"); ew.configure(bg=D["page"])
            ew.minsize(400, 200)
            sw2, sh2 = win.winfo_screenwidth(), win.winfo_screenheight()
            w2, h2 = min(int(sw2*0.4), 550), min(int(sh2*0.3), 250)
            ew.geometry(f"{w2}x{h2}+{(sw2-w2)//2}+{(sh2-h2)//2}")
            ew.transient(win); ew.grab_set()
            tk.Label(ew, text="编辑收藏", bg=D["page"], fg=D["ink"], font=H2).pack(anchor=tk.W, padx=20, pady=(20, 12))
            nf = tk.Frame(ew, bg=D["page"]); nf.pack(fill=tk.X, padx=20, pady=(0, 8))
            tk.Label(nf, text="名称", bg=D["page"], fg=D["ink"], font=SM, width=6, anchor="w").pack(side=tk.LEFT)
            ne = tk.Entry(nf, font=BODY, bg=D["input_bg"], fg=D["ink"], relief="solid", bd=1, highlightthickness=0)
            ne.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3); ne.insert(0, fav.get("name", ""))
            ntf2 = tk.Frame(ew, bg=D["page"]); ntf2.pack(fill=tk.X, padx=20, pady=(0, 12))
            tk.Label(ntf2, text="备注", bg=D["page"], fg=D["ink"], font=SM, width=6, anchor="w").pack(side=tk.LEFT)
            nte = tk.Entry(ntf2, font=BODY, bg=D["input_bg"], fg=D["ink"], relief="solid", bd=1, highlightthickness=0)
            nte.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3); nte.insert(0, fav.get("note", ""))
            def save_fav():
                self.m3u8_dl.store.update_favorite(fav["url"], name=ne.get().strip(), note=nte.get().strip())
                ew.destroy(); refresh()
            bf2 = tk.Frame(ew, bg=D["page"]); bf2.pack(fill=tk.X, padx=20, pady=(0, 16))
            self._btn(bf2, "保存", save_fav, "primary", padx=16).pack(side=tk.LEFT)
            self._btn(bf2, "取消", ew.destroy, "ghost", padx=16).pack(side=tk.LEFT, padx=(8, 0))

        def use_sel():
            sel = lb.curselection()
            if not sel: return
            fav = favs[sel[0]]
            self.m3u8_url.delete("1.0", tk.END); self.m3u8_url.insert("1.0", fav["url"])
            from urllib.parse import urlparse, unquote
            pn = unquote(urlparse(fav["url"]).path.split("/")[-1].split("?")[0])
            if pn and not pn.endswith(".m3u8"):
                self.m3u8_name.delete(0, tk.END); self.m3u8_name.insert(0, pn)
            win.destroy()

        def add_q():
            sel = lb.curselection()
            if not sel: return
            fav = favs[sel[0]]
            url = fav["url"]
            if any(q["url"] == url for q in self.m3u8_queue):
                messagebox.showwarning("提示", "该链接已在队列中"); return
            import hashlib
            from urllib.parse import urlparse, unquote
            parsed = urlparse(url)
            base = unquote(os.path.basename(parsed.path.rstrip("/")))
            if "." in base: base = os.path.splitext(base)[0]
            name = base if base and 2 <= len(base) <= 30 and base.isalnum() else hashlib.md5(url.encode()).hexdigest()[:12]
            self.m3u8_queue.append({"url": url, "master_url": url, "name": name, "status": "等待"})
            self.m3u8_listbox.insert(tk.END, f"  {name}  —  {url[:50]}")
            self.m3u8_count_label.configure(text=f"{len(self.m3u8_queue)} 个任务")

        def rem_sel():
            sel = lb.curselection()
            if not sel: return
            self.m3u8_dl.store.remove_favorite(favs[sel[0]]["url"]); refresh()

        bf = tk.Frame(win, bg=D["page"]); bf.pack(fill=tk.X, padx=16, pady=(0, 12))
        self._btn(bf, "填入链接", use_sel, "primary", padx=12).pack(side=tk.LEFT)
        self._btn(bf, "加入队列", add_q, padx=12).pack(side=tk.LEFT, padx=(8, 0))
        self._btn(bf, "重命名/备注", edit_sel, padx=12).pack(side=tk.LEFT, padx=(8, 0))
        self._btn(bf, "取消收藏", rem_sel, "ghost", padx=12).pack(side=tk.LEFT, padx=(8, 0))
        self._btn(bf, "关闭", win.destroy, "ghost", padx=12).pack(side=tk.RIGHT)

    def _m3u8_show_history(self):
        history = self.m3u8_dl.store.get_history()
        win = tk.Toplevel(self.root)
        win.title("下载历史")
        win.configure(bg=D["page"])
        win.minsize(600, 400)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = min(int(sw*0.55), 850), min(int(sh*0.6), 550)
        win.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        win.transient(self.root); win.grab_set()
        tk.Label(win, text="下载历史", bg=D["page"], fg=D["ink"], font=H2).pack(anchor=tk.W, padx=16, pady=(16, 8))
        lf = tk.Frame(win, bg=D["card"]); lf.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))
        lb = tk.Listbox(lf, font=(FT, 10), bg=D["card"], fg=D["ink"], selectbackground=D["select_bg"], selectforeground=D["select_fg"], bd=0, highlightthickness=0, activestyle="none")
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scr = ttk.Scrollbar(lf, orient=tk.VERTICAL, command=lb.yview)
        lb.configure(yscrollcommand=scr.set); scr.pack(side=tk.RIGHT, fill=tk.Y)
        for h in history:
            sz = f"{h.get('size', 0)/1024/1024:.1f}MB" if h.get("size", 0) > 0 else ""
            lb.insert(tk.END, f"  {h.get('name', '?')}  {sz}  {h.get('time', '')}")
        def redl():
            sel = lb.curselection()
            if not sel: return
            self.m3u8_url.delete("1.0", tk.END); self.m3u8_url.insert("1.0", history[sel[0]].get("url", "")); win.destroy()
        def clear_all():
            if messagebox.askyesno("确认", "确定清空所有下载历史？"):
                self.m3u8_dl.store.clear_history(); win.destroy()
        bf = tk.Frame(win, bg=D["page"]); bf.pack(fill=tk.X, padx=16, pady=(0, 12))
        self._btn(bf, "重新下载", redl, "primary", padx=12).pack(side=tk.LEFT)
        self._btn(bf, "清空历史", clear_all, "ghost", padx=12).pack(side=tk.LEFT, padx=(8, 0))
        self._btn(bf, "关闭", win.destroy, "ghost", padx=12).pack(side=tk.RIGHT)

    def _go_m3u8(self):
        if not self.m3u8_queue:
            messagebox.showwarning("提示", "请先添加下载链接"); return
        if not self.ffmpeg_mgr.is_available():
            messagebox.showwarning("提示", "FFmpeg 未就绪，请稍后重试"); return

        # 检查是否有重复链接
        dup_count = 0
        for item in self.m3u8_queue:
            if self.m3u8_dl.store.is_downloaded(item["url"]):
                dup_count += 1
        if dup_count > 0:
            if not messagebox.askyesno("提示", f"有 {dup_count} 个链接已下载过，是否继续重新下载？"):
                return

        out_dir = self.m3u8_out_dir.get()
        os.makedirs(out_dir, exist_ok=True); self.last_output_dir = out_dir
        self.m3u8_go.configure(state=tk.DISABLED)
        self.m3u8_ca.configure(state=tk.NORMAL)
        self.m3u8_pg["value"] = 0
        self.converting = True; self._disable_all_panels(); self._clear_task_list()
        threads = int(self.m3u8_threads.get())
        output_format = self.m3u8_format.get()
        speed_str = self.m3u8_speed.get()
        speed_limit = 0 if speed_str == "不限" else int(speed_str)
        cookie = self.m3u8_cookie.get().strip() or None
        proxy = self.m3u8_proxy.get().strip() or None
        resume = self.m3u8_resume.get()
        download_sub = self.m3u8_download_sub.get()
        notify = self.m3u8_notify.get()
        custom_headers = {}
        hdr_str = self.m3u8_headers.get().strip()
        if hdr_str:
            for pair in hdr_str.split(","):
                if ":" in pair:
                    k, v = pair.split(":", 1)
                    custom_headers[k.strip()] = v.strip()
        for i, item in enumerate(self.m3u8_queue):
            url = item["url"]
            master_url = item.get("master_url", url)
            name = item["name"]
            output_path = os.path.join(out_dir, name + "." + output_format)
            if os.path.exists(output_path):
                base, ext = os.path.splitext(output_path); counter = 1
                while os.path.exists(f"{base}_{counter}{ext}"): counter += 1
                output_path = f"{base}_{counter}{ext}"
            self._add_task(f"M3U8下载 - {name}", "m3u8", {
                "file_path": "", "output_path": output_path, "files": [], "task_type": "m3u8", "panel_name": "m3u8",
                "params": {"url": url, "master_url": master_url, "name": name, "index": i,
                           "threads": threads, "output_format": output_format, "speed_limit": speed_limit,
                           "cookie": cookie, "headers": custom_headers, "proxy": proxy,
                           "resume": resume, "download_sub": download_sub, "notify": notify}
            })
        self._log_status(f"共添加 {len(self.m3u8_queue)} 个下载任务，开始队列下载", "success")

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
    #  yt-dlp
    # ══════════════════════════════════════════
    def _check_ytdlp(self):
        if getattr(self, '_yt_checking', False):
            return
        self._yt_checking = True
        def check():
            # 优先检查便携版exe
            from utils.tool_downloader import tool_downloader
            exe_path = tool_downloader.ytdlp_path()
            if exe_path:
                try:
                    r = subprocess.run([exe_path, "--version"], capture_output=True, text=True, timeout=5,
                                       creationflags=0x08000000)
                    cur = r.stdout.strip() if r.returncode == 0 else "?"
                except Exception:
                    cur = "?"
                self.root.after(0, lambda: self.yt_lbl.configure(
                    text=f"yt-dlp · {cur}", fg=D["ink_dis"]))
                self._yt_checking = False
                return

            # 再检查pip安装版
            try:
                import importlib.metadata as ilm
                cur = ilm.version("yt-dlp")
            except Exception:
                cur = None

            if not cur:
                # 未安装，自动下载便携版
                self.root.after(0, lambda: self.yt_lbl.configure(
                    text="yt-dlp · 自动安装中…", fg=D["warn"]))
                tool_downloader.download_ytdlp_async(callback=self._on_ytdlp_installed)
                return

            self.root.after(0, lambda: self.yt_lbl.configure(
                text=f"yt-dlp · {cur}", fg=D["ink_dis"]))
            self._yt_checking = False
        threading.Thread(target=check, daemon=True).start()

    def _update_ytdlp(self, frame):
        frame.destroy()
        self.yt_lbl.configure(text="yt-dlp · 更新中…", fg=D["ink_dis"])
        def upgrade():
            try:
                import subprocess, sys
                subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.root.after(0, self._check_ytdlp)
            except Exception:
                self.root.after(0, lambda: self.yt_lbl.configure(
                    text="yt-dlp · 更新失败", fg=D["err"]))
        threading.Thread(target=upgrade, daemon=True).start()

    def _on_ytdlp_installed(self, ok, msg):
        def _update():
            if ok:
                self.yt_lbl.configure(text=f"yt-dlp · 已安装", fg=D["ok"])
            else:
                self.yt_lbl.configure(text="yt-dlp · 安装失败", fg=D["err"])
            self._yt_checking = False
        self.root.after(0, _update)

    def _show_ytdlp_update(self, latest):
        try:
            frame = tk.Frame(self.root, bg=D["accent_pale"], padx=16, pady=8)
            frame.pack(fill=tk.X)
            tk.Label(frame, text=f"yt-dlp v{latest} 可用，点击更新",
                     bg=D["accent_pale"], fg=D["accent"], font=SM).pack(side=tk.LEFT)
            self._btn(frame, "更新", lambda f=frame: self._update_ytdlp(f),
                      style="ghost", padx=8).pack(side=tk.RIGHT)
            self._btn(frame, "×", frame.destroy,
                      style="ghost", padx=4).pack(side=tk.RIGHT, padx=(8, 0))
        except Exception:
            pass

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
            "download":    (self.dl_pg, self.dl_st, self.dl_go, self.dl_ca),
            "crop":        (self.crp_pg, self.crp_st, self.crp_go, self.crp_ca),
            "m3u8":        (self.m3u8_pg, self.m3u8_st, self.m3u8_go, self.m3u8_ca),
            "ocr":         (self.ocr_pg, self.ocr_st, self.ocr_go, self.ocr_ca),
        }
        pg, st, go, ca = m.get(t, (None, None, None, None))
        return {"pg": pg, "st": st, "go": go, "ca": ca}

    def _parse_time(self, time_str):
        try:
            parts = list(map(float, time_str.split(":")))
            if len(parts) == 3:
                return parts[0] * 3600 + parts[1] * 60 + parts[2]
            elif len(parts) == 2:
                return parts[0] * 60 + parts[1]
            return float(parts[0])
        except Exception:
            return 0

    def _format_time(self, seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h:02d}:{m:02d}:{s:06.3f}"

    def _show_complete_dialog(self, title, success_count, total_count, output_dir, elapsed_time):
        messagebox.showinfo("完成", f"成功转换 {success_count}/{total_count} 个文件")

    def _open_folder(self, path):
        if path and os.path.exists(path):
            os.startfile(path)
    
    def _disable_all_panels(self, disable=True):
        self.panels_disabled = disable
        
        for panel_name in self.panels:
            self._disable_panel_inputs(panel_name, disable)
        
        for k, (row, ind, badge, lbl) in self.nav.items():
            row.configure(cursor="arrow" if disable else "hand2")
            lbl.configure(fg=D["ink_dis"] if disable else D["ink_sec"])
    
    def _disable_panel_inputs(self, panel_name, disable=True):
        state = tk.DISABLED if disable else tk.NORMAL
        
        panel = self.panels.get(panel_name)
        if panel:
            self._disable_widget_recursive(panel, disable)
    
    def _disable_widget_recursive(self, parent, disable=True):
        state = tk.DISABLED if disable else tk.NORMAL
        
        for child in parent.winfo_children():
            try:
                widget_type = child.winfo_class()
                
                if widget_type in ["TCombobox", "Entry", "Spinbox"]:
                    child.configure(state=state)
                elif widget_type == "Checkbutton":
                    child.configure(state=state)
                elif widget_type in ["Button", "TButton"]:
                    child.configure(state=state)
                
                if hasattr(child, 'winfo_children'):
                    self._disable_widget_recursive(child, disable)
            except Exception:
                pass

    

    def _go(self, t):
        files = self.panel_data.get(t, {}).get("files", [])
        if not files:
            messagebox.showwarning("提示", "请先添加文件"); return
        if t in ("video","audio","extract","compress","gif") and not self.ffmpeg_mgr.is_available():
            messagebox.showwarning("提示", "FFmpeg 未就绪，请稍后重试"); return
        if t == "doc":
            tgt = self.d_tgt.get()
            if not tgt or tgt == "请先添加文件":
                self._detect()
                tgt = self.d_tgt.get()
                if not tgt or tgt == "请先添加文件":
                    messagebox.showwarning("提示", "无法检测文件格式，请确保文件格式受支持"); return

        task_names = {
            "video": "视频转换", "audio": "音频转换", "image": "图片转换",
            "doc": "文档转换", "gif": "视频转GIF", "pdf": "PDF处理",
            "compress_img": "图片压缩", "rename": "批量重命名",
            "extract": "提取音频", "compress": "视频压缩",
            "crop": "图像裁剪", "ocr": "OCR文字识别",
        }
        
        w = self._w(t)
        w["go"].configure(state=tk.DISABLED)
        w["ca"].configure(state=tk.NORMAL)
        w["pg"]["value"] = 0
        self.converting = True
        
        self._disable_all_panels()
        w["ca"].configure(state=tk.NORMAL)
        self._clear_task_list()
        
        if t == "video":
            video_params = {
                "fmt": self.v_fmt.get(),
                "codec": self.v_codec.get(),
                "preset": self.v_preset.get(),
                "res": self.v_res.get(),
                "fps": self.v_fps.get(),
                "br": self.v_br.get(),
                "copy_mode": self.v_copy_mode.get() if hasattr(self, 'v_copy_mode') else False,
                "out_dir_combo": self.v_out_dir_combo.get(),
                "out_dir_path": self.v_out_dir_path.get() if hasattr(self, 'v_out_dir_path') else ""
            }
            
            for fp in files:
                fn = os.path.basename(fp)
                nm = os.path.splitext(fn)[0]
                ext = SUPPORTED_VIDEO[video_params["fmt"]]
                od = os.path.dirname(fp)
                if video_params["out_dir_combo"] == "自定义目录" and video_params["out_dir_path"]:
                    od = video_params["out_dir_path"]
                self.last_output_dir = od
                output_path = os.path.join(od, nm + ext)
                
                if output_path.lower() == fp.lower():
                    base, ext = os.path.splitext(output_path)
                    output_path = base + "_1" + ext
                
                if os.path.exists(output_path):
                    base, ext = os.path.splitext(output_path)
                    counter = 1
                    while os.path.exists(f"{base}_{counter}{ext}"):
                        counter += 1
                    output_path = f"{base}_{counter}{ext}"
                
                task_name = f"{task_names[t]} - {fn}"
                task_id = self._add_task(task_name, t, {
                    "file_path": fp,
                    "output_path": output_path,
                    "files": [fp],
                    "task_type": t,
                    "panel_name": t,
                    "params": video_params.copy()
                })
                
                if task_id:
                    self._log_status(f"任务已添加到队列：{task_name}", "info")
            
            self._log_status(f"共添加 {len(files)} 个视频转换任务", "info")
        else:
            if t == "pdf" and hasattr(self, 'pdf_mode') and "合并" in self.pdf_mode.get():
                mode = self.pdf_mode.get()
                od = os.path.dirname(files[0])
                dir_combo_attr = "pdf_out_dir_combo"
                dir_path_attr = "pdf_out_dir_path"
                if hasattr(self, dir_combo_attr) and hasattr(self, dir_path_attr):
                    combo = getattr(self, dir_combo_attr)
                    path_var = getattr(self, dir_path_attr)
                    if combo.get() == "自定义目录":
                        custom_path = path_var.get()
                        if custom_path:
                            od = custom_path
                self.last_output_dir = od
                output_path = os.path.join(od, "merged.pdf")
                if os.path.exists(output_path):
                    base, ext = os.path.splitext(output_path)
                    counter = 1
                    while os.path.exists(f"{base}_{counter}{ext}"):
                        counter += 1
                    output_path = f"{base}_{counter}{ext}"
                module_params = {
                    "mode": mode,
                    "range": self.pdf_range.get() if hasattr(self, 'pdf_range') else "",
                    "open_pwd": self.pdf_open_pwd.get() if hasattr(self, 'pdf_open_pwd') else "",
                    "owner_pwd": self.pdf_owner_pwd.get() if hasattr(self, 'pdf_owner_pwd') else "",
                    "encrypt_method": self.pdf_encrypt_method.get() if hasattr(self, 'pdf_encrypt_method') else "",
                    "decrypt_pwd": self.pdf_decrypt_pwd.get() if hasattr(self, 'pdf_decrypt_pwd') else "",
                    "compress_dpi": self.pdf_compress_dpi.get() if hasattr(self, 'pdf_compress_dpi') else "",
                    "compress_quality": self.pdf_compress_quality.get() if hasattr(self, 'pdf_compress_quality') else ""
                }
                task_name = f"PDF合并 - {len(files)}个文件"
                task_id = self._add_task(task_name, "pdf", {
                    "file_path": "",
                    "output_path": output_path,
                    "files": files,
                    "task_type": "pdf",
                    "panel_name": "pdf",
                    "params": module_params
                })
                if task_id:
                    self._log_status(f"任务已添加到队列：{task_name}", "info")
                    self._log_status(f"共添加 1 个PDF合并任务", "info")
                return
            
            if t == "rename":
                od = os.path.dirname(files[0])
                dir_combo_attr = "rn_out_dir_combo"
                dir_path_attr = "rn_out_dir_path"
                if hasattr(self, dir_combo_attr) and hasattr(self, dir_path_attr):
                    combo = getattr(self, dir_combo_attr)
                    path_var = getattr(self, dir_path_attr)
                    if combo.get() == "自定义目录":
                        custom_path = path_var.get()
                        if custom_path:
                            od = custom_path
                self.last_output_dir = od
                case_map = {"不转换": "none", "全大写": "upper", "全小写": "lower", "首字母大写": "title"}
                module_params = {
                    "pattern": self.rn_pattern.get(),
                    "start": self.rn_start.get(),
                    "search": self.rn_search.get() if hasattr(self, 'rn_search') else "",
                    "replace": self.rn_replace.get() if hasattr(self, 'rn_replace') else "",
                    "case": case_map.get(self.rn_case.get() if hasattr(self, 'rn_case') else "不转换", "none"),
                    "regex_pattern": self.rn_regex.get() if hasattr(self, 'rn_regex') else "",
                    "regex_replace": self.rn_regex_replace.get() if hasattr(self, 'rn_regex_replace') else "",
                }
                task_name = f"批量重命名 - {len(files)}个文件"
                task_id = self._add_task(task_name, "rename", {
                    "file_path": "",
                    "output_path": od,
                    "files": files,
                    "task_type": "rename",
                    "panel_name": "rename",
                    "params": module_params
                })
                if task_id:
                    self._log_status(f"任务已添加到队列：{task_name}", "info")
                self._log_status(f"共添加 1 个批量重命名任务", "info")
                return
            
            if t == "crop":
                od = os.path.dirname(files[0])
                if hasattr(self, 'crp_out_dir_combo') and self.crp_out_dir_combo.get() == "自定义目录" and self.crp_out_dir_path.get():
                    od = self.crp_out_dir_path.get()
                self.last_output_dir = od
                preset_key = self.crp_preset.get()
                mode = "cover" if "cover" in self.crp_mode.get() else "fit"
                module_params = {"preset": preset_key, "crop_mode": mode}
                output_path = od
                task_name = f"图像裁剪 - {len(files)}个文件"
                task_id = self._add_task(task_name, "crop", {
                    "file_path": "", "output_path": output_path,
                    "files": files, "task_type": "crop",
                    "panel_name": "crop", "params": module_params
                })
                if task_id:
                    self._log_status(f"任务已添加到队列：{task_name}", "info")
                self._log_status(f"共添加 1 个图像裁剪任务", "info")
                return

            for fp in files:
                fn = os.path.basename(fp)
                nm = os.path.splitext(fn)[0]
                
                od = os.path.dirname(fp)
                dir_combo_attr = None
                dir_path_attr = None
                if t == "audio":
                    dir_combo_attr, dir_path_attr = "a_out_dir_combo", "a_out_dir_path"
                elif t == "image":
                    dir_combo_attr, dir_path_attr = "i_out_dir_combo", "i_out_dir_path"
                elif t == "doc":
                    dir_combo_attr, dir_path_attr = "d_out_dir_combo", "d_out_dir_path"
                elif t == "extract":
                    dir_combo_attr, dir_path_attr = "e_out_dir_combo", "e_out_dir_path"
                elif t == "compress":
                    dir_combo_attr, dir_path_attr = "c_out_dir_combo", "c_out_dir_path"
                elif t == "gif":
                    dir_combo_attr, dir_path_attr = "gif_out_dir_combo", "gif_out_dir_path"
                elif t == "pdf":
                    dir_combo_attr, dir_path_attr = "pdf_out_dir_combo", "pdf_out_dir_path"
                elif t == "compress_img":
                    dir_combo_attr, dir_path_attr = "ci_out_dir_combo", "ci_out_dir_path"
                elif t == "rename":
                    dir_combo_attr, dir_path_attr = "rn_out_dir_combo", "rn_out_dir_path"
                
                if dir_combo_attr and dir_path_attr:
                    if hasattr(self, dir_combo_attr) and hasattr(self, dir_path_attr):
                        combo = getattr(self, dir_combo_attr)
                        path_var = getattr(self, dir_path_attr)
                        if combo.get() == "自定义目录":
                            custom_path = path_var.get()
                            if custom_path:
                                od = custom_path
                self.last_output_dir = od
                
                output_path = ""
                
                if t == "audio":
                    fmt = self.a_fmt.get()
                    ext = SUPPORTED_AUDIO[fmt]
                    output_path = os.path.join(od, nm + ext)
                    module_params = {
                        "fmt": fmt,
                        "codec": {"MP3":"libmp3lame","AAC":"aac","FLAC":"flac","WAV":"pcm_s16le",
                                  "WMA":"wmav2","OGG":"libvorbis","M4A":"aac","AMR":"libopencore_amrnb","OPUS":"libopus"}.get(fmt),
                        "bitrate": self.a_br.get(),
                        "sample_rate": self.a_sr.get(),
                        "channels": self.a_ch.get(),
                        "volume": self.a_vol.get()
                    }
                elif t == "image":
                    ext = SUPPORTED_IMAGE[self.i_fmt.get()]
                    output_path = os.path.join(od, nm + ext)
                    module_params = {
                        "fmt": self.i_fmt.get(),
                        "quality": self.i_q.get(),
                        "size": self.i_sz.get(),
                        "watermark": self.i_watermark.get(),
                        "watermark_pos": self.i_watermark_pos.get(),
                        "rotate": self.i_rotate.get(),
                        "crop": self.i_crop.get(),
                        "grayscale": self.i_grayscale.get()
                    }
                elif t == "doc":
                    tgt = self.d_tgt.get()
                    ext = tgt.split("（")[0]
                    output_path = os.path.join(od, nm + ext)
                    module_params = {"target": tgt}
                elif t == "extract":
                    fmt = self.e_fmt.get()
                    ext = {"MP3":".mp3","AAC":".aac","FLAC":".flac","WAV":".wav"}[fmt]
                    output_path = os.path.join(od, nm + ext)
                    module_params = {"fmt": fmt, "bitrate": self.e_br.get()}
                elif t == "compress":
                    output_path = os.path.join(od, nm + "_compressed.mp4")
                    module_params = {"quality": self.c_q.get(), "resolution": self.c_res.get()}
                elif t == "gif":
                    output_path = os.path.join(od, nm + ".gif")
                    module_params = {
                        "width": self.gif_w.get(),
                        "fps": self.gif_fps.get(),
                        "start": self.gif_start.get(),
                        "duration": self.gif_dur.get()
                    }
                elif t == "pdf":
                    mode = self.pdf_mode.get()
                    if "合并" in mode:
                        output_path = os.path.join(od, "merged.pdf")
                    elif "拆分" in mode:
                        split_dir = os.path.join(od, nm + "_split")
                        os.makedirs(split_dir, exist_ok=True)
                        output_path = split_dir
                    elif "加密" in mode:
                        output_path = os.path.join(od, nm + "_encrypted.pdf")
                    elif "解密" in mode:
                        output_path = os.path.join(od, nm + "_decrypted.pdf")
                    elif "压缩" in mode:
                        output_path = os.path.join(od, nm + "_compressed.pdf")
                    elif "水印" in mode:
                        output_path = os.path.join(od, nm + "_watermarked.pdf")
                    elif "页码" in mode:
                        output_path = os.path.join(od, nm + "_numbered.pdf")
                    else:
                        output_path = os.path.join(od, nm + ".pdf")
                    module_params = {
                        "mode": mode,
                        "range": self.pdf_range.get() if hasattr(self, 'pdf_range') else "",
                        "open_pwd": self.pdf_open_pwd.get() if hasattr(self, 'pdf_open_pwd') else "",
                        "owner_pwd": self.pdf_owner_pwd.get() if hasattr(self, 'pdf_owner_pwd') else "",
                        "encrypt_method": self.pdf_encrypt_method.get() if hasattr(self, 'pdf_encrypt_method') else "",
                        "decrypt_pwd": self.pdf_decrypt_pwd.get() if hasattr(self, 'pdf_decrypt_pwd') else "",
                        "compress_dpi": self.pdf_compress_dpi.get() if hasattr(self, 'pdf_compress_dpi') else "",
                        "compress_quality": self.pdf_compress_quality.get() if hasattr(self, 'pdf_compress_quality') else "",
                        "wm_text": self.pdf_wm_text.get() if hasattr(self, 'pdf_wm_text') else "",
                        "wm_pos": self.pdf_wm_pos.get() if hasattr(self, 'pdf_wm_pos') else "居中",
                        "wm_opacity": float(self.pdf_wm_opacity.get().replace("°","")) if hasattr(self, 'pdf_wm_opacity') else 0.3,
                        "wm_rotate": int(self.pdf_wm_rotate.get().replace("°","")) if hasattr(self, 'pdf_wm_rotate') else 0,
                        "pn_start": int(self.pdf_pn_start.get()) if hasattr(self, 'pdf_pn_start') and self.pdf_pn_start.get().isdigit() else 1,
                        "pn_pos": self.pdf_pn_pos.get() if hasattr(self, 'pdf_pn_pos') else "底部居中",
                        "pn_fmt": self.pdf_pn_fmt.get() if hasattr(self, 'pdf_pn_fmt') else "{n}",
                    }
                elif t == "compress_img":
                    ext = os.path.splitext(fn)[1]
                    output_path = os.path.join(od, nm + "_compressed" + ext)
                    module_params = {"quality": self.ci_q.get(), "size": self.ci_sz.get()}
                elif t == "rename":
                    output_path = od
                    case_map = {"不转换": "none", "全大写": "upper", "全小写": "lower", "首字母大写": "title"}
                    module_params = {
                        "pattern": self.rn_pattern.get(),
                        "start": self.rn_start.get(),
                        "search": self.rn_search.get() if hasattr(self, 'rn_search') else "",
                        "replace": self.rn_replace.get() if hasattr(self, 'rn_replace') else "",
                        "case": case_map.get(self.rn_case.get() if hasattr(self, 'rn_case') else "不转换", "none"),
                        "regex_pattern": self.rn_regex.get() if hasattr(self, 'rn_regex') else "",
                        "regex_replace": self.rn_regex_replace.get() if hasattr(self, 'rn_regex_replace') else "",
                    }
                elif t == "ocr":
                    od = os.path.dirname(fp)
                    if hasattr(self, 'ocr_out_dir_combo') and self.ocr_out_dir_combo.get() == "自定义目录" and self.ocr_out_dir_path.get():
                        od = self.ocr_out_dir_path.get()
                    self.last_output_dir = od
                    output_path = os.path.join(od, nm + ".txt")
                    module_params = {"lang": self.ocr_lang.get()}
                else:
                    module_params = {}
                
                if t != "rename":
                    is_pdf_split = (t == "pdf" and hasattr(self, 'pdf_mode') and "拆分" in self.pdf_mode.get())
                    if not is_pdf_split:
                        if output_path and output_path.lower() == fp.lower():
                            base, ext = os.path.splitext(output_path)
                            output_path = base + "_1" + ext

                        if output_path and os.path.exists(output_path):
                            base, ext = os.path.splitext(output_path)
                            counter = 1
                            while os.path.exists(f"{base}_{counter}{ext}"):
                                counter += 1
                            output_path = f"{base}_{counter}{ext}"
            
                task_name = f"{task_names.get(t, t)} - {fn}"
                task_id = self._add_task(task_name, t, {
                    "file_path": fp,
                    "output_path": output_path,
                    "files": [fp],
                    "task_type": t,
                    "panel_name": t,
                    "params": module_params
                })
                
                if task_id:
                    self._log_status(f"任务已添加到队列：{task_name}", "info")
            
            self._log_status(f"共添加 {len(files)} 个{task_names.get(t, t)}任务", "info")

    def _stop(self, t):
        self.converting = False
        while not self.task_queue.empty():
            try: self.task_queue.get_nowait()
            except: break
        self.active_task_count = 0
        if t in ("video","compress","extract","gif"): self.video_conv.cancel()
        elif t == "audio":  self.audio_conv.cancel()
        elif t == "image":  self.image_conv.cancel()
        elif t == "doc":    self.doc_conv.cancel()
        elif t == "download" and hasattr(self, 'dl_obj'): self.dl_obj.cancel()
        elif t == "m3u8": self.m3u8_dl.cancel()
        for task in self.tasks:
            if task["status"] in ("waiting", "processing"):
                self._update_task_status(task["id"], "failed", 0)
        self._disable_all_panels(disable=False)
        w = self._w(t)
        if w and "pg" in w: w["pg"].configure(value=0)
        if w and "st" in w: w["st"].configure(text="已取消")
        if w and "go" in w: w["go"].configure(state=tk.NORMAL)
        if w and "ca" in w: w["ca"].configure(state=tk.DISABLED)

    def _on_close(self):
        if hasattr(self, 'current_tab') and self.current_tab.get():
            self._save_panel_prefs(self.current_tab.get())
        self.root.destroy()

    def _check_update(self):
        """后台线程检查 GitHub 最新版本
        风险规避：所有网络请求 try...except 包裹，超时或失败时静默忽略，绝不阻塞 UI 启动。
        """
        GITHUB_REPO = "Gu-0312/FormatMaster-EN"
        def check():
            try:
                import urllib.request
                import urllib.error
                import json
                import socket
                # 设置 socket 全局超时，作为 urlopen timeout 的兜底
                socket.setdefaulttimeout(5)
                url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
                req = urllib.request.Request(url, headers={
                    "User-Agent": "FormatMaster",
                    "Accept": "application/vnd.github+json"
                })
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                    latest_version = (data.get("tag_name") or "").lstrip("vV")
                    if latest_version and self._version_gt(latest_version, APP_VERSION):
                        USER_PREFS.set("global", "new_version", latest_version)
                        USER_PREFS.set("global", "update_url",
                                       data.get("html_url") or
                                       f"https://github.com/{GITHUB_REPO}/releases/latest")
                        self.root.after(0, self._show_update_notification)
            except urllib.error.URLError:
                # 网络错误：静默忽略
                pass
            except socket.timeout:
                # 超时：静默忽略
                pass
            except Exception:
                # 其他异常：静默忽略，绝不阻塞启动
                pass
        threading.Thread(target=check, daemon=True).start()

    @staticmethod
    def _version_gt(v1, v2):
        import re
        try:
            def clean(v):
                # 提取纯数字部分，过滤掉 beta 等非数字后缀
                return [int(x) for x in re.findall(r'\d+', v)]
            parts1 = clean(v1)
            parts2 = clean(v2)
            while len(parts1) < len(parts2):
                parts1.append(0)
            while len(parts2) < len(parts1):
                parts2.append(0)
            return parts1 > parts2
        except Exception:
            return False

    def _show_update_notification(self):
        new_version = USER_PREFS.get("global", "new_version")
        if new_version:
            def show():
                try:
                    # 去重：移除已有的通知条
                    if hasattr(self, '_update_bar') and self._update_bar and self._update_bar.winfo_exists():
                        self._update_bar.destroy()
                    self._update_bar = tk.Frame(self.root, bg=D["accent_pale"], padx=16, pady=8)
                    self._update_bar.pack(fill=tk.X)
                    tk.Label(self._update_bar, text=f"发现新版本 v{new_version}，点击前往下载",
                             bg=D["accent_pale"], fg=D["accent"], font=SM).pack(side=tk.LEFT)
                    update_url = USER_PREFS.get("global", "update_url", "")
                    if not update_url:
                        update_url = "https://github.com/Gu-0312/FormatMaster-EN/releases/latest"
                    self._btn(self._update_bar, "下载", lambda: webbrowser.open(update_url),
                              style="ghost", padx=8).pack(side=tk.RIGHT)
                    close_btn = self._btn(self._update_bar, "×", lambda: self._update_bar.destroy(),
                                          style="ghost", padx=4)
                    close_btn.pack(side=tk.RIGHT, padx=(8, 0))
                except Exception:
                    pass
            self.root.after(1000, show)

    def run(self):
        self.root.mainloop()


def main():
    FormatMaster().run()

if __name__ == "__main__":
    main()
