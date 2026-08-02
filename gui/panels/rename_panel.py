"""Rename panel — 批量重命名面板（DI 化，第 4 个迁移面板）。

按 audio 模板执行：把 main.py:_p_rename 的 UI 构建逻辑搬到这里，
状态从 self.rn_xxx 迁移到独立的 RenameContext dataclass，build 拆分为细分内部方法。

rename 面板比 audio/extract 复杂：含命名模板 + 查找替换 + 高级正则替换三块设置，
且有特有的业务逻辑方法 _rn_calc_name / _rn_start（留 main.py，通过 shim 访问控件）。

兼容策略与 audio 一致：FormatMaster._p_rename 改为薄代理，调用本类的 build() 后，
把 context 中的控件以别名（self.rn_pattern = context.pattern）回填到 self，
让 _rn_calc_name / _rn_start / _save_panel_prefs / _w / _bar 等旧代码无感继续工作。
"""
from dataclasses import dataclass
from typing import Optional
import tkinter as tk
from tkinter import ttk

from app.context import AppContext, PanelContext
from gui.panels.base_panel import BasePanel

# main 模块的 D/FT/XS/SM/BODY 是可变全局（暗色主题运行时改写 D[k]）。
# 本模块由 main._p_rename 延迟导入，此时 main 已完整加载，import 安全。
import main as _main

# 大小写：UI 中文显示值 → 调度层英文枚举值（与 main.py:_go 的 rename 分支一致）
CASE_MAP = {"不转换": "none", "全大写": "upper", "全小写": "lower", "首字母大写": "title"}

# 命名模板预置值（与 main.py:_p_rename 的 rn_pattern.configure(values=...) 一致）
PATTERN_VALUES = [
    "文件_{n:03d}",
    "{name}_压缩",
    "{name}_{date}",
    "{name}_{time}",
    "{folder}_{name}",
    "{name}_new",
    "IMG_{n:04d}",
    "{date}_{name}",
]


@dataclass
class RenameContext(PanelContext):
    """批量重命名面板状态。

    替代 _panel_attrs["rename"] 中的 11 个属性 + _w/_bar 引用的 4 个进度控件。
    """
    panel_key: str = "rename"

    # 命名规则
    pattern: Optional[ttk.Combobox] = None
    start: Optional[ttk.Combobox] = None

    # 查找替换
    search: Optional[tk.Entry] = None
    replace: Optional[tk.Entry] = None
    case: Optional[ttk.Combobox] = None

    # 高级正则替换
    regex: Optional[tk.Entry] = None
    regex_replace: Optional[tk.Entry] = None

    # 输出目录
    out_dir_combo: Optional[ttk.Combobox] = None
    out_dir_btn: Optional[tk.Widget] = None
    out_dir_label: Optional[tk.Widget] = None
    out_dir_path: Optional[tk.StringVar] = None

    # 底部进度栏控件（_w("rename") 通过 shim 命中）
    pg: Optional[ttk.Progressbar] = None
    st: Optional[tk.Label] = None
    go: Optional[tk.Widget] = None
    ca: Optional[tk.Widget] = None


