"""Pdf panel — PDF 工具面板（DI 化，第 7 个迁移面板）。

按 gif/compress 模板执行：把 main.py:_p_pdf 的 UI 构建逻辑搬到这里，
状态从 self.pdf_xxx 迁移到独立的 PdfContext dataclass，build 拆分为细分内部方法。

pdf 面板是迄今最复杂的面板：含合并/拆分/加密/解密/压缩/水印/页码 7 种模式，
每种模式有独立的子区 frame，通过 _mode_changed 切换显隐。
原 main.py:_pdf_mode_changed 也搬到本类（只引用 pdf frame + pdf_mode）。

兼容策略与前面面板一致：FormatMaster._p_pdf 改为薄代理，调用本类的 build() 后，
把 context 中的控件以别名回填到 self，让 _save_panel_prefs / _load_panel_prefs /
_w / _go / _show_pwd_history 等旧代码无感继续工作。

留在 main.py 不迁移的方法（靠 shim 访问 pdf 控件）：
  - _open_pdf_editor：编辑器按钮回调，引用 self.root，非 pdf 控件
  - _show_pwd_history：密码历史窗口，读 self.pdf_open_pwd/owner_pwd 作初始值
  - _save_pwd_history：加密成功后保存密码历史
"""
from dataclasses import dataclass
from typing import Optional
import tkinter as tk
from tkinter import ttk

from app.context import AppContext, PanelContext
from gui.panels.base_panel import BasePanel

# main 模块的 D/FT/XS/SM/BODY 是可变全局（暗色主题运行时改写 D[k]）。
# 本模块由 main._p_pdf 延迟导入，此时 main 已完整加载，import 安全。
import main as _main


# 操作模式预置值（与 main.py:_p_pdf 原始值一致）
MODE_VALUES = [
    "合并（多个→一个）",
    "拆分（一个→多个）",
    "加密（设置密码）",
    "解密（移除密码）",
    "压缩",
    "添加水印",
    "添加页码",
]


@dataclass
class PdfContext(PanelContext):
    """PDF 工具面板状态。

    替代 _panel_attrs["pdf"] 中的 25 个属性 + _w/_bar 引用的 4 个进度控件。
    含 7 个模式子区 frame，通过 _mode_changed 切换显隐。
    """
    panel_key: str = "pdf"

    # 模式切换
    mode: Optional[ttk.Combobox] = None

    # 拆分设置
    range_frame: Optional[tk.Frame] = None
    range: Optional[tk.Entry] = None

    # 加密设置
    encrypt_frame: Optional[tk.Frame] = None
    open_pwd: Optional[tk.Entry] = None
    owner_pwd: Optional[tk.Entry] = None
    encrypt_method: Optional[ttk.Combobox] = None

    # 解密设置
    decrypt_frame: Optional[tk.Frame] = None
    decrypt_pwd: Optional[tk.Entry] = None

    # 压缩设置
    compress_frame: Optional[tk.Frame] = None
    compress_dpi: Optional[ttk.Combobox] = None
    compress_quality: Optional[ttk.Combobox] = None

    # 水印设置
    wm_frame: Optional[tk.Frame] = None
    wm_text: Optional[tk.Entry] = None
    wm_pos: Optional[ttk.Combobox] = None
    wm_opacity: Optional[ttk.Combobox] = None
    wm_rotate: Optional[ttk.Combobox] = None

    # 页码设置
    pn_frame: Optional[tk.Frame] = None
    pn_start: Optional[tk.Entry] = None
    pn_pos: Optional[ttk.Combobox] = None
    pn_fmt: Optional[tk.Entry] = None

    # 输出目录
    out_dir_combo: Optional[ttk.Combobox] = None
    out_dir_btn: Optional[tk.Widget] = None
    out_dir_path: Optional[tk.StringVar] = None
    out_dir_label: Optional[tk.Widget] = None

    # 底部进度栏控件（_w("pdf") 通过 shim 命中）
    pg: Optional[ttk.Progressbar] = None
    st: Optional[tk.Label] = None
    go: Optional[tk.Widget] = None
    ca: Optional[tk.Widget] = None


