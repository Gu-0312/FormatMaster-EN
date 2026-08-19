"""frame_picker — 视频抽帧取景器（独立窗口）。

在预览播放器 + 时间轴播放头中定位任意时刻，点「导出此帧」
即把当前帧保存为图片；可连续导出多张（自动编号）。

复用 VideoPlayerWidget（可播放预览）与 TimelineTrackWidget（播放头）。
"""

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QSizePolicy,
                               QVBoxLayout, QWidget)
from qfluentwidgets import (CaptionLabel, FluentIcon, PrimaryPushButton,
                            PushButton, TransparentToolButton)

from gui_qt.components import design_system as ds
from gui_qt.components.video_preview import VideoPlayerWidget
from gui_qt.components.visual_widgets import TimelineTrackWidget
from gui_qt.i18n import tr


def _fmt(sec):
    s = max(0, int(sec))
    return f"{s // 60:02d}:{s % 60:02d}"


class FramePickerDialog(QDialog):
    """视频抽帧取景器：预览 + 时间轴定位 + 导出当前帧。

    确认/直接导出均不阻塞主流程；导出的图片路径通过 export_paths()
    返回（空列表表示未导出）。
    """

    def __init__(self, video_path, out_dir="", parent=None):
        super().__init__(parent)
        self._path = video_path or ""
        self._out_dir = out_dir or os.path.dirname(self._path) or "."
        self._exports = []      # 已导出的文件路径
        self._seq = 0           # 导出序号

        self.setWindowTitle(tr("视频抽帧取景器", "Frame Picker"))
        self.resize(960, 640)
        self.setMinimumSize(760, 520)
        self._tokens = ds.tokens()
        self._apply_theme_style()
        ds.bind_theme(self, self._refresh_theme)

        main = QVBoxLayout(self)
        main.setContentsMargins(14, 14, 14, 14)
        main.setSpacing(12)

        main.addLayout(self._build_top_bar())

        self.player = VideoPlayerWidget(self)
        self.player.setMinimumHeight(300)
        self.player.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main.addWidget(self.player, 1)

        main.addLayout(self._build_bottom())

        player = self.player.player
        player.durationChanged.connect(self._on_duration)
        player.positionChanged.connect(self._on_position)
        self.timeline.seek_requested.connect(
            lambda sec: player.setPosition(int(sec * 1000)))
        self.btn_play.clicked.connect(self.player.toggle_play)
        self.player.player.playbackStateChanged.connect(self._sync_play)
        self.btn_export.clicked.connect(self._export_current)
        self.btn_close.clicked.connect(self.accept)

        if os.path.isfile(self._path):
            self.player.audio_out.setVolume(0)
            self.player.set_source(self._path, autoplay=True)
        self._sync_play(self.player.player.playbackState())
        # 子控件全部就绪后按当前主题统一刷新
        self._apply_theme_style()

    # ── UI ──────────────────────────────────────
    def _build_top_bar(self):
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_play = PushButton(FluentIcon.PLAY, tr("播放", "Play"))
        self.btn_play.setFixedSize(88, 32)
        bar.addWidget(self.btn_play)
        self.lb_status = CaptionLabel(tr("拖动播放头定位，点「导出此帧」保存图片",
                                         "Drag playhead, then export frame"))
        bar.addWidget(self.lb_status)
        bar.addStretch(1)
        self.lb_top_time = CaptionLabel("--:-- / --:--")
        bar.addWidget(self.lb_top_time)
        return bar

    def _build_bottom(self):
        root = QVBoxLayout()
        root.setSpacing(8)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_export = PrimaryPushButton(
            FluentIcon.DOWNLOAD, tr("导出此帧", "Export Frame"))
        self.btn_export.setFixedHeight(32)
        bar.addWidget(self.btn_export)
        self.lb_dir = CaptionLabel(tr("输出到", "Output") + f"  {self._out_dir}")
        bar.addWidget(self.lb_dir, 1)
        self.btn_close = PushButton(tr("完成", "Done"))
        self.btn_close.setFixedHeight(32)
        bar.addWidget(self.btn_close)
        root.addLayout(bar)

        self.timeline = TimelineTrackWidget(self)
        self.timeline.setMinimumHeight(130)
        root.addWidget(self.timeline)
        return root

    def _apply_theme_style(self):
        """按当前主题应用对话框与子控件样式（返回 QSS 供 bind_theme 刷新）。"""
        t = self._tokens
        qss = f"""
            QDialog {{ background: {t['page_bg']}; }}
            PushButton {{
                background: {t['card_hover']}; color: {t['ink']};
                border: 1px solid {t['border']}; border-radius: 6px;
                padding: 5px 12px; font-size: 12px;
            }}
            PushButton:hover {{ background: {t['card_active']};
                border-color: {t['accent_soft']}; }}
            PrimaryPushButton {{
                background: {t['accent']}; color: #FFFFFF; border: none;
                border-radius: 6px; padding: 5px 14px; font-size: 12px;
                font-weight: 500;
            }}
            PrimaryPushButton:hover {{ background: {t['accent_hover']}; }}
            TransparentToolButton {{
                background: transparent; border: 1px solid {t['border']};
                border-radius: 6px;
            }}
            TransparentToolButton:hover {{ background: {t['card_hover']}; }}
        """
        self.setStyleSheet(qss)
        # 子控件样式（构造完成后才创建，用 hasattr 保护）
        if hasattr(self, "lb_status"):
            self.lb_status.setStyleSheet(
                f"font-size: 12px; color: {t['ink_sec']};"
                " background: transparent;")
        if hasattr(self, "lb_top_time"):
            self.lb_top_time.setStyleSheet(
                f"font-size: 13px; color: {t['ink']};"
                " font-family: Consolas; background: transparent;")
        if hasattr(self, "lb_dir"):
            self.lb_dir.setStyleSheet(
                f"font-size: 11px; color: {t['ink_dis']};"
                " background: transparent;")
        return qss

    def _refresh_theme(self):
        """主题切换时刷新颜色令牌与对话框样式。"""
        self._tokens = ds.tokens()
        return self._apply_theme_style()

    # ── 对外 ──
    def export_paths(self):
        return list(self._exports)

    # ── 联动 ──
    def _on_duration(self, ms):
        self.timeline.set_duration(ms / 1000.0)
        self._update_time()

    def _on_position(self, ms):
        self.timeline.set_playhead(ms / 1000.0)
        self._update_time()

    def _update_time(self):
        p = self.player.player
        self.lb_top_time.setText(
            f"{_fmt(p.position() / 1000)} / {_fmt(p.duration() / 1000)}")

    def _sync_play(self, state):
        if state == QMediaPlayer.PlayingState:
            self.btn_play.setIcon(FluentIcon.PAUSE)
            self.btn_play.setText(tr("暂停", "Pause"))
        else:
            self.btn_play.setIcon(FluentIcon.PLAY)
            self.btn_play.setText(tr("播放", "Play"))

    def _export_current(self):
        """导出播放头所在帧到输出目录。"""
        sec = self.player.player.position() / 1000.0
        if not self._path or not os.path.isfile(self._path):
            from gui_qt.components import toast
            toast.show_warning(self, tr("视频文件不存在", "Video missing"))
            return
        name = os.path.splitext(os.path.basename(self._path))[0]
        self._seq += 1
        out = os.path.join(self._out_dir,
                           f"{name}_帧{self._seq:02d}_{_fmt(sec)}.png")
        ok, msg = _export_single_frame(self._path, out, sec)
        from gui_qt.components import toast
        if ok:
            self._exports.append(out)
            toast.show_success(self, tr("已导出", "Exported") + f" {os.path.basename(out)}")
        else:
            toast.show_error(self, msg or tr("导出失败", "Export failed"))

    def done(self, r):
        self._release_media()
        super().done(r)

    def closeEvent(self, e):
        self._release_media()
        super().closeEvent(e)

    def _release_media(self):
        try:
            self.player.shutdown()
        except RuntimeError:
            pass


def _export_single_frame(video, out, sec):
    """用 FFmpeg 导出指定时间点的一帧；返回 (ok, msg)。"""
    import subprocess
    from utils.config import get_ffmpeg_path
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        return False, "FFmpeg 未就绪"
    try:
        result = subprocess.run(
            [ffmpeg, "-y", "-ss", f"{max(0.0, sec):.3f}", "-i", video,
             "-frames:v", "1", "-q:v", "2", out],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            creationflags=(subprocess.CREATE_NO_WINDOW
                           if os.name == "nt" else 0))
        if result.returncode == 0 and os.path.isfile(out):
            return True, ""
        return False, (result.stderr or b"").decode("utf-8", "replace")[-120:]
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
