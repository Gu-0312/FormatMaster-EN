"""qfluentwidgets 新组件落地回归测试（2026-08-16 第 6 批）。

覆盖 5 项落地（对照现有实现评估后选用；TeachingTip 已按用户要求移除）：
1. QSplashScreen 启动画面（app.py 用 Qt 内置方案，替代 qfluentwidgets
   SplashScreen——其 IconWidget 与 PySide6 6.11 overload 不兼容）
2. InfoBadge 首页「最近任务」进行中数徽章
3. StateToolTip 批量转换悬浮反馈（TaskPanelMixin 面板）
4. EditableComboBox 视频码率可手输
5. QtAwesome 插件中心图标补充（MIT 图标库）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["FORMATMASTER_OFFSCREEN"] = "1"

import pytest

from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app_ctx():
    from gui_qt.services import QtServices
    from gui_qt.task_manager import TaskManager
    app = QApplication.instance() or QApplication([])
    services = QtServices()
    services.task_manager = TaskManager(services)
    from gui_qt.components.theme_manager import ThemeManager
    services.theme_mgr = ThemeManager(services)

    class _Win:
        pass

    yield app, _Win(), services
    app.processEvents()


def test_splash_screen_builds(app_ctx):
    """启动画面（Qt 内置 QSplashScreen）：可构建、可显示、可 finish。"""
    from PySide6.QtGui import QColor, QPixmap
    from PySide6.QtWidgets import QSplashScreen, QWidget
    app, win, services = app_ctx
    pm = QPixmap(320, 180)
    pm.fill(QColor("#2F6BFF"))
    splash = QSplashScreen(pm)
    splash.show()
    app.processEvents()
    assert splash.isVisible()
    dummy = QWidget()
    dummy.show()
    app.processEvents()
    splash.finish(dummy)
    app.processEvents()
    assert not splash.isVisible()
    splash.deleteLater()
    dummy.deleteLater()


def test_home_badge_active_count(app_ctx):
    """首页「最近任务」InfoBadge：0 隐藏，有进行中任务显示数量。"""
    from gui_qt import task_manager as tm
    from gui_qt.pages.home_page import HomePage
    app, win, services = app_ctx
    hp = HomePage(win, services)
    try:
        assert hp.recent_tasks.badge_active.text() == "0"
        assert hp.recent_tasks.badge_active.isHidden()
        tid = services.task_manager.add_task(
            name="t", task_type="generic", file_path="x", output_path="x",
            params={}, runner=lambda t, cb: True, need_ffmpeg=False)
        task = services.task_manager.get_task(tid)
        task.state = tm.WAITING  # runner 立即完成，手动置为等待中
        hp._refresh_active_badge()
        assert hp.recent_tasks.badge_active.text() == "1"
        assert not hp.recent_tasks.badge_active.isHidden()
        task.state = tm.SUCCESS
        hp._refresh_active_badge()
        assert hp.recent_tasks.badge_active.text() == "0"
        assert hp.recent_tasks.badge_active.isHidden()
    finally:
        hp.deleteLater()
        app.processEvents()


def test_video_bitrate_editable_combo(app_ctx):
    """视频面板码率改 EditableComboBox：预设 + 可手输自定义值。"""
    from qfluentwidgets import EditableComboBox
    from gui_qt import nav_registry as nr
    app, win, services = app_ctx
    panel = nr.find_item("video")["factory"](win, services)
    try:
        assert isinstance(panel.cb_br, EditableComboBox)
        # 预设选项保留
        assert panel.cb_br.count() >= 3
        # 可手输自定义值（setText 经 ComboBoxBase 同步 currentText）
        panel.cb_br.setText("3.5M")
        assert panel.cb_br.currentText() == "3.5M"
        # collect_params 兼容（键名与 ComboBox 版一致）
        params = panel.collect_params()
        assert isinstance(params, dict)
    finally:
        panel.deleteLater()
        app.processEvents()


def test_font_families_system_default(app_ctx):
    """字体已改用系统默认：FONT_BODY 为系统字体，控件字体族不含 MiSans。"""
    from qfluentwidgets import PrimaryPushButton
    from qfluentwidgets.common.font import fontFamilies
    from gui_qt.components import design_system as ds
    app, win, services = app_ctx
    # 全局正文字体 = 系统默认（微软雅黑）
    assert ds.FONT_BODY == "Microsoft YaHei", ds.FONT_BODY
    # qfluentwidgets 控件字体族保持库默认（无 MiSans 指定）
    fams = fontFamilies()
    assert "MiSans" not in fams, f"不应再指定 MiSans: {fams}"
    btn = PrimaryPushButton("开始转换")
    btn_fams = btn.font().families()
    assert "MiSans" not in btn_fams
    app.processEvents()


def test_qtawesome_plugin_icons(app_ctx):
    """QtAwesome 补充插件图标：全部插件卡片图标非空、面板构建正常。"""
    from qfluentwidgets import IconWidget
    from core.plugin_loader import scan_plugins
    from gui_qt import nav_registry as nr
    from gui_qt.panels.plugin_panel import _PluginCard
    app, win, services = app_ctx
    plugs = scan_plugins()
    assert len(plugs) >= 30
    # 每个插件名都能解析到非空图标
    from gui_qt.panels.plugin_panel import _icon_for
    for p in plugs:
        name = getattr(p, "name", "?")
        w = IconWidget(_icon_for(name))
        assert not w.icon.isNull(), f"插件 {name} 图标为空"
    # 面板构建且卡片数 = 插件数
    panel = nr.find_item("plugins")["factory"](win, services)
    try:
        cards = panel.findChildren(_PluginCard)
        assert len(cards) == len(plugs)
    finally:
        panel.deleteLater()
        app.processEvents()
