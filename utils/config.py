"""配置文件 - 兼容开发环境与PyInstaller打包"""
from gui_qt.i18n import tr
import os
import sys
import shutil
import threading
import time as _time_mod

APP_NAME = tr("格式大师", "FormatMaster")
APP_VERSION = "1.4.0"

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

# ffmpeg/ffprobe 路径查找缓存：运行期路径基本不变，避免每次调用
# 都做 4 层文件系统探测（转换任务中每个 Popen 前至少调两次）。
# 下载/更新新版本后由 ffmpeg_manager 调用 invalidate_ffmpeg_path_cache() 失效。
_FFMPEG_PATH_CACHE = {}
_FFMPEG_PATH_CACHE_LOCK = threading.Lock()


def invalidate_ffmpeg_path_cache():
    """清除 ffmpeg/ffprobe 路径缓存（下载/更新新版本后调用）。"""
    with _FFMPEG_PATH_CACHE_LOCK:
        _FFMPEG_PATH_CACHE.clear()


def _find_ffmpeg(name: str):
    """
    按优先级查找FFmpeg/FFprobe:
    0. 用户自定义路径（设置页"浏览…"手动选择，优先级最高）
    1. 用户可写目录（下载/更新后的版本）
    2. 打包嵌入的资源（_internal/bin，只读）
    3. 系统环境变量PATH

    结果缓存到 _FFMPEG_PATH_CACHE，避免重复文件系统探测。
    缓存键含自定义路径值，用户修改路径后自动重新探测。
    """
    custom = USER_PREFS.get("qt_app", "ffmpeg_custom_path", "")
    cache_key = (name, custom)
    with _FFMPEG_PATH_CACHE_LOCK:
        cached = _FFMPEG_PATH_CACHE.get(cache_key)
        if cached is not None:
            return cached

    # 0. 用户自定义路径
    if custom and os.path.isfile(custom):
        if name.startswith("ffprobe"):
            probe = os.path.join(os.path.dirname(custom),
                                 "ffprobe.exe" if os.name == "nt" else "ffprobe")
            if os.path.isfile(probe):
                with _FFMPEG_PATH_CACHE_LOCK:
                    _FFMPEG_PATH_CACHE[cache_key] = probe
                return probe
        with _FFMPEG_PATH_CACHE_LOCK:
            _FFMPEG_PATH_CACHE[cache_key] = custom
        return custom

    # 1. 用户数据目录
    user_path = os.path.join(get_writable_bin_dir(), name)
    if os.path.exists(user_path):
        with _FFMPEG_PATH_CACHE_LOCK:
            _FFMPEG_PATH_CACHE[cache_key] = user_path
        return user_path

    # 2. 打包嵌入的资源
    bundled_path = get_resource_path(f"bin/{name}")
    if os.path.exists(bundled_path):
        with _FFMPEG_PATH_CACHE_LOCK:
            _FFMPEG_PATH_CACHE[cache_key] = bundled_path
        return bundled_path

    # 3. 系统PATH（None 也缓存，避免重复探测）
    result = shutil.which(name.replace(".exe", ""))
    with _FFMPEG_PATH_CACHE_LOCK:
        _FFMPEG_PATH_CACHE[cache_key] = result
    return result

# ═══════════════════════════════════════════════
#  FFmpeg 错误信息中文翻译
# ═══════════════════════════════════════════════
# 按关键词长度降序排列——确保更具体的长匹配优先于短子串匹配，
# 避免 "not found" 误匹配 "Could not find codec parameters" 等具体错误
_FFMPEG_ERROR_RULES = [
    ("Could not find codec parameters", "无法解析媒体参数，文件可能已损坏"),
    ("Invalid data found when processing input", "文件格式不支持或文件已损坏"),
    ("codec not currently supported in container", "当前封装格式不支持该编码器，请换用其他格式"),
    ("No such file or directory", "找不到输入文件，请检查路径是否正确"),
    ("Device or resource busy", "设备或资源繁忙，请稍后重试"),
    ("Unknown encoder", "缺少编码器，请检查FFmpeg安装或换用其他编码"),
    ("Connection refused", "无法连接到服务器"),
    ("Permission denied", "无法写入输出文件，权限不足"),
    ("Invalid argument", "参数无效，请检查设置"),
    ("FileNotFoundError", "找不到输入文件"),
    ("ValueError", "参数值错误"),
    ("not found", "找不到必要组件，请重新安装FFmpeg"),
]


