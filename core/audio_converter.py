"""音频格式转换"""
import os
import re
import json
import subprocess
from utils.config import get_ffmpeg_path, get_ffprobe_path, translate_ffmpeg_error

class AudioConverter:
    def __init__(self):
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def _get_duration(self, input_path):
        ffprobe = get_ffprobe_path()
        if not ffprobe:
            return 0
        try:
            cmd = [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", input_path]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                                    errors='ignore', timeout=10,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout)
                return float(data.get("format", {}).get("duration", 0))
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

            time_pattern = re.compile(r'time=(\d+):(\d+):(\d+)\.(\d+)')
            error_output = []
            import select
            import time

            last_update_time = 0
            update_interval = 0.3
            last_pct = -1

            while True:
                if self._cancel:
                    process.terminate()
                    try: process.wait(timeout=3)
                    except Exception: process.kill()
                    if progress_callback: progress_callback(-1, "已取消")
                    return False

                try: ready, _, _ = select.select([process.stderr], [], [], 0.1)
                except Exception: ready = [process.stderr]
                if not ready:
                    if process.poll() is not None: break
                    continue

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
                        if duration > 0:
                            pct = min(99, int(current * 100 / duration))
                            now = time.time()
                            if progress_callback and (pct != last_pct or now - last_update_time >= update_interval):
                                progress_callback(pct, f"转换中...")
                                last_pct = pct
                                last_update_time = now
                        else:
                            pct = min(99, int(current) % 100)
                            if progress_callback:
                                progress_callback(pct, f"处理中... ({int(current)}s)")

            if process.returncode == 0:
                if progress_callback:
                    progress_callback(100, "转换完成")
                return True
            else:
                err = ''.join(error_output[-5:])
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
