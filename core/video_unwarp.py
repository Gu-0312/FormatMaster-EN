"""video_unwarp — 视频反挤压（宽高比修复）。

场景：老视频 / 模拟采集 / 非正方形像素视频在播放时画面被压扁或拉长
（人物变胖变瘦），需要把画面恢复到正确的显示比例。

两种模式：
- 自动修复：按视频自带的 DAR（显示宽高比）修正 SAR 元数据，流复制、快
- 手动反挤压：把画面按目标比例（4:3 / 16:9 / 9:16 / 1:1 / 自定义）拉伸到
  对应像素尺寸，重编码
"""

from core.ffmpeg_executor import get_ffprobe_raw
from core.ffmpeg_progress import run_ffmpeg
from utils.config import get_ffmpeg_path, get_ffprobe_path


def get_video_dar(path):
    """读取视频的 (width, height, dar_str, sar_str)；失败返回 None。

    dar_str 如 '16:9' / '4:3' / '0:1'（未知）。
    """
    info = get_ffprobe_raw(path)
    if not info or not info.get("streams"):
        return None
    for s in info["streams"]:
        if s.get("codec_type") == "video":
            w = s.get("width") or 0
            h = s.get("height") or 0
            dar = s.get("display_aspect_ratio", "0:1")
            sar = s.get("sample_aspect_ratio", "1:1")
            return (int(w), int(h), str(dar), str(sar))
    return None


def _run_ffmpeg(args, duration, label, progress_cb, cancel_check):
    """启动 FFmpeg 并等待完成。"""
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        if progress_cb:
            progress_cb(-1, "错误: FFmpeg 未安装")
        return False
    result = run_ffmpeg(args, duration=duration, label=label,
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


def _parse_dar(dar_str):
    """'16:9' → (16, 9)；非法返回 None。"""
    if not dar_str or ":" not in dar_str:
        return None
    a, b = dar_str.split(":", 1)
    try:
        x, y = int(a), int(b)
    except ValueError:
        return None
    if x <= 0 or y <= 0:
        return None
    return (x, y)


def fix_aspect(input_path, output_path, target="auto",
               progress_cb=None, cancel_check=None):
    """反挤压修复。

    target:
        "auto"            按视频自带 DAR 修正 SAR 元数据（流复制，快）
        "4:3"/"16:9"/"9:16"/"1:1"
                          手动反挤压：拉伸画面到目标比例（重编码）
        自定义 "W:H"      同上，任意比例
    返回 True/False。
    """
    meta = get_video_dar(input_path)
    if not meta:
        if progress_cb:
            progress_cb(-1, "错误: 无法读取视频信息")
        return False
    width, height, dar_str, sar_str = meta
    duration = _probe_duration(input_path)

    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        if progress_cb:
            progress_cb(-1, "错误: FFmpeg 未安装")
        return False

    if target == "auto":
        # 自动：用视频自带 DAR 修正 SAR（只改元数据，流复制）
        ratio = _parse_dar(dar_str)
        if not ratio:
            if progress_cb:
                progress_cb(-1, "该视频没有 DAR 信息，请手动选择目标比例")
            return False
        dar = f"{ratio[0]}:{ratio[1]}"
        args = [ffmpeg, "-y", "-i", input_path,
                "-c", "copy", "-aspect", dar, "-map_metadata", "0",
                output_path]
        return _run_ffmpeg(args, duration or 1.0, "反挤压修复中",
                           progress_cb, cancel_check)

    # 手动：拉伸到目标比例
    ratio = _parse_dar(target)
    if not ratio:
        if progress_cb:
            progress_cb(-1, "目标比例无效")
        return False
    r_dst = ratio[0] / ratio[1]
    r_src = width / height if height else 1.0
    if r_src > r_dst:
        new_w, new_h = width, max(2, round(width / r_dst))
    elif r_src < r_dst:
        new_w, new_h = max(2, round(height * r_dst)), height
    else:
        new_w, new_h = width, height
    if abs(new_w - width) <= 2 and abs(new_h - height) <= 2:
        # 已是目标比例 → 仅重编码（或直接流复制）
        args = [ffmpeg, "-y", "-i", input_path,
                "-c", "copy", "-map_metadata", "0", output_path]
        return _run_ffmpeg(args, duration or 1.0, "反挤压修复中",
                           progress_cb, cancel_check)
    vf = f"scale={new_w}:{new_h},setsar=1"
    args = [ffmpeg, "-y", "-i", input_path,
            "-vf", vf, "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac", "-map_metadata", "0", output_path]
    return _run_ffmpeg(args, duration or 1.0, "反挤压修复中",
                       progress_cb, cancel_check)


def _probe_duration(path):
    try:
        info = get_ffprobe_raw(path)
        if info and info.get("format"):
            return float(info["format"].get("duration", 0) or 0)
    except Exception:  # noqa: BLE001
        pass
    return 0.0
