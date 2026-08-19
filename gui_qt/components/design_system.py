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
from PySide6.QtCore import (QPointF, QPropertyAnimation, Qt, QRectF, QTimer)
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter,
                            QPen, QPainterPath)
from PySide6.QtWidgets import (QApplication, QGraphicsDropShadowEffect,
                                QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                                QWidget)
from qfluentwidgets import (FluentIcon, isDarkTheme)
import math
import os
import re

# ─────────────────────────────────────────────────────
#  SpinBox 微调箭头资源（修复 qfw 资源包缺 spin_box SVG → 灰色方块）
# ─────────────────────────────────────────────────────
_SPIN_ICON_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "assets", "icons")
_SPIN_UP_SVG = os.path.join(_SPIN_ICON_DIR, "spin_up.svg").replace("\\", "/")
_SPIN_DOWN_SVG = os.path.join(_SPIN_ICON_DIR, "spin_down.svg").replace("\\", "/")


def _patch_qfw_spinbox_icons():
    """修复 qfw SpinBox 上下箭头图标缺失（resource.py 缺 spin_box SVG）。

    SpinIcon.UP/DOWN 的 path 指向不存在的 qrc 资源，QSvgRenderer 渲染空 →
    微调按钮显示灰色方块。改指项目本地 SVG 箭头。
    """
    try:
        from qfluentwidgets.components.widgets import spin_box as _sb
        _sb.SpinIcon.UP.path = lambda theme=None: _SPIN_UP_SVG
        _sb.SpinIcon.DOWN.path = lambda theme=None: _SPIN_DOWN_SVG
    except Exception:  # noqa: BLE001 - 库结构变化时静默跳过
        pass


_patch_qfw_spinbox_icons()

# ─────────────────────────────────────────────────────
#  令牌边界（重要）
# ─────────────────────────────────────────────────────
# 本文件 LIGHT / DARK 是 Qt 界面唯一色彩/样式真源。
# app/theme.py 为 tkinter 遗留层（已无代码引用，仅 build.py 打包保留），
# 禁止作为新样式来源；新面板/新组件一律从本模块取令牌，不得硬编码颜色。

# ─────────────────────────────────────────────────────
#  圆角规范（全站统一两档）
# ─────────────────────────────────────────────────────
# RADIUS_CARD  = 12   卡片/表面类（面板、表格、列表、日志框、ActionBar）
# RADIUS_CTRL  = 8    交互控件（按钮/输入框/下拉/菜单，Fluent 标准）
# 小元素保留：滚动条 8、进度条 4、工具提示 6、图标方块按需
RADIUS_CARD = 12
RADIUS_CTRL = 8

# ─────────────────────────────────────────────────────
#  外观运行时状态（外观设置页写入，全局生效）
# ─────────────────────────────────────────────────────
_animations = True          # 界面动画开关
_card_radius = RADIUS_CARD  # 卡片圆角（12 圆角 / 0 直角）

# ─────────────────────────────────────────────────────
#  字体层级（全站统一：系统默认字体 Microsoft YaHei）
# ─────────────────────────────────────────────────────
FONT_BODY = "Microsoft YaHei"   # 正文（Windows 系统默认中文 UI 字体）
FONT_MONO = "Cascadia Code, Consolas, Microsoft YaHei"  # 代码/路径/日志
# 字号阶梯（px，基准值；全局缩放见 ui_scale()）
FONT_DISPLAY = 27    # Hero 主标题
FONT_H1 = 20         # 页面大标题
FONT_H2 = 16         # 区块/卡片标题
FONT_BODY_SZ = 13    # 正文默认
FONT_CAPTION = 12    # 辅助说明/状态


def ui_scale() -> float:
    """全局界面缩放系数（0.85~1.5，默认 1.0）。

    读用户偏好 qt_app/ui_scale；缩放作用于 QSS 字号与 QApplication
    默认字体，改动后需重启生效（QSS 在启动时生成）。
    """
    try:
        from utils.config import USER_PREFS
        v = USER_PREFS.get("qt_app", "ui_scale", 1.0)
        v = float(v)
        return 0.85 if v < 0.85 else (1.5 if v > 1.5 else v)
    except Exception:  # noqa: BLE001 - 读取失败用默认
        return 1.0

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
    "ocr":     ("#DB2777", "#FCE7F3"),
    "utility": ("#6366F1", "#E0E7FF"),
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
    "ocr":     ("#F472B6", "#3B0D24"),
    "utility": ("#818CF8", "#1E1B4B"),
}


