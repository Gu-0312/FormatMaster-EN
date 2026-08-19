"""audio_tools — 音频增强工具（降噪 / 响度归一化）。

基于 FFmpeg 滤镜：afftdn（降噪）、loudnorm（EBU R128 响度归一），
复用 core.ffmpeg_progress 的进度解析链路。
"""
import os

from utils.config import get_ffmpeg_path
from core.ffmpeg_progress import run_ffmpeg
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
        result = run_ffmpeg(cmd, duration=duration, label=label,
                            cancel_check=cancel_check,
                            progress_callback=progress_cb,
                            translate_error=True)
        if result.success:
            return True
        if result.cancelled:
            return False
        if progress_cb:
            progress_cb(-1, f"失败: {result.error_cn}")
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
# ─────────────────────────────────────────────────────
#  扩展音频滤镜集（2026-08-15 合并进「音频增强」等面板）
#  人声/伴奏提取 · 均衡器 EQ · 动态压限 ·
#  去除静音 · 变调不变速
# ─────────────────────────────────────────────────────

def extract_vocal(input_path, output_path, progress_cb=None,
                  cancel_check=None):
    """人声提取：中置声道增强（pan (L+R)/2），适合清唱/人声处理。

    说明：非 AI 算法，靠"人声居中"原理增强中置成分，纯伴奏
    段落人声残留较多，效果为"人声突出"而非"纯人声"。
    """
    af = "pan=stereo|c0=0.5*c0+0.5*c1|c1=0.5*c0+0.5*c1"
    return _run_ffmpeg(input_path, output_path, af, "提取人声中",
                       progress_cb, cancel_check)


def extract_music(input_path, output_path, progress_cb=None,
                  cancel_check=None):
    """伴奏提取：消除中置人声（pan L-R），得到伴奏版。"""
    af = "pan=stereo|c0=c0-c1|c1=c1-c0"
    return _run_ffmpeg(input_path, output_path, af, "提取伴奏中",
                       progress_cb, cancel_check)


def audio_equalizer(input_path, output_path, low=0, mid=0, high=0,
                    progress_cb=None, cancel_check=None):
    """三段式均衡器：低/中/高频增益（-12 ~ +12 dB，0 表示不动）。"""
    try:
        low, mid, high = float(low), float(mid), float(high)
    except (TypeError, ValueError):
        low = mid = high = 0.0
    bands = []
    if abs(low) > 0.01:
        bands.append(f"equalizer=f=200:t=q:w=1:g={low:+.1f}")
    if abs(mid) > 0.01:
        bands.append(f"equalizer=f=1000:t=q:w=1:g={mid:+.1f}")
    if abs(high) > 0.01:
        bands.append(f"equalizer=f=5000:t=q:w=1:g={high:+.1f}")
    if not bands:
        if progress_cb:
            progress_cb(-1, "错误: 三频段增益均为 0")
        return False
    return _run_ffmpeg(input_path, output_path, ",".join(bands),
                       "均衡器处理中", progress_cb, cancel_check)


def audio_compress(input_path, output_path, threshold=-20, ratio=4,
                   progress_cb=None, cancel_check=None):
    """动态范围压缩 + 峰值限制（平衡忽大忽小的音量）。"""
    try:
        threshold = float(threshold)
        ratio = max(1.0, float(ratio))
    except (TypeError, ValueError):
        threshold, ratio = -20.0, 4.0
    threshold = max(-50.0, min(-5.0, threshold))
    af = (f"acompressor=threshold={threshold:.0f}dB:ratio={ratio:.1f}"
          f":attack=20:release=250:makeup=1,alimiter=limit=0.95")
    return _run_ffmpeg(input_path, output_path, af, "压限处理中",
                       progress_cb, cancel_check)


def remove_silence(input_path, output_path, threshold=-50, min_silence=0.5,
                   progress_cb=None, cancel_check=None):
    """去除静音段：silenceremove 自动剪掉安静片段并拼接。"""
    try:
        threshold = float(threshold)
        min_silence = max(0.1, float(min_silence))
    except (TypeError, ValueError):
        threshold, min_silence = -50.0, 0.5
    threshold = max(-70.0, min(-20.0, threshold))
    af = (f"silenceremove=start_periods=1:start_threshold={threshold:.0f}dB"
          f":start_silence=0.1:stop_periods=1:stop_threshold={threshold:.0f}dB"
          f":stop_silence={min_silence:.2f}")
    return _run_ffmpeg(input_path, output_path, af, "去除静音中",
                       progress_cb, cancel_check)


def audio_pitch(input_path, output_path, semitones=0,
                progress_cb=None, cancel_check=None):
    """变调不变速：asetrate + atempo（±12 半音）。"""
    try:
        semitones = int(semitones)
    except (TypeError, ValueError):
        semitones = 0
    semitones = max(-12, min(12, semitones))
    if semitones == 0:
        if progress_cb:
            progress_cb(-1, "错误: 变调为 0（无需处理）")
        return False
    import math as _math
    factor = 2.0 ** (semitones / 12.0)
    sr = 44100
    # asetrate 变采样率（改变音高），aresample 还原，atempo 校正时长
    af = (f"asetrate={sr * factor:.0f},aresample={sr},"
          f"atempo={1.0 / factor:.4f}")
    return _run_ffmpeg(input_path, output_path, af, "变调处理中",
                       progress_cb, cancel_check)


def concat_audio(input_paths, output_path, progress_cb=None,
                 cancel_check=None):
    """音频拼接：按列表顺序合并多个音频（concat demuxer 流复制优先）。"""
    if not input_paths or len(input_paths) < 2:
        if progress_cb:
            progress_cb(-1, "错误: 拼接至少需要 2 个音频")
        return False
    total = sum(_duration_of(p) for p in input_paths) or 1.0
    list_path = os.path.join(os.path.dirname(output_path) or ".",
                             "_fm_aconcat.txt")
    try:
        with open(list_path, "w", encoding="utf-8") as f:
            for p in input_paths:
                esc = p.replace("'", "'\''")
                f.write(f"file '{esc}'\n")
        args = ["-f", "concat", "-safe", "0", "-i", list_path,
                "-c", "copy", "-map_metadata", "0", output_path]
        ffmpeg = get_ffmpeg_path()
        if not ffmpeg:
            if progress_cb:
                progress_cb(-1, "错误: FFmpeg 未安装")
            return False
        cmd = [ffmpeg, "-y", "-nostats", "-progress", "pipe:2"] + args
        result = run_ffmpeg(cmd, duration=total, label="音频拼接中",
                            cancel_check=cancel_check,
                            progress_callback=progress_cb,
                            translate_error=True)
        if result.success:
            return True
        if result.cancelled:
            return False
        # 编码/采样率不一致 → 重编码兜底（统一 aac 192k）
        args = ["-f", "concat", "-safe", "0", "-i", list_path,
                "-c:a", "aac", "-b:a", "192k", "-map_metadata", "0",
                output_path]
        cmd = [ffmpeg, "-y", "-nostats", "-progress", "pipe:2"] + args
        result = run_ffmpeg(cmd, duration=total, label="音频拼接中(重编码)",
                            cancel_check=cancel_check,
                            progress_callback=progress_cb,
                            translate_error=True)
        if result.success:
            return True
        if result.cancelled:
            return False
        if progress_cb:
            progress_cb(-1, f"失败: {result.error_cn}")
        return False
    finally:
        try:
            os.remove(list_path)
        except OSError:
            pass
