"""theme_manager — 亮/暗/跟随系统主题切换与持久化（Prism 设计系统）。

切换主题时同步刷新 Prism 设计系统的全局 QSS 与主题色。

性能：qfluentwidgets 的 setTheme 支持 lazy 模式——对不可见控件
延迟刷样式（标记 dirty-qss，显示时再应用），主题切换从 ~1s 降到 ~250ms。
"""
from gui_qt.i18n import tr
from PySide6.QtCore import QObject
from qfluentwidgets import Theme, qconfig, setTheme

from gui_qt.components import design_system as ds

# 模式标识（持久化到 USER_PREFS 的 qt_app.theme）
MODE_LIGHT = tr("浅色", "Light")
MODE_DARK = tr("深色", "Dark")
MODE_AUTO = tr("跟随系统", "System")
MODES = [MODE_LIGHT, MODE_DARK, MODE_AUTO]

_MODE_THEME = {MODE_LIGHT: Theme.LIGHT, MODE_DARK: Theme.DARK, MODE_AUTO: Theme.AUTO}

# 预置主题色：(显示名, 十六进制)。
# 第一项为默认色（使用设计系统默认 accent），其余为 Tailwind 500 色系，
# 与 Prism 设计系统（indigo→violet→pink 渐变）协调且饱和鲜明。
ACCENT_COLORS = [
    ("默认", None),          # 设计系统默认靛蓝 #5B5BD6
    ("天蓝", "#0EA5E9"),
    ("蓝色", "#3B82F6"),
    ("青色", "#06B6D4"),
    ("翠绿", "#10B981"),
    ("紫色", "#8B5CF6"),
    ("玫红", "#EC4899"),
    ("橙色", "#F97316"),
    ("琥珀", "#F59E0B"),
]


class ThemeManager(QObject):
    """主题管理：切换 qfluentwidgets 主题并写入用户偏好，同步刷新 Prism 样式。"""

    def __init__(self, services):
        super().__init__()
        self.services = services
        self._style_refresh_timer = None
        self._style_dirty = False
        self._mode_style_timer = None

    def current_mode(self) -> str:
        return self.services.get_pref("theme", MODE_AUTO)

    def current_accent(self) -> str:
        """返回当前主题色 hex；空串表示默认。"""
        return self.services.get_pref("accent_color", "") or ""

    def apply_saved(self):
        """启动时按持久化偏好应用主题与主题色。

        延迟 QSS 生成到事件循环空闲（defer_style=True），
        避免启动时 ~400ms 冻结；setTheme(lazy=True) 已让 qfluentwidgets
        控件立即变色，Prism 细节样式稍后补上。
        """
        ds.set_accent(self.current_accent())
        # 同步 qfluentwidgets 主题色：导航选中背景/图标等由 qconfig.themeColor
        # 驱动（运行时 set_accent 有同步，这里漏了会导致重启后侧边栏回到
        # qfluentwidgets 默认蓝，与预设色不一致）
        try:
            from PySide6.QtGui import QColor
            from qfluentwidgets import qconfig
            qconfig.set(qconfig.themeColor, QColor(ds.accent()), save=False)
        except Exception:  # noqa: BLE001 - 同步失败不阻塞启动
            pass
        # 延迟 QSS 全量重算到事件循环空闲，避免启动冻结
        self.set_mode(self.current_mode(), persist=False, defer_style=True)

    def set_mode(self, mode: str, persist=True, defer_style=True):
        if mode not in _MODE_THEME:
            mode = MODE_AUTO
        # lazy=True：不可见控件延迟刷样式，显著加速主题切换。
        # setTheme 内部已用当前主题色重新渲染所有控件（含 ThemeColor
        # 占位符替换），无需再调 apply_theme_color_all（明暗切换主题色
        # 未变，重复的 setThemeColor 全量刷新是纯浪费 ~700ms）。
        setTheme(_MODE_THEME[mode], lazy=True)
        # 主窗口 Prism QSS 全量重算（~420ms）延迟到事件循环空闲执行：
        # setTheme 已让 qfluentwidgets 控件与窗口背景立即变色，Prism 的
        # 滚动条/表格/日志等细节样式稍后补上，避免一次 ~950ms 长冻结，
        # 让主题切换的视觉反馈从 ~950ms 提前到 setTheme 完成的那一刻。
        if defer_style:
            self._schedule_mode_style()
        else:
            ds.set_app_style()
        if persist:
            self.services.set_pref("theme", mode)

    def _schedule_mode_style(self):
        """延迟（0ms，事件循环空闲）执行主窗口 QSS 重算，连续切换自动合并。"""
        from PySide6.QtCore import QTimer
        if self._mode_style_timer is None:
            self._mode_style_timer = QTimer(self)
            self._mode_style_timer.setSingleShot(True)
            self._mode_style_timer.timeout.connect(ds.set_app_style)
        self._mode_style_timer.start(0)

    def set_accent(self, color: str, persist=True):
        """设置主题色（hex，空串恢复默认）。

        拆成两步避免点击色块时 UI 卡顿：
        1. 立即更新主题色值 + 触发 themeColor 信号（导航选中态颜色过渡
           动画、色块、图标等轻量即时刷新）+ 只刷新含主题色的可见控件
           （~25ms，替代 setThemeColor 全量 400ms）；
        2. 重量级主窗口 QSS 全量重算（~400ms）去抖延迟执行，快速来回
           切换时合并为一次，避免「点一下卡一下/卡死」。
        """
        from PySide6.QtGui import QColor
        ds.set_accent(color)
        if persist:
            self.services.set_pref("accent_color", color or "")
        # 立即触发 themeColorChanged → 导航/图标等即时变色
        qconfig.set(qconfig.themeColor, QColor(ds.accent()), save=False)
        # 即时刷新含主题色的可见控件（开关/按钮高亮等，~25ms）
        ds.apply_theme_color_fast()
        # 重量级主窗口 QSS 重算：去抖延迟（快速切换合并）
        self._schedule_style_refresh()

    def _schedule_style_refresh(self):
        from PySide6.QtCore import QTimer
        self._style_dirty = True
        if self._style_refresh_timer is None:
            self._style_refresh_timer = QTimer(self)
            self._style_refresh_timer.setSingleShot(True)
            self._style_refresh_timer.timeout.connect(self._apply_style_refresh)
        # 800ms 去抖：主窗口 QSS 的 setStyleSheet 会触发 Qt 对全窗口上千
        # 控件的样式重算（空 QSS 也要 ~326ms，与内容无关），连续点选期间
        # 完全跳过，只在停止操作 800ms 后才执行一次，避免打断选择操作
        self._style_refresh_timer.start(800)

    def _apply_style_refresh(self):
        if not self._style_dirty:
            return
        self._style_dirty = False
        ds.set_app_style()

    @staticmethod
    def current_theme() -> Theme:
        return qconfig.theme