# ─────────────────────────────────────────────────────
#  令牌访问器
# ─────────────────────────────────────────────────────

def tokens():
    """返回当前主题的色彩令牌字典。"""
    return DARK if isDarkTheme() else LIGHT


def _accent_tokens(t):
    """若设置了自定义主题色，基于它派生整套 accent 令牌（覆盖默认）。

    保持 HSL 饱和度/亮度关系，确保 QSS 里滚动条/进度条/菜单/表格选中态/
    日志等所有用到 accent 系列的样式都能跟随用户主题色，而不仅 qfluentwidgets
    控件（后者由 qconfig.themeColor 独立驱动）。
    """
    if not _accent_override:
        return t
    c = QColor(_accent_override)
    dark = isDarkTheme()
    h, s, l, _ = c.getHslF()

    def hsl(h_, s_, l_):
        return QColor.fromHslF(
            h_ % 1.0, min(max(s_, 0.0), 1.0), min(max(l_, 0.0), 1.0)).name()

    out = dict(t)
    out["accent"] = c.name()
    # hover：浅色更深、深色更亮，保持可点按的对比
    out["accent_hover"] = hsl(h, s, l - 0.12) if not dark else hsl(h, s, l + 0.12)
    # soft：更亮一档（用于次级高亮/边框）
    out["accent_soft"] = hsl(h, s, l + 0.10) if not dark else hsl(h, s, l + 0.14)
    # pale：淡背景（保留主题色相，加深到可见的淡色，避免接近白色）
    out["accent_pale"] = hsl(h, min(s * 0.55, 1.0), 0.88) if not dark \
        else hsl(h, min(s * 0.65, 1.0), 0.28)
    # deep：更深一档
    out["accent_deep"] = hsl(h, s, l - 0.22) if not dark else hsl(h, s, l - 0.05)
    return out


def is_dark():
    return isDarkTheme()


# 用户自定义主题色（None = 使用设计系统默认令牌）。
# 由外观设置里的「主题色」写入；accent()/accent_hover() 等优先返回它。
_accent_override = None


def set_accent(color_hex):
    """设置全局主题色覆盖；传 None/空串恢复设计系统默认。

    切换主题色需让 QSS 缓存失效（QSS 内含 accent 系列色），否则
    generate_qss 会继续返回旧主题色的缓存，导致视觉不更新。
    """
    global _accent_override
    _accent_override = (color_hex or "").strip() or None
    _QSS_CACHE.clear()
    global _last_applied_qss
    _last_applied_qss = None


def accent():
    if _accent_override:
        return _accent_override
    return tokens()["accent"]


def accent_hover():
    if _accent_override:
        c = QColor(_accent_override)
        # 浅色主题 hover 变深，深色主题 hover 变亮，保持对比度
        return (c.darker(115) if not isDarkTheme() else c.lighter(118)).name()
    return tokens()["accent_hover"]


def set_animations(on: bool):
    """开/关全局界面动画（页面淡入、卡片悬停浮起等）。"""
    global _animations
    _animations = bool(on)


def animations_enabled() -> bool:
    return _animations


def set_card_radius(rounded: bool):
    """设置卡片圆角：True 圆角(12)、False 直角(0)。"""
    global _card_radius
    _card_radius = RADIUS_CARD if rounded else 0
    # 圆角写入 QSS（预计算缓存需失效）
    _QSS_CACHE.clear()
    global _last_applied_qss
    _last_applied_qss = None


def card_radius() -> int:
    return _card_radius


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


def bind_theme(widget, style_fn):
    """让独立窗口/控件监听主题切换，切换时用 style_fn() 返回的 QSS 刷新。

    style_fn: 无参可调用，返回要应用的 QSS 字符串（内部按 isDarkTheme 取色）。
    返回内部刷新函数，便于外部手动触发。
    """
    from qfluentwidgets import qconfig

    def _refresh():
        try:
            widget.setStyleSheet(style_fn())
        except Exception:  # noqa: BLE001 - 刷新失败不影响运行
            pass

    try:
        qconfig.themeChanged.connect(_refresh)
    except Exception:  # noqa: BLE001
        pass
    # 主题色切换也要刷新（导航选中背景、图标色等跟随 qconfig.themeColor 派生）
    try:
        qconfig.themeColorChanged.connect(_refresh)
    except Exception:  # noqa: BLE001
        pass
    return _refresh


