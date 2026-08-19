# -*- coding: utf-8 -*-
"""窗口置顶按钮回归测试。

历史 bug：btn_pin 是 checkable 按钮——点击时 Qt 已自动翻转 checked 并把新状态
通过 clicked(bool) 传入；旧版 _toggle_pin 无参并再次 setChecked(not isChecked())，
导致状态被翻转两次：按钮视觉回弹、置顶永远不生效。
修复：_toggle_pin(checked=None)，按钮路径直接使用 Qt 传入的状态，快捷键路径
（checked=None）才手动翻转。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["FORMATMASTER_OFFSCREEN"] = "1"


def _make_win():
    """构造最小化 FakeWin：真实 QWidget + checkable 按钮，绑定 MainWindow._toggle_pin。"""
    from PySide6.QtWidgets import QApplication, QWidget
    from qfluentwidgets import TransparentToolButton
    from gui_qt.app import MainWindow

    app = QApplication.instance() or QApplication([])

    win = QWidget()
    win.btn_pin = TransparentToolButton(win)
    win.btn_pin.setCheckable(True)
    # 复用 MainWindow 的 _toggle_pin（动态绑定到 win）
    win._toggle_pin = MainWindow._toggle_pin.__get__(win, MainWindow)
    win.btn_pin.clicked.connect(win._toggle_pin)
    return app, win


def test_pin_button_click_no_double_toggle():
    """按钮点击路径：Qt 已翻转 checked 并传入 → _toggle_pin 不得再翻转（不回弹）。"""
    app, win = _make_win()
    try:
        win.show()
        app.processEvents()
        assert win.btn_pin.isChecked() is False
        # 模拟真实点击：Qt 自动 setChecked(True) → clicked(True) → _toggle_pin(True)
        win.btn_pin.click()
        app.processEvents()
        # 核心断言：状态保持 True，绝不能被二次翻转回 False
        assert win.btn_pin.isChecked() is True, \
            "点击置顶后按钮状态回弹 = 双重翻转 bug（置顶永远不生效）"
        # 再次点击 → 取消置顶
        win.btn_pin.click()
        app.processEvents()
        assert win.btn_pin.isChecked() is False, "再次点击应取消置顶"
    finally:
        win.deleteLater()
        app.processEvents()


def test_pin_shortcut_path_manual_toggle():
    """快捷键路径（checked=None）：_toggle_pin 手动翻转状态。"""
    app, win = _make_win()
    try:
        win.show()
        app.processEvents()
        assert win.btn_pin.isChecked() is False
        win._toggle_pin()          # 模拟快捷键（无参）
        assert win.btn_pin.isChecked() is True, "快捷键应手动翻转开启置顶"
        win._toggle_pin()
        assert win.btn_pin.isChecked() is False, "快捷键再次调用应取消置顶"
    finally:
        win.deleteLater()
        app.processEvents()
