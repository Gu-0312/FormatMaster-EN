"""audio_tools — 音频增强工具（降噪 / 响度归一化）。

基于 FFmpeg 滤镜：afftdn（降噪）、loudnorm（EBU R128 响度归一），
复用 core.ffmpeg_progress 的进度解析链路。
"""
import os
import subprocess

from utils.config import get_ffmpeg_path, translate_ffmpeg_error
from core.ffmpeg_progress import FFmpegProgressReader
from core.ffmpeg_executor import get_ffprobe_raw


def _duration_of(path):
    try:
        info = get_ffprobe_raw(path, timeout=10)
        if info and "format" in info:
            return float(info["format"].get("duration", 0))
    except Exception:
        pass
    return 0


def _run_ffmpeg(input_path, output_path, af_chain, label,
                progress_cb=None, cancel_check=None):
    """执行 ffmpeg 音频滤镜链，返回是否成功。"""
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        if progress_cb:
            progress_cb(-1, "错误: FFmpeg 未安装")
        return False
    duration = _duration_of(input_path)
    cmd = [ffmpeg, "-y", "-i", input_path, "-af", af_chain,
           "-c:a", "aac", "-b:a", "192k", "-threads", "0", output_path]
    try:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        reader = FFmpegProgressReader(process, duration, label=label,
                                      done_message="完成", fail_message="失败")
        result = reader.read_loop(cancel_check=cancel_check,
                                  progress_callback=progress_cb)
        if result is True:
            return True
        if result is None:
            return False
        err = "".join(reader.error_output[-5:])
        chn_msg = translate_ffmpeg_error(err)
        detail = err.strip()[-80:] if err.strip() else ""
        if progress_cb:
            progress_cb(-1, f"处理失败：{chn_msg}")
            if detail and chn_msg not in detail:
                progress_cb(-1, f"详细信息：{detail}")
        return False
    except Exception as e:
        if progress_cb:
            progress_cb(-1, f"错误: {e}")
        return False


def denoise(input_path, output_path, strength=25, progress_cb=None,
            cancel_check=None):
    """音频降噪：FFmpeg afftdn 自适应滤波降噪。

    strength: 1~50（越大降噪越强，过大可能损伤人声，默认 25 均衡）。
    """
    strength = max(1, min(50, int(strength or 25)))
    af = f"afftdn=nf=-{strength}"
    return _run_ffmpeg(input_path, output_path, af, "降噪处理中",
                       progress_cb, cancel_check)


def normalize(input_path, output_path, target_lufs=-14, progress_cb=None,
              cancel_check=None):
    """响度归一化：EBU R128 loudnorm，把响度统一到目标 LUFS。

    target_lufs: -23~-9，默认 -14（流媒体平台常用）。
    """
    try:
        target_lufs = float(target_lufs)
    except (TypeError, ValueError):
        target_lufs = -14
    target_lufs = max(-23, min(-9, target_lufs))
    af = f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11"
    return _run_ffmpeg(input_path, output_path, af, "响度归一化中",
                       progress_cb, cancel_check)


def enhance(input_path, output_path, mode="denoise", strength=25,
            target_lufs=-14, progress_cb=None, cancel_check=None):
    """组合处理：denoise / normalize / both。

    mode: "denoise" 降噪、"normalize" 响度归一、"both" 先降噪再归一。
    """
    mode = mode or "denoise"
    if mode == "normalize":
        return normalize(input_path, output_path, target_lufs, progress_cb, cancel_check)
    if mode == "both":
        strength = max(1, min(50, int(strength or 25)))
        af = f"afftdn=nf=-{strength},loudnorm=I={target_lufs}:TP=-1.5:LRA=11"
        return _run_ffmpeg(input_path, output_path, af, "降噪+响度归一",
                           progress_cb, cancel_check)
    return denoise(input_path, output_path, strength, progress_cb, cancel_check)
