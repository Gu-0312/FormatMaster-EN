# -*- coding: utf-8 -*-
"""core/audio_converter.py focused 单元测试。

覆盖 trigger → decision → recovery → result 链路：
- trigger: convert / _get_duration 入口
- decision: ffmpeg 命令构建（编码参数、音量滤镜）与进度解析
- recovery: ffmpeg 缺失、探测失败降级、进程失败、异常、取消
- result: 返回值与 progress_callback 最终状态

所有 subprocess 均 mock，不依赖真实 ffmpeg。
"""
import json

import pytest

from core import audio_converter as ac_mod
from core.audio_converter import AudioConverter
from core import ffmpeg_executor as ffprobe_mod


class FakeProcess:
    """模拟 Popen 进程（stderr 即自身）。"""

    def __init__(self, stderr_lines=(), returncode=0, on_readline=None):
        self._lines = [
            l if isinstance(l, bytes) else l.encode("utf-8") for l in stderr_lines
        ]
        self._final_rc = returncode
        self.returncode = None
        self._on_readline = on_readline
        self.terminated = False
        self.killed = False
        self.stderr = self

    def readline(self):
        if self._on_readline:
            self._on_readline(self)
        if self._lines:
            return self._lines.pop(0)
        return b""

    def poll(self):
        if self._lines:
            return None
        self.returncode = self._final_rc
        return self._final_rc

    def terminate(self):
        self.terminated = True
        self.returncode = self._final_rc

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return self._final_rc


class FakeRunResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def fake_select_factory():
    def fake_select(rlist, wlist, xlist, timeout=None):
        return list(rlist), [], []
    return fake_select


@pytest.fixture
def patched_env(monkeypatch):
    monkeypatch.setattr(ac_mod, "get_ffmpeg_path", lambda: "/fake/ffmpeg")
    monkeypatch.setattr(ac_mod, "get_ffprobe_raw", lambda fp, timeout=None: None)
    monkeypatch.setattr("select.select", fake_select_factory())
    record = {"cmds": [], "proc": None}

    def fake_popen(cmd, *args, **kwargs):
        record["cmds"].append(list(cmd))
        return record["proc"] if record["proc"] is not None else FakeProcess()

    monkeypatch.setattr(ac_mod.subprocess, "Popen", fake_popen)
    return record


@pytest.fixture
def converter():
    return AudioConverter()


# ═══════════════════════════════════════════════
#  _get_duration（探测 recovery：失败必须降级为 0）
# ═══════════════════════════════════════════════

class TestGetDuration:
    def test_parses_valid_json(self, converter, monkeypatch):
        monkeypatch.setattr(ac_mod, "get_ffprobe_raw",
                            lambda fp, timeout=None: {"format": {"duration": "3.5"}})
        assert converter._get_duration("a.mp3") == 3.5

    def test_returns_zero_when_no_ffprobe(self, converter, monkeypatch):
        monkeypatch.setattr(ac_mod, "get_ffprobe_raw", lambda fp, timeout=None: None)
        assert converter._get_duration("a.mp3") == 0

    def test_returns_zero_on_probe_failure(self, converter, monkeypatch):
        monkeypatch.setattr(ac_mod, "get_ffprobe_raw", lambda fp, timeout=None: None)
        assert converter._get_duration("a.mp3") == 0

    def test_returns_zero_on_exception(self, converter, monkeypatch):
        def boom(fp, timeout=None):
            raise OSError("probe crashed")
        monkeypatch.setattr(ac_mod, "get_ffprobe_raw", boom)
        assert converter._get_duration("a.mp3") == 0


# ═══════════════════════════════════════════════
#  convert：recovery
# ═══════════════════════════════════════════════

