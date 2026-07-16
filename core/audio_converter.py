"""音频格式转换"""
import os
import re
import subprocess
from utils.config import get_ffmpeg_path

class AudioConverter:
    def __init__(self):
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def convert(self, input_path, output_path, codec=None, bitrate="192k",
                sample_rate=None, channels=None, volume=None, progress_callback=None):
        self._cancel = False
        ffmpeg = get_ffmpeg_path()
        if not ffmpeg:
            if progress_callback:
                progress_callback(-1, "错误: FFmpeg未安装")
            return False

        cmd = [ffmpeg, "-y", "-i", input_path]

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

        cmd.append(output_path)

        try:
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            time_pattern = re.compile(r'time=(\d+):(\d+):(\d+)\.(\d+)')
            error_output = []

            while True:
                if self._cancel:
                    process.terminate()
                    if progress_callback:
                        progress_callback(-1, "已取消")
                    return False

                line = process.stderr.readline()
                if not line:
                    if process.poll() is not None:
                        break
                    continue

                line_str = line.decode('utf-8', errors='replace')
                error_output.append(line_str)

                match = time_pattern.search(line_str)
                if match:
                    h, m, s, ms = match.groups()
                    current = int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 100
                    if current > 0:
                        pct = min(99, int(current % 100))
                        if progress_callback:
                            progress_callback(pct, f"转换中...")

            if process.returncode == 0:
                if progress_callback:
                    progress_callback(100, "转换完成")
                return True
            else:
                err = ''.join(error_output[-5:])
                if progress_callback:
                    progress_callback(-1, f"转换失败: {err[:200]}")
                return False

        except Exception as e:
            if progress_callback:
                progress_callback(-1, f"错误: {e}")
            return False
