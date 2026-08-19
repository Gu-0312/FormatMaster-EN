"""设置页新增功能的核心逻辑测试（无 GUI 依赖）。"""

import os
import threading

import pytest

from utils.net_proxy import apply_proxy, proxy_args_for_ytdlp
from utils.temp_cleanup import cleanup_temp_files, _matches_dir


class TestProxy:
    def teardown_method(self):
        apply_proxy("off")

    def test_manual_sets_env(self):
        assert apply_proxy("manual", "127.0.0.1", 7890) is True
        assert os.environ.get("HTTP_PROXY") == "http://127.0.0.1:7890"
        assert os.environ.get("HTTPS_PROXY") == "http://127.0.0.1:7890"

    def test_off_clears_env(self):
        apply_proxy("manual", "127.0.0.1", 7890)
        assert apply_proxy("off") is False
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                  "http_proxy", "https_proxy"):
            assert k not in os.environ

    def test_invalid_port_noop(self):
        assert apply_proxy("manual", "host", 0) is False
        assert "HTTP_PROXY" not in os.environ

    def test_ytdlp_args(self):
        class Prefs:
            def get_pref(self, k, d=None):
                return {"proxy_mode": "manual", "proxy_host": "h",
                        "proxy_port": 8080}.get(k, d)
        assert proxy_args_for_ytdlp(Prefs().get_pref) == ["--proxy", "http://h:8080"]

    def test_ytdlp_args_off(self):
        class Prefs:
            def get_pref(self, k, d=None):
                return {"proxy_mode": "off"}.get(k, d)
        assert proxy_args_for_ytdlp(Prefs().get_pref) == []