class RenamePanel(BasePanel):
    panel_key = "rename"
    context_cls = RenameContext

    def build(self) -> tk.Widget:
        """构建批量重命名面板 UI。

        按 audio 模板：实例化 context，委托给细分的内部方法构建各区域，
        最后注册到 AppContext。
        """
        D = _main.D
        app = self.ctx._app  # FormatMaster 实例，用于复用 UI 原语与回调

        p = tk.Frame(app.content, bg=D["page"])
        self.frame = p
        app.panels["rename"] = p

        c = RenameContext()
        self.context = c

        self._build_header(p)
        self._build_file_section(p)
        self._build_naming_card(p, c, app)
        self._build_bottom_bar(p, c, app)

        self.ctx.register_panel("rename", c)
        return p

    # ── UI 分区构建（细分内部方法）─────────────────
    def _build_header(self, parent: tk.Frame) -> None:
        app = self.ctx._app
        app._hdr(parent, "批量重命名", "统一添加前缀/后缀、序号命名、正则替换等")

    def _build_file_section(self, parent: tk.Frame) -> None:
        app = self.ctx._app
        app._file_sec(parent, "rename", [("所有文件", "*.*")])

    def _build_naming_card(self, parent: tk.Frame, c: RenameContext, app) -> None:
        """构建"命名规则"卡片：模板 + 起始序号 + 查找替换 + 高级正则 + 输出目录。

        rename 的设置较多，故拆为 _build_pattern_row / _build_search_replace
        / _build_regex_replace / _build_output_dir 四个子方法，各自布局到卡片内。
        """
        D = _main.D
        XS = _main.XS

        s = app._card(parent, "命名规则")
        # 占位符提示
        tk.Label(s, text="占位符：{n}=序号  {name}=原名  {ext}=扩展名  {date}=日期  {time}=时间  {folder}=文件夹",
                 bg=D["card"], fg=D["ink_dis"], font=XS).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        self._build_pattern_row(s, c, app)
        opt_card = self._build_search_replace(s, c, app)
        self._build_regex_replace(opt_card, c, app)
        self._build_output_dir(s, c, app)

    def _build_pattern_row(self, card: tk.Frame, c: RenameContext, app) -> None:
        """命名模板 + 起始序号（布局到卡片 row 1）。"""
        c.pattern = app._row(card, "命名模板", [], "文件_{n:03d}", 22)
        c.pattern.configure(values=PATTERN_VALUES)
        c.start = app._row(card, "起始序号", ["1", "0", "100"], "1")

    def _build_search_replace(self, card: tk.Frame, c: RenameContext, app) -> tk.Frame:
        """查找替换区（布局到卡片 row 2，含子 frame opt_card）。

        返回 opt_card 供 _build_regex_replace 复用（高级正则区挂在同一 opt_card 内）。
        """
        D = _main.D
        SM = _main.SM
        BODY = _main.BODY
        FT = _main.FT

        opt_card = tk.Frame(card, bg=D["card"])
        opt_card.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        card.columnconfigure(0, weight=1)

        tk.Label(opt_card, text="查找替换", bg=D["card"], fg=D["ink_sec"],
                 font=(FT, 9, "bold")).pack(anchor=tk.W, padx=5, pady=(4, 4))

        sr_row = tk.Frame(opt_card, bg=D["card"])
        sr_row.pack(fill=tk.X, padx=5)
        tk.Label(sr_row, text="查找", bg=D["card"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(0, 4))
        c.search = tk.Entry(sr_row, font=BODY, bg=D["input_bg"], fg=D["ink"],
                            relief="flat", highlightthickness=1,
                            highlightbackground=D["input_bd"], width=14)
        c.search.pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(sr_row, text="替换为", bg=D["card"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(0, 4))
        c.replace = tk.Entry(sr_row, font=BODY, bg=D["input_bg"], fg=D["ink"],
                             relief="flat", highlightthickness=1,
                             highlightbackground=D["input_bd"], width=14)
        c.replace.pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(sr_row, text="大小写", bg=D["card"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(8, 4))
        c.case = ttk.Combobox(sr_row, values=["不转换", "全大写", "全小写", "首字母大写"],
                              state="readonly", width=10)
        c.case.set("不转换")
        c.case.pack(side=tk.LEFT)
        return opt_card

    def _build_regex_replace(self, opt_card: tk.Frame, c: RenameContext, app) -> None:
        """高级正则替换区（布局到 opt_card 内，需 _build_search_replace 先创建并返回 opt_card）。"""
        D = _main.D
        SM = _main.SM
        FT = _main.FT

        # 分隔线
        tk.Frame(opt_card, bg=D["border"], height=1).pack(fill=tk.X, padx=5, pady=(8, 6))
        tk.Label(opt_card, text="高级替换（正则）", bg=D["card"], fg=D["ink_sec"],
                 font=(FT, 9, "bold")).pack(anchor=tk.W, padx=5, pady=(0, 4))

        adv_row = tk.Frame(opt_card, bg=D["card"])
        adv_row.pack(fill=tk.X, padx=5)
        tk.Label(adv_row, text="查找内容", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT)
        c.regex = tk.Entry(adv_row, font=("Consolas", 10), bg=D["input_bg"], fg=D["ink"],
                           relief="flat", highlightthickness=1,
                           highlightbackground=D["input_bd"], width=14)
        c.regex.pack(side=tk.LEFT, padx=(4, 8))

        tk.Label(adv_row, text="替换为", bg=D["card"], fg=D["ink"], font=SM).pack(side=tk.LEFT)
        c.regex_replace = tk.Entry(adv_row, font=("Consolas", 10), bg=D["input_bg"], fg=D["ink"],
                                   relief="flat", highlightthickness=1,
                                   highlightbackground=D["input_bd"], width=14)
        c.regex_replace.pack(side=tk.LEFT, padx=(4, 8))

    def _build_output_dir(self, card: tk.Frame, c: RenameContext, app) -> None:
        """输出目录区（布局到卡片 row 3）。"""
        D = _main.D
        SM = _main.SM
        XS = _main.XS

        out_frame = tk.Frame(card, bg=D["card"])
        out_frame.grid(row=3, column=0, columnspan=3, sticky="ew", padx=16, pady=(8, 10))
        tk.Label(out_frame, text="输出目录", bg=D["card"], fg=D["ink"], font=SM).pack(
            side=tk.LEFT, padx=(0, 8))
        c.out_dir_combo = ttk.Combobox(out_frame, values=["与源文件同目录", "自定义目录"],
                                       state="readonly", width=14)
        c.out_dir_combo.set("与源文件同目录")
        c.out_dir_combo.pack(side=tk.LEFT)
        c.out_dir_btn = app._btn(out_frame, "浏览",
                                  lambda: app._select_out_dir("rename"), style="secondary")
        c.out_dir_btn.pack(side=tk.LEFT, padx=(8, 0))
        c.out_dir_path = tk.StringVar(value="")
        c.out_dir_label = tk.Label(out_frame, textvariable=c.out_dir_path,
                                    bg=D["card"], fg=D["ink_dis"], font=XS)
        c.out_dir_label.pack(side=tk.LEFT, padx=(8, 0))

    def _build_bottom_bar(self, parent: tk.Frame, c: RenameContext, app) -> None:
        """构建底部进度栏 + 操作按钮。

        rename 的 go 按钮文案改为"开始重命名"，回调是 _rn_start（含确认对话框），
        而非直接 _go("rename")。
        """
        c.pg, c.st, c.go, c.ca, _ = app._bar(parent)
        c.go.configure(text="开始重命名", command=app._rn_start)
        c.ca.configure(command=lambda: app._stop("rename"))

    # ── 参数收集（供 _go / _batch_convert_from_detect 调度使用）──────────
    def collect_params(self) -> dict:
        """返回调度层期望的参数（8 键，与 main.py:_go 的 rename 分支构建的 dict 一致）。

        case 字段做中文→英文转换（"不转换"→"none"），与 _go 原始 case_map 逻辑一致。
        _run_task_general 的 rename 分支直接读 module_params.get("case") 传给 batch_rename，
        故此处必须返回英文枚举值。
        """
        c = self.context
        return {
            "pattern": c.pattern.get(),
            "start": c.start.get(),
            "search": c.search.get(),
            "replace": c.replace.get(),
            "case": CASE_MAP.get(c.case.get(), "none"),
            "regex_pattern": c.regex.get(),
            "regex_replace": c.regex_replace.get(),
        }

    # ── 偏好持久化 ──────────────────────────────────
    def collect_prefs(self) -> dict:
        """返回持久化偏好（与原 _save_panel_prefs 的 rename 分支一致）。

        case 存中文显示值（"不转换"），与 UI 一致，便于 _load 时直接 set 回 combobox。
        不含 regex/regex_replace（原 _save_panel_prefs 未持久化这两个，保持兼容）。
        """
        c = self.context
        return {
            "pattern": c.pattern.get(),
            "start": c.start.get(),
            "search": c.search.get(),
            "replace": c.replace.get(),
            "case": c.case.get(),
            "out_dir_combo": c.out_dir_combo.get(),
            "out_dir_path": c.out_dir_path.get(),
        }

    def apply_prefs(self, prefs: dict) -> None:
        """从持久化 prefs 恢复控件状态（与原 _load_panel_prefs 的 rename 分支一致）。

        Entry 控件需 delete+insert，不能直接 set。
        """
        c = self.context
        if prefs.get("pattern"):     c.pattern.set(prefs["pattern"])
        if prefs.get("start"):       c.start.set(prefs["start"])
        if prefs.get("search"):
            c.search.delete(0, tk.END)
            c.search.insert(0, prefs["search"])
        if prefs.get("replace"):
            c.replace.delete(0, tk.END)
            c.replace.insert(0, prefs["replace"])
        if prefs.get("case"):        c.case.set(prefs["case"])
        if prefs.get("out_dir_combo"): c.out_dir_combo.set(prefs["out_dir_combo"])
        if prefs.get("out_dir_path"):  c.out_dir_path.set(prefs["out_dir_path"])