def group_color(name):
    """Map a navigation group name to its foreground color."""
    return group_colors(group_key_for_name(name))[0]


def group_key_for_name(name):
    """Resolve a navigation group name to a stable palette key.

    按 NAV_GROUPS 顺序显式映射（跳过首页，idx1..9 → keys 0..8）：
    转换中心→convert、PDF工具→doc、视频工具→video、音频工具→audio、
    图片工具→image、识别工具→ocr、实用工具→utility、下载→net、管理→manage。
    """
    from gui_qt.nav_registry import NAV_GROUPS
    keys = ["convert", "doc", "video", "audio", "image",
            "ocr", "utility", "net", "manage"]
    for idx, (group_name, _items) in enumerate(NAV_GROUPS):
        if group_name == name:
            return keys[idx - 1] if 0 < idx <= len(keys) else "manage"
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

    # ── 圆角（直角模式时卡片/表面类归零）──
    r_card = card_radius()

    # ── 窗口背景（FluentTitleBar 透明，必须由 QSS 提供底色）──
    win_bg = t["page_bg"]
    scroll_bg = t["page_bg"]

    parts.append(f"""
    FluentWindow {{
        background: {win_bg};
    }}
    """)

    # ── 滚动区域（禁用动态调整大小，启用像素级平滑滚动）──
    parts.append(f"""
    QScrollArea {{
        background: {scroll_bg};
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

    # ── 文本标签 ──
    # 原生 QLabel 不跟随 qfluentwidgets 主题（palette 固定），深色模式下
    # 若未单独设色会以 palette 黑字融入深色背景。全局兜底用 ink 令牌，
    # 已用内联 QSS 单独设色的标签优先级更高、不受影响。
    parts.append(f"""
    QLabel {{
        color: {t["ink"]};
        background: transparent;
    }}
    QLabel:disabled {{
        color: {t["ink_dis"]};
    }}
    QLabel[sec="true"] {{
        color: {t["ink_sec"]};
    }}
    """)

    # ── 数值输入框（QSpinBox / QDoubleSpinBox）──
    parts.append(f"""
    QSpinBox, QDoubleSpinBox {{
        background: {t["input_bg"]};
        color: {t["ink"]};
        border: 1px solid {t["input_bd"]};
        border-radius: 8px;
        padding: 4px 10px;
        min-height: 24px;
    }}
    QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {t["accent"]};
    }}
    QSpinBox:disabled, QDoubleSpinBox:disabled {{
        background: {t["table_header"]};
        color: {t["ink_dis"]};
    }}
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        background: transparent;
        border: none;
        width: 18px;
    }}
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
        image: url("{_SPIN_UP_SVG}");
        width: 8px; height: 8px;
    }}
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
        image: url("{_SPIN_DOWN_SVG}");
        width: 8px; height: 8px;
    }}
    """)

    # ── 关于页推荐条（QWidget#aboutCallout）──
    # 由全局 QSS 托管：主题切换自动刷新，避免实例快照残留浅紫底
    parts.append(f"""
    QWidget#aboutCallout {{
        background: {t["accent_pale"]};
        border: 1px solid {t["border"]};
        border-radius: 10px;
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
        font-family: "Cascadia Code", "Consolas", "Microsoft YaHei";
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

    qss = "\n".join(parts)
    # 直角模式：把卡片面 12px 圆角归零（控件 8px 圆角保留，观感更协调）
    if r_card == 0:
        qss = qss.replace("border-radius: 12px;", "border-radius: 0px;")
    # 全局界面缩放：按 ui_scale() 等比缩放所有 font-size（最小 8px 防挤）
    scale = ui_scale()
    if abs(scale - 1.0) > 0.01:
        qss = re.sub(
            r"font-size:\s*(\d+)px",
            lambda m: f"font-size: {max(8, int(int(m.group(1)) * scale))}px",
            qss)
    return qss


