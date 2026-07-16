"""视频格式转换"""
import os
import re
import subprocess
import json
import threading
from utils.config import get_ffmpeg_path, get_ffprobe_path

class VideoConverter:
    def __init__(self):
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def get_media_info(self, filepath):
        ffprobe = get_ffprobe_path()
        if not ffprobe:
            return None
        try:
            cmd = [
                ffprobe, "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", filepath
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            return json.loads(result.stdout)
        except Exception:
            return None

    def get_duration(self, filepath):
        info = self.get_media_info(filepath)
        if info and "format" in info:
            return float(info["format"].get("duration", 0))
        return 0

    def get_resolution(self, filepath):
        info = self.get_media_info(filepath)
        if info and "streams" in info:
            for s in info["streams"]:
                if s.get("codec_type") == "video":
                    return s.get("width", 0), s.get("height", 0)
        return 0, 0

    def convert(self, input_path, output_path, fmt_ext, codec=None, preset=None,
                resolution=None, bitrate=None, fps=None, progress_callback=None):
        self._cancel = False
        ffmpeg = get_ffmpeg_path()
        if not ffmpeg:
            if progress_callback:
                progress_callback(-1, "错误: FFmpeg未安装")
            return False

        duration = self.get_duration(input_path)
        cmd = [ffmpeg, "-y", "-i", input_path]

        if codec:
            cmd.extend(["-c:v", codec])
        if preset == "high":
            cmd.extend(["-crf", "18"])
        elif preset == "medium":
            cmd.extend(["-crf", "23"])
        elif preset == "low":
            cmd.extend(["-crf", "28"])
        elif preset == "mobile":
            cmd.extend(["-crf", "26", "-preset", "fast"])
        elif preset == "web":
            cmd.extend(["-crf", "24", "-preset", "medium", "-movflags", "+faststart"])

        if resolution:
            cmd.extend(["-vf", f"scale={resolution[0]}:{resolution[1]}"])
        if bitrate:
            cmd.extend(["-b:v", bitrate])
        if fps:
            cmd.extend(["-r", str(fps)])

        cmd.extend(["-c:a", "aac", "-b:a", "192k"])
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

                if duration > 0:
                    match = time_pattern.search(line_str)
                    if match:
                        h, m, s, ms = match.groups()
                        current = int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 100
                        pct = min(99, int(current * 100 / duration))
                        if progress_callback:
                            progress_callback(pct, f"转换中... {pct}%")

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

    def extract_audio(self, input_path, output_path, audio_codec="aac", bitrate="192k",
                      progress_callback=None):
        self._cancel = False
        ffmpeg = get_ffmpeg_path()
        if not ffmpeg:
            if progress_callback:
                progress_callback(-1, "错误: FFmpeg未安装")
            return False

        duration = self.get_duration(input_path)
        codec_map = {"aac": "aac", "mp3": "libmp3lame", "flac": "flac", "wav": "pcm_s16le"}
        ac = codec_map.get(audio_codec, "aac")

        cmd = [ffmpeg, "-y", "-i", input_path, "-vn", "-c:a", ac, "-b:a", bitrate, output_path]

        try:
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            time_pattern = re.compile(r'time=(\d+):(\d+):(\d+)\.(\d+)')
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
                if duration > 0:
                    match = time_pattern.search(line_str)
                    if match:
                        h, m, s, ms = match.groups()
                        current = int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 100
                        pct = min(99, int(current * 100 / duration))
                        if progress_callback:
                            progress_callback(pct, f"提取中... {pct}%")

            if process.returncode == 0:
                if progress_callback:
                    progress_callback(100, "提取完成")
                return True
            else:
                if progress_callback:
                    progress_callback(-1, "提取失败")
                return False
        except Exception as e:
            if progress_callback:
                progress_callback(-1, f"错误: {e}")
            return False
