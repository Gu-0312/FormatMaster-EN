"""audio_editor — 音频波形编辑器（独立窗口）。

波形可视化 + 播放头 + 入/出点游标 + 点击定位，确认后回填主面板起止时间。

复用 core.audio_trimmer.get_waveform_data / get_audio_duration 读取波形。
"""

import os

from PySide6.QtCore import Qt, QRectF, QUrl, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QSizePolicy, QSlider,
                               QVBoxLayout, QWidget)
from qfluentwidgets import (CaptionLabel, FluentIcon, PrimaryPushButton,
                            PushButton)

from gui_qt.components import design_system as ds
from gui_qt.i18n import tr


def _fmt(sec):
    s = max(0, int(sec))
    return f"{s // 60:02d}:{s % 60:02d}"


class WaveformView(QWidget):
    """波形条 + 播放头 + 入/出点游标 + 点击定位。"""

    clicked = Signal(float)  # 点击位置（秒）

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = []
        self.duration = 0.0
        self.playhead = 0.0
        self.in_sec = 0.0
        self.out_sec = 0.0
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_wave(self, data, duration):
        self.data = list(data or [])
        self.duration = float(duration or 0.0)
        self.out_sec = self.duration
        self.update()

    def set_playhead(self, sec):
        self.playhead = max(0.0, float(sec))
        self.update()

    def set_range(self, in_sec, out_sec):
        self.in_sec = max(0.0, float(in_sec))
        self.out_sec = max(self.in_sec, float(out_sec))
        self.update()

    def range(self):
        return (self.in_sec, self.out_sec)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        mid = h // 2
        p.setPen(QPen(QColor(ds.border_color()), 0.5))
        p.setBrush(QColor(ds.card_bg()))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 8, 8)

        if not self.data or self.duration <= 0:
            p.setPen(QPen(QColor(ds.ink_dis()), 0))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter,
                       tr("正在读取波形…", "Loading waveform…"))
            p.end()
            return

        # 区间外遮罩
        if self.out_sec > self.in_sec:
            x1 = int(self.in_sec / self.duration * w)
            x2 = int(self.out_sec / self.duration * w)
            mask = QColor(8, 10, 18, 120)
            p.fillRect(QRectF(0, 0, x1, h), mask)
            p.fillRect(QRectF(x2, 0, w - x2, h), mask)

        # 波形条
        n = len(self.data)
        bar_w = max(1.0, w / n)
        pen = QPen(QColor(96, 140, 255), max(1, int(bar_w)))
        p.setPen(pen)
        for i, val in enumerate(self.data):
            x = int(i * bar_w)
            bar_h = max(1, int(val * (mid - 8)))
            p.drawLine(x, mid - bar_h, x, mid + bar_h)

        # 入/出点
        p.setPen(QPen(QColor(80, 200, 120), 2))
        p.drawLine(int(self.in_sec / self.duration * w), 0,
                   int(self.in_sec / self.duration * w), h)
        p.setPen(QPen(QColor(230, 90, 90), 2))
        p.drawLine(int(self.out_sec / self.duration * w), 0,
                   int(self.out_sec / self.duration * w), h)

        # 播放头
        px = int(self.playhead / self.duration * w)
        p.setPen(QPen(QColor(255, 170, 60), 2))
        p.drawLine(px, 0, px, h)
        p.end()

    def mousePressEvent(self, e):
        if self.duration <= 0 or e.button() != Qt.LeftButton:
            return
        sec = max(0.0, min(e.position().x() / max(self.width(), 1)
                           * self.duration, self.duration))
        self.clicked.emit(round(sec, 3))


