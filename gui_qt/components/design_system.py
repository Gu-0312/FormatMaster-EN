"""design_system — 格式大师 Prism 设计系统。

「棱镜光谱」视觉语言：indigo → violet → pink 渐变作为核心装饰元素，
隐喻「格式转换 = 光线棱镜变换」。亮色模式「暖纸棱镜」、暗色模式「午夜棱镜」。

提供：
- 色彩令牌（亮/暗双套，运行时按主题切换）
- QSS 样式表动态生成（滚动条/表格/菜单/日志/工具提示）
- QGraphicsDropShadowEffect 工厂
- HeroBanner 首页渐变横幅组件
- set_app_style() 全局样式应用入口
"""
from gui_qt.i18n import tr
from PySide6.QtCore import (QEasingCurve, QPointF, QPropertyAnimation,
                            Qt, QRectF)
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter,
                            QPen, QPainterPath)
from PySide6.QtWidgets import (QApplication, QGraphicsDropShadowEffect,
                                QHBoxLayout, QPushButton, QVBoxLayout,
                                QWidget)
from qfluentwidgets import (BodyLabel, CaptionLabel, FluentIcon, TitleLabel,
                            isDarkTheme, setThemeColor)

# ─────────────────────────────────────────────────────
#  圆角规范（全站统一两档）
# ─────────────────────────────────────────────────────
# RADIUS_CARD  = 12   卡片/表面类（面板、表格、列表、日志框、ActionBar）
# RADIUS_CTRL  = 8    交互控件（按钮/输入框/下拉/菜单，Fluent 标准）
# 小元素保留：滚动条 8、进度条 4、工具提示 6、图标方块按需
RADIUS_CARD = 12
RADIUS_CTRL = 8

# ─────────────────────────────────────────────────────
#  色彩令牌
# ─────────────────────────────────────────────────────

LIGHT = {
    "page_bg":        "#F3F4F8",
    "card_bg":        "#FFFFFF",
    "card_hover":     "#F7F7FD",
    "card_active":    "#EEF0FF",
    "table_bg":       "#FFFFFF",
    "table_alt":      "#F8F8FC",
    "accent":         "#5B5BD6",
    "accent_hover":   "#4A4ACF",
    "accent_soft":    "#7C7CF5",
    "accent_pale":    "#EDEEFF",
    "accent_deep":    "#3F3FB8",
    "ink":            "#1D1F2E",
    "ink_sec":        "#5F6472",
    "ink_dis":        "#9AA0AC",
    "border":         "#E3E5EC",
    "border_hi":      "#C9CDD8",
    "divider":        "#EFF0F5",
    "success":        "#0FA47A",
    "warn":           "#D98324",
    "error":          "#E5484D",
    "input_bg":       "#FFFFFF",
    "input_bd":       "#D9DCE4",
    "prog_trough":    "#ECEAF6",
    "table_header":   "#F6F7FB",
    "table_grid":     "#ECEEF4",
    "table_sel":      "#E9EBFF",
    "table_border":   "#DFE2EA",
    "scrollbar":      "#C7CBD6",
    "scrollbar_hv":   "#A8AEBC",
    "log_bg":         "#FAFBFD",
    "tooltip_bg":     "#232634",
    "tooltip_fg":     "#F4F5F9",
}

DARK = {
    "page_bg":        "#0E0F16",
    "card_bg":        "#161824",
    "card_hover":     "#1C1F2E",
    "card_active":    "#232544",
    "table_bg":       "#181A27",
    "table_alt":      "#1D2030",
    "accent":         "#8B8CF8",
    "accent_hover":   "#6F71F0",
    "accent_soft":    "#A5A7FF",
    "accent_pale":    "#3A3D5C",
    "accent_deep":    "#5A5CE0",
    "ink":            "#E6E8F2",
    "ink_sec":        "#9BA1B4",
    "ink_dis":        "#666C80",
    "border":         "#272B3A",
    "border_hi":      "#383D50",
    "divider":        "#1D2030",
    "success":        "#2FC99A",
    "warn":           "#F0A63A",
    "error":          "#F26D6D",
    "input_bg":       "#161824",
    "input_bd":       "#2B3040",
    "prog_trough":    "#202433",
    "table_header":   "#151724",
    "table_grid":     "#202433",
    "table_sel":      "#242649",
    "table_border":   "#34394B",
    "scrollbar":      "#383D50",
    "scrollbar_hv":   "#4A5065",
    "log_bg":         "#11131D",
    "tooltip_bg":     "#262B3C",
    "tooltip_fg":     "#E6E8F2",
}

