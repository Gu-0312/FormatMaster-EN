"""局域网传输面板全屏/最大化响应式适配测试。"""

import os


def _make_panel():
    from PySide6.QtWidgets import QApplication
    from gui_qt.services import QtServices
    from gui_qt.task_manager import TaskManager
    from gui_qt.components.theme_manager import ThemeManager
    from gui_qt.panels.lan_transfer_panel import LanTransferPanelPage

    app = QApplication.instance() or QApplication([])
    services = QtServices()
    services.task_manager = TaskManager(services)
    services.theme_mgr = ThemeManager(services)

    class _Window:
        pass

    panel = LanTransferPanelPage(_Window(), services)
    app.processEvents()
    return app, panel


def test_lan_panel_responsive_fullscreen_and_narrow():
    """内容占满窗口（不封顶、不居中留白），QR 阶梯随宽度，窄窗竖排。"""
    from PySide6.QtWidgets import QBoxLayout

    app, panel = _make_panel()
    try:
        # 模拟全屏/最大化：宽窗
        panel.resize(1920, 1080)
        panel._apply_responsive()
        # 不封顶：inner 可占满任意宽度（默认 QWIDGETSIZE_MAX，不再限制 1180）
        assert panel.inner.maximumWidth() >= 1920, panel.inner.maximumWidth()
        assert panel.url_h.direction() == QBoxLayout.LeftToRight
        # 二维码随宽度放大（≥1800 → 340）
        panel._current_url = "http://192.168.1.10:8000/chat"
        panel._set_qr(panel._current_url)
        assert panel.lb_qr.width() == 340, panel.lb_qr.width()
        assert panel.lb_url.wordWrap() is False  # URL 强制单行

        # 模拟正常窄窗（<820 竖排，<800 → 200）
        panel.resize(700, 600)
        panel._apply_responsive()
        assert panel.url_h.direction() == QBoxLayout.TopToBottom
        panel._set_qr(panel._current_url)
        assert panel.lb_qr.width() == 200, panel.lb_qr.width()

        # 中间宽(1200)：横排，QR=260（给 URL 完整地址留位）
        panel.resize(1200, 800)
        panel._apply_responsive()
        assert panel.url_h.direction() == QBoxLayout.LeftToRight
        panel._set_qr(panel._current_url)
        assert panel.lb_qr.width() == 260, panel.lb_qr.width()
    finally:
        panel.deleteLater()
        app.processEvents()


def test_lan_panel_qr_regenerates_on_resize():
    """服务运行中改变窗口尺寸时，二维码按新尺寸重绘（不糊、不残留旧尺寸）。"""
    app, panel = _make_panel()
    try:
        panel._current_url = "http://10.0.0.5:8000/chat"
        panel._set_qr(panel._current_url)
        assert panel.lb_qr.width() == 200  # 默认宽度（<800）下 200
        panel.resize(1600, 900)
        panel._apply_responsive()  # resizeEvent 会触发，这里显式确保
        assert panel.lb_qr.width() == 300, panel.lb_qr.width()  # <1800 → 300
    finally:
        panel.deleteLater()
        app.processEvents()


def test_lan_panel_paddings_follow_window():
    """内边距/外边距随窗口宽度阶梯变化：窄窗紧凑、全屏宽松。"""
    app, panel = _make_panel()
    try:
        # 窄窗（<820）：外边距 16
        panel.resize(700, 600)
        panel._apply_responsive()
        assert panel.content_layout.contentsMargins().left() == 16
        assert panel._inner_lay.spacing() == 12
        assert panel._cfg_lay.contentsMargins().left() == 16

        # 窗口化（1100）：外边距 24
        panel.resize(1100, 760)
        panel._apply_responsive()
        assert panel.content_layout.contentsMargins().left() == 24
        assert panel._inner_lay.spacing() == 14

        # 全屏（1920）：外边距 40、间距 18
        panel.resize(1920, 1080)
        panel._apply_responsive()
        assert panel.content_layout.contentsMargins().left() == 40
        assert panel._inner_lay.spacing() == 18
        assert panel._cfg_lay.contentsMargins().left() == 28
        assert panel._tip_lay.contentsMargins().left() == 20
    finally:
        panel.deleteLater()
        app.processEvents()
