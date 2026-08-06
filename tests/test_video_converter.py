# -*- coding: utf-8 -*-
"""core/video_converter.py focused 单元测试。

覆盖 trigger → decision → recovery → result 链路：
- trigger: convert / crop / concat / extract_audio 入口调用
- decision: ffmpeg 命令构建（编码器选择、硬件加速、预设、流映射）
- recovery: ffmpeg 缺失、进程失败、异常抛出、用户取消
- result: 返回值与 progress_callback 的最终状态

所有 subprocess 与外部路径均 mock，不依赖真实 ffmpeg。
"""
import json

import pytest

from core import video_converter as vc_mod
from core.video_converter import VideoConverter
from core import ffmpeg_executor as ffprobe_mod


# ═══════════════════════════════════════════════
#  Fakes
# ═══════════════════════════════════════════════

class FakeProcess:
    """模拟 subprocess.Popen 返回的进程对象（stderr 即自身）。"""

    def __init__(self, stderr_lines=(), returncode=0, on_readline=None):
        self._lines = [
            l if isinstance(l, bytes) else l.encode("utf-8") for l in stderr_lines
        ]
        self._final_rc = returncode
        self.returncode = None
        self._on_readline = on_readline
        self.terminated = False
        self.killed = False
        self.stderr = self  # process.stderr.readline() 可直接调用

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
    """select.select 替身：立即返回第一个参数就绪。"""
    def fake_select(rlist, wlist, xlist, timeout=None):
        return list(rlist), [], []
    return fake_select


@pytest.fixture
def patched_env(monkeypatch):
    """统一补丁环境：ffmpeg 路径存在、select 就绪、Popen 可记录。"""
    monkeypatch.setattr(vc_mod, "get_ffmpeg_path", lambda: "/fake/ffmpeg")
    monkeypatch.setattr(vc_mod, "get_ffprobe_raw", lambda fp, timeout=None: None)
    monkeypatch.setattr("select.select", fake_select_factory())
    record = {"cmds": [], "proc": None}

    def fake_popen(cmd, *args, **kwargs):
        record["cmds"].append(list(cmd))
        return record["proc"] if record["proc"] is not None else FakeProcess()

    monkeypatch.setattr(vc_mod.subprocess, "Popen", fake_popen)
    return record


def set_proc(monkeypatch, record, proc):
    record["proc"] = proc
    return proc


@pytest.fixture
def converter():
    return VideoConverter()


def probe_info(duration="10.0", streams=None):
    return {
        "format": {"duration": duration},
        "streams": streams if streams is not None else [
            {"index": 0, "codec_type": "video", "codec_name": "h264",
             "width": 1920, "height": 1080},
            {"index": 1, "codec_type": "audio", "codec_name": "aac"},
        ],
    }


def mock_probe_run(monkeypatch, info=None, returncode=0, stdout=None):
    """补丁 get_ffprobe_raw（ffprobe 探测）。"""
    if returncode != 0 or (stdout is not None and not stdout):
        monkeypatch.setattr(vc_mod, "get_ffprobe_raw", lambda fp, timeout=None: None)
    elif info is not None:
        monkeypatch.setattr(vc_mod, "get_ffprobe_raw", lambda fp, timeout=None: info)
    else:
        monkeypatch.setattr(vc_mod, "get_ffprobe_raw", lambda fp, timeout=None: None)


# ═══════════════════════════════════════════════
#  get_media_info / 探测类方法（trigger + recovery）
# ═══════════════════════════════════════════════

