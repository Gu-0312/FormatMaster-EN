"""视频格式转换"""
import os
import re
import threading
from utils.config import get_ffmpeg_path, get_ffprobe_path
from utils.hardware_accel import get_best_hw_accel, detect_hardware_acceleration
from core.ffmpeg_progress import run_ffmpeg, _parse_time_line
from core.ffmpeg_executor import get_ffprobe_raw

class VideoConverter:
    # NOTE: ffprobe 结果缓存已提升到 ffmpeg_executor 模块级，
    # 按 (路径, mtime, 文件大小) 失效，跨 VideoConverter / AudioConverter
    # / VideoCompressor 等实例共享，不再需要实例缓存。

    def __init__(self):
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def get_media_info(self, filepath):
        return get_ffprobe_raw(filepath, timeout=30)

    def _get_or_load_info(self, filepath):
        """获取 ffprobe 原始数据（经模块级缓存，mtime+size 失效）。"""
        return get_ffprobe_raw(filepath, timeout=10)

    def get_duration(self, filepath):
        info = self._get_or_load_info(filepath)
        if info and "format" in info:
            return float(info["format"].get("duration", 0))
        return 0

    def get_resolution(self, filepath):
        info = self._get_or_load_info(filepath)
        if info and "streams" in info:
            for s in info["streams"]:
                if s.get("codec_type") == "video":
                    return s.get("width", 0), s.get("height", 0)
        return 0, 0

    def has_audio_stream(self, filepath):
        info = self._get_or_load_info(filepath)
        if info and "streams" in info:
            for s in info["streams"]:
                if s.get("codec_type") == "audio":
                    return True
        return False

    def _get_video_codec_name(self, filepath):
        info = self._get_or_load_info(filepath)
        if info and "streams" in info:
            for s in info["streams"]:
                if s.get("codec_type") == "video":
                    return s.get("codec_name", "")
        return ""

    def _get_stream_type(self, filepath, stream_index):
        info = self._get_or_load_info(filepath)
        if info and "streams" in info:
            for s in info["streams"]:
                if s.get("index") == stream_index:
                    return s.get("codec_type", "")
        return ""

    def convert(self, input_path, output_path, fmt_ext, codec=None, preset=None,
                resolution=None, bitrate=None, fps=None, progress_callback=None,
                copy_mode=False, selected_streams=None, hw_accel=None,
                subtitle_path=None, sub_font_size=None, max_threads=0,
                metadata=None):
        """视频格式转换。

        启用硬件加速但转换失败时（驱动/设备不可用等），
        自动降级为 CPU 软编重试一次，避免任务直接失败。
        max_threads: ffmpeg -threads 值，0=自动（不限制），>0 用于并行场景
                     按核数分配避免多任务同时争抢核心资源。
        sub_font_size: 字幕烧录字号（>0 时经 subtitles 滤镜 force_style 生效）。
        metadata: dict（如 {"title": "...", "artist": "..."}），写入输出元数据。
        """
        self._cancel = False
        ok = self._convert_once(input_path, output_path, fmt_ext, codec, preset,
                                resolution, bitrate, fps, progress_callback,
                                copy_mode, selected_streams, hw_accel,
                                subtitle_path=subtitle_path,
                                sub_font_size=sub_font_size,
                                max_threads=max_threads,
                                metadata=metadata)
        if not ok and hw_accel and not self._cancel:
            # 硬件加速失败：降级纯 CPU 软编重试（-y 会覆盖残留的部分输出）
            if progress_callback:
                progress_callback(0, "硬件加速不可用，已改用 CPU 软编")
            ok = self._convert_once(input_path, output_path, fmt_ext, codec, preset,
                                    resolution, bitrate, fps, progress_callback,
                                    copy_mode, selected_streams, None,
                                    subtitle_path=subtitle_path,
                                    sub_font_size=sub_font_size,
                                    max_threads=max_threads,
                                    metadata=metadata)
        return ok

    def _convert_once(self, input_path, output_path, fmt_ext, codec=None, preset=None,
                      resolution=None, bitrate=None, fps=None, progress_callback=None,
                      copy_mode=False, selected_streams=None, hw_accel=None,
                      subtitle_path=None, sub_font_size=None, max_threads=0,
                      metadata=None):
        self._cancel = False
        ffmpeg = get_ffmpeg_path()
        if not ffmpeg:
            if progress_callback:
                progress_callback(-1, "错误: FFmpeg未安装")
            return False

        duration = self.get_duration(input_path)
        
        hw_info = None
        if hw_accel == "auto":
            # 自动：选用检测到的最佳 GPU 加速器
            hw_info = get_best_hw_accel()
        elif hw_accel:
            available = detect_hardware_acceleration()
            for accel in available:
                if accel["key"] == hw_accel:
                    hw_info = accel
                    break
        
        if hw_info:
            cmd = [ffmpeg, "-y", "-nostats", "-progress", "pipe:2",
                   "-hwaccel", hw_info["hwaccel"], "-i", input_path]
        else:
            cmd = [ffmpeg, "-y", "-nostats", "-progress", "pipe:2", "-i", input_path]

        if copy_mode:
            cmd.extend(["-c", "copy", "-map_metadata", "0"])
        else:
            video_codec = codec
            using_hw_enc = False
            if hw_info and not codec:
                codec_name = self._get_video_codec_name(input_path)
                if codec_name:
                    codec_key = "hevc" if codec_name.lower() == "hevc" or codec_name.lower() == "h265" else "h264"
                    video_codec = hw_info["codecs"].get(codec_key, hw_info["codecs"].get("h264"))
                    using_hw_enc = True
            if not video_codec:
                # 默认软编 H.264（不设 -c:v 时 ffmpeg 会用容器默认编码器，如 mp4 的 mpeg4，又慢又差）
                video_codec = "libx264"
            elif any(video_codec.endswith(s) for s in ("_nvenc", "_qsv", "_amf")):
                using_hw_enc = True

            if video_codec:
                cmd.extend(["-c:v", video_codec])

            # 质量/速度参数：硬件编码器与软编码器参数体系不同，分开处理
            _q_map = {"high": 18, "medium": 23, "low": 28, "mobile": 26, "web": 24}
            _q = _q_map.get(preset, 23)
            if using_hw_enc:
                if "nvenc" in video_codec:
                    cmd.extend(["-preset", "p5", "-tune", "hq", "-rc", "vbr", "-cq", str(_q)])
                elif "qsv" in video_codec:
                    cmd.extend(["-preset", "medium", "-global_quality", str(_q)])
                elif "amf" in video_codec:
                    cmd.extend(["-quality", "speed"])
            else:
                # 软编：统一加 -preset 提速（不指定时用 fast，比默认 medium 快约 1.5-2 倍）
                if preset == "high":
                    cmd.extend(["-crf", "18", "-preset", "fast"])
                elif preset == "medium":
                    cmd.extend(["-crf", "23", "-preset", "fast"])
                elif preset == "low":
                    cmd.extend(["-crf", "28", "-preset", "veryfast"])
                elif preset == "mobile":
                    cmd.extend(["-crf", "26", "-preset", "fast"])
                elif preset == "web":
                    cmd.extend(["-crf", "24", "-preset", "medium", "-movflags", "+faststart"])
                else:
                    cmd.extend(["-crf", "23", "-preset", "fast"])

            # 分辨率必须是 (宽, 高) 元组/列表；字符串等非法值会被忽略，
            # 避免生成 scale=原:始 之类的非法滤镜导致转换失败
            if (isinstance(resolution, (tuple, list)) and len(resolution) == 2
                    and all(isinstance(v, (int, float)) for v in resolution)):
                vf_parts = [f"scale={int(resolution[0])}:{int(resolution[1])}"]
            else:
                vf_parts = []

            if subtitle_path and os.path.isfile(subtitle_path):
                # 字幕烧录：转义滤镜特殊字符（冒号/引号/方括号/逗号等，防 Windows 路径含特殊字符崩溃）
                sub_escaped = (subtitle_path.replace("\\", "/")
                               .replace(":", "\\:")
                               .replace("'", "\\'")
                               .replace("[", "\\[")
                               .replace("]", "\\]")
                               .replace("%", "\\%")
                               .replace(",", "\\,"))
                vf_part = f"subtitles='{sub_escaped}'"
                # 字号：force_style 追加在滤镜参数末尾（路径引号已闭合）：
                # subtitles='path':force_style='FontSize=24'
                try:
                    fs = int(sub_font_size) if sub_font_size else 0
                except (TypeError, ValueError):
                    fs = 0
                if fs > 0:
                    vf_part = vf_part + ":force_style='FontSize=%d'" % fs
                vf_parts.append(vf_part)

            if vf_parts:
                cmd.extend(["-vf", ",".join(vf_parts)])
            if bitrate:
                cmd.extend(["-b:v", bitrate])
            if fps:
                cmd.extend(["-r", str(fps)])

            if not selected_streams:
                # 未指定流选择：按源是否含音轨决定音频输出
                if self.has_audio_stream(input_path):
                    cmd.extend(["-c:a", "aac", "-b:a", "192k"])
                else:
                    cmd.append("-an")
            # 指定了 selected_streams 时流选择完全由 map 控制，此处不加
            # -an/-c:a（否则 -an 会把下面 map 选中的音频流也禁掉）

            cmd.extend(["-threads", str(max_threads or 0)])
        
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

            # 只选了音频流 → 禁视频（-vn），否则 -an 会把选中的音频也禁用
            if not has_video:
                cmd.append("-vn" if has_audio else "-an")

        # 元数据写入（标题/艺术家等）
        if isinstance(metadata, dict):
            for _k in ("title", "artist", "album", "comment", "description"):
                _v = (metadata.get(_k) or "").strip()
                if _v:
                    cmd.extend(["-metadata", f"{_k}={_v}"])

        cmd.append(output_path)

        result = run_ffmpeg(cmd, duration=duration, label="转换中",
                            cancel_check=lambda: self._cancel,
                            progress_callback=progress_callback,
                            speed_enabled=True, translate_error=True)
        if result.success:
            return True
        if result.cancelled:
            return False
        if progress_callback:
            progress_callback(-1, f"转换失败：{result.error_cn}")
        return False

    def crop(self, input_path, output_path, start_time, end_time, copy_mode=False, progress_callback=None):
        self._cancel = False
        ffmpeg = get_ffmpeg_path()
        if not ffmpeg:
            if progress_callback:
                progress_callback(-1, "错误: FFmpeg未安装")
            return False

        duration = self.get_duration(input_path)
        cmd = [ffmpeg, "-y", "-nostats", "-progress", "pipe:2",
               "-hwaccel", "auto", "-ss", start_time, "-i", input_path, "-to", end_time]

        if copy_mode:
            cmd.extend(["-c", "copy"])
        else:
            cmd.extend(["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-c:a", "aac", "-b:a", "192k", "-threads", "0"])

        cmd.append(output_path)

        result = run_ffmpeg(cmd, duration=duration, label="裁剪中",
                            cancel_check=lambda: self._cancel,
                            progress_callback=progress_callback)
        if result.success:
            return True
        if result.cancelled:
            return False
        if progress_callback:
            progress_callback(-1, f"裁剪失败：{result.error_cn}")
        return False

    def concat(self, input_files, output_path, copy_mode=True, progress_callback=None):
        self._cancel = False
        ffmpeg = get_ffmpeg_path()
        if not ffmpeg:
            if progress_callback:
                progress_callback(-1, "错误: FFmpeg未安装")
            return False

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
            cmd = [ffmpeg, "-y", "-nostats", "-progress", "pipe:2"]
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

            total_duration = sum(self.get_duration(f) for f in input_files)

            result = run_ffmpeg(cmd, duration=total_duration, label="拼接中",
                                cancel_check=lambda: self._cancel,
                                progress_callback=progress_callback)
            if result.success:
                return True
            if result.cancelled:
                return False
            if progress_callback:
                progress_callback(-1, f"拼接失败：{result.error_cn}")
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
            ffmpeg, "-y", "-nostats", "-progress", "pipe:2",
            "-hwaccel", "auto", "-i", input_path,
            "-filter_complex", filter_complex,
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-c:a", "aac", "-b:a", "192k", "-threads", "0",
            output_path
        ]

        total_segment_duration = sum(self._parse_time(e) - self._parse_time(s) for s, e in segments)

        result = run_ffmpeg(cmd, duration=total_segment_duration, label="裁剪中",
                            cancel_check=lambda: self._cancel,
                            progress_callback=progress_callback)
        if result.success:
            return True
        if result.cancelled:
            return False
        if progress_callback:
            progress_callback(-1, f"裁剪失败：{result.error_cn}")
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

        # 输出目录可能不存在（用户自定义目录），先创建，否则 FFmpeg 无法写出文件
        out_dir = os.path.dirname(output_path)
        if out_dir:
            try:
                os.makedirs(out_dir, exist_ok=True)
            except OSError:
                if progress_callback:
                    progress_callback(-1, f"错误: 无法创建输出目录 {out_dir}")
                return False

        cmd = [ffmpeg, "-y", "-nostats", "-progress", "pipe:2",
               "-i", input_path, "-vn", "-c:a", ac, "-b:a", bitrate,
               "-map_metadata", "0", output_path]

        result = run_ffmpeg(cmd, duration=duration, label="提取中",
                            cancel_check=lambda: self._cancel,
                            progress_callback=progress_callback,
                            translate_error=True)
        if result.success:
            return True
        if result.cancelled:
            return False
        if progress_callback:
            progress_callback(-1, f"提取失败：{result.error_cn}")
        return False


