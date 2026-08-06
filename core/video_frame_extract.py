# -*- coding: utf-8 -*-
"""视频抽帧 / 场景截图：按固定间隔批量截取视频关键帧。"""
import os
import subprocess

from utils.config import get_ffmpeg_path, get_ffprobe_path
from core.ffmpeg_executor import get_ffprobe_raw

_SUPPORTED = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm",
              ".ts", ".m4v", ".mpg", ".mpeg", ".3gp"}


def duration_of(path):
    """视频时长（秒），失败返回 0。"""
    try:
        info = get_ffprobe_raw(path, timeout=10)
        if info and "format" in info:
            return float(info["format"].get("duration", 0) or 0)
    except Exception:
        pass
    return 0


def extract_frames(input_path, output_dir, interval_sec=1.0, fmt="PNG",
                   progress_cb=None, cancel_check=None):
    """按间隔抽帧到 output_dir，返回 (成功, 帧数)。

    progress_cb(pct, msg)：0~100 进度回调。
    cancel_check() -> bool：返回 True 时中断（抛 InterruptedError）。
    """
    if not os.path.isfile(input_path):
        return False, 0
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        return False, 0
    os.makedirs(output_dir, exist_ok=True)
    duration = duration_of(input_path) or 0
    if duration <= 0:
        duration = 0  # 未知时长时按 100% 上报（仅 ffmpeg 侧结束）

    # 清除旧帧，避免混淆
    for f in os.listdir(output_dir):
        if f.lower().startswith("frame_") and f.lower().endswith(
                (".png", ".jpg", ".jpeg")):
            try:
                os.remove(os.path.join(output_dir, f))
            except OSError:
                pass

    ext = "jpg" if fmt.upper() in ("JPG", "JPEG") else "png"
    fps = max(0.01, 1.0 / max(interval_sec, 0.1))
    out_tpl = os.path.join(output_dir, "frame_%05d." + ext)
    cmd = [ffmpeg, "-y", "-i", input_path, "-vf", f"fps={fps}",
           "-start_number", "0", "-q:v", "2" if ext == "jpg" else "1",
           out_tpl]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    # 解析 stderr 的 time= 进度
    total_frames = 0
    done = False
    while True:
        line = proc.stderr.readline()
        if not line and proc.poll() is not None:
            break
        text = line.decode("utf-8", errors="ignore")
        if "time=" in text:
            try:
                t = text.split("time=")[1].split()[0]
                sec = sum(float(x) * 60 ** i for i, x in
                          enumerate(reversed(t.split(":"))))
                if duration > 0:
                    pct = min(99, int(sec / duration * 100))
                    if progress_cb:
                        progress_cb(pct, f"{sec:.1f}s / {duration:.1f}s")
            except Exception:
                pass
        if cancel_check is not None and cancel_check():
            try:
                proc.terminate()
            except Exception:
                pass
            raise InterruptedError("已取消")
    proc.wait()
    for f in os.listdir(output_dir):
        if f.lower().startswith("frame_") and f.lower().endswith(
                (".png", ".jpg", ".jpeg")):
            total_frames += 1
    if progress_cb:
        progress_cb(100, "")
    return proc.returncode == 0, total_frames
