"""配置文件 - 兼容开发环境与PyInstaller打包"""
import os
import sys
import shutil

APP_NAME = "格式大师"
APP_VERSION = "1.2.0"

# ═══════════════════════════════════════════════
#  路径管理（核心修复区）
# ═══════════════════════════════════════════════

def _is_frozen():
    """判断是否为PyInstaller打包环境"""
    return getattr(sys, 'frozen', False)

def get_app_dir():
    """获取应用程序根目录（仅用于定位项目结构，不用于读写资源）"""
    if _is_frozen():
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_resource_path(relative_path: str) -> str:
    """
    获取只读资源路径
    - 打包后: 指向 _MEIPASS/_internal（PyInstaller解压的临时目录）
    - 开发时: 指向项目根目录
    """
    if _is_frozen():
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)

def get_writable_bin_dir() -> str:
    """
    获取可写的bin目录（用于下载FFmpeg、缓存等运行时生成的文件）
    - 打包后: %APPDATA%/FormatMaster/bin（持久化，重启不丢失）
    - 开发时: 项目根目录/bin
    """
    if _is_frozen():
        app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
        bin_dir = os.path.join(app_data, APP_NAME, "bin")
    else:
        bin_dir = os.path.join(get_app_dir(), "bin")
    os.makedirs(bin_dir, exist_ok=True)
    return bin_dir

# ✅ 保留此函数名以兼容 ffmpeg_manager.py 的调用
# 但内部已改为返回【可写目录】而非exe同级目录
def get_bin_dir():
    return get_writable_bin_dir()

def _find_bin(name: str):
    """通用二进制查找（用户目录 → 打包嵌入 → 系统PATH）"""
    # 1. 用户可写目录
    user_path = os.path.join(get_writable_bin_dir(), name)
    if os.path.exists(user_path):
        return user_path
    # 2. 打包嵌入的资源 — 遍历所有可能位置
    if _is_frozen():
        candidates = [
            os.path.join(sys._MEIPASS, "bin", name),
            os.path.join(sys._MEIPASS, name),
            os.path.join(os.path.dirname(sys.executable), "bin", name),
            os.path.join(os.path.dirname(sys.executable), name),
        ]
    else:
        candidates = [
            os.path.join(get_app_dir(), "bin", name),
        ]
    for p in candidates:
        if os.path.exists(p):
            return p
    # 3. 系统PATH
    return shutil.which(name.replace(".exe", ""))

def _find_ffmpeg(name: str):
    return _find_bin(name)

# ═══════════════════════════════════════════════
#  FFmpeg 错误信息中文翻译
# ═══════════════════════════════════════════════
FFMPEG_ERROR_MAP = {
    "No such file or directory": "找不到输入文件，请检查路径是否正确",
    "Invalid data found when processing input": "文件格式不支持或文件已损坏",
    "Unknown encoder": "缺少编码器，请检查FFmpeg安装或换用其他编码",
    "codec not currently supported in container": "当前封装格式不支持该编码器，请换用其他格式",
    "Permission denied": "无法写入输出文件，权限不足",
    "not found": "找不到必要组件，请重新安装FFmpeg",
    "Could not find codec parameters": "无法解析媒体参数，文件可能已损坏",
    "Invalid argument": "参数无效，请检查设置",
    "Connection refused": "无法连接到服务器",
    "Device or resource busy": "设备或资源繁忙，请稍后重试",
    "ValueError": "参数值错误",
    "FileNotFoundError": "找不到输入文件",
}

def translate_ffmpeg_error(stderr_text):
    """将 FFmpeg 错误输出翻译为中文说明"""
    for eng, chn in FFMPEG_ERROR_MAP.items():
        if eng.lower() in stderr_text.lower():
            return chn
    return "转换失败，请检查文件是否完整或尝试其他格式"

def get_ffmpeg_path():
    name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    return _find_ffmpeg(name)

def get_ffprobe_path():
    name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    return _find_ffmpeg(name)