def translate_ffmpeg_error(stderr_text):
    """将 FFmpeg 错误输出翻译为中文说明。

    按规则列表顺序（长关键词优先）逐条匹配，避免短子串
    （如 "not found"）贪婪命中更具体的错误描述。
    """
    if not stderr_text:
        return "转换失败，请检查文件是否完整或尝试其他格式"
    lower = stderr_text.lower()
    for eng, chn in _FFMPEG_ERROR_RULES:
        if eng.lower() in lower:
            return chn
    return "转换失败，请检查文件是否完整或尝试其他格式"

def get_ffmpeg_path():
    name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    return _find_ffmpeg(name)

def get_ffprobe_path():
    name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    return _find_ffmpeg(name)

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


def _atomic_write_json(path, data):
    """健壮的 JSON 原子写：tmp + replace，瞬时占用（多实例/杀软锁定）时
    重试 3 次，仍失败则降级直接写原文件（避免丢失本次保存）。"""
    import json
    import time as _time
    tmp = path + ".tmp"
    last_err = None
    for attempt in range(3):
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, path)
            return True
        except OSError as e:
            last_err = e
            _time.sleep(0.15 * (attempt + 1))
    # 降级：直接写原文件（非原子，但能保存数据；目标文件被占用时放弃）
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except OSError as e:
        last_err = e
    print(f"[WARN] 保存用户偏好失败（已重试）：{last_err}")
    return False


