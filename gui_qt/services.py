"""QtServices — Qt 层轻量服务容器。

对应 tkinter 版 app/context.py 的角色，但不依赖 tkinter：
集中持有转换器、FFmpeg 管理器、偏好与历史记录，供面板/页面注入使用。
依赖方向：gui_qt -> core/ + utils/，严格单向。

转换器采用懒加载：首次访问时才 import 重库（PIL/docx/openpyxl）并实例化，
避免启动时加载不需要的依赖，减少冷启动时间。
"""
from gui_qt.i18n import tr
import time

from core.video_converter import VideoConverter
from utils.config import USER_PREFS, CONV_HISTORY
from utils.ffmpeg_manager import FFmpegManager

# Qt 版偏好统一前缀，避免与 tkinter 旧偏好键冲突
QT_PREFS_PANEL = "qt_app"


class _HistoryStats:
    """Read-only statistics adapter backed by conversion history."""

    def __init__(self, history):
        self._history = history

    def get_range(self, start, end):
        """Return records whose date (YYYY-MM-DD) falls inside [start, end]."""
        out = {}
        for rec in self._history.get_all():
            day = str(rec.get("time", ""))[:10]
            if start <= day <= end:
                out.setdefault(day, []).append(rec)
        return out


class QtServices:
    """全局服务容器，主窗口创建一次后注入各页面/面板。

    转换器属性懒加载：首次访问时才实例化（含重库 import），
    避免启动时加载全部依赖。
    """

    def __init__(self):
        self.video_conv = VideoConverter()
        self.ffmpeg_mgr = FFmpegManager()
        self.prefs = USER_PREFS
        self.history = CONV_HISTORY
        self.stats = _HistoryStats(self.history)
        self.start_time = time.time()
        # 上次使用的输出目录（与 tkinter 版 last_output_dir 语义一致）
        self.last_output_dir = self.prefs.get(QT_PREFS_PANEL, "last_output_dir", "")
        # 懒加载缓存
        self._audio_conv = None
        self._image_conv = None
        self._doc_conv = None
        self._video_compressor = None

    @property
    def audio_conv(self):
        if self._audio_conv is None:
            from core.audio_converter import AudioConverter
            self._audio_conv = AudioConverter()
        return self._audio_conv

    @property
    def image_conv(self):
        if self._image_conv is None:
            from core.image_converter import ImageConverter
            self._image_conv = ImageConverter()
        return self._image_conv

    @property
    def doc_conv(self):
        if self._doc_conv is None:
            from core.doc_converter import DocumentConverter
            self._doc_conv = DocumentConverter()
        return self._doc_conv

    @property
    def video_compressor(self):
        if self._video_compressor is None:
            from core.video_compress import VideoCompressor
            self._video_compressor = VideoCompressor()
        return self._video_compressor

    # ── 偏好便捷读写（统一前缀）──────────────────
    def get_pref(self, key, default=None):
        return self.prefs.get(QT_PREFS_PANEL, key, default)

    def set_pref(self, key, value):
        self.prefs.set(QT_PREFS_PANEL, key, value)
        if key == "last_output_dir":
            self.last_output_dir = value

    # ── FFmpeg 状态 ──────────────────────────────
    def ffmpeg_ready(self) -> bool:
        return self.ffmpeg_mgr.is_available()

    def uptime_str(self) -> str:
        """运行时长文案（首页统计卡片用）。"""
        secs = int(time.time() - self.start_time)
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        if h > 0:
            return tr("{} 小时 {} 分", "{}h {}m").format(h, m)
        if m > 0:
            return tr("{} 分 {} 秒", "{}m {}s").format(m, s)
        return tr("{} 秒", "{}s").format(s)