class WaveformEditorDialog(QDialog):
    """音频波形编辑器：波形 + 播放 + 入出点。

    属性（确认后有效）：
        start_sec / end_sec
    方法：
        clip_range()  返回 (start_sec, end_sec)
    """

    def __init__(self, audio_path, start=0.0, end=None, parent=None):
        super().__init__(parent)
        self._path = audio_path or ""
        self._in_sec = float(start or 0)
        self._out_sec = float(end) if end is not None else None

        self.setWindowTitle(tr("音频波形编辑器", "Audio Waveform Editor"))
        self.resize(900, 520)
        self.setMinimumSize(720, 420)
        self._tokens = ds.tokens()
        self._apply_theme_style()
        ds.bind_theme(self, self._refresh_theme)

        main = QVBoxLayout(self)
        main.setContentsMargins(14, 14, 14, 14)
        main.setSpacing(12)

        main.addLayout(self._build_top_bar())

        # 波形
        self.wave = WaveformView(self)
        main.addWidget(self.wave, 1)

        # 进度条
        bar = QHBoxLayout()
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setFixedHeight(22)
        self.slider.sliderMoved.connect(self._seek)
        bar.addWidget(self.slider)
        main.addLayout(bar)

        main.addLayout(self._build_bottom())

        # 播放器（音频）
        self.player = QMediaPlayer(self)
        self.audio_out = QAudioOutput(self)
        self.audio_out.setVolume(0.8)
        self.player.setAudioOutput(self.audio_out)
        self.player.durationChanged.connect(self._on_duration)
        self.player.positionChanged.connect(self._on_position)
        self.player.playbackStateChanged.connect(self._sync_play)
        self.player.errorOccurred.connect(self._on_error)

        self.wave.clicked.connect(
            lambda sec: self.player.setPosition(int(sec * 1000)))
        self.btn_play.clicked.connect(self._toggle_play)
        self.btn_set_in.clicked.connect(self._set_in)
        self.btn_set_out.clicked.connect(self._set_out)
        self.btn_go_in.clicked.connect(
            lambda: self.player.setPosition(int(self._in_sec * 1000)))
        self.btn_go_out.clicked.connect(
            lambda: self.player.setPosition(int(self._out_sec * 1000)))
        self.btn_reset.clicked.connect(self._reset)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self.accept)

        if os.path.isfile(self._path):
            self.player.setSource(QUrl.fromLocalFile(self._path))
            self._load_waveform()
        self._refresh_labels()
        # 子控件全部就绪后按当前主题统一刷新
        self._apply_theme_style()

    # ── UI ──────────────────────────────────────
    def _build_top_bar(self):
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_play = PushButton(FluentIcon.PLAY, tr("播放", "Play"))
        self.btn_play.setFixedSize(88, 32)
        bar.addWidget(self.btn_play)
        self.lb_status = CaptionLabel(tr("点击波形定位，设置入/出点",
                                         "Click waveform to seek, set in/out"))
        bar.addWidget(self.lb_status)
        bar.addStretch(1)
        self.lb_time = CaptionLabel("--:-- / --:--")
        bar.addWidget(self.lb_time)
        return bar

    def _build_bottom(self):
        root = QVBoxLayout()
        root.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_set_in = PushButton(FluentIcon.PIN, tr("设置入点", "Set In"))
        self.btn_set_out = PushButton(FluentIcon.PIN, tr("设置出点", "Set Out"))
        self.btn_go_in = PushButton(FluentIcon.LEFT_ARROW, tr("跳转入点", "Go In"))
        self.btn_go_out = PushButton(FluentIcon.RIGHT_ARROW, tr("跳转出点", "Go Out"))
        self.btn_reset = PushButton(FluentIcon.CANCEL, tr("重置区间", "Reset"))
        for b in (self.btn_set_in, self.btn_set_out, self.btn_go_in,
                  self.btn_go_out, self.btn_reset):
            b.setFixedHeight(30)
            row.addWidget(b)
        row.addStretch(1)
        self.lb_in = CaptionLabel("")
        self.lb_out = CaptionLabel("")
        row.addWidget(self.lb_in)
        row.addWidget(self.lb_out)
        root.addLayout(row)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = PushButton(tr("取消", "Cancel"))
        self.btn_cancel.setFixedHeight(34)
        self.btn_ok = PrimaryPushButton(
            FluentIcon.PLAY_SOLID, tr("开始转换", "Start Converting"))
        self.btn_ok.setFixedHeight(34)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)
        root.addLayout(btns)
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
            QSlider::groove:horizontal {{ height: 4px;
                background: {t['card_active']}; border-radius: 2px; }}
            QSlider::handle:horizontal {{ width: 12px; height: 12px;
                margin: -4px 0; border-radius: 6px;
                background: {t['accent']}; }}
        """
        self.setStyleSheet(qss)
        # 子控件样式（构造完成后才创建，用 hasattr 保护）
        if hasattr(self, "lb_status"):
            self.lb_status.setStyleSheet(
                f"font-size: 12px; color: {t['ink_sec']};"
                " background: transparent;")
        if hasattr(self, "lb_time"):
            self.lb_time.setStyleSheet(
                f"font-size: 13px; color: {t['ink']};"
                " font-family: Consolas; background: transparent;")
        for name in ("lb_in", "lb_out"):
            lb = getattr(self, name, None)
            if lb is not None:
                lb.setStyleSheet(
                    f"font-size: 12px; color: {t['ink_sec']};"
                    " background: transparent;")
        return qss

    def _refresh_theme(self):
        """主题切换时刷新颜色令牌与对话框样式。"""
        self._tokens = ds.tokens()
        return self._apply_theme_style()

    # ── 波形加载 ──
    def _load_waveform(self):
        from core.audio_trimmer import get_audio_duration, get_waveform_data
        try:
            duration = get_audio_duration(self._path) or 0.0
        except Exception:
            duration = 0.0
        try:
            data = get_waveform_data(self._path, 600)
        except Exception:
            data = []
        self.wave.set_wave(data, duration)
        if duration > 0:
            if self._out_sec is None or self._out_sec <= 0 or self._out_sec > duration:
                self._out_sec = duration
            self.wave.set_range(self._in_sec, self._out_sec)
            self.slider.setEnabled(True)
        self._refresh_labels()

    # ── 对外 ──
    def clip_range(self):
        return (self._in_sec, self._out_sec)

    # ── 播放联动 ──
    def _on_duration(self, ms):
        if ms > 0 and self.wave.duration <= 0:
            self.wave.set_wave(self.wave.data, ms / 1000.0)
            if self._out_sec is None or self._out_sec <= 0:
                self._out_sec = ms / 1000.0
            self.wave.set_range(self._in_sec, self._out_sec)
        self._update_time()

    def _on_position(self, ms):
        sec = ms / 1000.0
        self.wave.set_playhead(sec)
        dur = self.player.duration()
        if dur > 0:
            self.slider.setValue(int(sec / (dur / 1000.0) * 1000))
        self._update_time()

    def _update_time(self):
        p = self.player
        self.lb_time.setText(
            f"{_fmt(p.position() / 1000)} / {_fmt(p.duration() / 1000)}")

    def _sync_play(self, state):
        if state == QMediaPlayer.PlayingState:
            self.btn_play.setIcon(FluentIcon.PAUSE)
            self.btn_play.setText(tr("暂停", "Pause"))
        else:
            self.btn_play.setIcon(FluentIcon.PLAY)
            self.btn_play.setText(tr("播放", "Play"))

    def _toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _seek(self, v):
        dur = self.player.duration()
        if dur > 0:
            self.player.setPosition(int(dur * v / 1000))

    def _set_in(self):
        self._in_sec = self.player.position() / 1000.0
        self.wave.set_range(self._in_sec, self._out_sec)
        self._refresh_labels()

    def _set_out(self):
        sec = self.player.position() / 1000.0
        if sec > self._in_sec:
            self._out_sec = sec
            self.wave.set_range(self._in_sec, self._out_sec)
            self._refresh_labels()

    def _reset(self):
        self._in_sec = 0.0
        self._out_sec = self.wave.duration or 0.0
        self.wave.set_range(self._in_sec, self._out_sec)
        self.player.setPosition(0)
        self._refresh_labels()

    def _refresh_labels(self):
        self.lb_in.setText(tr("入点", "In") + f"  {_fmt(self._in_sec)}")
        self.lb_out.setText(tr("出点", "Out") + f"  {_fmt(self._out_sec)}")

    def _on_error(self, error, errorString):
        self.lb_status.setText(
            tr("播放错误", "Playback error") + f": {errorString or error}")
        self.lb_status.setStyleSheet(
            "font-size: 12px; color: #FF6B6B; background: transparent;")

    def done(self, r):
        self._release_media()
        super().done(r)

    def closeEvent(self, e):
        self._release_media()
        super().closeEvent(e)

    def _release_media(self):
        try:
            self.player.stop()
            self.player.setSource(QUrl())
            self.audio_out.setVolume(0)
        except RuntimeError:
            pass