class UserPrefs:
    """用户偏好：内存读写即时、磁盘写后台合并（性能优化 2026-08-18）。

    原来 set()/set_batch() 每次都全量 JSON dump + 原子写盘（UI 线程），
    面板实时记忆（500ms 防抖）、设置页联动等高频场景会造成主线程卡顿。
    现在：
    - set()/set_batch()/save_panel_batch() 只更新内存并标记 dirty，
      由后台 daemon 线程按「150ms 合并窗口」落盘一次（窗口内多次变更
      合并为一次写，UI 线程零文件 IO）；
    - _save()/flush() 保持同步写（退出收尾、测试断言等显式场景）；
    - 退出时调用 flush() 兜底（见 app.py closeEvent）。
    多实例由单实例锁保证，崩溃时最多丢失 150ms 窗口内的偏好。
    """

    def __init__(self):
        self.prefs = {}
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()   # 串行化磁盘写（后台/同步共存）
        self._defer_save = False
        self._dirty = threading.Event()       # 有未落盘变更
        self._load()
        # 后台写线程（daemon，进程结束自动终止）
        try:
            threading.Thread(
                target=self._writer_loop, name="prefs-writer",
                daemon=True).start()
        except Exception:  # noqa: BLE001 - 线程启动失败退化为同步写
            pass

    def _writer_loop(self):
        """后台合并写：等 dirty → 150ms 合并窗口 → 无新变更才写盘。"""
        import copy
        while True:
            self._dirty.wait()
            self._dirty.clear()
            _time_mod.sleep(0.15)            # 合并窗口：连续变更归并为一次写
            if self._dirty.is_set():
                continue                     # 窗口内又有新变更 → 再等一轮
            path = get_user_prefs_path()
            try:
                with self._lock:
                    data = copy.deepcopy(self.prefs)
            except Exception:  # noqa: BLE001
                continue
            with self._write_lock:
                _atomic_write_json(path, data)

    def _load(self):
        path = get_user_prefs_path()
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    import json
                    self.prefs = json.load(f)
            except Exception:
                # 备份损坏的文件
                try:
                    backup = path + ".bak"
                    if os.path.exists(backup):
                        os.remove(backup)
                    os.rename(path, backup)
                except Exception:
                    pass
                self.prefs = {}

    def _save(self):
        """同步落盘（显式调用场景：退出收尾/测试断言）。"""
        if self._defer_save:
            return
        path = get_user_prefs_path()
        with self._write_lock:
            _atomic_write_json(path, self.prefs)

    def flush(self):
        """手动触发落盘：先把内存中未落盘的变更同步写盘（退出前兜底）。"""
        # 清掉后台待写标记（数据马上由本方法同步写盘，避免重复写）
        if self._dirty.is_set():
            self._dirty.clear()
        path = get_user_prefs_path()
        with self._write_lock:
            _atomic_write_json(path, self.prefs)

    def get(self, panel, key, default=None):
        with self._lock:
            return self.prefs.get(panel, {}).get(key, default)

    def set(self, panel, key, value):
        with self._lock:
            if panel not in self.prefs:
                self.prefs[panel] = {}
            self.prefs[panel][key] = value
        self._dirty.set()   # 后台合并写，UI 线程零 IO

    def set_batch(self, items):
        """批量写入多个 panel 配置，只落盘一次（退出收尾用，避免 N 次全量写盘卡顿）。

        items: [(panel, key, value), ...]；内存更新全部后由后台线程合并落盘。
        """
        with self._lock:
            for panel, key, value in items:
                if panel not in self.prefs:
                    self.prefs[panel] = {}
                self.prefs[panel][key] = value
        self._dirty.set()

    def save_panel_batch(self, panels):
        """批量替换多个 panel 的整个配置，只落盘一次。

        panels: {panel: params_dict}。
        注意：以 panel 为粒度整体替换该 panel 的值，但**不删除**该
        命名空间下 panels 未提到的其他键（如 qt_app 下的 close_confirm
        等应用级设置不会被批量面板保存抹掉）。
        """
        with self._lock:
            for panel, params in panels.items():
                if panel in self.prefs and isinstance(self.prefs[panel], dict):
                    # 合并式更新：保留该 panel 下未涉及的键
                    self.prefs[panel].update(params or {})
                else:
                    self.prefs[panel] = params or {}
            self._save()
    
    def save_panel(self, panel, params):
        with self._lock:
            self.prefs[panel] = params
            self._save()
    
    def get_panel(self, panel):
        with self._lock:
            return dict(self.prefs.get(panel, {}))

    def clear(self):
        """清空全部偏好并落盘（「恢复默认设置」用，调用方负责重启生效）。"""
        with self._lock:
            self.prefs = {}
            self._save()

USER_PREFS = UserPrefs()


class ConversionHistory:
    """转换历史记录管理"""

    MAX_RECORDS = 200

    def __init__(self):
        self.records = []
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        path = get_history_path()
        if os.path.exists(path):
            try:
                import json
                with open(path, 'r', encoding='utf-8') as f:
                    self.records = json.load(f)
            except Exception:
                # 备份损坏的文件
                try:
                    backup = path + ".bak"
                    if os.path.exists(backup):
                        os.remove(backup)
                    os.rename(path, backup)
                except Exception:
                    pass
                self.records = []

    def _save(self):
        path = get_history_path()
        _atomic_write_json(path, self.records)

    def add(self, record: dict):
        """添加一条历史记录"""
        import time as tm
        record["time"] = tm.strftime("%Y-%m-%d %H:%M:%S")
        record["timestamp"] = tm.time()
        with self._lock:
            self.records.insert(0, record)
            if len(self.records) > self.MAX_RECORDS:
                self.records = self.records[:self.MAX_RECORDS]
            self._save()

    def get_all(self, limit=None):
        with self._lock:
            if limit:
                return list(self.records[:limit])
            return list(self.records)

    def clear(self):
        with self._lock:
            self.records.clear()
            self._save()

    def delete(self, index):
        with self._lock:
            if 0 <= index < len(self.records):
                self.records.pop(index)
                self._save()

CONV_HISTORY = ConversionHistory()

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
    "TIFF": ".tiff", "WEBP": ".webp", "AVIF": ".avif", "HEIC": ".heic",
    "ICO": ".ico", "TGA": ".tga",
}

VIDEO_CODECS = {
    tr("默认", "Default"): None,
    "H.264": "libx264",
    "H.265/HEVC": "libx265",
    "VP9": "libvpx-vp9",
    "MPEG4": "mpeg4",
}