# 棱镜渐变色（核心装饰元素）
PRISM_LIGHT = ["#5B5BD6", "#8B5CF6", "#EC4899"]
PRISM_DARK  = ["#8B8CF8", "#A78BFA", "#F472B6"]

# 分组色系（工具卡片分类标记）
GROUP_COLORS = {
    "media":  ("#5B5BD6", "#EDEEFF"),
    "edit":   ("#8B5CF6", "#F3E8FF"),
    "tool":   ("#0FA47A", "#DDF5EC"),
    "net":    ("#EA7A23", "#FFF1E5"),
    "manage": ("#5F6472", "#F0F1F5"),
    "convert": ("#5B5BD6", "#EDEEFF"),
    "audio":   ("#8B5CF6", "#F3E8FF"),
    "video":   ("#0284C7", "#E0F2FE"),
    "image":   ("#0FA47A", "#DDF5EC"),
    "doc":     ("#D98324", "#FEF1DE"),
}
GROUP_COLORS_DARK = {
    "media":  ("#8B8CF8", "#252747"),
    "edit":   ("#A78BFA", "#2A2050"),
    "tool":   ("#2FC99A", "#0D2A20"),
    "net":    ("#F59E4C", "#2A1A0A"),
    "manage": ("#9BA1B4", "#1E2230"),
    "convert": ("#8B8CF8", "#252747"),
    "audio":   ("#A78BFA", "#2A2050"),
    "video":   ("#38BDF8", "#082F49"),
    "image":   ("#2FC99A", "#0D2A20"),
    "doc":     ("#F0A63A", "#2A1A0A"),
}


# ─────────────────────────────────────────────────────
#  令牌访问器
# ─────────────────────────────────────────────────────

def tokens():
    """返回当前主题的色彩令牌字典。"""
    return DARK if isDarkTheme() else LIGHT


def is_dark():
    return isDarkTheme()


def accent():
    return tokens()["accent"]


def accent_hover():
    return tokens()["accent_hover"]


def page_bg():
    return tokens()["page_bg"]


def card_bg():
    return tokens()["card_bg"]


def border_color():
    return tokens()["border"]


def ink():
    return tokens()["ink"]


def ink_sec():
    return tokens()["ink_sec"]


def ink_dis():
    return tokens()["ink_dis"]


def prism_colors():
    """当前主题的棱镜渐变色列表。"""
    return PRISM_DARK if isDarkTheme() else PRISM_LIGHT


def group_colors(key):
    """返回 (前景色, 浅背景色) 用于分组标记。"""
    table = GROUP_COLORS_DARK if isDarkTheme() else GROUP_COLORS
    return table.get(key, table["manage"])


def group_color(name):
    """Map a navigation group name to its foreground color."""
    return group_colors(group_key_for_name(name))[0]


def group_key_for_name(name):
    """Resolve a navigation group name to a stable palette key."""
    from gui_qt.nav_registry import NAV_GROUPS
    keys = ["convert", "edit", "tool", "net", "manage"]
    for idx, (group_name, _items) in enumerate(NAV_GROUPS):
        if group_name == name and 0 < idx <= len(keys):
            return keys[idx - 1]
    return "manage"


def with_alpha(hex_color, alpha):
    """给十六进制颜色叠加透明度，返回 Qt 支持的颜色字符串。"""
    c = QColor(hex_color)
    c.setAlpha(alpha)
    return c.name(QColor.HexArgb)

# ─────────────────────────────────────────────────────
#  QSS 生成（预计算缓存）
# ─────────────────────────────────────────────────────

_QSS_CACHE = {}