class TestGetMediaInfo:
    def test_valid_json_returns_dict(self, converter, monkeypatch):
        info = probe_info()
        mock_probe_run(monkeypatch, info=info)
        assert converter.get_media_info("a.mp4") == info

    def test_ffprobe_missing_returns_none(self, converter, monkeypatch):
        monkeypatch.setattr(vc_mod, "get_ffprobe_path", lambda: None)
        assert converter.get_media_info("a.mp4") is None

    def test_nonzero_returncode_returns_none(self, converter, monkeypatch):
        mock_probe_run(monkeypatch, returncode=1)
        assert converter.get_media_info("a.mp4") is None

    def test_empty_stdout_returns_none(self, converter, monkeypatch):
        mock_probe_run(monkeypatch, stdout="")
        assert converter.get_media_info("a.mp4") is None

    def test_invalid_json_returns_none(self, converter, monkeypatch):
        mock_probe_run(monkeypatch, stdout="not json at all")
        assert converter.get_media_info("a.mp4") is None

    def test_duration_and_resolution_parsed(self, converter, monkeypatch):
        mock_probe_run(monkeypatch, info=probe_info(duration="12.5"))
        assert converter.get_duration("a.mp4") == 12.5
        assert converter.get_resolution("a.mp4") == (1920, 1080)

    def test_duration_zero_when_probe_fails(self, converter, monkeypatch):
        mock_probe_run(monkeypatch, returncode=1)
        assert converter.get_duration("a.mp4") == 0
        assert converter.get_resolution("a.mp4") == (0, 0)

    def test_has_audio_stream(self, converter, monkeypatch):
        mock_probe_run(monkeypatch, info=probe_info())
        assert converter.has_audio_stream("a.mp4") is True
        converter._info_cache.clear()
        video_only = probe_info(streams=[
            {"index": 0, "codec_type": "video", "codec_name": "h264"}])
        mock_probe_run(monkeypatch, info=video_only)
        assert converter.has_audio_stream("a.mp4") is False


# ═══════════════════════════════════════════════
#  convert：recovery（前置失败与运行中失败）
# ═══════════════════════════════════════════════

class TestConvertRecovery:
    def test_no_ffmpeg_returns_false(self, converter, monkeypatch):
        monkeypatch.setattr(vc_mod, "get_ffmpeg_path", lambda: None)
        calls = []
        ok = converter.convert("in.mp4", "out.mp4", "mp4",
                               progress_callback=lambda p, m: calls.append((p, m)))
        assert ok is False
        assert calls == [(-1, "错误: FFmpeg未安装")]

    def test_ffmpeg_nonzero_exit_returns_false_with_error(
            self, converter, monkeypatch, patched_env):
        monkeypatch.setattr(converter, "get_duration", lambda fp: 10.0)
        monkeypatch.setattr(converter, "has_audio_stream", lambda fp: True)
        set_proc(monkeypatch, patched_env, FakeProcess(
            stderr_lines=["No such file or directory\n"], returncode=1))
        calls = []
        ok = converter.convert("in.mp4", "out.mp4", "mp4",
                               progress_callback=lambda p, m: calls.append((p, m)))
        assert ok is False
        assert any(p == -1 and m.startswith("转换失败：") for p, m in calls)
        assert not any(p == 100 for p, m in calls)

    def test_popen_exception_returns_false(self, converter, monkeypatch):
        monkeypatch.setattr(vc_mod, "get_ffmpeg_path", lambda: "/fake/ffmpeg")
        monkeypatch.setattr("select.select", fake_select_factory())
        monkeypatch.setattr(converter, "get_duration", lambda fp: 0)

        def boom(cmd, *a, **k):
            raise OSError("cannot spawn")

        monkeypatch.setattr(vc_mod.subprocess, "Popen", boom)
        calls = []
        ok = converter.convert("in.mp4", "out.mp4", "mp4",
                               progress_callback=lambda p, m: calls.append((p, m)))
        assert ok is False
        assert calls and calls[-1][0] == -1 and "cannot spawn" in calls[-1][1]

    def test_cancel_terminates_process(self, converter, monkeypatch, patched_env):
        monkeypatch.setattr(converter, "get_duration", lambda fp: 10.0)
        monkeypatch.setattr(converter, "has_audio_stream", lambda fp: True)
        proc = FakeProcess(stderr_lines=["out_time_us=1000000\n"], returncode=0)
        # 读第一行后置取消标志，下一轮循环应触发 terminate
        proc._on_readline = lambda p: setattr(converter, "_cancel", True)
        patched_env["proc"] = proc
        calls = []
        ok = converter.convert("in.mp4", "out.mp4", "mp4",
                               progress_callback=lambda p, m: calls.append((p, m)))
        assert ok is False
        assert proc.terminated is True
        assert calls and calls[-1] == (-1, "已取消")


