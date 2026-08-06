"""FFprobe 元数据读取工具
统一封装 ffprobe 调用，强制 timeout 防止大文件卡顿。
"""
import os
import json
import subprocess

from utils.config import get_ffprobe_path


# 大文件元数据读取超时（秒）
# 按风险规避要求：强制 3 秒超时，获取失败则直接返回 None，绝不占用 UI 主线程
FFPROBE_TIMEOUT = 3

# 转换管线用超时（秒）— 允许更大文件，但仍防止卡死
FFPROBE_TIMEOUT_LONG = 10


def get_ffprobe_info(filepath):
    """读取媒体文件元数据，返回字典：
        {
            "duration": "00:01:23",
            "resolution": "1920x1080",
            "codec": "h264",
            "bit_rate": "2.5 Mbps",
            "size": "12.3 MB"
        }
    获取失败返回 None。

    使用 timeout=3 秒限制，避免读取大文件时阻塞 UI。
    """
    ffprobe = get_ffprobe_path()
    if not ffprobe:
        return None

    try:
        cmd = [
            ffprobe,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            filepath
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=FFPROBE_TIMEOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        if result.returncode != 0 or not result.stdout:
            return None

        data = json.loads(result.stdout)
        return _parse_ffprobe_data(data, filepath)
    except subprocess.TimeoutExpired:
        # 超时直接返回 None，不抛出异常
        return None
    except json.JSONDecodeError:
        return None
    except FileNotFoundError:
        return None
    except Exception:
        return None


def get_ffprobe_raw(filepath, timeout=None):
    """读取媒体文件的原始 ffprobe JSON 数据（format + streams）。

    用于转换管线中需要 duration / codec / has_audio 等原始字段的场景。
    timeout 默认 FFPROBE_TIMEOUT_LONG（10 秒），可自定义。
    获取失败返回 None。
    """
    ffprobe = get_ffprobe_path()
    if not ffprobe:
        return None
    try:
        cmd = [
            ffprobe, "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", filepath
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore',
            timeout=timeout or FFPROBE_TIMEOUT_LONG,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        if result.returncode != 0 or not result.stdout:
            return None
        return json.loads(result.stdout)
    except Exception:
        return None


def _parse_ffprobe_data(data, filepath):
    """解析 ffprobe JSON 输出，提取关键字段"""
    info = {
        "duration": "-",
        "resolution": "-",
        "codec": "-",
        "bit_rate": "-",
        "size": "-"
    }

    try:
        fmt = data.get("format", {})
        # 时长格式化
        duration_sec = float(fmt.get("duration", 0))
        if duration_sec > 0:
            hours = int(duration_sec // 3600)
            minutes = int((duration_sec % 3600) // 60)
            seconds = int(duration_sec % 60)
            if hours > 0:
                info["duration"] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                info["duration"] = f"{minutes:02d}:{seconds:02d}"

        # 码率
        bit_rate = int(fmt.get("bit_rate", 0))
        if bit_rate > 0:
            if bit_rate >= 1_000_000:
                info["bit_rate"] = f"{bit_rate / 1_000_000:.2f} Mbps"
            else:
                info["bit_rate"] = f"{bit_rate / 1000:.0f} kbps"

        # 文件大小
        size_bytes = os.path.getsize(filepath) if os.path.exists(filepath) else 0
        if size_bytes > 0:
            if size_bytes >= 1_073_741_824:
                info["size"] = f"{size_bytes / 1_073_741_824:.2f} GB"
            elif size_bytes >= 1_048_576:
                info["size"] = f"{size_bytes / 1_048_576:.2f} MB"
            else:
                info["size"] = f"{size_bytes / 1024:.1f} KB"
    except Exception:
        pass

    # 从 streams 中提取视频/音频编码与分辨率
    try:
        streams = data.get("streams", [])
        has_video = False
        for stream in streams:
            codec_type = stream.get("codec_type", "")
            codec_name = stream.get("codec_name", "")
            if codec_type == "video":
                has_video = True
                if info["codec"] == "-":
                    info["codec"] = codec_name
                width = stream.get("width")
                height = stream.get("height")
                if width and height:
                    info["resolution"] = f"{width}×{height}"
                break
        # 没有视频流时，从音频流提取编码
        if not has_video:
            for stream in streams:
                if stream.get("codec_type") == "audio":
                    info["codec"] = stream.get("codec_name", "-")
                    break
    except Exception:
        pass

    return info
