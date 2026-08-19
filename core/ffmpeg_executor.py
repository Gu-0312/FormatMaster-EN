"""FFprobe 元数据读取工具
统一封装 ffprobe 调用，强制 timeout 防止大文件卡顿。

跨模块共享的 ffprobe 结果缓存：以 (路径, mtime, 文件大小) 为键，
LRU 淘汰（上限 200），避免转换管线中 video/audio/img 转换器各自
重复启动 ffprobe 子进程（每个 ~50-200ms）。
"""
import os
import json
import subprocess
import threading
from collections import OrderedDict

from utils.config import get_ffprobe_path


# 大文件元数据读取超时（秒）
# 按风险规避要求：强制 3 秒超时，获取失败则直接返回 None，绝不占用 UI 主线程
FFPROBE_TIMEOUT = 3

# 转换管线用超时（秒）— 允许更大文件，但仍防止卡死
FFPROBE_TIMEOUT_LONG = 10

# 全局 ffprobe 结果缓存：上限 200，LRU 淘汰
_FFPROBE_CACHE_MAX = 200
_FFPROBE_CACHE = OrderedDict()
_FFPROBE_CACHE_LOCK = threading.Lock()


def _ffprobe_cache_key(filepath):
    """生成缓存键：(filepath, mtime, size)。文件修改后自动失效。"""
    try:
        st = os.stat(filepath)
        return (os.path.abspath(filepath), st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def _ffprobe_cache_get(key):
    with _FFPROBE_CACHE_LOCK:
        if key in _FFPROBE_CACHE:
            _FFPROBE_CACHE.move_to_end(key)
            return _FFPROBE_CACHE[key]
    return None


def _ffprobe_cache_set(key, value):
    with _FFPROBE_CACHE_LOCK:
        if key in _FFPROBE_CACHE:
            _FFPROBE_CACHE.move_to_end(key)
            _FFPROBE_CACHE[key] = value
        else:
            _FFPROBE_CACHE[key] = value
            if len(_FFPROBE_CACHE) > _FFPROBE_CACHE_MAX:
                _FFPROBE_CACHE.popitem(last=False)


def invalidate_ffprobe_cache():
    """清空 ffprobe 缓存（ffmpeg 版本变更等场景调用）。"""
    with _FFPROBE_CACHE_LOCK:
        _FFPROBE_CACHE.clear()


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
    结果经模块级缓存（按 mtime+size 失效），获取失败返回 None。
    """
    # 1) 查缓存
    cache_key = _ffprobe_cache_key(filepath)
    if cache_key:
        cached = _ffprobe_cache_get(cache_key)
        if cached is not None:
            return cached

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
        data = json.loads(result.stdout)
        # 清洗：部分流媒体/损坏文件的 duration 可能是 "N/A" 或空字符串，
        # 下游 float(...) 会 ValueError。统一归一为 "0"。
        try:
            _fmt = data.get("format") or {}
            _d = _fmt.get("duration")
            if not isinstance(_d, (int, float)) and (
                    _d is None or not str(_d).strip().lstrip("-").replace(".", "", 1).isdigit()):
                _fmt["duration"] = "0"
        except Exception:  # noqa: BLE001 - 清洗失败不影响原数据
            pass
        # 2) 写缓存（文件存在时）
        if cache_key:
            _ffprobe_cache_set(cache_key, data)
        return data
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
