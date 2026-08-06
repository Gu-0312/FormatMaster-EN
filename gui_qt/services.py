"""QtServices — Qt 层轻量服务容器。

对应 tkinter 版 app/context.py 的角色，但不依赖 tkinter：
集中持有转换器、FFmpeg 管理器、偏好与历史记录，供面板/页面注入使用。
依赖方向：gui_qt -> core/ + utils/，严格单向。
"""
from gui_qt.i18n import tr
import time

from core.audio_converter import AudioConverter
from core.doc_converter import DocumentConverter
from core.image_converter import ImageConverter
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
    """全局服务容器，主窗口创建一次后注入各页面/面板。"""

    def __init__(self):
        self.video_conv = VideoConverter()
        self.audio_conv = AudioConverter()
        self.image_conv = ImageConverter()
        self.doc_conv = DocumentConverter()
        self.ffmpeg_mgr = FFmpegManager()
        self.prefs = USER_PREFS
        self.history = CONV_HISTORY
        self.stats = _HistoryStats(self.history)
        self.start_time = time.time()
        # 上次使用的输出目录（与 tkinter 版 last_output_dir 语义一致）
        self.last_output_dir = self.prefs.get(QT_PREFS_PANEL, "last_output_dir", "")

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

    def get(self, key, default=None):
        """Generic service accessor used by pages and panels."""
        return {"stats": self.stats}.get(key, default)

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