def _build_qss(t):
    """用给定令牌字典生成 QSS（不依赖 isDarkTheme()）。"""
    parts = []

    # ── 窗口背景（FluentTitleBar 是透明背景，必须由 QSS 提供底色）──
    parts.append(f"""
    FluentWindow {{
        background: {t["page_bg"]};
    }}
    """)

    # ── 滚动区域（禁用动态调整大小，启用像素级平滑滚动）──
    parts.append(f"""
    QScrollArea {{
        background: {t["page_bg"]};
        border: none;
    }}
    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}
    QScrollArea QScrollBar:vertical,
    QScrollArea QScrollBar:horizontal {{
        background: transparent;
    }}
    """)

    # ── 面板底部操作栏（ActionBar）──
    # 背景色走全局 QSS，主题切换时自动刷新，避免实例级 setStyleSheet 快照残留
    parts.append(f"""
    #actionBar {{
        background: {t["card_bg"]};
        border: 1px solid {t["border"]};
        border-radius: 12px;
    }}
    """)

    # ── 原生滚动类控件：启用像素平滑滚动 ──
    parts.append(f"""
    QAbstractScrollArea, QListView, QTableView, QTreeView {{
    }}
    """)

    # ── 侧边导航栏 ──
    parts.append(f"""
    NavigationInterface {{
        border-right: 1px solid {t["border"]};
    }}
    """)

    # ── 滚动条 ──
    parts.append(f"""
    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {t["scrollbar"]};
        border-radius: 4px;
        min-height: 32px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {t["scrollbar_hv"]};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0; border: none;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 8px;
        margin: 0;
    }}
    QScrollBar::handle:horizontal {{
        background: {t["scrollbar"]};
        border-radius: 4px;
        min-width: 32px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {t["scrollbar_hv"]};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0; border: none;
    }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: transparent;
    }}
    """)

    # ── 工具提示 ──
    parts.append(f"""
    QToolTip {{
        background: {t["tooltip_bg"]};
        color: {t["tooltip_fg"]};
        border: 1px solid {t["border_hi"]};
        border-radius: 6px;
        padding: 5px 10px;
        font-size: 12px;
    }}
    """)

    # ── 菜单 ──
    parts.append(f"""
    QMenu {{
        background: {t["card_bg"]};
        color: {t["ink"]};
        border: 1px solid {t["border"]};
        border-radius: 8px;
        padding: 6px;
    }}
    QMenu::item {{
        background: transparent;
        padding: 7px 24px 7px 12px;
        border-radius: 6px;
        font-size: 13px;
    }}
    QMenu::item:selected {{
        background: {t["accent_pale"]};
        color: {t["ink"]};
    }}
    QMenu::separator {{
        height: 1px;
        background: {t["divider"]};
        margin: 5px 8px;
    }}
    """)

    # ── 输入框 ──
    # 样式化 QLineEdit 与 QTextEdit。qfluentwidgets 的 TextEdit 背景是
    # 半透明白（rgba(255,255,255,0.06)），其 viewport palette 在深色下
    # 可能残留白色，导致透出白色（URL 输入框显示为白/黑块）。这里显式
    # 设置主题背景色，覆盖该问题。
    parts.append(f"""
    QLineEdit {{
        background: {t["input_bg"]};
        color: {t["ink"]};
        border: 1px solid {t["input_bd"]};
        border-radius: 8px;
        padding: 6px 12px;
        selection-background-color: {t["accent_pale"]};
    }}
    QLineEdit:focus {{
        border: 1px solid {t["accent"]};
    }}
    QLineEdit:disabled {{
        background: {t["table_header"]};
        color: {t["ink_dis"]};
    }}
    TextEdit, QTextEdit, QPlainTextEdit {{
        background: {t["input_bg"]};
        color: {t["ink"]};
        border: 1px solid {t["input_bd"]};
        border-radius: 8px;
        padding: 6px 10px;
    }}
    QTextEdit::selection {{
        background: {t["accent_pale"]};
        color: {t["ink"]};
    }}
    TextEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
        border: 1px solid {t["accent"]};
    }}
    """)

    # ── 下拉框 ──
    parts.append(f"""
    QComboBox {{
        background: {t["input_bg"]};
        color: {t["ink"]};
        border: 1px solid {t["input_bd"]};
        border-radius: 8px;
        padding: 6px 12px;
        min-height: 22px;
    }}
    QComboBox:focus {{
        border: 1px solid {t["accent"]};
    }}
    QComboBox QAbstractItemView {{
        background: {t["card_bg"]};
        color: {t["ink"]};
        border: 1px solid {t["border"]};
        border-radius: 8px;
        selection-background-color: {t["accent_pale"]};
        selection-color: {t["ink"]};
        outline: none;
    }}
    """)

    # ── 按钮（非 qfluentwidgets 原生按钮）──
    parts.append(f"""
    QPushButton {{
        border-radius: 8px;
        padding: 7px 18px;
        font-size: 13px;
        font-weight: 600;
        border: 1px solid {t["border"]};
        background: {t["card_bg"]};
        color: {t["ink"]};
        min-height: 22px;
    }}
    QPushButton:hover {{
        background: {t["card_hover"]};
        border-color: {t["accent_soft"]};
    }}
    QPushButton:pressed {{
        background: {t["card_active"]};
    }}
    QPushButton:focus {{
        border: 1px solid {t["accent"]};
    }}
    QPushButton:disabled {{
        background: {t["table_header"]};
        color: {t["ink_dis"]};
        border-color: {t["border"]};
    }}
    QPushButton[accent="true"] {{
        background: {t["accent"]};
        color: #FFFFFF;
        border: none;
    }}
    QPushButton[accent="true"]:hover {{
        background: {t["accent_hover"]};
    }}
    QPushButton[accent="true"]:disabled {{
        background: {t["prog_trough"]};
        color: {t["ink_dis"]};
    }}
    """)

    # ── 勾选框 ──
    parts.append(f"""
    QCheckBox {{
        color: {t["ink_sec"]};
        font-size: 13px;
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 5px;
        border: 1px solid {t["input_bd"]};
        background: {t["input_bg"]};
    }}
    QCheckBox::indicator:checked {{
        background: {t["accent"]};
        border-color: {t["accent"]};
    }}
    QCheckBox::indicator:hover {{
        border-color: {t["accent_soft"]};
    }}
    """)

    # ── 列表（原生 QListWidget，如 PDF 缩略图网格）──
    parts.append(f"""
    QListWidget {{
        background: {t["table_bg"]};
        alternate-background-color: {t["table_alt"]};
        border: 1px solid {t["table_border"]};
        border-radius: 12px;
        outline: none;
        padding: 4px;
    }}
    QListWidget::item {{
        padding: 8px 10px;
        border: none;
        color: {t["ink"]};
        border-radius: 8px;
    }}
    QListWidget::item:hover {{
        background: {t["card_hover"]};
    }}
    QListWidget::item:selected {{
        background: {t["table_sel"]};
        color: {t["ink"]};
    }}
    QListWidget::item:selected:active {{
        background: {t["accent_pale"]};
    }}
    QListWidget::item:selected:!active {{
        background: {t["table_sel"]};
    }}
    """)

    # ── 表格 ──
    parts.append(f"""
    QTableWidget {{
        background: {t["table_bg"]};
        alternate-background-color: {t["table_alt"]};
        border: 1px solid {t["table_border"]};
        border-radius: 12px;
        gridline-color: {t["table_grid"]};
        outline: none;
    }}
    QTableWidget::item {{
        padding: 6px 10px;
        border: none;
        color: {t["ink"]};
    }}
    QTableWidget::item:hover {{
        background: {t["card_hover"]};
    }}
    QTableWidget::item:selected {{
        background: {t["table_sel"]};
        color: {t["ink"]};
    }}
    QHeaderView::section {{
        background: {t["table_header"]};
        color: {t["ink_sec"]};
        border: none;
        border-bottom: 1px solid {t["table_border"]};
        border-right: 1px solid {t["table_grid"]};
        padding: 9px 12px;
        font-weight: 600;
        font-size: 12px;
    }}
    QTableCornerButton::section {{
        background: {t["table_header"]};
        border: none;
        border-bottom: 1px solid {t["border"]};
    }}
    """)

    # ── 进度条 ──
    parts.append(f"""
    QProgressBar {{
        background: {t["prog_trough"]};
        border: none;
        border-radius: 3px;
        min-height: 4px;
        max-height: 6px;
        text-align: center;
        font-size: 9px;
        color: transparent;
    }}
    QProgressBar::chunk {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {t["accent"]},
            stop:1 {t["accent_soft"]});
        border-radius: 3px;
    }}
    """)

    # ── 日志查看器（#logView 专用，避免影响输入框 TextEdit）──
    parts.append(f"""
    QPlainTextEdit#logView {{
        background: {t["log_bg"]};
        color: {t["ink_sec"]};
        border: 1px solid {t["border"]};
        border-radius: 12px;
        padding: 10px 12px;
        font-family: "Cascadia Code", "Consolas", "Microsoft YaHei UI";
        font-size: 12px;
    }}
    QPlainTextEdit#logView::selection {{
        background: {t["accent_pale"]};
        color: {t["ink"]};
    }}
    QPlainTextEdit#logView:focus {{
        border: 1px solid {t["accent_soft"]};
    }}
    """)

    return "\n".join(parts)


