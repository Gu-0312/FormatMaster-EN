"""config.py 核心函数测试：错误翻译 & FFmpeg 路径"""

import os
import pytest
from utils.config import (
    translate_ffmpeg_error, _find_ffmpeg, invalidate_ffmpeg_path_cache,
)


class TestTranslateFfmpegError:
    """错误翻译：长关键词优先，避免子串误匹配"""

    def test_empty_input(self):
        assert translate_ffmpeg_error("") != ""
        assert translate_ffmpeg_error(None) != ""

    def test_specific_match_takes_priority(self):
        # "Could not find codec parameters" 含 "not found" 子串，
        # 但应返回更具体的文案而非泛化的"找不到必要组件"
        result = translate_ffmpeg_error("Could not find codec parameters")
        assert "媒体参数" in result
        assert "重新安装" not in result  # 不应是泛化的 not found 提示

    def test_not_found_fallback(self):
        # 纯粹 "not found" 应命中末尾兜底规则
        result = translate_ffmpeg_error("somefile.exe: not found")
        assert "编码器" not in result  # 不是 Unknown encoder 误判
        assert "找不到" in result or "重新安装" in result

    def test_unknown_encoder(self):
        result = translate_ffmpeg_error("Unknown encoder 'libx265'")
        assert "编码器" in result

    def test_permission_denied(self):
        result = translate_ffmpeg_error("Permission denied")
        assert "权限" in result

    def test_connection_refused(self):
        result = translate_ffmpeg_error("Connection refused")
        assert "连接" in result or "服务器" in result

    def test_case_insensitive(self):
        result = translate_ffmpeg_error("NO SUCH FILE OR DIRECTORY")
        assert "路径" in result or "输入文件" in result


class TestFfmpegPathCache:

    def teardown_method(self):
        invalidate_ffmpeg_path_cache()

    def test_cache_reuses_result(self, monkeypatch):
        """首次调用走真实路径，后续命中缓存不再探测"""
        call_count = [0]
        origin_which = __import__("shutil").which

        def tracked_which(name):
            call_count[0] += 1
            return origin_which(name)
        monkeypatch.setattr("shutil.which", tracked_which)
        monkeypatch.setattr("utils.config.USER_PREFS", type("p", (), {
            "get": lambda s, p, k, d="": d})())
        invalidate_ffmpeg_path_cache()

        _find_ffmpeg("ffmpeg.exe")
        first = call_count[0]
        _find_ffmpeg("ffmpeg.exe")
        second = call_count[0]
        # 缓存后不应再调用 which
        assert second == first

    def test_invalidate_clears_cache(self, monkeypatch):
        monkeypatch.setattr("utils.config.USER_PREFS", type("p", (), {
            "get": lambda s, p, k, d="": d})())
        invalidate_ffmpeg_path_cache()
        p1 = _find_ffmpeg("ffmpeg.exe")
        invalidate_ffmpeg_path_cache()
        p2 = _find_ffmpeg("ffmpeg.exe")
        assert p1 == p2


class TestMakeOutputPath:
    """输出路径生成：避重名、源目冲突"""

    def test_basic(self, tmp_path):
        from gui_qt.task_manager import make_output_path
        p = make_output_path("D:/videos/test.mp4", str(tmp_path), ".avi")
        assert p.endswith(".avi")
        assert os.path.basename(p) == "test.avi"

    def test_custom_name(self, tmp_path):
        from gui_qt.task_manager import make_output_path
        p = make_output_path("D:/videos/test.mp4", str(tmp_path), ".mp4", name="output")
        assert os.path.basename(p) == "output.mp4"

    def test_same_path_avoids_overwrite(self, tmp_path):
        from gui_qt.task_manager import make_output_path
        src = str(tmp_path / "video.mp4")
        p = make_output_path(src, str(tmp_path), ".mp4")
        assert os.path.basename(p) == "video_1.mp4"

    def test_increments_on_conflict(self, tmp_path):
        from gui_qt.task_manager import make_output_path
        # 源目同路径时自动加 _1，然后与已有文件冲突时按 _N 递增
        (tmp_path / "file.mp4").touch()
        (tmp_path / "file_1.mp4").touch()
        (tmp_path / "file_1_1.mp4").touch()
        p = make_output_path(str(tmp_path / "file.mp4"), str(tmp_path), ".mp4")
        assert os.path.basename(p) == "file_1_2.mp4"


class TestThreadsPerTask:

    def test_single_task_auto(self):
        from gui_qt.task_manager import _threads_per_task
        assert _threads_per_task(1) == 0

    def test_parallel_divides_cores(self):
        from gui_qt.task_manager import _threads_per_task
        t = _threads_per_task(4)
        assert t >= 1

    def test_at_least_one(self):
        from gui_qt.task_manager import _threads_per_task
        t = _threads_per_task(64)
        assert t >= 1
