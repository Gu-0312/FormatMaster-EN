"""通用格式辅助函数

从 main.py 提取的纯函数模块。
"""
import re


def extract_urls(text):
    """从文本中提取所有 http(s) URL"""
    return list(set(re.findall(r"https?://[^\s\u4e00-\u9fff\u3000-\u303f\uff00-\uffef<>\"']+", text)))


def format_size(size):
    """格式化文件大小为人类可读字符串"""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    else:
        return f"{size / (1024 * 1024 * 1024):.1f} GB"


def parse_time(time_str):
    """将 HH:MM:SS / MM:SS / SS 格式的时间字符串转换为秒数"""
    try:
        parts = list(map(float, time_str.split(":")))
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        elif len(parts) == 2:
            return parts[0] * 60 + parts[1]
        return float(parts[0])
    except Exception:
        return 0


def format_time(seconds):
    """将秒数格式化为 HH:MM:SS.sss 字符串"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"