def generate_qss():
    """返回当前主题的 QSS（预计算缓存，避免每次切换重复生成）。"""
    key = "dark" if isDarkTheme() else "light"
    if key not in _QSS_CACHE:
        t = DARK if key == "dark" else LIGHT
        _QSS_CACHE[key] = _build_qss(t)
    return _QSS_CACHE[key]


# 最近一次应用给窗口的 QSS（set_app_style 据此跳过无变化的重复刷新）
_last_applied_qss = None
# ─────────────────────────────────────────────────────

def apply_card_shadow(widget, blur=24, y_offset=4, alpha=18):
    """给 widget 添加柔和的 accent 色调阴影。"""
    c = QColor(accent())
    c.setAlpha(alpha)
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y_offset)
    effect.setColor(c)
    widget.setGraphicsEffect(effect)
    return effect


def apply_text_edit_style(edit):
    """给 qfluentwidgets TextEdit 显式设置主题背景与文字色。

    qfluentwidgets 的 TextEdit 实例样式是半透明白
    （rgba(255,255,255,0.06)），其 viewport palette 在深色模式下可能
    残留浅色，导致输入框背景与文字色不匹配（深底深字 / 浅底浅字，
    看不清输入内容）。QSS 的 color 对 QTextEdit viewport 文字色不可靠
    （Qt 会用 viewport 的 QPalette 渲染文字），必须同时设置 viewport
    的 QPalette 才能确保亮/暗主题下都可读。主题切换时需重新调用。
    """
    from PySide6.QtGui import QPalette
    t = tokens()
    bg = QColor(t["input_bg"])
    ink = QColor(t["ink"])
    ink_dis = QColor(t["ink_dis"])
    accent_pale = QColor(t["accent_pale"])

    # QPalette 必须先设，QSS 会覆盖 palette；selection 用 ::selection 选择器
    vp = edit.viewport()
    pal = QPalette(vp.palette())
    pal.setColor(QPalette.Window, bg)
    pal.setColor(QPalette.Base, bg)
    pal.setColor(QPalette.WindowText, ink)
    pal.setColor(QPalette.Text, ink)
    pal.setColor(QPalette.PlaceholderText, ink_dis)
    pal.setColor(QPalette.Highlight, accent_pale)
    pal.setColor(QPalette.HighlightedText, ink)
    vp.setPalette(pal)

    edit.setStyleSheet(
        f"TextEdit, QTextEdit, QPlainTextEdit {{" +
        f"background: {t['input_bg']};" +
        f"color: {t['ink']};" +
        f"border: 1px solid {t['input_bd']};" +
        f"border-radius: 8px;" +
        f"padding: 6px 10px;" +
        f"}}" +
        f"QTextEdit::selection {{" +
        f"background: {t['accent_pale']};" +
        f"color: {t['ink']};" +
        f"}}")


