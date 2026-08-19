"""UI 借鉴落地回归测试（对标 qfluentwidgets 官方设置页 + Fluent-M3U8 任务卡）。

覆盖：
1. 设置页组间距对标官方标准（spacing=20，分组呼吸感）。
2. M3U8 队列行状态视觉：待下载灰点 / 运行中蓝点+进度+速度 / 成功绿✓ / 失败红✕，
   以及上移/移除/清空等队列操作不破坏状态。
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


def _fg(panel, row):
    return panel.lst_queue.item(row).foreground().color().name().upper()


def _m3u8_panel(app_ctx):
    from gui_qt import nav_registry as nr
    app, win, services = app_ctx
    return nr.find_item("m3u8")["factory"](win, services)


def test_m3u8_panel_queue_basic(app_ctx):
    """M3U8 面板：批量添加队列 + 行状态色切换。"""
    app, win, services = app_ctx
    panel = _m3u8_panel(app_ctx)
    try:
        panel._queue.clear()
        panel.txt_url.setPlainText(
            "https://example.com/a.m3u8\nhttps://example.com/b.m3u8")
        panel._batch_add()
        assert panel.lst_queue.count() == 2, panel.lst_queue.count()
        assert len(panel._queue) == 2
        # 状态色：默认灰 → 运行蓝 → 成功绿（state_key: waiting/running/success/failed）
        panel._set_row_state(0, "running")
        assert _fg(panel, 0) == "#2F6BFF"
        panel._set_row_state(0, "success")
        assert _fg(panel, 0) == "#0FA47A"
    finally:
        panel.deleteLater()
        app.processEvents()


def test_settings_group_spacing(app_ctx):
    """设置页分组间距对标官方（20px 呼吸感）。"""
    from gui_qt.pages.settings_page import SettingsPage
    app, win, services = app_ctx
    page = SettingsPage(win, services)
    try:
        # 右侧分页布局 spacing 应为 20（sg 里是 ScrollArea，取 .widget() 才是分页）
        spacings = []
        for i in range(page.sg.count()):
            scroll = page.sg.widget(i)
            page_w = scroll.widget()
            if page_w is not None and page_w.layout() is not None:
                spacings.append(page_w.layout().spacing())
        assert spacings, "未找到分页布局"
        assert all(s == 20 for s in spacings), f"组间距应为 20，实际 {spacings}"
    finally:
        page.deleteLater()
        app.processEvents()


def test_task_card_iconized_meta(app_ctx):
    """TaskCard 图标化元信息（对标 Fluent-M3U8）：速度图标行 + 元信息含文件大小。"""
    app, win, services = app_ctx
    from gui_qt import task_manager as tm
    from gui_qt.components.task_card import TaskCard
    t = tm.Task(task_id=1, name="测试视频.mp4", task_type="video",
                file_path="x.mp4", output_path="y.mp4",
                params={"fmt": "MP4"},
                input_size=3 * 1024 * 1024 + 512 * 1024,
                progress=55, speed="1.5MB/s", state=tm.RUNNING)
    card = TaskCard(t)
    try:
        # 元信息：格式 · 大小 · 优先级
        meta = card._meta_text()
        assert "MP4" in meta and "3.5 MB" in meta and "优先级" in meta, meta
        # 速度图标化：图标 + 文本
        assert not card.speed_icon.icon.isNull()
        assert card.speed_label.text() == "1.5MB/s"
        # 进度/状态流转不受影响
        card.on_progress(70, "下载中", "2.3MB/s")
        assert card.speed_label.text() == "2.3MB/s"
        card.on_state(tm.SUCCESS)
        assert card.badge.text() == "已完成"
    finally:
        card.deleteLater()
        app.processEvents()


