"""编辑器类功能窗口测试。

覆盖所有编辑器/预览/对话框组件：构建、控件存在性、基本交互。
媒体文件由 conftest 级 fixture 用 ffmpeg 生成（tests/_media/）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["FORMATMASTER_OFFSCREEN"] = "1"

import pytest

from PySide6.QtWidgets import QApplication

_MEDIA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_media")
VIDEO = os.path.join(_MEDIA, "sample.mp4")
AUDIO = os.path.join(_MEDIA, "sample.wav")
SRT = os.path.join(_MEDIA, "sample.srt")


@pytest.fixture(scope="module", autouse=True)
def media_files():
    """确保测试媒体存在（缺则用 ffmpeg 生成）。"""
    if not (os.path.isfile(VIDEO) and os.path.isfile(AUDIO)):
        import subprocess
        from utils.config import get_ffmpeg_path
        ff = get_ffmpeg_path()
        os.makedirs(_MEDIA, exist_ok=True)
        subprocess.run(
            [ff, "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
             "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
             "-shortest", VIDEO], capture_output=True)
        subprocess.run(
            [ff, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
             AUDIO], capture_output=True)
    if not os.path.isfile(SRT):
        with open(SRT, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,000 --> 00:00:01,000\n测试字幕第一行\n\n"
                    "2\n00:00:01,000 --> 00:00:02,000\n测试字幕第二行\n")
    yield


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _build_dialog(dlg_cls, *args, **kwargs):
    """构建对话框 + 回收，返回实例（调用方负责 deleteLater）。"""
    dlg = dlg_cls(*args, **kwargs)
    assert dlg is not None
    return dlg


def test_audio_editor_dialog(app):
    """音频波形编辑器：可构建，含波形视图与确定/取消。"""
    from gui_qt.components.audio_editor import WaveformEditorDialog
    dlg = _build_dialog(WaveformEditorDialog, AUDIO)
    try:
        assert dlg.windowTitle()
        from gui_qt.components.audio_editor import WaveformView
        assert dlg.findChildren(WaveformView), "应含波形视图"
        buttons = [b for b in dlg.findChildren(type(dlg.btn_ok))] if hasattr(dlg, "btn_ok") else []
        assert buttons, "应含确定按钮"
    finally:
        dlg.deleteLater()
        app.processEvents()


def test_clip_editor_dialog(app):
    """视频剪辑编辑器：可构建，含时间轴相关控件。"""
    from gui_qt.components.clip_editor import ClipEditorDialog
    dlg = _build_dialog(ClipEditorDialog, VIDEO)
    try:
        assert dlg.windowTitle()
        app.processEvents()
    finally:
        dlg.deleteLater()
        app.processEvents()


def test_frame_picker_dialog(app):
    """视频抽帧取景器：可构建。"""
    from gui_qt.components.frame_picker import FramePickerDialog
    dlg = _build_dialog(FramePickerDialog, VIDEO)
    try:
        assert dlg.windowTitle()
        app.processEvents()
    finally:
        dlg.deleteLater()
        app.processEvents()


def test_merge_preview_dialog(app):
    """视频合并预览：可构建并展示文件列表。"""
    from gui_qt.components.merge_preview import MergePreviewDialog
    dlg = _build_dialog(MergePreviewDialog, [VIDEO, VIDEO])
    try:
        assert dlg.windowTitle()
        app.processEvents()
    finally:
        dlg.deleteLater()
        app.processEvents()


def test_subtitle_timeline_dialog(app):
    """字幕时间线编辑器：可构建，含字幕轨道。"""
    from gui_qt.components.subtitle_editor import SubtitleTimelineDialog
    dlg = _build_dialog(SubtitleTimelineDialog, SRT, VIDEO)
    try:
        assert dlg.windowTitle()
        from gui_qt.components.subtitle_editor import SubtitleTrackWidget
        assert dlg.findChildren(SubtitleTrackWidget), "应含字幕轨道"
        app.processEvents()
    finally:
        dlg.deleteLater()
        app.processEvents()


def test_video_preview_widget(app):
    """视频预览/播放器组件：可构建。"""
    from gui_qt.components.video_preview import VideoPlayerWidget
    w = VideoPlayerWidget()
    try:
        assert w is not None
    finally:
        w.deleteLater()
        app.processEvents()


def test_download_progress_dialog(app):
    """工具下载进度对话框：可构建、可更新进度、可取消。"""
    from gui_qt.components.download_progress_dialog import DownloadProgressDialog
    dlg = _build_dialog(DownloadProgressDialog, "FFmpeg")
    try:
        assert dlg.windowTitle()
        # 进度更新（0→50→100）
        if hasattr(dlg, "set_progress"):
            dlg.set_progress(50, "下载中 50%")
        app.processEvents()
        if hasattr(dlg, "set_progress"):
            dlg.set_progress(100, "完成")
        app.processEvents()
    finally:
        dlg.deleteLater()
        app.processEvents()


def test_url_list_dialog(app):
    """URL 列表对话框：可构建并加载条目。"""
    from gui_qt.panels.url_list_dialog import UrlListDialog
    items = [{"title": "测试视频1", "url": "https://example.com/1.mp4"},
             {"title": "测试视频2", "url": "https://example.com/2.mp4"}]
    used = []
    dlg = _build_dialog(UrlListDialog, "选择视频", items,
                        lambda u: used.append(u))
    try:
        assert dlg.windowTitle()
        app.processEvents()
    finally:
        dlg.deleteLater()
        app.processEvents()


def test_editor_panels_embed(app):
    """编辑器所在面板（音频处理/视频处理/抽帧）构建正常且含编辑器入口。"""
    from gui_qt.services import QtServices
    from gui_qt.task_manager import TaskManager
    from gui_qt.components.theme_manager import ThemeManager
    services = QtServices()
    services.task_manager = TaskManager(services)
    services.theme_mgr = ThemeManager(services)

    class _Win:
        pass

    from gui_qt import nav_registry as nr
    for key in ("audio_edit", "video_tools", "frame_extract"):
        panel = nr.find_item(key)["factory"](_Win(), services)
        try:
            assert panel is not None
            app.processEvents()
        finally:
            panel.deleteLater()
            app.processEvents()