class TestTempCleanup:
    def test_matches_dir(self):
        assert _matches_dir("fm_share_abc")
        assert _matches_dir("xyz_m3u8")
        assert not _matches_dir("normal_dir")
        assert not _matches_dir("formatmaster_concat_1.txt")

    def test_cleanup_files_and_empty_dirs(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        # 匹配文件
        (tmp_path / "formatmaster_concat_123.txt").write_text("x")
        (tmp_path / "formatmaster_update_123.zip").write_text("x")
        # 不匹配文件（不动）
        (tmp_path / "user_file.txt").write_text("keep")
        # 空目录（删）与非空目录（保留）
        (tmp_path / "fm_share_a").mkdir()
        (tmp_path / "fm_share_b").mkdir()
        (tmp_path / "fm_share_b" / "file.bin").write_bytes(b"x")
        (tmp_path / "keep_dir").mkdir()
        (tmp_path / "keep_dir" / "f").write_text("x")

        n = cleanup_temp_files()
        assert not (tmp_path / "formatmaster_concat_123.txt").exists()
        assert not (tmp_path / "formatmaster_update_123.zip").exists()
        assert (tmp_path / "user_file.txt").exists(), "不应动用户文件"
        assert not (tmp_path / "fm_share_a").exists(), "空目录应清理"
        assert (tmp_path / "fm_share_b").exists(), "非空目录应保留"
        assert (tmp_path / "keep_dir").exists()
        assert n >= 3

    def test_cleanup_no_match_noop(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        (tmp_path / "random.txt").write_text("x")
        assert cleanup_temp_files() == 0
        assert (tmp_path / "random.txt").exists()


class TestLoggerConfigure:
    def test_level_filter(self, tmp_path, monkeypatch):
        from app import logger
        # 重定向日志目录到临时目录，避免污染真实日志
        monkeypatch.setattr(logger, "get_log_dir", lambda: str(tmp_path))
        logger.configure(level="error")
        assert logger._LEVEL == logger.ERROR
        # 真实 log：error 级别下 DEBUG/INFO 应被过滤
        logger.log("debug line", logger.DEBUG)
        logger.log("info line", logger.INFO)
        logger.log("error line", logger.ERROR)
        content = (tmp_path / "debug.log").read_text(encoding="utf-8")
        assert "error line" in content
        assert "debug line" not in content
        assert "info line" not in content
        logger.configure(level="debug")
        assert logger._LEVEL == logger.DEBUG

    def test_backup_count(self):
        from app import logger
        logger.configure(backup_count=5)
        assert logger.BACKUP_COUNT == 5
        logger.configure(backup_count=1)
        assert logger.BACKUP_COUNT == 1


class TestUpdateCheckDue:
    def test_always(self):
        from gui_qt.app import _update_check_due
        assert _update_check_due(lambda k, d=None: "always" if k == "update_check_freq" else d) is True

    def test_daily_due_today(self):
        import datetime
        from gui_qt.app import _update_check_due
        today = datetime.date.today().isoformat()
        prefs = {"update_check_freq": "daily", "update_last_check": today}
        assert _update_check_due(lambda k, d=None: prefs.get(k, d)) is False
        prefs["update_last_check"] = "2020-01-01"
        assert _update_check_due(lambda k, d=None: prefs.get(k, d)) is True

    def test_weekly(self):
        import datetime
        from gui_qt.app import _update_check_due
        prefs = {"update_check_freq": "weekly", "update_last_check": ""}
        assert _update_check_due(lambda k, d=None: prefs.get(k, d)) is True
        # 8 天前 → 应检查
        from datetime import date, timedelta
        prefs["update_last_check"] = (date.today() - timedelta(days=8)).isoformat()
        assert _update_check_due(lambda k, d=None: prefs.get(k, d)) is True
        # 3 天前 → 不检查
        prefs["update_last_check"] = (date.today() - timedelta(days=3)).isoformat()
        assert _update_check_due(lambda k, d=None: prefs.get(k, d)) is False


class TestSubtitleFontFilter:
    def _run_convert(self, monkeypatch, sub_font_size):
        """mock 掉 ffmpeg 执行，返回构建的 cmd；返回 -vf 值或 None。"""
        from types import SimpleNamespace
        from core import video_converter as vc
        captured = {}

        def fake_run(cmd, **kw):
            captured["cmd"] = list(cmd)
            return SimpleNamespace(success=True, cancelled=False, error_cn="")

        monkeypatch.setattr(vc, "run_ffmpeg", fake_run)
        monkeypatch.setattr(vc, "get_ffmpeg_path", lambda: "C:/ffmpeg.exe")
        monkeypatch.setattr(vc, "get_best_hw_accel", lambda: None)
        monkeypatch.setattr(vc, "detect_hardware_acceleration", lambda: [])
        # 实例方法 mock：不探测真实输入文件
        monkeypatch.setattr(vc.VideoConverter, "get_duration", lambda self, p: 10.0)
        monkeypatch.setattr(vc.VideoConverter, "_get_video_codec_name", lambda self, p: "")
        monkeypatch.setattr(vc.VideoConverter, "has_audio_stream", lambda self, p: False)

        import tempfile
        sub = os.path.join(tempfile.gettempdir(), "fm_test_sub.srt")
        with open(sub, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,000 --> 00:00:01,000\nhello\n")
        try:
            conv = vc.VideoConverter()
            ok = conv._convert_once("in.mp4", "out.mp4", "mp4",
                                    subtitle_path=sub, sub_font_size=sub_font_size)
            assert ok
            cmd = captured["cmd"]
            if "-vf" in cmd:
                return cmd[cmd.index("-vf") + 1]
            return None
        finally:
            try:
                os.remove(sub)
            except OSError:
                pass

    def test_force_style_added(self, monkeypatch):
        vf = self._run_convert(monkeypatch, 32)
        assert vf is not None, "应有 -vf 滤镜"
        # 正确语法：subtitles='路径':force_style='FontSize=32'（路径引号闭合）
        assert vf.startswith("subtitles='"), vf
        assert ":force_style='FontSize=32'" in vf, vf
        # 路径引号必须闭合后再接 force_style（修复前会缺引号）
        assert "subtitles='" in vf and vf.count("'") >= 4, vf

    def test_no_font_no_force_style(self, monkeypatch):
        vf = self._run_convert(monkeypatch, None)
        assert vf is not None
        assert "force_style" not in vf
        assert vf.startswith("subtitles='") and vf.endswith("'"), vf

    def test_signature_default(self):
        import inspect
        from core.video_converter import VideoConverter
        sig = inspect.signature(VideoConverter.convert)
        assert "sub_font_size" in sig.parameters
        assert sig.parameters["sub_font_size"].default is None
