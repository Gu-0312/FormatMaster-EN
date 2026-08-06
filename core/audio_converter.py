"""音频格式转换"""
import os
import subprocess
from utils.config import get_ffmpeg_path, translate_ffmpeg_error
from core.ffmpeg_progress import FFmpegProgressReader
from core.ffmpeg_executor import get_ffprobe_raw

class AudioConverter:
    def __init__(self):
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def _get_duration(self, input_path):
        try:
            info = get_ffprobe_raw(input_path, timeout=10)
            if info and "format" in info:
                return float(info["format"].get("duration", 0))
        except Exception:
            pass
        return 0

    def convert(self, input_path, output_path, codec=None, bitrate="192k",
                sample_rate=None, channels=None, volume=None, progress_callback=None):
        self._cancel = False
        ffmpeg = get_ffmpeg_path()
        if not ffmpeg:
            if progress_callback:
                progress_callback(-1, "错误: FFmpeg未安装")
            return False

        duration = self._get_duration(input_path)
        cmd = [ffmpeg, "-y", "-hwaccel", "auto", "-i", input_path]

        if volume is not None and volume != 100:
            cmd.extend(["-af", f"volume={volume/100}"])
        if codec:
            cmd.extend(["-c:a", codec])
        if bitrate:
            cmd.extend(["-b:a", bitrate])
        if sample_rate:
            cmd.extend(["-ar", str(sample_rate)])
        if channels:
            cmd.extend(["-ac", str(channels)])
        
        cmd.extend(["-threads", "0"])
        cmd.append(output_path)

        try:
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            reader = FFmpegProgressReader(process, duration, label="转换中",
                                           done_message="转换完成", fail_message="转换失败")
            result = reader.read_loop(
                cancel_check=lambda: self._cancel,
                progress_callback=progress_callback,
            )
            if result is True:
                return True
            if result is None:
                return False
            err = ''.join(reader.error_output[-5:])
            chn_msg = translate_ffmpeg_error(err)
            detail = err.strip()[-80:] if err.strip() else ""
            if progress_callback:
                progress_callback(-1, f"转换失败：{chn_msg}")
                if detail and chn_msg not in detail:
                    progress_callback(-1, f"详细信息：{detail}")
            return False

        except Exception as e:
            if progress_callback:
                progress_callback(-1, f"错误: {e}")
            return False