# ═══════════════════════════════════════════════
#  convert：decision（命令构建）+ result（成功链路）
# ═══════════════════════════════════════════════

class TestConvertDecisionAndResult:
    def _run_ok(self, converter, monkeypatch, patched_env, stderr_lines=(), **kw):
        monkeypatch.setattr(converter, "get_duration", lambda fp: 10.0)
        monkeypatch.setattr(converter, "has_audio_stream", lambda fp: True)
        patched_env["proc"] = FakeProcess(stderr_lines=stderr_lines, returncode=0)
        calls = []
        ok = converter.convert("in.mp4", "out.mp4", "mp4",
                               progress_callback=lambda p, m: calls.append((p, m)),
                               **kw)
        return ok, calls, patched_env["cmds"][-1]

    def test_success_returns_true_and_final_callback(
            self, converter, monkeypatch, patched_env):
        ok, calls, cmd = self._run_ok(converter, monkeypatch, patched_env)
        assert ok is True
        assert calls[-1] == (100, "转换完成")

    def test_default_soft_h264_encoding(self, converter, monkeypatch, patched_env):
        _, _, cmd = self._run_ok(converter, monkeypatch, patched_env)
        assert cmd[-1] == "out.mp4"
        i = cmd.index("-c:v")
        assert cmd[i + 1] == "libx264"
        assert "-crf" in cmd and "23" in cmd[cmd.index("-crf") + 1]
        assert "-an" not in cmd
        assert "-c:a" in cmd and cmd[cmd.index("-c:a") + 1] == "aac"

    def test_copy_mode_uses_stream_copy(self, converter, monkeypatch, patched_env):
        _, _, cmd = self._run_ok(converter, monkeypatch, patched_env, copy_mode=True)
        i = cmd.index("-c")
        assert cmd[i + 1] == "copy"
        assert "-crf" not in cmd  # copy 模式不设质量参数

    def test_preset_high_maps_to_crf18(self, converter, monkeypatch, patched_env):
        _, _, cmd = self._run_ok(converter, monkeypatch, patched_env, preset="high")
        assert cmd[cmd.index("-crf") + 1] == "18"

    def test_resolution_bitrate_fps_in_cmd(self, converter, monkeypatch, patched_env):
        _, _, cmd = self._run_ok(converter, monkeypatch, patched_env,
                                 resolution=(1280, 720), bitrate="2M", fps=30)
        assert cmd[cmd.index("-vf") + 1] == "scale=1280:720"
        assert cmd[cmd.index("-b:v") + 1] == "2M"
        assert cmd[cmd.index("-r") + 1] == "30"

    def test_no_audio_stream_appends_an(self, converter, monkeypatch, patched_env):
        monkeypatch.setattr(converter, "get_duration", lambda fp: 10.0)
        monkeypatch.setattr(converter, "has_audio_stream", lambda fp: False)
        patched_env["proc"] = FakeProcess(returncode=0)
        assert converter.convert("in.mp4", "out.mp4", "mp4") is True
        cmd = patched_env["cmds"][-1]
        assert "-an" in cmd and "-c:a" not in cmd

    def test_hw_accel_auto_picks_hw_encoder(self, converter, monkeypatch, patched_env):
        monkeypatch.setattr(converter, "get_duration", lambda fp: 10.0)
        monkeypatch.setattr(converter, "has_audio_stream", lambda fp: True)
        monkeypatch.setattr(converter, "_get_video_codec_name", lambda fp: "h264")
        monkeypatch.setattr(vc_mod, "get_best_hw_accel", lambda: {
            "key": "nvidia", "hwaccel": "cuda",
            "codecs": {"h264": "h264_nvenc", "hevc": "hevc_nvenc"},
        })
        patched_env["proc"] = FakeProcess(returncode=0)
        assert converter.convert("in.mp4", "out.mp4", "mp4", hw_accel="auto") is True
        cmd = patched_env["cmds"][-1]
        assert cmd[cmd.index("-hwaccel") + 1] == "cuda"
        assert cmd[cmd.index("-c:v") + 1] == "h264_nvenc"
        # NVENC 专属参数
        assert "-rc" in cmd and "vbr" in cmd

    def test_hw_accel_hevc_source_uses_hevc_encoder(
            self, converter, monkeypatch, patched_env):
        monkeypatch.setattr(converter, "get_duration", lambda fp: 10.0)
        monkeypatch.setattr(converter, "has_audio_stream", lambda fp: True)
        monkeypatch.setattr(converter, "_get_video_codec_name", lambda fp: "hevc")
        monkeypatch.setattr(vc_mod, "get_best_hw_accel", lambda: {
            "key": "nvidia", "hwaccel": "cuda",
            "codecs": {"h264": "h264_nvenc", "hevc": "hevc_nvenc"},
        })
        patched_env["proc"] = FakeProcess(returncode=0)
        assert converter.convert("in.mp4", "out.mp4", "mp4", hw_accel="auto") is True
        cmd = patched_env["cmds"][-1]
        assert cmd[cmd.index("-c:v") + 1] == "hevc_nvenc"

    def test_explicit_hw_accel_key_matched(self, converter, monkeypatch, patched_env):
        monkeypatch.setattr(converter, "get_duration", lambda fp: 10.0)
        monkeypatch.setattr(converter, "has_audio_stream", lambda fp: True)
        monkeypatch.setattr(converter, "_get_video_codec_name", lambda fp: "h264")
        monkeypatch.setattr(vc_mod, "detect_hardware_acceleration", lambda: [
            {"key": "intel", "hwaccel": "qsv",
             "codecs": {"h264": "h264_qsv", "hevc": "hevc_qsv"}},
        ])
        patched_env["proc"] = FakeProcess(returncode=0)
        assert converter.convert("in.mp4", "out.mp4", "mp4", hw_accel="intel") is True
        cmd = patched_env["cmds"][-1]
        assert cmd[cmd.index("-c:v") + 1] == "h264_qsv"

    def test_selected_streams_audio_only_appends_an(
            self, converter, monkeypatch, patched_env):
        monkeypatch.setattr(converter, "get_duration", lambda fp: 10.0)
        monkeypatch.setattr(converter, "has_audio_stream", lambda fp: True)
        monkeypatch.setattr(converter, "_get_stream_type",
                            lambda fp, idx: "audio" if idx == 1 else "video")
        patched_env["proc"] = FakeProcess(returncode=0)
        assert converter.convert("in.mp4", "out.mp4", "mp4",
                                 selected_streams={0: False, 1: True}) is True
        cmd = patched_env["cmds"][-1]
        assert "-map" in cmd and cmd[cmd.index("-map") + 1] == "0:1"
        assert "-an" in cmd  # 无视频流时禁音轨参数兜底

    def test_progress_parsed_from_out_time_us(self, converter, monkeypatch, patched_env):
        ok, calls, _ = self._run_ok(
            converter, monkeypatch, patched_env,
            stderr_lines=["out_time_us=5000000\n"])  # 5s / 10s = 50%
        assert ok is True
        assert (50, "转换中 50%") in calls
        assert calls[-1] == (100, "转换完成")