class PdfPanel(BasePanel):
    panel_key = "pdf"
    context_cls = PdfContext

    def build(self) -> tk.Widget:
        """构建 PDF 工具面板 UI。

        按 gif/compress 模板：实例化 context，委托给细分的内部方法构建各区域，
        最后注册到 AppContext。pdf 面板含 7 个模式子区，每个子区独立构建。
        """
        D = _main.D
        app = self.ctx._app  # FormatMaster 实例，用于复用 UI 原语与回调

        p = tk.Frame(app.content, bg=D["page"])
        self.frame = p
        app.panels["pdf"] = p

        c = PdfContext()
        self.context = c

        self._build_header(p)
        self._build_file_section(p)
        s = self._build_settings_card(p, c, app)
        self._build_mode_row(s, c, app)
        self._build_split_section(s, c)
        self._build_encrypt_section(s, c, app)
        self._build_decrypt_section(s, c)
        self._build_compress_section(s, c)
        self._build_watermark_section(s, c)
        self._build_page_number_section(s, c)
        self._build_output_dir(s, c, app)
        self._build_bottom_bar(p, c, app)

        self.ctx.register_panel("pdf", c)
        return p

    # ── UI 分区构建（细分内部方法）─────────────────
    def _build_header(self, parent: tk.Frame) -> None:
        app = self.ctx._app
        app._hdr(parent, "PDF 工具", "合并、拆分、加密、解密、压缩")

    def _build_file_section(self, parent: tk.Frame) -> None:
        app = self.ctx._app
        app._file_sec(parent, "pdf", [("PDF文件", "*.pdf"), ("所有文件", "*.*")])

    def _build_settings_card(self, parent: tk.Frame, c: PdfContext, app) -> tk.Frame:
        """创建"操作设置"卡片，返回卡片 frame 供后续子区挂载。"""
        return app._card(parent, "操作设置")

    def _build_mode_row(self, card: tk.Frame, c: PdfContext, app) -> None:
        """构建模式切换行：操作模式下拉 + 编辑器按钮（靠右）。"""
        D = _main.D
        BODY = _main.BODY

        mode_row = tk.Frame(card, bg=D["card"])
        mode_row.pack(fill=tk.X, pady=(0, 12))

        tk.Label(mode_row, text="操作模式", bg=D["card"], fg=D["ink"],
                 font=BODY).pack(side=tk.LEFT, padx=(0, 8))
        c.mode = ttk.Combobox(mode_row, values=MODE_VALUES, state="readonly", width=22)
        c.mode.set("合并（多个→一个）")
        c.mode.pack(side=tk.LEFT)
        c.mode.bind("<<ComboboxSelected>>", lambda e: self._mode_changed())

        # 编辑按钮 - 靠右
        edit_btn = tk.Button(mode_row, text="✏️ 编辑器", font=(BODY[0], BODY[1], "bold"),
                             bg=D["accent"], fg=D["ink_inv"], relief="flat",
                             padx=12, pady=3, cursor="hand2",
                             activebackground=D["accent_deep"],
                             command=app._open_pdf_editor)
        edit_btn.pack(side=tk.RIGHT)

    def _build_split_section(self, card: tk.Frame, c: PdfContext) -> None:
        """构建拆分设置子区：页码范围输入框。初始 pack_forget 隐藏。"""
        D = _main.D
        BODY = _main.BODY
        XS = _main.XS

        c.range_frame = tk.Frame(card, bg=D["card"])
        tk.Label(c.range_frame, text="页码范围", bg=D["card"], fg=D["ink"],
                 font=BODY).pack(side=tk.LEFT, padx=(0, 8))
        c.range = tk.Entry(c.range_frame, font=BODY, bg=D["input_bg"], fg=D["ink"],
                           insertbackground=D["ink"], relief="flat", highlightthickness=1,
                           highlightbackground=D["input_bd"], highlightcolor=D["accent"])
        c.range.insert(0, "1-3,5,7-10")
        c.range.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(c.range_frame, text="示例: 1-3,5,7-10", bg=D["card"],
                 fg=D["ink_dis"], font=XS).pack(side=tk.LEFT, padx=(8, 0))
        c.range_frame.pack_forget()

    def _build_encrypt_section(self, card: tk.Frame, c: PdfContext, app) -> None:
        """构建加密设置子区：打开密码 + 权限密码 + 加密方式 + 密码历史按钮。

        含 _make_pwd_field 辅助方法创建密码输入字段（带眼睛切换显示）。
        初始 pack_forget 隐藏。
        """
        D = _main.D
        BODY = _main.BODY

        c.encrypt_frame = tk.Frame(card, bg=D["card"])

        # 密码行
        pwd_row = tk.Frame(c.encrypt_frame, bg=D["card"])
        pwd_row.pack(fill=tk.X, pady=(0, 8))

        c.open_pwd = self._make_pwd_field(pwd_row, "打开密码")
        c.owner_pwd = self._make_pwd_field(pwd_row, "权限密码")

        # 加密方式行
        method_row = tk.Frame(c.encrypt_frame, bg=D["card"])
        method_row.pack(fill=tk.X, pady=(0, 6))
        tk.Label(method_row, text="加密方式", bg=D["card"], fg=D["ink"], font=BODY).pack(side=tk.LEFT)
        c.encrypt_method = ttk.Combobox(method_row, values=["AES-256", "AES-128"],
                                       state="readonly", width=10)
        c.encrypt_method.set("AES-256")
        c.encrypt_method.pack(side=tk.LEFT, padx=(8, 16))

        tk.Button(method_row, text="📋 密码历史", font=BODY,
                  bg=D["card"], fg=D["accent"], relief="flat", cursor="hand2",
                  activebackground=D["card_alt"],
                  command=app._show_pwd_history).pack(side=tk.LEFT)

        c.encrypt_frame.pack_forget()

    def _make_pwd_field(self, parent: tk.Frame, label: str) -> tk.Entry:
        """创建密码输入字段（含眼睛按钮切换显示/隐藏）。

        原 main.py:_p_pdf 内的嵌套函数 make_pwd_field 用 setattr(self, attr_name, entry)
        设置属性；迁移后改为返回 entry，由调用方赋值给 context 字段。
        """
        D = _main.D
        BODY = _main.BODY

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
        return entry

    def _build_decrypt_section(self, card: tk.Frame, c: PdfContext) -> None:
        """构建解密设置子区：密码输入框 + 眼睛切换。初始 pack_forget 隐藏。"""
        D = _main.D
        BODY = _main.BODY

        c.decrypt_frame = tk.Frame(card, bg=D["card"])
        tk.Label(c.decrypt_frame, text="输入密码", bg=D["card"], fg=D["ink"],
                 font=BODY).pack(side=tk.LEFT, padx=(0, 8))
        c.decrypt_pwd = tk.Entry(c.decrypt_frame, font=BODY, bg=D["input_bg"], fg=D["ink"],
                                 insertbackground=D["ink"], relief="flat", highlightthickness=1,
                                 highlightbackground=D["input_bd"], highlightcolor=D["accent"],
                                 show="•", width=30)
        c.decrypt_pwd.pack(side=tk.LEFT)

        def toggle_decrypt_show():
            e = c.decrypt_pwd
            e.configure(show="" if e.cget("show") else "•")
        tk.Button(c.decrypt_frame, text="👁", font=("Segoe UI Symbol", 10),
                  bg=D["card"], relief="flat", cursor="hand2",
                  activebackground=D["card_alt"], bd=0,
                  command=toggle_decrypt_show).pack(side=tk.LEFT, padx=(4, 0))
        c.decrypt_frame.pack_forget()

    def _build_compress_section(self, card: tk.Frame, c: PdfContext) -> None:
        """构建压缩设置子区：目标分辨率 + 图片质量。初始 pack_forget 隐藏。"""
        D = _main.D
        BODY = _main.BODY

        c.compress_frame = tk.Frame(card, bg=D["card"])
        compress_row = tk.Frame(c.compress_frame, bg=D["card"])
        compress_row.pack(fill=tk.X)
        tk.Label(compress_row, text="目标分辨率", bg=D["card"], fg=D["ink"], font=BODY).pack(side=tk.LEFT)
        c.compress_dpi = ttk.Combobox(compress_row, values=["72dpi", "100dpi", "150dpi", "200dpi"],
                                      state="readonly", width=10)
        c.compress_dpi.set("150dpi")
        c.compress_dpi.pack(side=tk.LEFT, padx=(8, 16))
        tk.Label(compress_row, text="图片质量", bg=D["card"], fg=D["ink"], font=BODY).pack(side=tk.LEFT)
        c.compress_quality = ttk.Combobox(compress_row, values=["60", "70", "80", "90"],
                                          state="readonly", width=8)
        c.compress_quality.set("80")
        c.compress_quality.pack(side=tk.LEFT, padx=(8, 0))
        c.compress_frame.pack_forget()

    def _build_watermark_section(self, card: tk.Frame, c: PdfContext) -> None:
        """构建水印设置子区：水印文字 + 位置 + 透明度 + 旋转。初始 pack_forget 隐藏。"""
        D = _main.D
        BODY = _main.BODY

        c.wm_frame = tk.Frame(card, bg=D["card"])
        wm_row1 = tk.Frame(c.wm_frame, bg=D["card"])
        wm_row1.pack(fill=tk.X, pady=(0, 6))
        tk.Label(wm_row1, text="水印文字", bg=D["card"], fg=D["ink"], font=BODY).pack(side=tk.LEFT, padx=(0, 6))
        c.wm_text = tk.Entry(wm_row1, font=BODY, bg=D["input_bg"], fg=D["ink"],
                             insertbackground=D["ink"], relief="flat", highlightthickness=1,
                             highlightbackground=D["input_bd"], width=20)
        c.wm_text.insert(0, "机密")
        c.wm_text.pack(side=tk.LEFT)

        wm_row2 = tk.Frame(c.wm_frame, bg=D["card"])
        wm_row2.pack(fill=tk.X, pady=(2, 0))
        tk.Label(wm_row2, text="位置", bg=D["card"], fg=D["ink"], font=BODY).pack(side=tk.LEFT, padx=(0, 6))
        c.wm_pos = ttk.Combobox(wm_row2, values=["左上角", "右上角", "左下角", "右下角", "居中"],
                               state="readonly", width=8)
        c.wm_pos.set("居中")
        c.wm_pos.pack(side=tk.LEFT, padx=(0, 16))
        tk.Label(wm_row2, text="透明度", bg=D["card"], fg=D["ink"], font=BODY).pack(side=tk.LEFT)
        c.wm_opacity = ttk.Combobox(wm_row2, values=["0.1", "0.2", "0.3", "0.5", "0.7", "0.9"],
                                    state="readonly", width=6)
        c.wm_opacity.set("0.3")
        c.wm_opacity.pack(side=tk.LEFT, padx=(8, 16))
        tk.Label(wm_row2, text="旋转", bg=D["card"], fg=D["ink"], font=BODY).pack(side=tk.LEFT)
        c.wm_rotate = ttk.Combobox(wm_row2, values=["0°", "45°", "90°"],
                                  state="readonly", width=6)
        c.wm_rotate.set("0°")
        c.wm_rotate.pack(side=tk.LEFT, padx=(8, 0))
        c.wm_frame.pack_forget()

    def _build_page_number_section(self, card: tk.Frame, c: PdfContext) -> None:
        """构建页码设置子区：起始页码 + 位置 + 格式。初始 pack_forget 隐藏。"""
        D = _main.D
        BODY = _main.BODY
        XS = _main.XS

        c.pn_frame = tk.Frame(card, bg=D["card"])
        pn_row = tk.Frame(c.pn_frame, bg=D["card"])
        pn_row.pack(fill=tk.X)
        tk.Label(pn_row, text="起始页码", bg=D["card"], fg=D["ink"], font=BODY).pack(side=tk.LEFT, padx=(0, 6))
        c.pn_start = tk.Entry(pn_row, font=BODY, bg=D["input_bg"], fg=D["ink"],
                              insertbackground=D["ink"], relief="flat", highlightthickness=1,
                              highlightbackground=D["input_bd"], width=6)
        c.pn_start.insert(0, "1")
        c.pn_start.pack(side=tk.LEFT, padx=(0, 16))
        tk.Label(pn_row, text="位置", bg=D["card"], fg=D["ink"], font=BODY).pack(side=tk.LEFT)
        c.pn_pos = ttk.Combobox(pn_row, values=["底部居中", "底部左对齐", "底部右对齐", "顶部居中"],
                                state="readonly", width=12)
        c.pn_pos.set("底部居中")
        c.pn_pos.pack(side=tk.LEFT, padx=(8, 16))
        tk.Label(pn_row, text="格式", bg=D["card"], fg=D["ink"], font=BODY).pack(side=tk.LEFT)
        c.pn_fmt = tk.Entry(pn_row, font=BODY, bg=D["input_bg"], fg=D["ink"],
                            insertbackground=D["ink"], relief="flat", highlightthickness=1,
                            highlightbackground=D["input_bd"], width=12)
        c.pn_fmt.insert(0, "第{n}页")
        c.pn_fmt.pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(pn_row, text="{n}=页码", bg=D["card"], fg=D["ink_dis"], font=XS).pack(side=tk.LEFT, padx=(6, 0))
        c.pn_frame.pack_forget()

    def _build_output_dir(self, card: tk.Frame, c: PdfContext, app) -> None:
        """构建输出目录区（布局到卡片内）。"""
        D = _main.D
        BODY = _main.BODY
        XS = _main.XS

        out_frame = tk.Frame(card, bg=D["card"])
        out_frame.pack(fill=tk.X, padx=16, pady=(8, 10))
        tk.Label(out_frame, text="输出目录", bg=D["card"], fg=D["ink"], font=BODY).pack(
            side=tk.LEFT, padx=(0, 8))
        c.out_dir_combo = ttk.Combobox(out_frame, values=["与源文件同目录", "自定义目录"],
                                       state="readonly", width=14)
        c.out_dir_combo.set("与源文件同目录")
        c.out_dir_combo.pack(side=tk.LEFT)
        c.out_dir_btn = app._btn(out_frame, "浏览",
                                  lambda: app._select_out_dir("pdf"), style="secondary")
        c.out_dir_btn.pack(side=tk.LEFT, padx=(8, 0))
        c.out_dir_path = tk.StringVar(value="")
        c.out_dir_label = tk.Label(out_frame, textvariable=c.out_dir_path,
                                   bg=D["card"], fg=D["ink_dis"], font=XS)
        c.out_dir_label.pack(side=tk.LEFT, padx=(8, 0))

    def _build_bottom_bar(self, parent: tk.Frame, c: PdfContext, app) -> None:
        """构建底部进度栏 + 操作按钮。"""
        c.pg, c.st, c.go, c.ca, _ = app._bar(parent)
        c.go.configure(command=lambda: app._go("pdf"))
        c.ca.configure(command=lambda: app._stop("pdf"))

    # ── 模式切换（从 main._pdf_mode_changed 搬来）──────────
    def _mode_changed(self) -> None:
        """根据当前模式显隐对应的子区 frame。

        原 main.py:_pdf_mode_changed 的逻辑：先全部 pack_forget，
        再根据 mode 关键字显示对应子区。
        """
        c = self.context
        c.range_frame.pack_forget()
        c.encrypt_frame.pack_forget()
        c.decrypt_frame.pack_forget()
        c.compress_frame.pack_forget()
        c.wm_frame.pack_forget()
        c.pn_frame.pack_forget()

        mode = c.mode.get()
        if "拆分" in mode:
            c.range_frame.pack(fill=tk.X, pady=(8, 0))
        elif "加密" in mode:
            c.encrypt_frame.pack(fill=tk.X, pady=(8, 0))
        elif "解密" in mode:
            c.decrypt_frame.pack(fill=tk.X, pady=(8, 0))
        elif "压缩" in mode:
            c.compress_frame.pack(fill=tk.X, pady=(8, 0))
        elif "水印" in mode:
            c.wm_frame.pack(fill=tk.X, pady=(8, 0))
        elif "页码" in mode:
            c.pn_frame.pack(fill=tk.X, pady=(8, 0))

    # ── 参数收集（供 _go 调度使用）──────────
    def collect_params(self) -> dict:
        """返回调度层期望的参数（15 键，与 main.py:_go 的 pdf 分支一致）。

        含类型转换（与原 _go 内联逻辑一致）：
        - wm_opacity: float（去°，原值如 "0.3"）
        - wm_rotate: int（去°，原值如 "45°"）
        - pn_start: int（非数字时回退 1）
        其余键保持字符串原值，_run_task_general 的 pdf 分支按需自行转换。
        """
        c = self.context
        return {
            "mode": c.mode.get(),
            "range": c.range.get(),
            "open_pwd": c.open_pwd.get(),
            "owner_pwd": c.owner_pwd.get(),
            "encrypt_method": c.encrypt_method.get(),
            "decrypt_pwd": c.decrypt_pwd.get(),
            "compress_dpi": c.compress_dpi.get(),
            "compress_quality": c.compress_quality.get(),
            "wm_text": c.wm_text.get(),
            "wm_pos": c.wm_pos.get(),
            "wm_opacity": float(c.wm_opacity.get().replace("°", "")),
            "wm_rotate": int(c.wm_rotate.get().replace("°", "")),
            "pn_start": int(c.pn_start.get()) if c.pn_start.get().isdigit() else 1,
            "pn_pos": c.pn_pos.get(),
            "pn_fmt": c.pn_fmt.get(),
        }

    # ── 偏好持久化 ──────────────────────────────────
    def collect_prefs(self) -> dict:
        """返回持久化偏好（与原 _save_panel_prefs 的 pdf 分支一致，3 键）。

        原 _save 只持久化 mode + out_dir_combo + out_dir_path，
        各模式子区的参数不持久化（保持与原行为一致）。
        """
        c = self.context
        return {
            "mode": c.mode.get(),
            "out_dir_combo": c.out_dir_combo.get(),
            "out_dir_path": c.out_dir_path.get(),
        }

    def apply_prefs(self, prefs: dict) -> None:
        """从持久化 prefs 恢复控件状态（与原 _load_panel_prefs 的 pdf 分支一致）。

        设置 mode 后需调用 _mode_changed 显示对应子区（原 _load 逻辑）。
        """
        c = self.context
        if prefs.get("mode"):
            c.mode.set(prefs["mode"])
            self._mode_changed()
        if prefs.get("out_dir_combo"):
            c.out_dir_combo.set(prefs["out_dir_combo"])
        if prefs.get("out_dir_path"):
            c.out_dir_path.set(prefs["out_dir_path"])