def generate_qss():
    """返回当前主题的 QSS（预计算缓存，避免每次切换重复生成）。

    注意：用 tokens()（含玻璃模式的半透明表面色），而非直接 DARK/LIGHT。
    缓存 key 含 ui_scale——缩放偏好变化后强制重建，避免字号不刷新。
    """
    key = f"{'dark' if isDarkTheme() else 'light'}:{ui_scale():.2f}"
    if key not in _QSS_CACHE:
        _QSS_CACHE[key] = _build_qss(_accent_tokens(tokens()))
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
    """应用 Prism 设计系统：应用预缓存 QSS 到主窗口 + 修复窗口背景。

    明暗/主题色切换时调用。FluentTitleBar 是透明背景，会透出 FluentWindow
    底层色。深色模式下必须强制设置窗口背景，否则显示为系统浅色。

    注意：这里只做主窗口 QSS 全量重算（重量级，~400ms）。qfluentwidgets
    控件的主题色刷新由 setTheme 内部完成（明暗切换）或
    apply_theme_color_fast（主题色切换）负责，本函数只处理 Prism 自定义 QSS。
    """
    app = QApplication.instance()
    if app is None:
        return
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


# 控件 → 是否含 ThemeColor 占位符（weakref，避免泄漏）
import weakref as _weakref
_theme_color_cache = _weakref.WeakKeyDictionary()


def _widget_has_theme_color(widget, file):
    """判断某控件的 QSS 源是否含 ThemeColor 占位符（结果缓存）。

    主题色（accent）切换只影响含 ThemeColor 的控件；不含的控件（如
    QLabel/ComboBox 等大控件）刷新它们反而触发昂贵的级联重算。
    """
    cached = _theme_color_cache.get(widget)
    if cached is not None:
        return cached
    has = False
    try:
        from qfluentwidgets import qconfig
        for src in file.sources:
            if "ThemeColor" in src.content(qconfig.theme):
                has = True
                break
    except Exception:  # noqa: BLE001
        has = False
    _theme_color_cache[widget] = has
    return has


def apply_theme_color_fast():
    """主题色切换的即时刷新：只刷新含 ThemeColor 的可见控件（~25ms），
    不含的控件跳过（主题色不影响它们），隐藏控件标记 dirty-qss 延迟刷新。

    替代 setThemeColor 全量（预热后可见控件逐个 setStyleSheet 可达 400ms），
    把主题色切换的即时反馈降到 ~25ms，剩余重量级工作由 set_app_style
    去抖延迟执行。
    """
    from qfluentwidgets import qconfig
    from qfluentwidgets.common import style_sheet as _ss
    for widget, file in list(_ss.styleSheetManager.items()):
        try:
            if not widget.isVisible():
                widget.setProperty("dirty-qss", True)
                continue
            if _widget_has_theme_color(widget, file):
                _ss.setStyleSheet(widget, file, qconfig.theme)
        except RuntimeError:  # noqa: BLE001
            pass


def _refresh_text_edits(root):
    """遍历 root 下所有 TextEdit，重新应用主题背景样式。"""
    from qfluentwidgets import TextEdit
    for edit in root.findChildren(TextEdit):
        try:
            apply_text_edit_style(edit)
        except Exception:  # noqa: BLE001 - 单个控件失败不阻断
            pass


def enable_smooth_scrolling(root):
    """遍历 root 下所有滚动视图，启用像素级即时滚动（无动画延迟）。

    原实现用 SmoothScrollDelegate 的 QPropertyAnimation（120ms OutCubic）做
    「平滑滚动」，滚轮滚一下页面要 120ms 才「追」到目标位置，产生慢一拍
    的滞后感。改为禁用动画（NO_SMOOTH + useAni=False），滚轮走原生
    QAbstractScrollArea.wheelEvent 即时响应，配合 install_scroll_speed_booster
    的增量放大，滚动又快又跟手。
    """
    apply_fast_scroll(root)