AUDIO_CODECS = {
    tr("默认", "Default"): None,
    "AAC": "aac",
    "MP3": "libmp3lame",
    "FLAC": "flac",
    "Vorbis": "libvorbis",
    "Opus": "libopus",
    "PCM": "pcm_s16le",
}

VIDEO_PRESETS = {
    tr("原始质量", "Original quality"): None,
    "高质量 (大文件)": "high",
    "中等质量": "medium",
    "低质量 (小文件)": "low",
    "手机": "mobile",
    "网络分享": "web",
}

RESOLUTIONS = {
    tr("原始分辨率", "Original resolution"): None,
    "4K (3840x2160)": (3840, 2160),
    "2K (2560x1440)": (2560, 1440),
    "1080p (1920x1080)": (1920, 1080),
    "720p (1280x720)": (1280, 720),
    "480p (854x480)": (854, 480),
    "360p (640x360)": (640, 360),
}

# ── 视频转换预设模板 ────────────────────────────
# 每个预设包含一组面板参数，选择后自动填充
VIDEO_CONVERT_PRESETS = {
    tr("自定义", "Custom"): {},
    "高质量": {
        "codec": tr("默认", "Default"), "preset": tr("原始质量", "Original quality"), "res": tr("原始分辨率", "Original resolution"),
        "fps": tr("原始帧率", "Original FPS"), "br": tr("自动", "Auto"), "copy_mode": False,
    },
    "Web 优化": {
        "codec": "H.265", "preset": "中速", "res": "1080p (1920x1080)",
        "fps": "30", "br": "5M", "copy_mode": False,
    },
    "小体积": {
        "codec": "H.265", "preset": "慢速", "res": "720p (1280x720)",
        "fps": "30", "br": "2M", "copy_mode": False,
    },
    "极速复制": {
        "codec": tr("默认", "Default"), "preset": tr("原始质量", "Original quality"), "res": tr("原始分辨率", "Original resolution"),
        "fps": tr("原始帧率", "Original FPS"), "br": tr("自动", "Auto"), "copy_mode": True,
    },
    "手机竖屏": {
        "codec": "H.264", "preset": "中速", "res": "720p (1280x720)",
        "fps": "30", "br": "3M", "copy_mode": False,
    },
    "4K 影院": {
        "codec": "H.265", "preset": "高质量", "res": "4K (3840x2160)",
        "fps": tr("原始帧率", "Original FPS"), "br": "20M", "copy_mode": False,
    },
}

DOC_READ_FORMATS = {
    ".pdf": "PDF文档", ".docx": "Word文档", ".doc": "Word97文档",
    ".wps": "WPS文档", ".xlsx": "Excel表格", ".xls": "Excel97表格",
    ".et": "WPS表格", ".csv": "CSV表格", ".pptx": "PPT演示",
    ".ppt": "PPT97演示", ".dps": "WPS演示", ".txt": "文本文件",
    ".html": "网页", ".htm": "网页",
    ".jpg": tr("图片", "Image"), ".jpeg": tr("图片", "Image"), ".png": tr("图片", "Image"),
    ".bmp": "图片", ".tiff": "图片", ".webp": "图片",
    ".md": "Markdown", ".epub": "EPUB电子书",
    ".rtf": "RTF富文本", ".odt": "ODT文档",
    ".ofd": "OFD文档",
}

DOC_CONVERSION_MAP = {
    "PDF文档": [".docx", ".doc", ".txt", ".jpg", ".png", ".html", ".pptx", ".xlsx"],
    "Word文档": [".pdf", ".txt", ".html", ".doc", ".wps", ".jpg", ".png", ".pptx", ".md", ".xlsx"],
    "Word97文档": [".pdf", ".txt", ".docx", ".html", ".md"],
    "WPS文档": [".docx", ".pdf", ".txt", ".html", ".md"],
    "Excel表格": [".pdf", ".csv", ".txt", ".jpg", ".png", ".html", ".md", ".et", ".docx"],
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
    "OFD文档": [".pdf"],
}
