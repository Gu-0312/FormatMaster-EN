"""shortcuts — 全局快捷键动作定义（设置页「快捷键」分组与主窗口共用）。"""

from qfluentwidgets import FluentIcon

from gui_qt.i18n import tr

# action key → 元数据（默认快捷键 / 标题 / 描述 / 图标）
SHORTCUT_ACTIONS = {
    "pin": {
        "title": tr("窗口置顶切换", "Toggle always-on-top"),
        "desc": tr("切换主窗口是否置顶", "Pin/unpin the main window"),
        "icon": FluentIcon.PIN,
        "default": "Ctrl+Shift+P",
    },
    "theme": {
        "title": tr("切换亮暗主题", "Toggle light/dark theme"),
        "desc": tr("在浅色与深色主题间切换", "Switch between light and dark"),
        "icon": FluentIcon.BRIGHTNESS,
        "default": "Ctrl+Shift+T",
    },
    "history": {
        "title": tr("打开转换历史", "Open history"),
        "desc": tr("跳转到转换历史页面", "Jump to the history page"),
        "icon": FluentIcon.HISTORY,
        "default": "Ctrl+Shift+H",
    },
    "settings": {
        "title": tr("打开设置", "Open settings"),
        "desc": tr("跳转到设置页面", "Jump to the settings page"),
        "icon": FluentIcon.SETTING,
        "default": "Ctrl+Shift+S",
    },
    "plugins": {
        "title": tr("打开插件系统", "Open plugins"),
        "desc": tr("跳转到插件系统页面", "Jump to the plugin system page"),
        "icon": FluentIcon.DEVELOPER_TOOLS,
        "default": "Ctrl+Shift+K",
    },
}