def apply_subtle_shadow(widget, blur=18, y_offset=2, alpha=12):
    """更淡的阴影，用于普通卡片。"""
    c = QColor("#000000")
    c.setAlpha(alpha)
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y_offset)
    effect.setColor(c)
    widget.setGraphicsEffect(effect)
    return effect


# ─────────────────────────────────────────────────────
#  全局样式应用
# ─────────────────────────────────────────────────────

_app_window = None


def set_app_window(window):
    """注册主窗口引用，供 set_app_style() 使用。"""
    global _app_window
    _app_window = window


def set_app_style():
    """应用 Prism 设计系统：设置主题色 + 应用预缓存 QSS + 修复窗口背景。

    主题切换时调用。FluentTitleBar 是透明背景，会透出 FluentWindow
    底层色。深色模式下必须强制设置窗口背景，否则显示为系统浅色。

    性能：qfluentwidgets 的 setTheme 已触发过一次 updateStyleSheet，
    这里用 qconfig 直接写入主题色配置（不触发第二次全量刷新），
    只应用窗口级 Prism QSS，避免每次切换两次全量重绘。
    """
    app = QApplication.instance()
    if app is None:
        return
    # 只更新主题色配置，不重复触发 updateStyleSheet（setTheme 已刷过）
    try:
        from qfluentwidgets import qconfig
        qconfig.set(qconfig.themeColor, QColor(accent()), save=False)
    except Exception:
        setThemeColor(accent(), lazy=True)
    target = _app_window if _app_window is not None else app
    qss = generate_qss()
    # 同主题重复切换时 QSS 内容不变，跳过 setStyleSheet 避免无谓的全量
    # 样式重算（约 180ms）；主题真正变化时才会重新应用。
    global _last_applied_qss
    if qss != _last_applied_qss:
        target.setStyleSheet(qss)
        _last_applied_qss = qss
    # 主题切换后刷新所有 TextEdit（qfluentwidgets 的半透明白样式在
    # 深色下会透出白色 viewport，需实例级覆盖）
    if _app_window is not None:
        _refresh_text_edits(_app_window)