class TestConvertRecovery:
    def test_no_ffmpeg_returns_false(self, converter, monkeypatch):
        monkeypatch.setattr(ac_mod, "get_ffmpeg_path", lambda: None)
        calls = []
        ok = converter.convert("a.wav", "a.mp3",
                               progress_callback=lambda p, m: calls.append((p, m)))
        assert ok is False
        assert calls == [(-1, "错误: FFmpeg未安装")]

    def test_ffmpeg_nonzero_exit_reports_translated_error(
            self, converter, monkeypatch, patched_env):
        patched_env["proc"] = FakeProcess(
            stderr_lines=["No such file or directory\n"], returncode=1)
        calls = []
        ok = converter.convert("a.wav", "a.mp3",
                               progress_callback=lambda p, m: calls.append((p, m)))
        assert ok is False
        assert any(p == -1 and m.startswith("转换失败：") for p, m in calls)
        assert not any(p == 100 for p, m in calls)

    def test_popen_exception_returns_false(self, converter, monkeypatch):
        monkeypatch.setattr(ac_mod, "get_ffmpeg_path", lambda: "/fake/ffmpeg")
        monkeypatch.setattr("select.select", fake_select_factory())

        def boom(cmd, *a, **k):
            raise OSError("cannot spawn")

        monkeypatch.setattr(ac_mod.subprocess, "Popen", boom)
        calls = []
        ok = converter.convert("a.wav", "a.mp3",
                               progress_callback=lambda p, m: calls.append((p, m)))
        assert ok is False
        assert calls and calls[-1][0] == -1 and "cannot spawn" in calls[-1][1]

    def test_cancel_terminates_process(self, converter, monkeypatch, patched_env):
        proc = FakeProcess(stderr_lines=["time=00:00:01.00\n"], returncode=0)
        proc._on_readline = lambda p: setattr(converter, "_cancel", True)
        patched_env["proc"] = proc
        calls = []
        ok = converter.convert("a.wav", "a.mp3",
                               progress_callback=lambda p, m: calls.append((p, m)))
        assert ok is False
        assert proc.terminated is True
        assert calls and calls[-1] == (-1, "已取消")


# ═══════════════════════════════════════════════
#  convert：decision（命令构建）+ result（成功链路）
# ═══════════════════════════════════════════════

class TestConvertDecisionAndResult:
    def test_success_returns_true_and_final_callback(
            self, converter, monkeypatch, patched_env):
        patched_env["proc"] = FakeProcess(returncode=0)
        calls = []
        ok = converter.convert("a.wav", "a.mp3", codec="libmp3lame",
                               progress_callback=lambda p, m: calls.append((p, m)))
        assert ok is True
        assert calls[-1] == (100, "转换完成")
        cmd = patched_env["cmds"][-1]
        assert cmd[-1] == "a.mp3"
        assert cmd[cmd.index("-c:a") + 1] == "libmp3lame"

    def test_full_param_cmd_construction(self, converter, monkeypatch, patched_env):
        patched_env["proc"] = FakeProcess(returncode=0)
        assert converter.convert("a.wav", "a.mp3", codec="libmp3lame",
                                 bitrate="320k", sample_rate=48000,
                                 channels=2, volume=50) is True
        cmd = patched_env["cmds"][-1]
        assert cmd[cmd.index("-af") + 1] == "volume=0.5"
        assert cmd[cmd.index("-b:a") + 1] == "320k"
        assert cmd[cmd.index("-ar") + 1] == "48000"
        assert cmd[cmd.index("-ac") + 1] == "2"

    def test_volume_100_skips_filter(self, converter, monkeypatch, patched_env):
        patched_env["proc"] = FakeProcess(returncode=0)
        assert converter.convert("a.wav", "a.mp3", volume=100) is True
        assert "-af" not in patched_env["cmds"][-1]

    def test_progress_parsed_with_known_duration(
            self, converter, monkeypatch, patched_env):
        monkeypatch.setattr(converter, "_get_duration", lambda fp: 10.0)
        patched_env["proc"] = FakeProcess(
            stderr_lines=["time=00:00:05.00\n"], returncode=0)
        calls = []
        ok = converter.convert("a.wav", "a.mp3",
                               progress_callback=lambda p, m: calls.append((p, m)))
        assert ok is True
        assert any(p == 50 for p, m in calls)
        assert calls[-1] == (100, "转换完成")

    def test_progress_fallback_when_duration_unknown(
            self, converter, monkeypatch, patched_env):
        monkeypatch.setattr(converter, "_get_duration", lambda fp: 0)
        patched_env["proc"] = FakeProcess(
            stderr_lines=["time=00:00:07.00\n"], returncode=0)
        calls = []
        ok = converter.convert("a.wav", "a.mp3",
                               progress_callback=lambda p, m: calls.append((p, m)))
        assert ok is True
        assert (7, "处理中... (7s)") in calls
