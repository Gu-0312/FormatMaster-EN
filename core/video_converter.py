"""视频格式转换"""
import os
import re
import subprocess
import json
import threading
from utils.config import get_ffmpeg_path, get_ffprobe_path, translate_ffmpeg_error

class VideoConverter:
    def __init__(self):
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def get_media_info(self, filepath):
        ffprobe = get_ffprobe_path()
        if not ffprobe:
            print(f"[ERROR] ffprobe not found")
            return None
        try:
            cmd = [
                ffprobe, "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", filepath
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=30,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if result.returncode != 0:
                print(f"[ERROR] ffprobe failed with code {result.returncode}")
                print(f"[ERROR] stderr: {result.stderr[:200]}")
                return None
            if not result.stdout:
                print(f"[ERROR] ffprobe returned empty output")
                return None
            return json.loads(result.stdout)
        except json.JSONDecodeError as e:
            print(f"[ERROR] JSON decode error: {e}")
            print(f"[ERROR] stdout: {result.stdout[:200]}")
            return None
        except FileNotFoundError:
            print(f"[ERROR] ffprobe executable not found at: {ffprobe}")
            return None
        except Exception as e:
            print(f"[ERROR] get_media_info failed: {e}")
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

    def _get_stream_type(self, filepath, stream_index):
        info = self.get_media_info(filepath)
        if info and "streams" in info:
            for s in info["streams"]:
                if s.get("index") == stream_index:
                    return s.get("codec_type", "")
        return ""

    def has_audio_stream(self, filepath):
        info = self.get_media_info(filepath)
        if info and "streams" in info:
            for s in info["streams"]:
                if s.get("codec_type") == "audio":
                    return True
        return False

    def convert(self, input_path, output_path, fmt_ext, codec=None, preset=None,
                resolution=None, bitrate=None, fps=None, progress_callback=None,
                copy_mode=False, selected_streams=None):
        self._cancel = False
        ffmpeg = get_ffmpeg_path()
        if not ffmpeg:
            if progress_callback:
                progress_callback(-1, "错误: FFmpeg未安装")
            return False

        duration = self.get_duration(input_path)
        cmd = [ffmpeg, "-y", "-i", input_path]

        if copy_mode:
            cmd.extend(["-c", "copy", "-map_metadata", "0"])
        else:
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

            if self.has_audio_stream(input_path):
                cmd.extend(["-c:a", "aac", "-b:a", "192k"])
            else:
                cmd.append("-an")
        
        if selected_streams:
            has_video = False
            has_audio = False
            for idx, selected in selected_streams.items():
                if selected:
                    cmd.extend([f"-map", f"0:{idx}"])
                    stype = self._get_stream_type(input_path, idx)
                    if stype == "video":
                        has_video = True
                    elif stype == "audio":
                        has_audio = True
            
            if not has_video:
                cmd.append("-an")
        
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
                    if duration > 0:
                        pct = min(99, int(current * 100 / duration))
                        if progress_callback:
                            progress_callback(pct, f"转换中... {pct}%")
                    else:
                        if progress_callback:
                            pct = min(99, int(current) % 100)
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

    def crop(self, input_path, output_path, start_time, end_time, copy_mode=False, progress_callback=None):
        self._cancel = False
        ffmpeg = get_ffmpeg_path()
        if not ffmpeg:
            if progress_callback:
                progress_callback(-1, "错误: FFmpeg未安装")
            return False

        duration = self.get_duration(input_path)
        cmd = [ffmpeg, "-y", "-hwaccel", "auto", "-ss", start_time, "-i", input_path, "-to", end_time]

        if copy_mode:
            cmd.extend(["-c", "copy"])
        else:
            cmd.extend(["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-c:a", "aac", "-b:a", "192k", "-threads", "0"])

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
                            progress_callback(pct, f"裁剪中... {pct}%")

            if process.returncode == 0:
                if progress_callback:
                    progress_callback(100, "裁剪完成")
                return True
            else:
                err = ''.join(error_output[-5:])
                if progress_callback:
                    progress_callback(-1, f"裁剪失败: {err[:200]}")
                return False

        except Exception as e:
            if progress_callback:
                progress_callback(-1, f"错误: {e}")
            return False

    def concat(self, input_files, output_path, copy_mode=True, progress_callback=None):
        self._cancel = False
        ffmpeg = get_ffmpeg_path()
        if not ffmpeg:
            if progress_callback:
                progress_callback(-1, "错误: FFmpeg未安装")
            return False

        try:
            if copy_mode:
                import tempfile
                list_path = os.path.join(tempfile.gettempdir(), f"formatmaster_concat_{os.getpid()}.txt")
                try:
                    with open(list_path, 'w', encoding='utf-8') as f:
                        for filepath in input_files:
                            abs_path = os.path.abspath(filepath)
                            f.write(f"file '{abs_path}'\n")
                    cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", list_path]
                    cmd.extend(["-c", "copy"])
                    cmd.append(output_path)
                finally:
                    if os.path.exists(list_path):
                        try:
                            os.remove(list_path)
                        except Exception:
                            pass
            else:
                cmd = [ffmpeg, "-y"]
                for filepath in input_files:
                    cmd.extend(["-i", os.path.abspath(filepath)])
                num_files = len(input_files)
                
                filter_parts = []
                scaled_v = []
                scaled_a = []
                
                for i in range(num_files):
                    filter_parts.append(f"[{i}:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2[v{i}]")
                    filter_parts.append(f"[{i}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[a{i}]")
                    scaled_v.append(f"[v{i}]")
                    scaled_a.append(f"[a{i}]")
                
                v_concat_input = "".join(scaled_v)
                a_concat_input = "".join(scaled_a)
                filter_complex = ";".join(filter_parts) + \
                    f";{v_concat_input}concat=n={num_files}:v=1:a=0[outv];{a_concat_input}concat=n={num_files}:v=0:a=1[outa]"
                cmd.extend(["-filter_complex", filter_complex])
                cmd.extend(["-map", "[outv]", "-map", "[outa]"])
                cmd.extend(["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-c:a", "aac", "-b:a", "192k", "-threads", "0"])
                cmd.append(output_path)

            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            time_pattern = re.compile(r'time=(\d+):(\d+):(\d+)\.(\d+)')
            error_output = []

            total_duration = sum(self.get_duration(f) for f in input_files)

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

                if total_duration > 0:
                    match = time_pattern.search(line_str)
                    if match:
                        h, m, s, ms = match.groups()
                        current = int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 100
                        pct = min(99, int(current * 100 / total_duration))
                        if progress_callback:
                            progress_callback(pct, f"拼接中... {pct}%")

            if process.returncode == 0:
                if progress_callback:
                    progress_callback(100, "拼接完成")
                return True
            else:
                err = ''.join(error_output[-5:])
                if progress_callback:
                    progress_callback(-1, f"拼接失败: {err[:200]}")
                return False

        except Exception as e:
            if progress_callback:
                progress_callback(-1, f"错误: {e}")
            return False

    def crop_multi_segment(self, input_path, output_path, segments, progress_callback=None):
        self._cancel = False
        ffmpeg = get_ffmpeg_path()
        if not ffmpeg:
            if progress_callback:
                progress_callback(-1, "错误: FFmpeg未安装")
            return False

        if len(segments) == 0:
            if progress_callback:
                progress_callback(-1, "错误: 未指定裁剪片段")
            return False

        if len(segments) == 1:
            return self.crop(input_path, output_path, segments[0][0], segments[0][1], False, progress_callback)

        try:
            filter_parts = []
            segment_labels = []
            
            for i, (start, end) in enumerate(segments):
                start_sec = self._parse_time(start)
                end_sec = self._parse_time(end)
                
                filter_parts.append(f"[0:v]trim=start={start_sec}:end={end_sec},setpts=PTS-STARTPTS[v{i}]")
                filter_parts.append(f"[0:a]atrim=start={start_sec}:end={end_sec},asetpts=PTS-STARTPTS[a{i}]")
                segment_labels.append(f"[v{i}][a{i}]")
            
            concat_input = "".join(segment_labels)
            num_segments = len(segments)
            
            filter_complex = ";".join(filter_parts) + \
                f";{concat_input}concat=n={num_segments}:v=1:a=1[outv][outa]"
            
            cmd = [
                ffmpeg, "-y", "-hwaccel", "auto", "-i", input_path,
                "-filter_complex", filter_complex,
                "-map", "[outv]", "-map", "[outa]",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-c:a", "aac", "-b:a", "192k", "-threads", "0",
                output_path
            ]

            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            time_pattern = re.compile(r'time=(\d+):(\d+):(\d+)\.(\d+)')
            error_output = []

            total_segment_duration = sum(self._parse_time(e) - self._parse_time(s) for s, e in segments)

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

                if total_segment_duration > 0:
                    match = time_pattern.search(line_str)
                    if match:
                        h, m, s, ms = match.groups()
                        current = int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 100
                        pct = min(99, int(current * 100 / total_segment_duration))
                        if progress_callback:
                            progress_callback(pct, f"裁剪中... {pct}%")

            if process.returncode == 0:
                if progress_callback:
                    progress_callback(100, "裁剪完成")
                return True
            else:
                err = ''.join(error_output[-5:])
                if progress_callback:
                    progress_callback(-1, f"裁剪失败: {err[:200]}")
                return False

        except Exception as e:
            if progress_callback:
                progress_callback(-1, f"错误: {e}")
            return False

    def _parse_time(self, time_str):
        parts = time_str.split(':')
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 1:
            return float(parts[0])
        return 0

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