def _refresh_text_edits(root):
    """遍历 root 下所有 TextEdit，重新应用主题背景样式。"""
    from qfluentwidgets import TextEdit
    for edit in root.findChildren(TextEdit):
        try:
            apply_text_edit_style(edit)
        except Exception:  # noqa: BLE001 - 单个控件失败不阻断
            pass


def enable_smooth_scrolling(root):
    """遍历 root 下所有滚动视图，启用像素级平滑滚动并优化速度。"""
    from PySide6.QtWidgets import QAbstractItemView, QAbstractScrollArea
    for sa in root.findChildren(QAbstractScrollArea):
        if hasattr(sa, 'setHorizontalScrollMode'):
            sa.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
            sa.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        # 优化 qfluentwidgets SmoothScrollDelegate 滚动速度
        if hasattr(sa, 'scrollDelagate') and sa.scrollDelagate:
            delegate = sa.scrollDelagate
            if hasattr(delegate, 'vScrollBar') and delegate.vScrollBar:
                delegate.vScrollBar.setScrollAnimation(120, QEasingCurve.OutCubic)
            if hasattr(delegate, 'hScrollBar') and delegate.hScrollBar:
                delegate.hScrollBar.setScrollAnimation(120, QEasingCurve.OutCubic)
            # 启用动画模式以获得更快响应
            delegate.useAni = True
    for view in root.findChildren(QAbstractItemView):
        view.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)


def install_scroll_speed_booster(app):
    """安装全局鼠标滚轮加速器，放大滚轮增量。"""
    from PySide6.QtCore import QEvent, Qt, QPoint, QObject
    from PySide6.QtWidgets import QAbstractScrollArea
    from PySide6.QtGui import QWheelEvent

    class _WheelBooster(QObject):
        def __init__(self, factor=1.5):
            super().__init__()
            self.factor = factor

        def eventFilter(self, obj, event):
            if event.type() == QEvent.Type.Wheel and isinstance(obj, QAbstractScrollArea):
                if event.angleDelta().isNull():
                    return False
                # 放大 angleDelta
                delta = event.angleDelta()
                new_delta = QPoint(int(delta.x() * 1.5), int(delta.y() * 1.5))
                # 创建新的 wheel event
                new_event = QWheelEvent(
                    event.position(), event.globalPosition(),
                    event.pixelDelta() * 1.5 if event.pixelDelta() else QPoint(0, 0),
                    QPoint(int(delta.x() * 1.5), int(delta.y() * 1.5)),
                    event.buttons(), event.modifiers(),
                    event.phase(), event.inverted()
                )
                return QApplication.sendEvent(obj, new_event)
            return False

    booster = _WheelBooster(1.5)
    app.installEventFilter(booster)
    return booster


