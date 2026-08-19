"""滚动性能回归测试：页面功能区滚轮必须原生即时滚动（无 400ms 动画延迟）。

背景：懒加载面板（BaseQtPanel 继承 qfluentwidgets ScrollArea）晚于启动时的
enable_smooth_scrolling 构建，SmoothScrollDelegate 保持 LINEAR 模式 →
滚轮事件进 FixedStepSmoothScrollEngine（400ms 逐帧动画）→ 每格滚轮
要 400ms 才滚完（表现为「页面滚轮滚动很慢」）。修复：apply_fast_scroll
处理 root 自身 + 全部子孙，NO_SMOOTH + ScrollPerPixel。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["FORMATMASTER_OFFSCREEN"] = "1"

import pytest

from PySide6.QtWidgets import QApplication, QWidget, QAbstractScrollArea
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QWheelEvent
from qfluentwidgets.common.smooth_scroll import SmoothMode


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _make_area(app):
    from qfluentwidgets import ScrollArea
    sa = ScrollArea()
    big = QWidget()
    big.setFixedHeight(3000)
    sa.setWidget(big)
    sa.setWidgetResizable(True)
    sa.resize(400, 300)
    sa.show()
    app.processEvents()
    sa.verticalScrollBar().setValue(1000)  # 定位到中间便于测双向滚动
    return sa


def _send_wheel(app, sa, delta):
    vp = sa.viewport()
    pos = QPoint(200, 150)
    ev = QWheelEvent(
        pos, sa.mapToGlobal(pos), QPoint(0, 0), QPoint(0, delta),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False)
    before = sa.verticalScrollBar().value()
    QApplication.sendEvent(vp, ev)
    app.processEvents()
    return before - sa.verticalScrollBar().value()


def test_panel_scroll_is_immediate(app):
    """面板滚动区域应用 apply_fast_scroll 后，滚轮立即滚动（NO_SMOOTH 原生）。"""
    from gui_qt.components import design_system as ds
    sa = _make_area(app)
    ds.apply_fast_scroll(sa)
    assert sa.scrollDelagate is not None
    assert sa.scrollDelagate.verticalSmoothScroll.smoothMode == SmoothMode.NO_SMOOTH
    moved = _send_wheel(app, sa, -120)  # 向下滚一格
    assert abs(moved) >= 30, f"滚轮一格应立即滚动 ≥30px，实际 {moved}px（疑似动画延迟）"


def test_scroll_boost_idempotent(app):
    """apply_fast_scroll 幂等：重复应用不重复处理（property 标记）。"""
    from gui_qt.components import design_system as ds
    sa = _make_area(app)
    n1 = ds.apply_fast_scroll(sa)
    n2 = ds.apply_fast_scroll(sa)
    assert n1 >= 1
    assert n2 == 0


def test_panel_build_applies_fast_scroll(app):
    """真实面板构建后自动应用快速滚动（BaseQtPanel.__init__ 内接线）。"""
    from gui_qt.services import QtServices
    from gui_qt.task_manager import TaskManager
    services = QtServices()
    services.task_manager = TaskManager(services)
    from gui_qt.components.theme_manager import ThemeManager
    services.theme_mgr = ThemeManager(services)

    class _Win:
        pass

    from gui_qt import nav_registry as nr
    item = nr.find_item("video")
    panel = item["factory"](_Win(), services)
    try:
        assert isinstance(panel, QAbstractScrollArea)
        assert panel.scrollDelagate is not None
        assert panel.scrollDelagate.verticalSmoothScroll.smoothMode == SmoothMode.NO_SMOOTH, \
            "面板构建后应自动进入 NO_SMOOTH（否则滚轮慢）"
    finally:
        panel.deleteLater()


def test_lazy_page_applies_fast_scroll(app):
    """懒加载页面构建后对整个页面子树应用快速滚动。"""
    from gui_qt.components.sidebar import LazyPage
    from gui_qt import nav_registry as nr
    from qfluentwidgets.common.smooth_scroll import SmoothMode

    item = nr.find_item("pdf")  # 含多个嵌套滚动区域的重面板
    page = LazyPage(item["factory"], object(), None)

    class _FakeServices:
        prefs = None
        def get_pref(self, *a, **k):
            return None

    class _FakeWindow:
        services = _FakeServices()

    # 手动模拟 _ensure（绕过需要真实 services 的构建）
    from gui_qt.services import QtServices
    from gui_qt.task_manager import TaskManager
    services = QtServices()
    services.task_manager = TaskManager(services)
    from gui_qt.components.theme_manager import ThemeManager
    services.theme_mgr = ThemeManager(services)
    page._window = _FakeWindow()
    page._services = services
    page._ensure()
    try:
        # 页面根（LazyPage 自身）+ 面板 + 嵌套滚动区都应被优化
        found = 0
        for sa in [page, page._real, *page.findChildren(QAbstractScrollArea)]:
            d = getattr(sa, "scrollDelagate", None)
            if d is not None:
                found += 1
                assert d.verticalSmoothScroll.smoothMode == SmoothMode.NO_SMOOTH
        assert found >= 1
    finally:
        page.deleteLater()