# ═══════════════════════════════════════════════
#  crop / crop_multi_segment / concat / extract_audio
# ═══════════════════════════════════════════════

class TestCrop:
    def test_success(self, converter, monkeypatch, patched_env):
        monkeypatch.setattr(converter, "get_duration", lambda fp: 10.0)
        patched_env["proc"] = FakeProcess(stderr_lines=["out_time_us=2000000\n"],
                                          returncode=0)
        calls = []
        ok = converter.crop("in.mp4", "out.mp4", "00:00:01", "00:00:05",
                            progress_callback=lambda p, m: calls.append((p, m)))
        assert ok is True
        assert calls[-1] == (100, "裁剪完成")
        cmd = patched_env["cmds"][-1]
        assert "-ss" in cmd and "-to" in cmd

    def test_failure_reports_error(self, converter, monkeypatch, patched_env):
        monkeypatch.setattr(converter, "get_duration", lambda fp: 10.0)
        patched_env["proc"] = FakeProcess(stderr_lines=["Invalid argument\n"],
                                          returncode=1)
        calls = []
        ok = converter.crop("in.mp4", "out.mp4", "0", "5",
                            progress_callback=lambda p, m: calls.append((p, m)))
        assert ok is False
        assert calls[-1][0] == -1 and calls[-1][1].startswith("裁剪失败")

    def test_no_ffmpeg(self, converter, monkeypatch):
        monkeypatch.setattr(vc_mod, "get_ffmpeg_path", lambda: None)
        assert converter.crop("in.mp4", "out.mp4", "0", "5") is False


