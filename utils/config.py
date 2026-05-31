"""配置文件"""
import os
import sys
import subprocess
import shutil

APP_NAME = "格式大师"
APP_VERSION = "1.0.0"

def get_app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_bin_dir():
    d = os.path.join(get_app_dir(), "bin")
    os.makedirs(d, exist_ok=True)
    return d

def _find_in_path(name):
    """在系统PATH中查找可执行文件"""
    result = shutil.which(name)
    return result

def get_ffmpeg_path():
    bin_dir = get_bin_dir()
    path = os.path.join(bin_dir, "ffmpeg.exe")
    if os.path.exists(path):
        return path
    return _find_in_path("ffmpeg")

def get_ffprobe_path():
    bin_dir = get_bin_dir()
    path = os.path.join(bin_dir, "ffprobe.exe")
    if os.path.exists(path):
        return path
    return _find_in_path("ffprobe")

TEMP_DIR = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "FormatMaster")
os.makedirs(TEMP_DIR, exist_ok=True)

SUPPORTED_VIDEO = {
    "MP4": ".mp4", "AVI": ".avi", "MKV": ".mkv", "WMV": ".wmv",
    "MOV": ".mov", "FLV": ".flv", "WEBM": ".webm", "TS": ".ts",
    "MPEG": ".mpeg", "3GP": ".3gp", "GIF": ".gif",
}

SUPPORTED_AUDIO = {
    "MP3": ".mp3", "WAV": ".wav", "WMA": ".wma", "AAC": ".aac",
    "FLAC": ".flac", "OGG": ".ogg", "M4A": ".m4a", "AMR": ".amr",
    "OPUS": ".opus",
}

SUPPORTED_IMAGE = {
    "JPG": ".jpg", "PNG": ".png", "BMP": ".bmp", "GIF": ".gif",
    "TIFF": ".tiff", "WEBP": ".webp", "ICO": ".ico", "TGA": ".tga",
}

VIDEO_CODECS = {
    "默认": None,
    "H.264": "libx264",
    "H.265/HEVC": "libx265",
    "VP9": "libvpx-vp9",
    "MPEG4": "mpeg4",
}

AUDIO_CODECS = {
    "默认": None,
    "AAC": "aac",
    "MP3": "libmp3lame",
    "FLAC": "flac",
    "Vorbis": "libvorbis",
    "Opus": "libopus",
    "PCM": "pcm_s16le",
}

VIDEO_PRESETS = {
    "原始质量": None,
    "高质量 (大文件)": "high",
    "中等质量": "medium",
    "低质量 (小文件)": "low",
    "手机": "mobile",
    "网络分享": "web",
}

RESOLUTIONS = {
    "原始分辨率": None,
    "4K (3840x2160)": (3840, 2160),
    "2K (2560x1440)": (2560, 1440),
    "1080p (1920x1080)": (1920, 1080),
    "720p (1280x720)": (1280, 720),
    "480p (854x480)": (854, 480),
    "360p (640x360)": (640, 360),
}

DOC_READ_FORMATS = {
    ".pdf": "PDF文档", ".docx": "Word文档", ".doc": "Word97文档",
    ".wps": "WPS文档", ".xlsx": "Excel表格", ".xls": "Excel97表格",
    ".et": "WPS表格", ".csv": "CSV表格", ".pptx": "PPT演示",
    ".ppt": "PPT97演示", ".dps": "WPS演示", ".txt": "文本文件",
    ".html": "网页", ".htm": "网页",
    ".jpg": "图片", ".jpeg": "图片", ".png": "图片",
    ".bmp": "图片", ".tiff": "图片", ".webp": "图片",
}

DOC_CONVERSION_MAP = {
    "PDF文档": [".docx", ".doc", ".txt", ".jpg", ".png", ".html"],
    "Word文档": [".pdf", ".txt", ".html", ".doc", ".wps"],
    "Word97文档": [".pdf", ".txt", ".docx"],
    "WPS文档": [".docx", ".pdf", ".txt"],
    "Excel表格": [".pdf", ".csv", ".txt"],
    "CSV表格": [".xlsx", ".txt"],
    "PPT演示": [".pdf", ".txt", ".jpg", ".png", ".ppt", ".dps"],
    "PPT97演示": [".pptx"],
    "WPS演示": [".pptx"],
    "WPS表格": [".xlsx"],
    "图片": [".pdf"],
    "文本文件": [".pdf", ".xlsx"],
    "网页": [".pdf"],
}
