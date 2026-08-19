# -*- coding: utf-8 -*-
"""video_compress — 视频压缩（HEVC/H.264 CRF 重编码 + 可选分辨率缩放）。

FFmpeg libx265/libx264 恒定质量（CRF）重编码，配合分辨率缩放把大视频
压小（微信/网盘传视频刚需）。进度复用 FFmpegProgressReader。
"""
import os

from core.ffmpeg_executor import get_ffprobe_raw
from core.ffmpeg_progress import run_ffmpeg
from utils.config import get_ffmpeg_path

# 压缩等级 → CRF（数值越大体积越小、质量越低；HEVC/H.264 通用）
CRF_PRESETS = {
    "高质量": 23,
    "平衡": 28,
    "小体积": 32,
}
# 目标分辨率 → 最大高度像素（None=不缩放）
RES_VALUES = {
    "原分辨率": None,
    "1080p": 1080,
    "720p": 720,
    "480p": 480,
}


class VideoCompressor:
    def __init__(self):
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def _get_duration(self, input_path):
        try:
            info = get_ffprobe_raw(input_path, timeout=15)
            if info and "format" in info:
                return float(info["format"].get("duration", 0))
        except Exception:  # noqa: BLE001 - 取不到时长只影响进度显示
            pass
        return 0

    def compress(self, input_path, output_path, crf=28, max_height=None,
                 codec="libx265", progress_callback=None):
        """压缩视频。

        crf: 23~32（见 CRF_PRESETS）；max_height: 最大高度或 None；
        codec: libx265（HEVC 推荐）/ libx264（兼容性更好）。
        返回 True/False。
        """
        self._cancel = False
        ffmpeg = get_ffmpeg_path()
        if not ffmpeg:
            if progress_callback:
                progress_callback(-1, "错误: FFmpeg未安装")
            return False

        duration = self._get_duration(input_path)
        cmd = [ffmpeg, "-y", "-hwaccel", "auto", "-i", input_path]
        if max_height:
            # 保持宽高比缩放到最大高度，宽度自动偶数对齐；不放大
            # filter 内逗号需转义（否则被当成滤镜分隔符）
            cmd.extend(["-vf", f"scale=-2:min(ih\\,{max_height})"])
        cmd.extend(["-c:v", codec, "-crf", str(crf), "-preset", "medium"])
        cmd.extend(["-c:a", "aac", "-b:a", "128k"])
        cmd.extend(["-movflags", "+faststart"])  # MP4 边下边播友好
        cmd.extend(["-threads", "0"])
        cmd.append(output_path)

        result = run_ffmpeg(cmd, duration=duration, label="压缩中",
                            cancel_check=lambda: self._cancel,
                            progress_callback=progress_callback,
                            translate_error=True)
        if result.success:
            return True
        if result.cancelled:
            return False
        if progress_callback:
            progress_callback(-1, f"压缩失败：{result.error_cn}")
        return False
