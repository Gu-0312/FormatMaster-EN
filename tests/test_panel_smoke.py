"""GUI 面板全量冒烟:41 面板 offscreen 构建 + 控件属性遍历 + params/prefs 往返。

运行:venv/Scripts/python -m pytest tests/test_panel_smoke.py -q
覆盖:nav_registry 全部入口的构建;面板类再验证 collect_params/collect_prefs/apply_prefs。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["FORMATMASTER_OFFSCREEN"] = "1"

import pytest

from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QLineEdit,
                               QSlider, QSpinBox)


@pytest.fixture(scope="module")
def app_ctx():
    from gui_qt.services import QtServices
    from gui_qt.task_manager import TaskManager
    app = QApplication.instance() or QApplication([])
    services = QtServices()
    services.task_manager = TaskManager(services)
    from gui_qt.components.theme_manager import ThemeManager
    services.theme_mgr = ThemeManager(services)

    class _Window:
        """最小主窗口桩:仅提供面板可能访问的通用接口。"""
        pass

    win = _Window()
    yield app, win, services
    app.processEvents()


def _iter_controls(panel):
    """遍历面板内可设置控件,按类型设置合理值。"""
    for w in panel.findChildren(QComboBox):
        if w.count() > 0:
            for i in range(w.count()):
                w.setCurrentIndex(i)
    for w in panel.findChildren(QCheckBox):
        w.setChecked(not w.isChecked())
    for w in panel.findChildren(QSlider):
        if w.minimum() != w.maximum():
            w.setValue(w.minimum())
    for w in panel.findChildren(QSpinBox):
        w.setValue(w.minimum())
    for w in panel.findChildren(QLineEdit):
        if not w.text():
            w.setText("测试")
    return True


def test_all_nav_entries_build(app_ctx):
    """全部导航入口(页面+面板)都能 offscreen 构建。"""
    app, win, services = app_ctx
    from gui_qt import nav_registry as nr
    failures = []
    built = 0
    for item in nr.all_items():
        key = item["key"]
        try:
            panel = item["factory"](win, services)
            assert panel is not None
            built += 1
            panel.deleteLater()
        except Exception as e:  # noqa: BLE001
            import traceback
            failures.append((key, f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}"))
    total = sum(1 for _ in nr.all_items())
    if failures:
        msg = "\n".join(f"  [{k}] {v}" for k, v in failures)
        print(msg)
    assert built == total, f"应构建 {total} 个,实际 {built}"
    assert not failures
    print(f"全部 {built} 个导航入口构建通过")


def test_ocr_switch_labels_persist_when_checked(app_ctx):
    """OCR 面板:表格识别/嵌入原图/批量模式 开关开启后标签仍显示中文(不变成 'On')。

    qfluentwidgets.SwitchButton 构造只设 offText,onText 默认 'On';
    开启(checked)后 _updateText 会用 onText 替换标签 → 中文名"消失"。
    面板已显式 setOnText 中文名,本测试锁定该行为。
    """
    app, win, services = app_ctx
    from gui_qt import nav_registry as nr
    item = next(i for i in nr.all_items() if i["key"] == "ocr")
    panel = item["factory"](win, services)
    try:
        for sw, expect in [
            (panel.sw_table, "表格识别"),
            (panel.sw_image, "嵌入原图"),
            (panel.sw_batch, "批量模式"),
        ]:
            sw.setChecked(False)
            assert sw.label.text() == expect, \
                f"{expect} 关闭态标签错误: {sw.label.text()!r}"
            sw.setChecked(True)
            assert sw.label.text() == expect, \
                f"{expect} 开启态标签错误(变成了 {sw.label.text()!r})"
    finally:
        panel.deleteLater()


def test_all_panels_controls_and_params(app_ctx):
    """面板类:构建 → 控件属性遍历 → collect_params/prefs 往返无异常。"""
    app, win, services = app_ctx
    from gui_qt import nav_registry as nr
    from gui_qt.panels.base_panel import BaseQtPanel
    failures = []
    passed = 0
    for item in nr.all_items():
        key = item["key"]
        try:
            panel = item["factory"](win, services)
            if not isinstance(panel, BaseQtPanel):
                panel.deleteLater()
                continue  # 页面类不做 params 验证
            _iter_controls(panel)
            params = panel.collect_params()
            assert isinstance(params, dict), "collect_params 非 dict"
            prefs = panel.collect_prefs()
            assert isinstance(prefs, dict), "collect_prefs 非 dict"
            panel.apply_prefs(prefs)
            passed += 1
            panel.deleteLater()
        except Exception as e:  # noqa: BLE001
            import traceback
            failures.append((key, f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}"))
    if failures:
        msg = "\n".join(f"  [{k}] {v}" for k, v in failures)
        print(msg)
    assert not failures, f"{len(failures)} 个面板失败"
    print(f"{passed} 个面板控件遍历 + params/prefs 往返通过")