def get_ytdlp_path():
    """获取 yt-dlp 可执行文件路径（支持所有打包布局）"""
    name = "yt-dlp.exe"
    # 1. 用户可写目录（已下载/更新的版本）
    user_path = os.path.join(get_writable_bin_dir(), name)
    if os.path.exists(user_path):
        return user_path
    # 2. 打包嵌入的资源 — 遍历所有可能位置
    if _is_frozen():
        candidates = [
            # _internal/bin/yt-dlp.exe（标准 --onedir 布局）
            os.path.join(sys._MEIPASS, "bin", name),
            # _internal/yt-dlp.exe（直接放在解压根目录）
            os.path.join(sys._MEIPASS, name),
            # exe 同级的 bin/yt-dlp.exe
            os.path.join(os.path.dirname(sys.executable), "bin", name),
            # exe 同级（用户手动放入便携版）
            os.path.join(os.path.dirname(sys.executable), name),
        ]
    else:
        candidates = [
            # 开发环境: bin/yt-dlp.exe
            os.path.join(get_app_dir(), "bin", name),
        ]
    for p in candidates:
        if os.path.exists(p):
            return p
    # 3. 系统PATH
    return shutil.which(name.replace(".exe", ""))

# ═══════════════════════════════════════════════
#  临时目录
# ═══════════════════════════════════════════════
TEMP_DIR = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), APP_NAME)
os.makedirs(TEMP_DIR, exist_ok=True)

def get_user_data_dir():
    """获取用户数据目录（用于存储配置、历史记录等）"""
    if _is_frozen():
        app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
        data_dir = os.path.join(app_data, APP_NAME, "data")
    else:
        data_dir = os.path.join(get_app_dir(), "data")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir

def get_config_path():
    """获取配置文件路径"""
    return os.path.join(get_user_data_dir(), "config.json")

def get_history_path():
    """获取历史记录文件路径"""
    return os.path.join(get_user_data_dir(), "history.json")

def get_presets_path():
    """获取预设模板文件路径"""
    return os.path.join(get_user_data_dir(), "presets.json")

def get_user_prefs_path():
    """获取用户偏好设置文件路径"""
    return os.path.join(get_user_data_dir(), "user_prefs.json")


class UserPrefs:
    def __init__(self):
        self.prefs = {}
        self._load()
    
    def _load(self):
        path = get_user_prefs_path()
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    import json
                    self.prefs = json.load(f)
            except Exception:
                self.prefs = {}
    
    def _save(self):
        path = get_user_prefs_path()
        try:
            import json
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.prefs, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    
    def get(self, panel, key, default=None):
        return self.prefs.get(panel, {}).get(key, default)
    
    def set(self, panel, key, value):
        if panel not in self.prefs:
            self.prefs[panel] = {}
        self.prefs[panel][key] = value
        self._save()
    
    def save_panel(self, panel, params):
        self.prefs[panel] = params
        self._save()
    
    def get_panel(self, panel):
        return self.prefs.get(panel, {})

USER_PREFS = UserPrefs()

# ═══════════════════════════════════════════════
#  格式与参数配置（以下保持不变）
# ═══════════════════════════════════════════════
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
    ".md": "Markdown", ".epub": "EPUB电子书",
    ".rtf": "RTF富文本", ".odt": "ODT文档",
}

DOC_CONVERSION_MAP = {
    "PDF文档": [".docx", ".doc", ".txt", ".jpg", ".png", ".html", ".pptx", ".xlsx"],
    "Word文档": [".pdf", ".txt", ".html", ".doc", ".wps", ".jpg", ".png", ".pptx", ".md"],
    "Word97文档": [".pdf", ".txt", ".docx", ".html", ".md"],
    "WPS文档": [".docx", ".pdf", ".txt", ".html", ".md"],
    "Excel表格": [".pdf", ".csv", ".txt", ".jpg", ".png", ".html", ".md", ".et"],
    "Excel97表格": [".xlsx", ".pdf", ".csv", ".txt", ".jpg", ".png", ".html", ".md"],
    "CSV表格": [".xlsx", ".pdf", ".txt", ".html", ".md"],
    "PPT演示": [".pdf", ".txt", ".jpg", ".png", ".ppt", ".dps", ".docx", ".html", ".md"],
    "PPT97演示": [".pptx", ".pdf", ".txt"],
    "WPS演示": [".pptx", ".pdf", ".txt"],
    "WPS表格": [".xlsx", ".pdf", ".csv"],
    "图片": [".pdf", ".docx"],
    "文本文件": [".pdf", ".xlsx", ".docx", ".pptx", ".html", ".md"],
    "网页": [".pdf", ".docx", ".txt", ".xlsx", ".md"],
    "Markdown": [".html", ".pdf", ".docx", ".txt"],
    "EPUB电子书": [".pdf", ".txt", ".html", ".docx"],
    "RTF富文本": [".txt", ".pdf", ".docx"],
    "ODT文档": [".pdf", ".docx", ".txt"],
}
