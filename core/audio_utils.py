"""audio_utils — 音频可视化数据提取（波形峰值 / 频谱幅度）。

仅提供纯数据函数（无 UI 依赖），供各音频面板的波形可视化组件使用。
FFmpeg 调用遵循项目规范（get_ffmpeg_path + CREATE_NO_WINDOW + 超时）。
"""

import math
import struct
import subprocess

import numpy as np

from utils.config import get_ffmpeg_path


def _run_ffmpeg_pcm(path, sample_rate=8000, timeout=15):
    """用 ffmpeg 将任意音频解码为单声道 16bit PCM 字节流。

    返回 (bytes, sample_rate)；失败返回 (None, sample_rate)。
    """
    ff = get_ffmpeg_path()
    if not ff:
        return None, sample_rate
    cmd = [ff, "-v", "error", "-i", path,
           "-f", "s16le", "-ac", "1", "-ar", str(sample_rate),
           "-acodec", "pcm_s16le", "-"]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW)
        if proc.returncode != 0:
            return None, sample_rate
        return proc.stdout, sample_rate
    except Exception:  # noqa: BLE001 - 解码失败返回 None，由调用方兜底
        return None, sample_rate


def read_waveform_peaks(path, max_points=1200, sample_rate=8000):
    """读取音频波形峰值数组（用于波形绘制）。

    返回归一化 [-1, 1] 的峰值序列（max_points 个）；失败返回空列表。
    """
    raw, sr = _run_ffmpeg_pcm(path, sample_rate=sample_rate)
    if not raw:
        return []
    n = len(raw) // 2
    if n == 0:
        return []
    samples = np.frombuffer(raw[:n * 2], dtype="<i2").astype(np.float32)
    samples /= 32768.0
    return _peaks_from_samples(samples, max_points)


def read_waveform_points(path, max_points=1200, sample_rate=8000):
    """读取波形（上下双点序列，用于折线绘制）。失败返回 []。"""
    raw, sr = _run_ffmpeg_pcm(path, sample_rate=sample_rate)
    if not raw:
        return []
    n = len(raw) // 2
    if n == 0:
        return []
    samples = np.frombuffer(raw[:n * 2], dtype="<i2").astype(np.float32)
    samples /= 32768.0
    out = []
    if len(samples) <= max_points:
        for v in samples:
            out.append((float(v), float(-v)))
        return out
    step = len(samples) / max_points
    for i in range(max_points):
        lo = int(i * step)
        hi = max(lo + 1, int((i + 1) * step))
        seg = samples[lo:hi]
        mx = float(np.max(seg)) if seg.size else 0.0
        mn = float(np.min(seg)) if seg.size else 0.0
        out.append((mx, mn))
    return out


def _peaks_from_samples(samples, max_points):
    """把采样数组降采样为峰值（每桶取 max|min|abs 最大）。"""
    if len(samples) <= max_points:
        return [float(v) for v in samples]
    step = len(samples) / max_points
    out = []
    for i in range(max_points):
        lo = int(i * step)
        hi = max(lo + 1, int((i + 1) * step))
        seg = samples[lo:hi]
        mx = float(np.max(seg)) if seg.size else 0.0
        mn = float(np.min(seg)) if seg.size else 0.0
        out.append(mx if abs(mx) >= abs(mn) else mn)
    return out


def read_spectrum(path, bands=64, sample_rate=16000, timeout=15):
    """读取音频短时频谱幅度（对数归一化 0..1，用于频谱可视化）。

    取前 ~2 秒，FFT 后按对数频带聚合为 bands 个值；失败返回 []。
    """
    raw, sr = _run_ffmpeg_pcm(path, sample_rate=sample_rate, timeout=timeout)
    if not raw:
        return []
    n = len(raw) // 2
    if n < 256:
        return []
    samples = np.frombuffer(raw[:n * 2], dtype="<i2").astype(np.float32)
    samples /= 32768.0
    # 取前 2 秒做一段 FFT（长度取 2 的幂）
    take = min(len(samples), sr * 2)
    seg = samples[:take]
    win = np.hanning(len(seg)) if len(seg) > 1 else np.ones(1)
    spec = np.abs(np.fft.rfft(seg * win))
    freqs = np.fft.rfftfreq(len(seg), d=1.0 / sr)
    freqs[0] = 1e-6
    # 对数频带聚合
    log_min, log_max = math.log10(50.0), math.log10(sr / 2)
    out = []
    for i in range(bands):
        f_lo = 10 ** (log_min + (log_max - log_min) * i / bands)
        f_hi = 10 ** (log_min + (log_max - log_min) * (i + 1) / bands)
        mask = (freqs >= f_lo) & (freqs < f_hi)
        if mask.any():
            v = float(np.mean(spec[mask]))
        else:
            v = 0.0
        out.append(v)
    mx = max(out) if out else 0.0
    if mx > 0:
        out = [math.log1p(v) / math.log1p(mx) for v in out]
    return out


def format_size(nbytes):
    """字节数 → 可读大小字符串。"""
    if nbytes < 1024:
        return f"{nbytes} B"
    if nbytes < 1048576:
        return f"{nbytes / 1024:.1f} KB"
    if nbytes < 1073741824:
        return f"{nbytes / 1048576:.1f} MB"
    return f"{nbytes / 1073741824:.2f} GB"
