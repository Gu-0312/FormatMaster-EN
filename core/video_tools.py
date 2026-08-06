"""video_tools — 视频处理工具集（剪辑 / 合并 / 字幕烧录 / 变速）。

统一基于 FFmpeg 子进程 + FFmpegProgressReader 进度解析，
复用 core/video_converter 的调用范式；不依赖 GUI。
各函数均接受 progress_cb(pct, msg) 进度回调，失败时回调 (-1, 原因)。
"""
import os
import subprocess

from core.ffmpeg_executor import get_ffprobe_info
from core.ffmpeg_progress import FFmpegProgressReader
from utils.config import get_ffmpeg_path

_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _duration_of(path):
    """用 ffprobe 获取媒体时长（秒），失败返回 0。"""
    try:
        info = get_ffprobe_info(path)
        if info:
            return float(info.get("duration") or 0.0)
    except Exception:
        pass
    return 0.0


def _run(args, duration, label, progress_cb, cancel_check=None):
    """启动 ffmpeg 并读取进度，返回 bool。"""
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        if progress_cb:
            progress_cb(-1, "错误: FFmpeg 未安装")
        return False
    cmd = [ffmpeg, "-y", "-nostats", "-progress", "pipe:2"] + args
    try:
        # 注意：不传 encoding——FFmpegProgressReader 按二进制逐行读取并
        # 自行 decode('utf-8', errors='replace')
        proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            creationflags=_CREATE_NO_WINDOW)
    except OSError:
        if progress_cb:
            progress_cb(-1, "错误: 无法启动 FFmpeg")
        return False
    reader = FFmpegProgressReader(proc, duration, label=label)
    return reader.read_loop(cancel_check, progress_cb)


def clip_video(input_path, output_path, start_sec=None, end_sec=None,
               progress_cb=None, cancel_check=None):
    """截取视频片段。start_sec/end_sec 为秒数（None 表示不限）。

    流复制优先（快），若失败自动降级为重编码。
    """
    duration = _duration_of(input_path)
    seg = (end_sec or duration) - (start_sec or 0.0)
    seg = max(seg, 1.0)
    args = []
    if start_sec:
        args += ["-ss", str(float(start_sec))]
    args += ["-i", input_path]
    if end_sec:
        args += ["-to", str(float(end_sec))]
    args += ["-c", "copy", "-map_metadata", "0", output_path]
    if _run(args, seg, "剪辑中", progress_cb, cancel_check):
        return True
    # 流复制失败（如非关键帧起点）→ 重编码兜底
    args = []
    if start_sec:
        args += ["-ss", str(float(start_sec))]
    args += ["-i", input_path]
    if end_sec:
        args += ["-to", str(float(end_sec))]
    args += ["-c:v", "libx264", "-preset", "fast", "-c:a", "aac",
             "-map_metadata", "0", output_path]
    return _run(args, seg, "剪辑中(重编码)", progress_cb, cancel_check)


def merge_videos(input_paths, output_path, progress_cb=None,
                 cancel_check=None):
    """合并多个视频（concat demuxer，自动选用兼容编码）。"""
    if len(input_paths) < 2:
        if progress_cb:
            progress_cb(-1, "错误: 合并至少需要 2 个文件")
        return False
    total = sum(_duration_of(p) for p in input_paths) or 1.0
    list_path = os.path.join(
        os.path.dirname(output_path) or ".", "_fm_concat.txt")
    try:
        with open(list_path, "w", encoding="utf-8") as f:
            for p in input_paths:
                f.write(f"file '{os.path.basename(p).replace(chr(39), chr(39)+chr(39)+chr(39))}'\n")
        # concat demuxer 需要相对路径（相对 list 文件目录）
        with open(list_path, "r", encoding="utf-8") as f:
            content = f.read()
        # 改为绝对路径更稳（不同盘符时 ffmpeg 相对解析可能失败）
        content = "".join(
            f"file '{p.replace(chr(39), chr(39)+chr(39)+chr(39))}'\n"
            for p in input_paths)
        with open(list_path, "w", encoding="utf-8") as f:
            f.write(content)
        args = ["-f", "concat", "-safe", "0", "-i", list_path,
                "-c", "copy", "-map_metadata", "0", output_path]
        ok = _run(args, total, "合并中", progress_cb, cancel_check)
        if not ok:
            # 编码不一致 → 统一重编码
            args = ["-f", "concat", "-safe", "0", "-i", list_path,
                    "-c:v", "libx264", "-preset", "fast", "-c:a", "aac",
                    "-map_metadata", "0", output_path]
            ok = _run(args, total, "合并中(重编码)", progress_cb, cancel_check)
        return ok
    finally:
        try:
            os.remove(list_path)
        except OSError:
            pass


def burn_subtitle(input_path, subtitle_path, output_path,
                  progress_cb=None, cancel_check=None):
    """字幕烧录（软字幕合成进画面，需要重编码）。"""
    if not os.path.isfile(subtitle_path):
        if progress_cb:
            progress_cb(-1, "错误: 字幕文件不存在")
        return False
    duration = _duration_of(input_path) or 1.0
    # subtitles 滤镜：Windows 下路径需转义（: 和 \）
    esc = subtitle_path.replace("\\", "/").replace(":", "\\:")
    args = ["-i", input_path,
            "-vf", f"subtitles='{esc}'",
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac", "-map_metadata", "0", output_path]
    return _run(args, duration, "烧录字幕中", progress_cb, cancel_check)


def change_speed(input_path, output_path, rate, progress_cb=None,
                 cancel_check=None):
    """视频变速。rate>1 加速，0<rate<1 减速。"""
    try:
        rate = float(rate)
    except (TypeError, ValueError):
        rate = 1.0
    if rate <= 0:
        rate = 1.0
    duration = _duration_of(input_path) / rate or 1.0
    args = ["-i", input_path,
            "-filter_complex",
            f"[0:v]setpts=PTS/{rate}[v];[0:a]atempo={max(rate, 0.5)}[a]"
            if 0.5 <= rate <= 2.0 else
            f"[0:v]setpts=PTS/{rate}[v];[0:a]atempo={rate}[a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "fast", "-c:a", "aac",
            "-map_metadata", "0", output_path]
    return _run(args, duration, "变速处理中", progress_cb, cancel_check)