def apply_fast_scroll(root):
    """把 root 自身及其全部子孙滚动区域切换为「原生即时滚动」。

    与 enable_smooth_scrolling 的关键差异：findChildren 不含 root 自身，
    导致懒加载面板（BaseQtPanel 继承 qfluentwidgets ScrollArea）自身的
    SmoothScrollDelegate 从未被关闭 —— 滚轮事件走 FixedStepSmoothScrollEngine
    （LINEAR 400ms 逐帧动画），每格滚轮要 400ms 才滚完，表现为「页面功能区
    滚轮滚动很慢、跟手差」（侧边导航栏启动时已被处理所以流畅）。

    修复要点：
    1. 处理 root 自身 + 递归全部子孙（findChildren 是深度遍历，一次调用
       即可覆盖所有嵌套滚动区域，无需递归）。
    2. SmoothMode.NO_SMOOTH：SmoothScroll.wheelEvent 直接走原生
       QAbstractScrollArea.wheelEvent（即时滚动），任何 delta 都不进动画引擎。
    3. ScrollPerPixel 像素滚动模式。
    4. setProperty 防重复处理（动态创建的面板/弹窗不会重复遍历开销）。
    """
    from PySide6.QtWidgets import QAbstractItemView, QAbstractScrollArea
    from qfluentwidgets.common.smooth_scroll import SmoothMode
    applied = 0
    targets = []
    if isinstance(root, QAbstractScrollArea):
        targets.append(root)
    targets.extend(root.findChildren(QAbstractScrollArea))
    for sa in targets:
        if sa.property("fm_fast_scroll"):
            continue
        sa.setProperty("fm_fast_scroll", True)
        applied += 1
        if hasattr(sa, "setHorizontalScrollMode"):
            sa.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
            sa.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        # 关闭 qfluentwidgets 平滑滚动动画，改为即时响应
        if hasattr(sa, 'scrollDelagate') and sa.scrollDelagate:
            delegate = sa.scrollDelagate
            delegate.useAni = False
            try:
                delegate.verticalSmoothScroll.setSmoothMode(SmoothMode.NO_SMOOTH)
                delegate.horizonSmoothScroll.setSmoothMode(SmoothMode.NO_SMOOTH)
            except Exception:  # noqa: BLE001 - 属性缺失时静默
                pass
    for view in root.findChildren(QAbstractItemView):
        view.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
    return applied