def fix_combobox_popup_direction():
    """修复 ComboBox 弹窗方向：强制优先向下弹出。

    qfluentwidgets ComboBoxBase._showComboMenu 比较 hd（下方可用高度）
    和 hu（上方可用高度）来决定弹窗方向。当 ComboBox 在 ScrollArea 内时，
    mapToGlobal 坐标映射可能偏差，导致误判为向上弹出。
    本函数 monkey-patch 该逻辑，改为只要下方有 >= 30% 上方空间就向下弹出。
    """
    from PySide6.QtCore import QPoint
    from qfluentwidgets.components.widgets.combo_box import ComboBoxBase
    from qfluentwidgets import MenuAnimationType

    _original = ComboBoxBase._showComboMenu

    def _patched(self):
        if not self.items:
            return
        menu = self._createComboMenu()
        for item in self.items:
            from PySide6.QtGui import QAction
            action = QAction(item.icon, item.text)
            action.setEnabled(item.isEnabled)
            menu.addAction(action)
        menu.view.itemClicked.connect(
            lambda i: self._onItemClicked(self.findText(i.text().lstrip())))
        if menu.view.width() < self.width():
            menu.view.setMinimumWidth(self.width())
            menu.adjustSize()
        menu.setMaxVisibleItems(self.maxVisibleItems())
        from PySide6.QtCore import Qt
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        menu.closedSignal.connect(self._onDropMenuClosed)
        self.dropMenu = menu
        if self.currentIndex() >= 0 and self.items:
            menu.setDefaultAction(menu.actions()[self.currentIndex()])
        x = -menu.width() // 2 + menu.layout().contentsMargins().left() + self.width() // 2
        pd = self.mapToGlobal(QPoint(x, self.height()))
        hd = menu.view.heightForAnimation(pd, MenuAnimationType.DROP_DOWN)
        pu = self.mapToGlobal(QPoint(x, 0))
        hu = menu.view.heightForAnimation(pu, MenuAnimationType.PULL_UP)
        # 修复：优先向下弹出，只要下方空间 >= 上方空间的 30%
        if hd >= hu * 0.3:
            menu.view.adjustSize(pd, MenuAnimationType.DROP_DOWN)
            menu.exec(pd, aniType=MenuAnimationType.DROP_DOWN)
        else:
            menu.view.adjustSize(pu, MenuAnimationType.PULL_UP)
            menu.exec(pu, aniType=MenuAnimationType.PULL_UP)

    ComboBoxBase._showComboMenu = _patched


# ─────────────────────────────────────────────────────
#  HeroBanner — 首页棱镜渐变横幅
# ─────────────────────────────────────────────────────

_LANE_LABELS = [tr("视频", "Video"), tr("音频", "Audio"), tr("图片", "Image"), tr("文档", "Document")]
_LANE_COLORS = ["#38BDF8", "#A78BFA", "#2FC99A", "#F0A63A"]


