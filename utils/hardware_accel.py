import subprocess
import os
import threading
from utils.config import get_ffmpeg_path

HW_ACCEL_ENCODERS = {
    "nvidia": {
        "name": "NVIDIA NVENC",
        "codecs": {
            "h264": "h264_nvenc",
            "hevc": "hevc_nvenc",
        },
        "hwaccel": "cuda",
        "test_codec": "h264_nvenc",
    },
    "intel": {
        "name": "Intel QSV",
        "codecs": {
            "h264": "h264_qsv",
            "hevc": "hevc_qsv",
        },
        "hwaccel": "qsv",
        "test_codec": "h264_qsv",
    },
    "amd": {
        "name": "AMD AMF",
        "codecs": {
            "h264": "h264_amf",
            "hevc": "hevc_amf",
        },
        "hwaccel": "d3d11va",
        "test_codec": "h264_amf",
    },
}

_detected_accel = None
_detect_lock = threading.Lock()


def _get_ffmpeg_encoders():
    """一次性获取 ffmpeg 全部编码器名（合并多次 subprocess 为一次）。

    原实现对 NVIDIA/Intel/AMD 各跑一次 `ffmpeg -encoders`（3 次 subprocess），
    首次打开视频面板时同步执行约 500ms，明显卡顿。合并为一次调用，
    用同一份 stdout 检查全部 codec，省 2/3 时间。
    """
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        return ""
    try:
        cmd = [ffmpeg, "-encoders"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        return result.stdout
    except Exception:
        return ""


def get_cached_hw_accel():
    """只读硬件加速检测缓存（不触发 subprocess）。

    UI 线程构建面板时用此接口：缓存命中（启动预热完成）直接返回 0ms；
    未命中返回 None，由调用方异步补全，避免 UI 线程同步跑 `ffmpeg
    -encoders`（85ms+）卡顿。
    """
    return _detected_accel


def detect_hardware_acceleration():
    global _detected_accel
    if _detected_accel is not None:
        return _detected_accel

    with _detect_lock:
        # double-check：后台预热线程可能已在本线程等待期间完成
        if _detected_accel is not None:
            return _detected_accel

        encoders = _get_ffmpeg_encoders()
        available = []

        for key, info in HW_ACCEL_ENCODERS.items():
            if info["test_codec"] in encoders:
                available.append({
                    "key": key,
                    "name": info["name"],
                    "codecs": info["codecs"],
                    "hwaccel": info["hwaccel"],
                })

        _detected_accel = available
        return available


def prewarm_hw_accel_async():
    """后台线程预检测硬件加速，避免首次打开视频面板时同步卡顿。

    daemon 线程在启动后立刻开始检测，视频面板构建时缓存大概率已命中
    （直接返回，0ms）。检测结果写入 _detected_accel（GIL 保证原子赋值），
    与 UI 线程的 detect 通过 _detect_lock 串行化。
    """
    def _run():
        try:
            detect_hardware_acceleration()
        except Exception:  # noqa: BLE001 - 预热失败不影响 UI
            pass

    threading.Thread(target=_run, daemon=True).start()


def get_hw_accel_info(key):
    return HW_ACCEL_ENCODERS.get(key)


def get_best_hw_accel():
    available = detect_hardware_acceleration()
    if not available:
        return None

    priority = ["nvidia", "intel", "amd"]
    for p in priority:
        for accel in available:
            if accel["key"] == p:
                return accel
    return available[0]


def is_hw_accel_available():
    return len(detect_hardware_acceleration()) > 0
