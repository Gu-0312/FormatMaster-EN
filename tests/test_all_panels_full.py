# -*- coding: utf-8 -*-
"""全功能面板全面测试（2026-08-21 第七轮 QA）。

覆盖全部导航入口面板：
1. 构建 + collect_prefs/apply_prefs 往返一致（偏好持久化无破坏）
2. collect_params 可调用（任务调度参数导出）
3. 属性控件遍历：SpinBox/DoubleSpinBox 越界 clamp、ComboBox 逐项切换、
   LineEdit 特殊字符+超长、CheckBox/Slider 极值、min>max 倒置检查
   —— 模拟用户交互，暴露面板联动逻辑 bug

offscreen 伪影规避：gc.disable；单窗口 fixture。
"""
import gc
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["FORMATMASTER_OFFSCREEN"] = "1"
if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
    gc.disable()

import pytest

from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox,
                               QDoubleSpinBox, QLineEdit, QPlainTextEdit,
                               QSlider, QSpinBox, QTextEdit)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def window(app):
    from gui_qt.app import MainWindow
    win = MainWindow()
    win.resize(1280, 820)
    win.show()
    app.processEvents()
    yield win
    win.deleteLater()
    app.processEvents()


def _all_panels(window):
    """返回 [(key, real_panel)]，全部懒加载构建。"""
    from gui_qt import nav_registry as nr
    out = []
    for item in nr.all_items():
        key = item["key"]
        window.switchTo(window.pages[key])
        window.services.set_pref("nav_page", "home")  # 不干扰后续测试
        app = QApplication.instance()
        app.processEvents()
        real = getattr(window.pages[key], "_real", window.pages[key])
        out.append((key, real))
    window.switchTo(window.pages["home"])
    app.processEvents()
    return out


def test_all_panels_build(window, app):
    """全部导航面板可构建（35+）。"""
    panels = _all_panels(window)
    assert len(panels) >= 35, f"面板数 {len(panels)} < 35"
    for key, real in panels:
        assert real is not None, f"{key} 未构建"


def test_all_panels_prefs_roundtrip(window, app):
    """collect_prefs → apply_prefs 往返：控件状态与导出一致（无破坏）。"""
    failures = []
    for key, real in _all_panels(window):
        collect = getattr(real, "collect_prefs", None)
        apply = getattr(real, "apply_prefs", None)
        if not callable(collect) or not callable(apply):
            continue
        try:
            prefs = collect()
            apply(prefs)
            prefs2 = collect()
            # 关键值（组合框/勾选/数字）往返一致
            for k, v in prefs.items():
                if v is None:
                    continue
                if k in prefs2 and prefs2[k] != v:
                    failures.append(f"[{key}] {k}: {v!r} → {prefs2[k]!r}")
        except Exception as e:  # noqa: BLE001
            failures.append(f"[{key}] roundtrip 异常: {type(e).__name__}: {e}")
    assert not failures, "\n".join(failures[:30])


def test_all_panels_collect_params(window, app):
    """collect_params 可调用（任务调度参数导出）。"""
    failures = []
    for key, real in _all_panels(window):
        fn = getattr(real, "collect_params", None)
        if not callable(fn):
            continue
        try:
            params = fn()
            assert isinstance(params, dict), f"{key} collect_params 非 dict"
        except Exception as e:  # noqa: BLE001
            failures.append(f"[{key}] collect_params 异常: {e}")
    assert not failures, "\n".join(failures)


def test_all_panels_control_bounds(window, app):
    """属性控件遍历：越界/特殊值/逐项切换不崩，SpinBox 无 min>max 倒置。"""
    SPECIAL_TEXT = "'\"<>|:*?/\\\u0000 中文😀\n\t"
    failures = []
    for key, real in _all_panels(window):
        # SpinBox 越界 + 倒置检查
        for w in real.findChildren(QSpinBox):
            if w.minimum() > w.maximum():
                failures.append(f"[{key}] SpinBox {w.objectName()} min>max")
                continue
            try:
                w.setValue(w.maximum() + 5000)
                w.setValue(w.minimum() - 5000)
                w.setValue(0)
            except Exception as e:  # noqa: BLE001
                failures.append(f"[{key}] SpinBox {w.objectName()}: {e}")
        for w in real.findChildren(QDoubleSpinBox):
            if w.minimum() > w.maximum():
                failures.append(f"[{key}] DSpinBox {w.objectName()} min>max")
                continue
            try:
                w.setValue(w.maximum() + 999.0)
                w.setValue(w.minimum() - 999.0)
                w.setValue(0.5)
            except Exception as e:  # noqa: BLE001
                failures.append(f"[{key}] DSpinBox {w.objectName()}: {e}")
        # ComboBox 逐项切换（触发面板联动）
        for w in real.findChildren(QComboBox):
            try:
                for i in range(w.count()):
                    w.setCurrentIndex(i)
            except Exception as e:  # noqa: BLE001
                failures.append(f"[{key}] ComboBox {w.objectName()}: {e}")
        # 输入框：特殊字符 + 超长
        for w in real.findChildren(QLineEdit):
            try:
                w.setText(SPECIAL_TEXT)
                w.setText("长" * 5000)
            except Exception as e:  # noqa: BLE001
                failures.append(f"[{key}] LineEdit {w.objectName()}: {e}")
        for w in real.findChildren(QTextEdit):
            try:
                w.setPlainText(SPECIAL_TEXT * 20)
            except Exception as e:  # noqa: BLE001
                failures.append(f"[{key}] TextEdit {w.objectName()}: {e}")
        for w in real.findChildren(QPlainTextEdit):
            try:
                w.setPlainText(SPECIAL_TEXT * 20)
            except Exception as e:  # noqa: BLE001
                failures.append(f"[{key}] PlainTextEdit: {e}")
        # CheckBox / Slider 极值
        for w in real.findChildren(QCheckBox):
            try:
                w.setChecked(True)
                w.setChecked(False)
            except Exception as e:  # noqa: BLE001
                failures.append(f"[{key}] CheckBox {w.objectName()}: {e}")
        for w in real.findChildren(QSlider):
            try:
                w.setValue(w.maximum())
                w.setValue(w.minimum())
            except Exception as e:  # noqa: BLE001
                failures.append(f"[{key}] Slider {w.objectName()}: {e}")
    assert not failures, f"{len(failures)} 处控件异常:\n" + "\n".join(
        failures[:40])
