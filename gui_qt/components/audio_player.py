"""audio_player — 音频试听播放条（QMediaPlayer + QAudioOutput）。

应用内播放音频文件：播放/暂停/停止 + 文件名与状态显示。
用于音频处理/增强面板"改完直接试听"。
"""

import os

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, FluentIcon, TransparentToolButton

from gui_qt.components import design_system as ds
from gui_qt.i18n import tr


class AudioPlayerBar(QWidget):
    """音频试听条。

    方法：
        set_source(path, auto_play=True)  加载音频文件（默认自动播放）
        set_source_quiet(path)            仅加载不自动播放
        stop()                            停止播放
        source()                          当前文件路径
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path = ""

        self.player = QMediaPlayer(self)
        self.audio_out = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_out)
        self.audio_out.setVolume(0.8)

        h = QHBoxLayout(self)
        h.setContentsMargins(8, 6, 8, 6)
        h.setSpacing(8)

        self.btn_play = TransparentToolButton(FluentIcon.PLAY, self)
        self.btn_play.setToolTip(tr("播放 / 暂停", "Play / Pause"))
        self.btn_play.setFixedSize(32, 32)
        h.addWidget(self.btn_play)

        self.btn_stop = TransparentToolButton(FluentIcon.CANCEL, self)
        self.btn_stop.setToolTip(tr("停止", "Stop"))
        self.btn_stop.setFixedSize(28, 28)
        h.addWidget(self.btn_stop)

        self.status_label = CaptionLabel(
            tr("未加载音频", "No audio loaded"), self)
        self.status_label.setStyleSheet(
            f"font-size: 12px; background: transparent;")
        self.status_label.setWordWrap(False)
        h.addWidget(self.status_label, 1)

        self.btn_play.clicked.connect(self._toggle_play)
        self.btn_stop.clicked.connect(self.stop)
        self.player.playbackStateChanged.connect(self._on_state_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status)
        self.player.errorOccurred.connect(self._on_error)

        self.btn_play.setEnabled(False)
        self.btn_stop.setEnabled(False)

    # ── 对外接口 ──
    def set_source(self, path, auto_play=True):
        """加载音频文件；auto_play=True 时自动开始播放。"""
        self._path = path or ""
        if not self._path or not os.path.isfile(self._path):
            self.set_status(tr("未加载音频", "No audio loaded"))
            self.btn_play.setEnabled(False)
            self.btn_stop.setEnabled(False)
            return
        self.btn_play.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.player.setSource(QUrl.fromLocalFile(self._path))
        if auto_play:
            self.player.play()
            self.set_status(tr("播放中…", "Playing…"))
        else:
            self.set_status(tr("已加载：{}", "Loaded: {}").format(
                os.path.basename(self._path)))

    def set_source_quiet(self, path):
        self.set_source(path, auto_play=False)

    def stop(self):
        self.player.stop()

    def source(self):
        return self._path

    def set_status(self, text):
        self.status_label.setText(text)

    # ── 内部 ──
    def _toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _on_state_changed(self, state):
        if state == QMediaPlayer.PlayingState:
            self.btn_play.setIcon(FluentIcon.PAUSE)
            self.set_status(tr("播放中", "Playing"))
        elif state == QMediaPlayer.PausedState:
            self.btn_play.setIcon(FluentIcon.PLAY)
            self.set_status(tr("已暂停", "Paused"))
        else:
            self.btn_play.setIcon(FluentIcon.PLAY)

    def _on_media_status(self, status):
        if status == QMediaPlayer.EndOfMedia:
            self.btn_play.setIcon(FluentIcon.PLAY)
            self.player.setPosition(0)
            self.set_status(tr("播放结束", "Finished"))

    def _on_error(self, *_args):
        self.set_status(tr("无法播放该音频", "Cannot play this audio"))
        self.btn_play.setEnabled(False)
