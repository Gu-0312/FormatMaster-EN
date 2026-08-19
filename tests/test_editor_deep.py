"""四个编辑器组件交互级深度测试（2026-08-16）。

剪辑器 ClipEditorDialog / 取景器 FramePickerDialog / 波形编辑器
WaveformEditorDialog / 合并预览 MergePreviewDialog：构建之上验证
控件交互与参数收集（变换/调整/音量/倍速、导出、入出点、排序）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["FORMATMASTER_OFFSCREEN"] = "1"

import gc

gc.disable()  # offscreen 下规避 Python 3.11 增量 GC 与 Shiboken 回收竞态

import pytest

from PySide6.QtWidgets import QApplication

_MEDIA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_media")
VIDEO = os.path.join(_MEDIA, "sample.mp4")
AUDIO = os.path.join(_MEDIA, "sample.wav")


@pytest.fixture(scope="module", autouse=True)
def media_files():
    """确保测试媒体存在（缺则用 ffmpeg 生成）。"""
    if not (os.path.isfile(VIDEO) and os.path.isfile(AUDIO)):
        import subprocess
        from utils.config import get_ffmpeg_path
        ff = get_ffmpeg_path()
        os.makedirs(_MEDIA, exist_ok=True)
        subprocess.run(
            [ff, "-y", "-f", "lavfi", "-i",
             "testsrc=duration=2:size=320x240:rate=10",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
             "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
             "-shortest", VIDEO], capture_output=True)
        subprocess.run(
            [ff, "-y", "-f", "lavfi", "-i",
             "sine=frequency=440:duration=2", AUDIO], capture_output=True)
    yield


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class TestClipEditor:
    """剪辑器：变换/调整/音量/倍速实时参数收集 + 裁剪范围。"""

    def test_tool_params_transform(self, app):
        from gui_qt.components.clip_editor import ClipEditorDialog
        dlg = ClipEditorDialog(VIDEO)
        try:
            app.processEvents()
            # 旋转
            dlg.cb_rotate.setCurrentIndex(1)   # 90°
            dlg._apply_transform()
            assert dlg.tool_params()["transform"]["rotate"] == 90
            dlg.cb_hflip.setChecked(True)
            dlg._apply_transform()
            assert dlg.tool_params()["transform"]["hflip"] is True
            assert dlg.tool_params()["transform"]["vflip"] is False
            # 裁剪范围初始 = 全片
            s, e = dlg.clip_range()
            assert s == 0.0 and e > 0
        finally:
            dlg._release_media() if hasattr(dlg, "_release_media") else None
            dlg.deleteLater()
            app.processEvents()

    def test_tool_params_adjust(self, app):
        from gui_qt.components.clip_editor import ClipEditorDialog
        dlg = ClipEditorDialog(VIDEO)
        try:
            app.processEvents()
            # 亮度滑杆范围 -50~50（0 默认）：30/50 = 0.6
            dlg._sl_bright.setValue(30)
            # 对比度 0~200（100 默认）：150/100 = 1.5
            dlg._sl_contrast.setValue(150)
            # 饱和度 0~200（100 默认）：80/100 = 0.8
            dlg._sl_satur.setValue(80)
            dlg._apply_adjust()
            adj = dlg.tool_params()["adjust"]
            assert abs(adj["brightness"] - 0.6) < 1e-6, adj
            assert abs(adj["contrast"] - 1.5) < 1e-6, adj
            assert abs(adj["saturation"] - 0.8) < 1e-6, adj
        finally:
            dlg._release_media() if hasattr(dlg, "_release_media") else None
            dlg.deleteLater()
            app.processEvents()

    def test_volume_and_rate(self, app):
        from gui_qt.components.clip_editor import ClipEditorDialog
        dlg = ClipEditorDialog(VIDEO)
        try:
            app.processEvents()
            dlg._sl_volume.setValue(70)
            dlg._apply_volume()
            assert dlg.lb_volume.text() == "70"
            # 静音
            dlg.cb_mute.setChecked(True)
            dlg._apply_volume()
            assert dlg.player.audio_out.volume() == 0
            # 倍速（VideoPlayerWidget.set_playback_rate 存 self._rate）
            dlg._apply_rate("2x")
            assert abs(dlg.player._rate - 2.0) < 1e-6
            dlg._apply_rate("0.5")
            assert abs(dlg.player._rate - 0.5) < 1e-6
            dlg._apply_rate("abc")   # 非法输入回退 1.0
            assert abs(dlg.player._rate - 1.0) < 1e-6
        finally:
            dlg._release_media() if hasattr(dlg, "_release_media") else None
            dlg.deleteLater()
            app.processEvents()


class TestFramePicker:
    """取景器：时间联动 + 单帧导出。"""

    def test_export_single_frame(self, app, tmp_path):
        from gui_qt.components.frame_picker import _export_single_frame
        out = os.path.join(str(tmp_path), "frame.png")
        ok, msg = _export_single_frame(VIDEO, out, 0.5)
        assert ok, msg
        assert os.path.isfile(out) and os.path.getsize(out) > 0
        # 有效 PNG 头
        with open(out, "rb") as f:
            assert f.read(4) == b"\x89PNG"

    def test_export_paths_and_time_link(self, app, tmp_path):
        from gui_qt.components.frame_picker import FramePickerDialog
        dlg = FramePickerDialog(VIDEO, out_dir=str(tmp_path))
        try:
            app.processEvents()
            assert dlg.export_paths() == []
            # 时间联动：duration → timeline（内部 _duration）
            dlg._on_duration(2000)
            assert abs(dlg.timeline._duration - 2.0) < 1e-6
            dlg._on_position(1000)
            assert abs(dlg.timeline._playhead - 1.0) < 1e-6
            assert "/" in dlg.lb_top_time.text()
        finally:
            dlg._release_media()
            dlg.deleteLater()
            app.processEvents()


class TestAudioEditor:
    """波形编辑器：波形加载 + 入出点 + 重置。"""

    def test_waveform_loaded(self, app):
        from gui_qt.components.audio_editor import WaveformEditorDialog
        dlg = WaveformEditorDialog(AUDIO)
        try:
            app.processEvents()
            assert dlg.wave.data, "波形数据应为空"
            assert dlg.wave.duration > 0
            s, e = dlg.clip_range()
            assert s == 0.0 and e > 0
            assert dlg.lb_in.text() and dlg.lb_out.text()
        finally:
            dlg._release_media()
            dlg.deleteLater()
            app.processEvents()

    def test_in_out_and_reset(self, app):
        from gui_qt.components.audio_editor import WaveformEditorDialog
        dlg = WaveformEditorDialog(AUDIO)
        try:
            app.processEvents()
            dur = dlg.wave.duration
            # 手动设入出点（offscreen 下 player.position 恒 0，直接赋值再刷新）
            dlg._in_sec = 0.3
            dlg._out_sec = 1.2
            dlg.wave.set_range(0.3, 1.2)
            dlg._refresh_labels()
            s, e = dlg.clip_range()
            assert abs(s - 0.3) < 1e-6 and abs(e - 1.2) < 1e-6
            # 重置回全片
            dlg._reset()
            s2, e2 = dlg.clip_range()
            assert s2 == 0.0 and abs(e2 - dur) < 1e-6
        finally:
            dlg._release_media()
            dlg.deleteLater()
            app.processEvents()


class TestMergePreview:
    """合并预览：文件列表填充 + 上移/下移排序。"""

    def _files(self):
        d = os.path.join(_MEDIA, "merge")
        os.makedirs(d, exist_ok=True)
        paths = []
        for i, name in enumerate(["a.mp4", "b.mp4", "c.mp4"], 1):
            p = os.path.join(d, name)
            if not os.path.isfile(p):
                import shutil
                shutil.copyfile(VIDEO, p)
            paths.append(p)
        return paths

    def test_order_and_move(self, app):
        from gui_qt.components.merge_preview import MergePreviewDialog
        files = self._files()
        dlg = MergePreviewDialog(files)
        try:
            app.processEvents()
            assert dlg.list_widget.count() == 3
            assert dlg.ordered_files() == files
            # 上移第 2 项 → [b, a, c]
            dlg.list_widget.setCurrentRow(1)
            dlg._move_up()
            assert dlg.ordered_files() == [files[1], files[0], files[2]]
            # 下移第 2 项 → [b, c, a]
            dlg.list_widget.setCurrentRow(1)
            dlg._move_down()
            assert dlg.ordered_files() == [files[1], files[2], files[0]]
            # 边界：第 0 项不能再上移
            dlg.list_widget.setCurrentRow(0)
            dlg._move_up()
            assert dlg.ordered_files() == [files[1], files[2], files[0]]
            # 边界：最后一项不能再下移
            dlg.list_widget.setCurrentRow(2)
            dlg._move_down()
            assert dlg.ordered_files() == [files[1], files[2], files[0]]
        finally:
            dlg._release_media()
            dlg.deleteLater()
            app.processEvents()
