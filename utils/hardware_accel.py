import subprocess
import os
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

def _check_ffmpeg_codec(codec_name):
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        return False
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
        return codec_name in result.stdout
    except Exception:
        return False

def detect_hardware_acceleration():
    global _detected_accel
    if _detected_accel is not None:
        return _detected_accel

    available = []
    
    for key, info in HW_ACCEL_ENCODERS.items():
        if _check_ffmpeg_codec(info["test_codec"]):
            available.append({
                "key": key,
                "name": info["name"],
                "codecs": info["codecs"],
                "hwaccel": info["hwaccel"],
            })
    
    _detected_accel = available
    return available

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