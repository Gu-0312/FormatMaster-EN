"""audio_norm — 批量音频标准化（EBU R128 loudnorm 响度归一）。

对每个文件执行 loudnorm 两遍处理（先测量响度参数，再按测量值应用），
测量失败时降级为单遍 loudnorm。可选目标采样率 / 声道。
统一遵循项目规范：get_ffmpeg_path()、CREATE_NO_WINDOW、
FFmpegProgressReader 进度解析；不依赖 GUI。
"""
import os
import re
import subprocess

from core.ffmpeg_executor import get_ffprobe_raw
from core.ffmpeg_progress import run_ffmpeg
from utils.config import get_ffmpeg_path

_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

# 输出扩展名 → 编码器（保持常见无损/有损格式语义）
_CODEC_MAP = {
    ".wav": "pcm_s16le",
    ".flac": "flac",
    ".ogg": "libvorbis",
    ".opus": "libopus",
    ".aac": "aac",
    ".m4a": "aac",
    ".mp3": "libmp3lame",
}

# 测量输出中的键值（loudnorm print_format=json 字段）
_MEASURE_RE = re.compile(
    r'"(input_i|input_tp|input_lra|input_thresh|target_offset|'
    r'normalization_type)"\s*:\s*"?([^",}]+)"?')


def _duration_of(path):
    """用 ffprobe 获取音频时长（秒），失败返回 0。"""
    try:
        info = get_ffprobe_raw(path, timeout=10)
        if info and "format" in info:
            return float(info["format"].get("duration", 0))
    except Exception:  # noqa: BLE001
        pass
    return 0.0


def _loudnorm_filter(target_lufs, measured=None):
    """构造 loudnorm 滤镜串。measured 为测量结果时做两遍精确归一。"""
    base = f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11"
    if not measured:
        return base
    return (base + f":measured_I={measured.get('input_i', target_lufs)}"
            f":measured_TP={measured.get('input_tp', -1.5)}"
            f":measured_LRA={measured.get('input_lra', 11)}"
            f":measured_thresh={measured.get('input_thresh', -30)}"
            f":offset={measured.get('target_offset', 0)}"
            ":linear=true:print_format=summary")


def _measure_loudness(input_path, target_lufs):
    """第一遍：测量响度参数，返回 dict 或 None。"""
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        return None
    af = f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11:print_format=json"
    cmd = [ffmpeg, "-nostats", "-i", input_path, "-af", af,
           "-f", "null", "-"]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="ignore", timeout=120,
            creationflags=_CREATE_NO_WINDOW)
    except Exception:  # noqa: BLE001 - 测量失败降级单遍
        return None
    if proc.returncode != 0:
        return None
    text = (proc.stderr or "") + (proc.stdout or "")
    measured = {}
    for key, val in _MEASURE_RE.findall(text):
        try:
            measured[key] = float(val)
        except ValueError:
            measured[key] = val
    if "input_i" not in measured:
        return None
    return measured


def _run_norm(input_path, output_path, af_chain, sample_rate, channels,
              label, progress_cb=None, cancel_check=None):
    """执行 ffmpeg 音频滤镜链，返回是否成功。"""
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        if progress_cb:
            progress_cb(-1, "错误: FFmpeg 未安装")
        return False
    duration = _duration_of(input_path)
    ext = os.path.splitext(output_path)[1].lower()
    codec = _CODEC_MAP.get(ext, "aac")
    cmd = [ffmpeg, "-y", "-i", input_path, "-af", af_chain,
           "-c:a", codec]
    if codec == "aac":
        cmd += ["-b:a", "192k"]
    if sample_rate:
        cmd += ["-ar", str(int(sample_rate))]
    if channels:
        cmd += ["-ac", str(int(channels))]
    cmd += ["-threads", "0", output_path]

    result = run_ffmpeg(cmd, duration=duration, label=label,
                        cancel_check=cancel_check, progress_callback=progress_cb,
                        translate_error=True)
    if result.success:
        return True
    if result.cancelled:
        return False
    if progress_cb:
        progress_cb(-1, f"处理失败：{result.error_cn}")
    return False


def normalize_audio(input_path, output_path, target_lufs=-14,
                    sample_rate=None, channels=None, progress_cb=None,
                    cancel_check=None):
    """音频响度标准化：EBU R128 loudnorm（两遍，测量失败降级单遍）。

    target_lufs: 目标响度，-23~-9，默认 -14（流媒体平台常用）。
    sample_rate: 目标采样率（None=保持原始 / 44100 / 48000）。
    channels:    目标声道数（None=保持原始 / 1 单声道 / 2 立体声）。
    返回是否成功。
    """
    try:
        target_lufs = float(target_lufs)
    except (TypeError, ValueError):
        target_lufs = -14
    target_lufs = max(-23, min(-9, target_lufs))

    if not os.path.isfile(input_path):
        if progress_cb:
            progress_cb(-1, "错误: 找不到输入文件")
        return False

    if progress_cb:
        progress_cb(5, "测量响度…")
    measured = _measure_loudness(input_path, target_lufs)
    if measured:
        af = _loudnorm_filter(target_lufs, measured)
        label = "响度归一化中"
    else:
        af = _loudnorm_filter(target_lufs, None)
        label = "响度归一化中(单遍)"
    if progress_cb:
        progress_cb(15, "开始处理…")
    return _run_norm(input_path, output_path, af, sample_rate, channels,
                       label, progress_cb, cancel_check)


def make_runner(task):
    """TaskManager 持久化重建用的 runner 工厂（runner_key="audio_norm"）。

    task.params 支持: target_lufs / sample_rate / channels。
    """
    def runner(t, prog):
        p = t.params or {}
        return normalize_audio(
            t.file_path, t.output_path,
            target_lufs=p.get("target_lufs", -14),
            sample_rate=p.get("sample_rate"),
            channels=p.get("channels"),
            progress_cb=prog,
            cancel_check=lambda: t.state == "cancelled")
    return runner
