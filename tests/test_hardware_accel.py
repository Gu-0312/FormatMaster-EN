# -*- coding: utf-8 -*-
"""utils/hardware_accel.py 测试。

detect_hardware_acceleration 依赖 ffmpeg subprocess，用 monkeypatch mock。
覆盖：无 ffmpeg 降级、有 codec 检测、优先级、缓存、可用性判断。
"""
import pytest
from utils import hardware_accel
from utils.hardware_accel import (
    detect_hardware_acceleration,
    get_best_hw_accel,
    get_hw_accel_info,
    is_hw_accel_available,
    HW_ACCEL_ENCODERS,
)


@pytest.fixture(autouse=True)
def reset_cache(monkeypatch):
    """每个测试前重置模块级缓存 _detected_accel，避免测试间互相污染。"""
    monkeypatch.setattr(hardware_accel, "_detected_accel", None)


class TestDetectHardwareAcceleration:
    def test_no_ffmpeg_returns_empty(self, monkeypatch):
        # _check_ffmpeg_codec 返回 False（无 ffmpeg 或无 codec）
        monkeypatch.setattr(hardware_accel, "_check_ffmpeg_codec", lambda codec: False)
        assert detect_hardware_acceleration() == []

    def test_nvidia_available(self, monkeypatch):
        def fake_check(codec):
            return codec == "h264_nvenc"
        monkeypatch.setattr(hardware_accel, "_check_ffmpeg_codec", fake_check)
        result = detect_hardware_acceleration()
        assert len(result) == 1
        assert result[0]["key"] == "nvidia"
        assert result[0]["name"] == "NVIDIA NVENC"
        assert result[0]["hwaccel"] == "cuda"

    def test_multiple_available(self, monkeypatch):
        available_codecs = {"h264_nvenc", "h264_qsv"}
        monkeypatch.setattr(hardware_accel, "_check_ffmpeg_codec",
                            lambda c: c in available_codecs)
        result = detect_hardware_acceleration()
        keys = [r["key"] for r in result]
        assert "nvidia" in keys and "intel" in keys
        assert "amd" not in keys

    def test_result_contains_codecs(self, monkeypatch):
        monkeypatch.setattr(hardware_accel, "_check_ffmpeg_codec",
                            lambda c: c == "h264_amf")
        result = detect_hardware_acceleration()
        assert len(result) == 1
        assert "h264" in result[0]["codecs"]
        assert result[0]["codecs"]["h264"] == "h264_amf"

    def test_caching(self, monkeypatch):
        call_count = [0]
        def fake_check(codec):
            call_count[0] += 1
            return False
        monkeypatch.setattr(hardware_accel, "_check_ffmpeg_codec", fake_check)
        detect_hardware_acceleration()
        first_calls = call_count[0]
        detect_hardware_acceleration()  # 第二次应命中缓存
        assert call_count[0] == first_calls  # 不再调用 _check_ffmpeg_codec


class TestGetBestHwAccel:
    def test_priority_nvidia_first(self, monkeypatch):
        available_codecs = {"h264_nvenc", "h264_qsv", "h264_amf"}
        monkeypatch.setattr(hardware_accel, "_check_ffmpeg_codec",
                            lambda c: c in available_codecs)
        best = get_best_hw_accel()
        assert best["key"] == "nvidia"

    def test_priority_intel_when_no_nvidia(self, monkeypatch):
        monkeypatch.setattr(hardware_accel, "_check_ffmpeg_codec",
                            lambda c: c in {"h264_qsv", "h264_amf"})
        best = get_best_hw_accel()
        assert best["key"] == "intel"

    def test_amd_when_only_amd(self, monkeypatch):
        monkeypatch.setattr(hardware_accel, "_check_ffmpeg_codec",
                            lambda c: c == "h264_amf")
        best = get_best_hw_accel()
        assert best["key"] == "amd"

    def test_none_when_no_available(self, monkeypatch):
        monkeypatch.setattr(hardware_accel, "_check_ffmpeg_codec", lambda c: False)
        assert get_best_hw_accel() is None


class TestIsHwAccelAvailable:
    def test_false_when_none(self, monkeypatch):
        monkeypatch.setattr(hardware_accel, "_check_ffmpeg_codec", lambda c: False)
        assert is_hw_accel_available() is False

    def test_true_when_available(self, monkeypatch):
        monkeypatch.setattr(hardware_accel, "_check_ffmpeg_codec",
                            lambda c: c == "h264_nvenc")
        assert is_hw_accel_available() is True


class TestGetHwAccelInfo:
    def test_known_keys(self):
        assert get_hw_accel_info("nvidia")["name"] == "NVIDIA NVENC"
        assert get_hw_accel_info("intel")["name"] == "Intel QSV"
        assert get_hw_accel_info("amd")["name"] == "AMD AMF"

    def test_unknown_key_returns_none(self):
        assert get_hw_accel_info("nonexistent") is None


class TestHwAccelEncodersDict:
    def test_all_vendors_have_required_fields(self):
        for key, info in HW_ACCEL_ENCODERS.items():
            assert "name" in info
            assert "codecs" in info
            assert "hwaccel" in info
            assert "test_codec" in info
            assert "h264" in info["codecs"]
            assert "hevc" in info["codecs"]

    def test_three_vendors(self):
        assert set(HW_ACCEL_ENCODERS.keys()) == {"nvidia", "intel", "amd"}