def install_scroll_speed_booster(app):
    """安装全局鼠标滚轮加速器，放大滚轮增量。

    滚轮事件实际发给滚动区域的 viewport（或其子控件），而非 QAbstractScrollArea
    本身，故需沿父链向上判断。放大后滚动更跟手（配合 enable_smooth_scrolling
    关闭动画的即时响应）。
    """
    from PySide6.QtCore import QEvent, Qt, QPoint, QObject
    from PySide6.QtWidgets import QAbstractScrollArea
    from PySide6.QtGui import QWheelEvent

    def _is_scroll_related(widget):
        """判断 widget 是否是滚动区域或其视口内的控件。"""
        return _find_scroll_area(widget) is not None

    def _find_scroll_area(widget):
        """向上找 widget 所在（4 层内）的 QAbstractScrollArea，找不到返回 None。"""
        w = widget
        for _ in range(4):  # 最多向上 4 层
            if w is None:
                return None
            if isinstance(w, QAbstractScrollArea):
                return w
            w = w.parent()
        return None

    class _WheelBooster(QObject):
        def __init__(self, factor=1.5):
            super().__init__()
            self.factor = factor

        def eventFilter(self, obj, event):
            if event.type() == QEvent.Type.Wheel and _is_scroll_related(obj):
                # 兜底：动态创建的滚动区域（懒加载面板/对话框/弹窗）在
                # 首次滚轮时现场应用快速滚动（NO_SMOOTH + 像素滚动），
                # 无需在每一处创建代码里手动接线。setProperty 标记保证
                # 只处理一次，遍历开销可忽略。
                try:
                    sa = _find_scroll_area(obj)
                    if sa is not None and not sa.property("fm_fast_scroll"):
                        apply_fast_scroll(sa)
                except Exception:  # noqa: BLE001 - 兜底失败不影响滚动
                    pass
                if event.angleDelta().isNull():
                    return False
                # 放大 angleDelta
                delta = event.angleDelta()
                new_delta = QPoint(int(delta.x() * self.factor),
                                   int(delta.y() * self.factor))
                # 创建新的 wheel event
                new_event = QWheelEvent(
                    event.position(), event.globalPosition(),
                    event.pixelDelta() * self.factor if event.pixelDelta() else QPoint(0, 0),
                    new_delta,
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
        font = QFont(FONT_BODY, 11)
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
        # 使用普通 QLabel，避免 qfluentwidgets 的 FluentLabelBase 在主题切换时
        # 自动重设 light/dark 文字色覆盖手动的白色样式。
        self.title_label = QLabel(self._title)
        self.title_label.setWordWrap(False)
        self.subtitle_label = QLabel(self._subtitle)
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setMaximumWidth(560)
        left.addWidget(self.title_label)
        left.addWidget(self.subtitle_label)
        left.addStretch()

        self.badge = QLabel(tr("本地转换 · FFmpeg 引擎", "Local convert · FFmpeg engine"))
        left.addWidget(self.badge)
        outer.addLayout(left, 1)

        self.pipeline = _HeroPipeline(self)
        outer.addWidget(self.pipeline, 0, Qt.AlignVCenter)

        self._orb1 = QPointF(58, 30)
        self._orb2 = QPointF(0, 0)
        self._orb3 = QPointF(0, 0)

        # 棱镜流动动效：色标微移 + 光斑缓慢漂移（ambient 动画，可见时运行）
        self._t = 0.0
        self._anim_timer = QTimer(self)
        # 10fps（100ms）：原 24fps（42ms）常驻全量重绘渐变+光斑导致界面
        # 交互卡顿（2026-08-15 性能修复）；降频后流动感仍保留、开销减半以上。
        self._anim_timer.setInterval(100)
        self._anim_timer.timeout.connect(self._on_anim_tick)

        # 背景为固定深色渐变，文字必须恒为白色。内部 label 已改为普通
        # QLabel 以避免 qfluentwidgets 的 FluentLabelBase 自动根据主题切换
        # 文字色；仍监听 themeChangedFinished 并在事件队列排空后再次刷新，
        # 作为防御性保险，防止全局 QSS 变更后颜色被意外覆盖。
        self._apply_text_styles()
        try:
            from qfluentwidgets import qconfig

            def _deferred_refresh():
                QTimer.singleShot(0, self._apply_text_styles)

            qconfig.themeChangedFinished.connect(_deferred_refresh)
        except Exception:  # noqa: BLE001 - 信号缺失不应阻断构建
            pass

    def _apply_text_styles(self):
        """重新应用 Hero 内文字样式（背景恒为深色渐变）。

        使用普通 QLabel + !important 颜色，确保 qfluentwidgets 主题切换后
        文字始终保持白色，不受 FluentLabelBase 自动 light/dark 重设影响。
        """
        self.title_label.setStyleSheet(
            "font-size: 27px; font-weight: 700; color: #FFFFFF !important;")
        self.subtitle_label.setStyleSheet(
            "font-size: 13px; color: rgba(255,255,255,0.82) !important;")
        self.badge.setStyleSheet(
            "background: rgba(0,0,0,0.28); color: #FFFFFF !important;"
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

        t = self._t
        # 棱镜渐变背景：色标随 t 微移（幅度 4%），形成缓慢流动感
        grad = QLinearGradient(0, 0, rect.width(), 0)
        s = math.sin(t) * 0.04
        grad.setColorAt(0.0, QColor("#4444C7"))
        grad.setColorAt(0.35 + s, QColor("#7C3AED"))
        grad.setColorAt(0.65 + s * 0.6, QColor("#C026D3"))
        grad.setColorAt(1.0, QColor("#DB2777"))
        painter.fillRect(rect, grad)

        # 装饰光斑：位置随 t 缓慢漂移（低调、有生命感；2 个足矣，减少重绘开销）
        painter.setPen(Qt.NoPen)
        w, h = rect.width(), rect.height()
        painter.setBrush(QColor(255, 255, 255, 20))
        painter.drawEllipse(
            QPointF(w * (0.88 + 0.02 * math.sin(t)), 18 + 6 * math.cos(t * 1.3)),
            76, 76)
        painter.setBrush(QColor(255, 255, 255, 12))
        painter.drawEllipse(
            QPointF(w * (0.96 + 0.015 * math.cos(t * 0.9)), h - 14 + 5 * math.sin(t * 0.7)),
            54, 54)

        painter.end()

    def _on_anim_tick(self):
        """驱动流动：更新相位并重绘；动画开关关闭时停止常驻重绘。"""
        if not animations_enabled():
            self._anim_timer.stop()
            return
        self._t += 0.02
        self.update()

    def showEvent(self, e):
        """可见且动画开关开启时才运行动画，避免后台空转耗电。"""
        super().showEvent(e)
        if animations_enabled() and not self._anim_timer.isActive():
            self._anim_timer.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._anim_timer.stop()

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


def screen_ratio_size(ratio=0.8, max_w=1200, max_h=800):
    """按屏幕可用区域比例返回弹窗尺寸 (w, h)，适配不同分辨率。

    ratio=0.8 表示占屏幕可用区域的 80%；超过上限时截断。
    """
    try:
        from PySide6.QtGui import QGuiApplication
        scr = QGuiApplication.primaryScreen()
        geo = scr.availableGeometry() if scr is not None else None
    except Exception:  # noqa: BLE001
        geo = None
    if geo is None or geo.width() <= 0:
        return 800, 600
    w = min(int(geo.width() * ratio), max_w)
    h = min(int(geo.height() * ratio), max_h)
    return max(w, 480), max(h, 360)
