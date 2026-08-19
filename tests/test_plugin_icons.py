"""插件中心图标映射回归测试。

确保插件中心所有插件都能解析到具体的 FluentIcon，不会再出现
「QtAwesome 缺失 → 整排回退成同一个 ROBOT 机器人」导致界面杂乱的问题。
"""
import os
import sys

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def _app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def test_all_plugin_icons_resolved(_app):
    from qfluentwidgets import FluentIcon
    from gui_qt.panels.plugin_panel import _icon_for, _DEFAULT_ICON
    from core.plugin_loader import scan_plugins

    plugins = scan_plugins()
    assert plugins, "应至少扫描到一个插件"
    for p in plugins:
        ic = _icon_for(p.name)
        assert isinstance(ic, FluentIcon), f"{p.name} 未返回 FluentIcon"
        assert ic is not _DEFAULT_ICON, f"{p.name} 回退成了 ROBOT 默认图标"


def test_icon_rules_are_fluent_icons(_app):
    from qfluentwidgets import FluentIcon
    from gui_qt.panels.plugin_panel import _ICON_RULES

    for kw, icon in _ICON_RULES:
        assert isinstance(icon, FluentIcon), f"规则 {kw!r} 的图标不是 FluentIcon"