class _HeroPipeline(QWidget):
    """Hero 右侧的格式转换流水线装饰图。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(360, 128)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        rect = self.rect()

        # 半透明背景底板
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), 14, 14)
        p.fillPath(path, QColor(255, 255, 255, 16))
        p.setPen(QPen(QColor(255, 255, 255, 70), 1))
        p.drawPath(path)

        card_w, card_h, gap = 118, 42, 14
        x0, y0 = 18, 16
        xs = [x0, x0 + card_w + gap]
        ys = [y0, y0 + card_h + gap]

        # 连接箭头
        pen = QPen(QColor(255, 255, 255, 110), 1)
        p.setPen(pen)
        for x, y in ((xs[0] + card_w, ys[0] + card_h // 2),
                     (xs[0] + card_w, ys[1] + card_h // 2)):
            p.drawLine(QPointF(x + 1, y), QPointF(x + gap - 3, y))
            p.drawLine(QPointF(x + gap - 7, y - 4), QPointF(x + gap - 3, y))
            p.drawLine(QPointF(x + gap - 7, y + 4), QPointF(x + gap - 3, y))
        p.drawLine(QPointF(xs[0] + card_w // 2, ys[0] + card_h),
                   QPointF(xs[0] + card_w // 2, ys[1] - 1))
        p.drawLine(QPointF(xs[0] + card_w // 2 - 4, ys[1] - 7),
                   QPointF(xs[0] + card_w // 2, ys[1] - 1))
        p.drawLine(QPointF(xs[0] + card_w // 2 + 4, ys[1] - 7),
                   QPointF(xs[0] + card_w // 2, ys[1] - 1))

        # 四个格式卡片
        font = QFont("Microsoft YaHei UI", 11)
        font.setBold(True)
        p.setFont(font)
        for i, (x, y) in enumerate(((xs[0], ys[0]), (xs[1], ys[0]),
                                    (xs[0], ys[1]), (xs[1], ys[1]))):
            card = QRectF(x, y, card_w, card_h)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 26))
            p.drawRoundedRect(card, 9, 9)
            p.setPen(QPen(QColor(255, 255, 255, 90), 1))
            p.drawRoundedRect(card, 9, 9)
            # 彩色圆点
            color = QColor(_LANE_COLORS[i % len(_LANE_COLORS)])
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawEllipse(QPointF(card.left() + 14, card.center().y()), 4, 4)
            # 文字
            p.setPen(QColor(255, 255, 255, 235))
            p.drawText(card.adjusted(24, 0, -8, 0),
                       Qt.AlignLeft | Qt.AlignVCenter, _LANE_LABELS[i])
        p.end()


class HeroBanner(QWidget):
    """首页 Hero 横幅：棱镜渐变背景 + 白色文字 + 装饰流水线。

    自定义 paintEvent 绘制 indigo→violet→pink 渐变 + 装饰光斑，
    右侧内置 _HeroPipeline 流水线装饰，不包含按钮。
    """

    def __init__(self, title="", subtitle="", parent=None):
        super().__init__(parent)
        self._title = title
        self._subtitle = subtitle
        self.setMinimumHeight(176)
        self.setMaximumHeight(220)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(30, 22, 30, 22)
        outer.setSpacing(24)

        left = QVBoxLayout()
        left.setSpacing(6)
        self.title_label = TitleLabel(self._title)
        self.subtitle_label = CaptionLabel(self._subtitle)
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setMaximumWidth(560)
        left.addWidget(self.title_label)
        left.addWidget(self.subtitle_label)
        left.addStretch()

        self.badge = CaptionLabel(tr("本地转换 · FFmpeg 引擎", "Local convert · FFmpeg engine"))
        left.addWidget(self.badge)
        outer.addLayout(left, 1)

        self.pipeline = _HeroPipeline(self)
        outer.addWidget(self.pipeline, 0, Qt.AlignVCenter)

        self._orb1 = QPointF(58, 30)
        self._orb2 = QPointF(0, 0)
        self._orb3 = QPointF(0, 0)

        # 背景为固定深色渐变，文字必须恒为白色。qfluentwidgets 主题切换会
        # 重置其控件的样式表，导致浅色模式下 TitleLabel/CaptionLabel 变回
        # 默认深色文字。themeChangedFinished 在 qfluentwidgets 控件刷新
        # 完成后触发，此时再恢复白色样式才能保证不被后续覆盖。
        self._apply_text_styles()
        try:
            from qfluentwidgets import qconfig
            qconfig.themeChangedFinished.connect(self._apply_text_styles)
        except Exception:  # noqa: BLE001 - 信号缺失不应阻断构建
            pass

    def _apply_text_styles(self):
        """重新应用 Hero 内文字样式（背景恒为深色渐变）。

        徽章/卡片底色用半透明深色（而非半透明白）——
        渐变右端为浅紫/粉色区，白字叠半透明白底对比度极低
        （tr("透明白字", "Translucent white text")），叠深色底则白字始终清晰。
        """
        self.title_label.setStyleSheet(
            "font-size: 27px; font-weight: 700; color: #FFFFFF;")
        self.subtitle_label.setStyleSheet(
            "font-size: 13px; color: rgba(255,255,255,0.82);")
        self.badge.setStyleSheet(
            "background: rgba(0,0,0,0.28); color: #FFFFFF;"
            "border: 1px solid rgba(255,255,255,0.22);"
            "border-radius: 12px; padding: 4px 12px;"
            "font-size: 12px; font-weight: 600;")

    def set_titles(self, title, subtitle):
        self._title = title
        self._subtitle = subtitle
        self.title_label.setText(title)
        self.subtitle_label.setText(subtitle)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()

        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), 16, 16)
        painter.setClipPath(path)

        # 棱镜渐变背景
        grad = QLinearGradient(0, 0, rect.width(), 0)
        grad.setColorAt(0.0, QColor("#4444C7"))
        grad.setColorAt(0.35, QColor("#7C3AED"))
        grad.setColorAt(0.65, QColor("#C026D3"))
        grad.setColorAt(1.0, QColor("#DB2777"))
        painter.fillRect(rect, grad)

        # 装饰光斑
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 20))
        painter.drawEllipse(QPointF(rect.width() * 0.88, 18), 76, 76)
        painter.setBrush(QColor(255, 255, 255, 12))
        painter.drawEllipse(QPointF(rect.width() * 0.96, rect.height() - 14),
                            54, 54)
        painter.setBrush(QColor(255, 255, 255, 10))
        painter.drawEllipse(QPointF(rect.width() * 0.52, -10), 46, 46)

        painter.end()

    def update_orb_positions(self):
        w = self.width()
        self._orb2 = QPointF(w * 0.55, 10)
        self._orb3 = QPointF(w * 0.75, self.height() - 10)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.update_orb_positions()

    def refresh(self):
        """主题切换后刷新（渐变色随主题变化）。"""
        self.update()