class TestCropMultiSegment:
    def test_empty_segments_fails(self, converter, monkeypatch, patched_env):
        calls = []
        ok = converter.crop_multi_segment("in.mp4", "out.mp4", [],
                                          progress_callback=lambda p, m: calls.append((p, m)))
        assert ok is False
        assert calls == [(-1, "错误: 未指定裁剪片段")]

    def test_single_segment_delegates_to_crop(self, converter, monkeypatch, patched_env):
        called = {}

        def fake_crop(inp, outp, start, end, copy_mode, progress_callback=None):
            called.update(start=start, end=end)
            return True

        monkeypatch.setattr(converter, "crop", fake_crop)
        assert converter.crop_multi_segment("in.mp4", "out.mp4", [("1", "3")]) is True
        assert called == {"start": "1", "end": "3"}

    def test_multi_segment_builds_filter_complex(
            self, converter, monkeypatch, patched_env):
        patched_env["proc"] = FakeProcess(returncode=0)
        ok = converter.crop_multi_segment(
            "in.mp4", "out.mp4", [("00:00:01", "00:00:02"), ("00:00:05", "00:00:07")])
        assert ok is True
        cmd = patched_env["cmds"][-1]
        fc = cmd[cmd.index("-filter_complex") + 1]
        assert "trim=start=1.0:end=2.0" in fc
        assert "concat=n=2:v=1:a=1[outv][outa]" in fc


class TestParseTime:
    @pytest.mark.parametrize("t,expected", [
        ("10", 10.0),
        ("01:30", 90.0),
        ("01:00:30.5", 3630.5),
    ])
    def test_parse_formats(self, converter, t, expected):
        assert converter._parse_time(t) == expected


class TestExtractAudio:
    def test_codec_mapping(self, converter, monkeypatch, patched_env):
        monkeypatch.setattr(converter, "get_duration", lambda fp: 10.0)
        patched_env["proc"] = FakeProcess(returncode=0)
        assert converter.extract_audio("in.mp4", "out.mp3", audio_codec="mp3") is True
        cmd = patched_env["cmds"][-1]
        assert cmd[cmd.index("-c:a") + 1] == "libmp3lame"
        assert "-vn" in cmd

    def test_success_and_failure(self, converter, monkeypatch, patched_env):
        monkeypatch.setattr(converter, "get_duration", lambda fp: 10.0)
        patched_env["proc"] = FakeProcess(returncode=0)
        calls = []
        assert converter.extract_audio("in.mp4", "out.m4a",
                                       progress_callback=lambda p, m: calls.append((p, m))) is True
        assert calls[-1] == (100, "提取完成")
        patched_env["proc"] = FakeProcess(returncode=1)
        assert converter.extract_audio("in.mp4", "out.m4a") is False
