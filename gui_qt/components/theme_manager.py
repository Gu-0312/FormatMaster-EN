"""theme_manager — 亮/暗/跟随系统主题切换与持久化（Prism 设计系统）。

切换主题时同步刷新 Prism 设计系统的全局 QSS 与主题色。

性能：qfluentwidgets 的 setTheme 支持 lazy 模式——对不可见控件
延迟刷样式（标记 dirty-qss，显示时再应用），主题切换从 ~1s 降到 ~250ms。
"""
from qfluentwidgets import Theme, qconfig, setTheme

from gui_qt.components import design_system as ds

# 模式标识（持久化到 USER_PREFS 的 qt_app.theme）
MODE_LIGHT = "浅色"
MODE_DARK = "深色"
MODE_AUTO = "跟随系统"
MODES = [MODE_LIGHT, MODE_DARK, MODE_AUTO]

_MODE_THEME = {MODE_LIGHT: Theme.LIGHT, MODE_DARK: Theme.DARK, MODE_AUTO: Theme.AUTO}


class ThemeManager:
    """主题管理：切换 qfluentwidgets 主题并写入用户偏好，同步刷新 Prism 样式。"""

    def __init__(self, services):
        self.services = services

    def current_mode(self) -> str:
        return self.services.get_pref("theme", MODE_AUTO)

    def apply_saved(self):
        """启动时按持久化偏好应用主题。"""
        self.set_mode(self.current_mode(), persist=False)

    def set_mode(self, mode: str, persist=True):
        if mode not in _MODE_THEME:
            mode = MODE_AUTO
        # lazy=True：不可见控件延迟刷样式，显著加速主题切换
        setTheme(_MODE_THEME[mode], lazy=True)
        ds.set_app_style()
        if persist:
            self.services.set_pref("theme", mode)

    @staticmethod
    def current_theme() -> Theme:
        return qconfig.theme
