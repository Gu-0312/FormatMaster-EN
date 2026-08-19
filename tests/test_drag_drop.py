"""拖拽测试：文件拖入 FileListCard 的接受逻辑。

覆盖：多文件拖入（扩展名过滤）、目录拖入（递归收集）、重复去重、
拖入后文件列表状态刷新、PDF 编辑器网格构建。

注意：手工构造 QDragEnterEvent/QDropEvent 时，QMimeData 的 Python 包装
必须保持存活（存到全局列表），否则被 GC 后事件内 C++ 指针悬垂，
mimeData() 会退化为 QObject（hasUrls 丢失）。测试结束前保持引用，
避免 pytest 对已回收 PySide6 对象做 repr 触发 access violation。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["FORMATMASTER_OFFSCREEN"] = "1"

import pytest

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QMimeData, QUrl, Qt, QPoint, QPointF
from PySide6.QtGui import QDropEvent, QDragEnterEvent

from gui_qt.widgets import FileListCard

# 保持 QMimeData Python 包装存活，防止事件内 C++ 指针悬垂
_KEEP_ALIVE = []


def _mime(paths):
    m = QMimeData()
    m.setUrls([QUrl.fromLocalFile(p) for p in paths])
    _KEEP_ALIVE.append(m)
    return m


def _drop_event(paths):
    return QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction,
                      _mime(paths), Qt.MouseButton.LeftButton,
                      Qt.KeyboardModifier.NoModifier)


def _drag_enter(paths):
    return QDragEnterEvent(QPoint(10, 10), Qt.DropAction.CopyAction,
                           _mime(paths), Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def tmp_files():
    with tempfile.TemporaryDirectory() as d:
        v1 = os.path.join(d, "a.mp4")
        v2 = os.path.join(d, "b.mp4")
        txt = os.path.join(d, "note.txt")
        for p in (v1, v2, txt):
            with open(p, "wb") as f:
                f.write(b"x" * 100)
        sub = os.path.join(d, "sub")
        os.makedirs(sub)
        v3 = os.path.join(sub, "c.mkv")
        with open(v3, "wb") as f:
            f.write(b"x" * 50)
        with open(os.path.join(sub, "d.log"), "wb") as f:
            f.write(b"x")
        yield {"d": d, "v1": v1, "v2": v2, "txt": txt, "v3": v3}


def test_drag_enter_accepts_urls(app, tmp_files):
    card = FileListCard(file_exts={".mp4", ".mkv"})
    e = _drag_enter([tmp_files["v1"]])
    card.dragEnterEvent(e)
    assert e.isAccepted(), "拖入合法文件应接受"


def test_drag_drop_multiple_with_filter(app, tmp_files):
    """多文件拖入：非法扩展名被过滤。"""
    card = FileListCard(file_exts={".mp4", ".mkv"})
    card.dropEvent(_drop_event([tmp_files["v1"], tmp_files["v2"], tmp_files["txt"]]))
    files = card.files()
    assert len(files) == 2, f"应只接受 2 个合法文件，实际 {files}"
    assert all(p.endswith((".mp4", ".mkv")) for p in files)


def test_drag_drop_folder_recursive(app, tmp_files):
    """目录拖入：递归收集合法扩展名文件。"""
    card = FileListCard(file_exts={".mp4", ".mkv"})
    card.dropEvent(_drop_event([tmp_files["d"]]))
    files = card.files()
    assert len(files) == 3, f"目录应递归收集 3 个合法文件，实际 {len(files)}"
    assert any("c.mkv" in p for p in files)


def test_drag_drop_dedup(app, tmp_files):
    """重复拖入同一文件：去重不重复添加。"""
    card = FileListCard(file_exts={".mp4"})
    card.dropEvent(_drop_event([tmp_files["v1"]]))
    card.dropEvent(_drop_event([tmp_files["v1"], tmp_files["v2"]]))
    files = card.files()
    assert files.count(tmp_files["v1"]) == 1, "同一文件不应重复添加"
    assert len(files) == 2


def test_drop_emits_files_changed(app, tmp_files):
    """拖入成功发射 files_changed 信号；无有效文件不发射。"""
    card = FileListCard(file_exts={".mp4"})
    fired = []
    card.files_changed.connect(lambda: fired.append(1))
    card.dropEvent(_drop_event([tmp_files["v1"]]))
    assert fired, "拖入文件应发射 files_changed"
    card2 = FileListCard(file_exts={".mp4"})
    fired2 = []
    card2.files_changed.connect(lambda: fired2.append(1))
    card2.dropEvent(_drop_event([tmp_files["txt"]]))
    assert not fired2, "无有效文件不应发射信号"


def test_pdf_editor_grid_builds(app):
    """PDF 可视化编辑器面板可构建（含缩略图网格）。"""
    from gui_qt.services import QtServices
    from gui_qt.task_manager import TaskManager
    from gui_qt.components.theme_manager import ThemeManager
    services = QtServices()
    services.task_manager = TaskManager(services)
    services.theme_mgr = ThemeManager(services)

    class _Win:
        pass

    from gui_qt import nav_registry as nr
    item = nr.find_item("pdf_editor")
    panel = item["factory"](_Win(), services)
    try:
        assert panel is not None
        from gui_qt.panels.pdf_editor_panel import _PageGrid
        grids = panel.findChildren(_PageGrid)
        assert len(grids) == 1, "PDF 编辑器应包含 1 个页面网格"
        grid = grids[0]
        from PySide6.QtWidgets import QAbstractItemView
        assert grid.dragDropMode() != QAbstractItemView.NoDragDrop, "网格应支持拖拽"
        assert grid.defaultDropAction() == Qt.MoveAction
    finally:
        panel.deleteLater()
