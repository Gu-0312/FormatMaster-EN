"""video_preview — 视频帧预览 / 视频播放预览组件（自适应窗口大小）。

- VideoPreviewWidget：显示静态帧，随组件/窗口尺寸等比缩放居中
- VideoPlayerWidget：可播放视频（QMediaPlayer），支持实时倍速与进度控制，
  画面等比显示适配当前屏幕窗口。
"""

import os

from PySide6.QtCore import Qt, QRectF, QTimer, QUrl
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QSizePolicy, QWidget
from qfluentwidgets import FluentIcon


# 播放器错误码 → 可读文案
_MEDIA_ERROR_TEXT = {
    QMediaPlayer.NoError: "",
    QMediaPlayer.ResourceError: "无法读取视频文件或资源错误",
    QMediaPlayer.FormatError: "视频格式/编码不支持",
    QMediaPlayer.NetworkError: "网络错误",
    QMediaPlayer.AccessDeniedError: "没有权限访问该视频",
}

from gui_qt.components import design_system as ds


class VideoPreviewWidget(QWidget):
    """视频帧预览。

    方法：
        set_pixmap(pm)   设置帧画面（QPixmap）；高度自动按宽高比跟随宽度
        clear()          清空显示空状态
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pm = QPixmap()
        self._hint = ""
        self.setMinimumHeight(120)

    def set_hint(self, text):
        """设置空状态提示文案。"""
        self._hint = text or ""
        self.update()

    def set_pixmap(self, pm):
        self._pm = pm if pm and not pm.isNull() else QPixmap()
        self._fit_height()
        self.update()

    def clear(self):
        self._pm = QPixmap()
        self.update()

    def has_frame(self):
        return not self._pm.isNull()

    def _fit_height(self):
        """高度 = 宽度 × 宽高比，限幅 [120, 320]，实现随窗口自适应。"""
        if self._pm.isNull():
            return
        w = max(self.width(), 100)
        ratio = self._pm.height() / max(self._pm.width(), 1)
        h = max(120, min(320, int(w * ratio)))
        if self.height() != h:
            self.setFixedHeight(h)
            self.resize(self.width(), h)  # 立即应用（setFixedHeight 只改约束）

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # 窗口/侧边栏变化后重新适配高度
        self._fit_height()
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(QPen(QColor(ds.border_color()), 0.5))
        p.setBrush(QColor(ds.card_bg()))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 8, 8)
        if self._pm.isNull():
            p.setPen(QPen(QColor(ds.ink_dis()), 0))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter,
                       self._hint or "选择视频后显示画面预览")
            p.end()
            return
        # 等比缩放居中（不拉伸变形，留白用背景色）
        scaled = self._pm.scaled(w - 8, h - 8, Qt.KeepAspectRatio,
                                 Qt.SmoothTransformation)
        x = (w - scaled.width()) / 2
        y = (h - scaled.height()) / 2
        p.drawPixmap(QRectF(x, y, scaled.width(), scaled.height()),
                     scaled, QRectF(0, 0, scaled.width(), scaled.height()))
        p.end()


class _VideoSurface(QWidget):
    """视频画面显示面：当前帧等比缩放居中绘制（支持实时滤镜输出）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pm = QPixmap()
        self._hint = ""
        self.setMinimumHeight(140)

    def set_hint(self, text):
        self._hint = text or ""
        self.update()

    def set_frame(self, pm):
        self._pm = pm if pm and not pm.isNull() else QPixmap()
        self.update()

    def clear(self):
        self._pm = QPixmap()
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(QPen(QColor(ds.border_color()), 0.5))
        p.setBrush(QColor(ds.card_bg()))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 8, 8)
        if self._pm.isNull():
            p.setPen(QPen(QColor(ds.ink_dis()), 0))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter,
                       self._hint or "正在加载视频…")
            p.end()
            return
        scaled = self._pm.scaled(w - 8, h - 8, Qt.KeepAspectRatio,
                                 Qt.SmoothTransformation)
        x = (w - scaled.width()) / 2
        y = (h - scaled.height()) / 2
        p.drawPixmap(QRectF(x, y, scaled.width(), scaled.height()),
                     scaled, QRectF(0, 0, scaled.width(), scaled.height()))
        p.end()


# ─────────────────────────────────────────────────────
#  VideoPlayerWidget — 可播放的视频预览（实时调速 + 实时滤镜）
# ─────────────────────────────────────────────────────
class VideoPlayerWidget(QWidget):
    """视频预览播放器：播放/暂停/停止 + 进度拖动 + 时间显示 + 实时倍速。

    视频输出走 QVideoSink 逐帧管线（numpy 实时应用变换/调整滤镜），
    因此无需原生窗口也能渲染，且支持实时旋转/翻转/亮度/对比度/饱和度。

    方法：
        set_source(path, autoplay=False)  加载视频
        set_playback_rate(rate)           实时调速（0.5 / 1.0 / 1.5 …）
        set_effects(...)                  实时设置变换/调整滤镜
        toggle_play() / play() / pause() / stop()
        is_loaded()
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        import numpy as np  # noqa: F401  确保 numpy 可用
        from PySide6.QtMultimedia import QVideoSink
        from PySide6.QtWidgets import QHBoxLayout, QSlider, QVBoxLayout
        from qfluentwidgets import CaptionLabel, TransparentToolButton

        self._path = ""
        self._rate = 1.0
        self._effects = {"rotate": 0, "hflip": False, "vflip": False,
                         "brightness": 0.0, "contrast": 1.0, "saturation": 1.0}
        self._latest = None       # 最新一帧 QImage（媒体线程写入）
        self._last_img = None     # 已渲染帧（引用比较去重）
        self._last_sig = None     # 已渲染帧对应的滤镜参数签名

        self.player = QMediaPlayer(self)
        self.audio_out = QAudioOutput(self)
        self.audio_out.setVolume(0.8)
        self.player.setAudioOutput(self.audio_out)

        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)

        # 画面显示面（QPainter 绘制，无需原生窗口）
        self.video_view = _VideoSurface(self)
        self.video_view.setSizePolicy(QSizePolicy.Expanding,
                                      QSizePolicy.Expanding)
        v.addWidget(self.video_view, 1)

        # 逐帧管线：QVideoSink → numpy 滤镜 → 画面
        self._sink = QVideoSink(self)
        self.player.setVideoOutput(self._sink)
        self._sink.videoFrameChanged.connect(self._on_frame)
        self._frame_timer = QTimer(self)
        self._frame_timer.setInterval(33)  # ~30fps 节流 UI 刷新
        self._frame_timer.timeout.connect(self._flush_frame)

        # 控制条
        ctrl = QHBoxLayout()
        ctrl.setSpacing(6)
        self.btn_play = TransparentToolButton(FluentIcon.PLAY, self)
        self.btn_play.setToolTip("播放 / 暂停")
        self.btn_play.setFixedSize(30, 30)
        self.btn_stop = TransparentToolButton(FluentIcon.CANCEL, self)
        self.btn_stop.setToolTip("停止")
        self.btn_stop.setFixedSize(26, 26)
        ctrl.addWidget(self.btn_play)
        ctrl.addWidget(self.btn_stop)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setFixedHeight(22)
        ctrl.addWidget(self.slider, 1)

        self.lb_time = CaptionLabel("--:-- / --:--", self)
        self.lb_time.setStyleSheet(
            f"font-size: 11px; color: {ds.ink_sec()}; background: transparent;")
        ctrl.addWidget(self.lb_time)
        self.lb_rate = CaptionLabel("", self)
        self.lb_rate.setStyleSheet(
            f"font-size: 11px; color: {ds.accent()}; background: transparent;")
        ctrl.addWidget(self.lb_rate)
        v.addLayout(ctrl)

        self.btn_play.clicked.connect(self._toggle_play)
        self.btn_stop.clicked.connect(self.stop)
        self.slider.sliderMoved.connect(self._seek)
        self.player.playbackStateChanged.connect(self._on_state)
        self.player.positionChanged.connect(self._on_pos)
        self.player.durationChanged.connect(self._on_dur)
        self.player.mediaStatusChanged.connect(self._on_status)
        self.player.errorOccurred.connect(self._on_error)

        self.btn_play.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.slider.setEnabled(False)

    # ── 对外接口 ──
    def set_source(self, path, autoplay=False):
        """加载视频文件；autoplay=True 自动播放。"""
        self._path = path or ""
        if not self._path or not os.path.isfile(self._path):
            self._reset_controls()
            return
        self.player.stop()
        self._latest = None
        self._last_img = None
        self._last_sig = None
        self.player.setSource(QUrl.fromLocalFile(self._path))
        self.btn_play.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.slider.setEnabled(True)
        self.lb_rate.setText("")
        if autoplay:
            self.player.play()
        else:
            self.player.play()
            QTimer.singleShot(120, self.player.pause)

    def set_playback_rate(self, rate):
        """实时调整播放倍速（处理设置联动）。"""
        try:
            self._rate = max(0.25, min(8.0, float(rate)))
        except (TypeError, ValueError):
            self._rate = 1.0
        self.player.setPlaybackRate(self._rate)
        self.lb_rate.setText(f"{self._rate:g}x")

    def set_effects(self, rotate=0, hflip=False, vflip=False,
                    brightness=0.0, contrast=1.0, saturation=1.0):
        """实时设置变换/调整滤镜（签名去重，不闪屏不重置）。"""
        self._effects = {
            "rotate": int(rotate or 0) % 360,
            "hflip": bool(hflip),
            "vflip": bool(vflip),
            "brightness": float(brightness),
            "contrast": float(contrast),
            "saturation": float(saturation),
        }
        if not self._frame_timer.isActive():
            self._frame_timer.start()
        self._flush_frame()

    def stop(self):
        self.player.stop()
        self.slider.setValue(0)
        self.lb_time.setText("--:-- / --:--")

    def play(self):
        self.player.play()

    def pause(self):
        self.player.pause()

    def toggle_play(self):
        self._toggle_play()

    def is_loaded(self):
        return bool(self._path) and os.path.isfile(self._path)

    def shutdown(self):
        """关闭时释放媒体资源：停节流器、停止播放、清空媒体源与声音。"""
        self._frame_timer.stop()
        self._latest = None
        self._last_img = None
        self._last_sig = None
        try:
            self.player.stop()
            self.player.setSource(QUrl())   # 释放媒体后端
            self.audio_out.setVolume(0)
        except RuntimeError:
            pass  # 控件可能已被销毁

    # ── 帧管线 ──
    def _on_frame(self, frame):
        """QVideoSink 每帧回调（信号自动排队到 UI 线程）。"""
        if not frame.isValid():
            return
        img = frame.toImage()
        if img.isNull():
            return
        self._latest = img
        if not self._frame_timer.isActive():
            self._frame_timer.start()

    def _flush_frame(self):
        """节流处理最新一帧；帧或滤镜参数变化才重绘（不闪屏不重置）。"""
        img = self._latest
        if img is None:
            return
        e = self._effects
        sig = (e["rotate"], e["hflip"], e["vflip"],
               e["brightness"], e["contrast"], e["saturation"])
        if img is self._last_img and sig == self._last_sig:
            return
        self._last_img = img
        self._last_sig = sig
        self.video_view.set_frame(QPixmap.fromImage(self._process(img)))

    def _process(self, img):
        """QImage → numpy → 旋转/翻转/亮度/对比度/饱和度 → QImage。"""
        import numpy as np
        e = self._effects
        need = (e["rotate"] or e["hflip"] or e["vflip"]
                or e["brightness"] != 0.0 or e["contrast"] != 1.0
                or e["saturation"] != 1.0)
        if not need:
            return img
        # 限制处理分辨率，保证实时
        if img.width() > 1280:
            img = img.scaledToWidth(1280, Qt.SmoothTransformation)
        img = img.convertToFormat(QImage.Format_RGBA8888)
        w, h = img.width(), img.height()
        buf = img.bits()
        arr = np.frombuffer(buf, np.uint8,
                            count=h * img.bytesPerLine()).reshape(
            h, img.bytesPerLine())
        arr = arr[:, :w * 4].reshape(h, w, 4)
        rgb = arr[..., :3]

        # 亮度/对比度/饱和度（LUT 加速）
        b, c, s = e["brightness"], e["contrast"], e["saturation"]
        if b or c != 1.0 or s != 1.0:
            lut = np.arange(256, dtype=np.float32)
            lut = np.clip((lut - 128.0) * c + 128.0 + b * 255.0, 0, 255)
            if s != 1.0:
                gray = rgb.mean(axis=2, keepdims=True)
                out = gray + (rgb.astype(np.float32) - gray) * s
                rgb = np.clip(out, 0, 255).astype(np.uint8)
                rgb = lut[rgb].astype(np.uint8)
            else:
                rgb = lut[rgb].astype(np.uint8)

        # 旋转 / 翻转
        rot = e["rotate"]
        if rot == 90:
            rgb = np.rot90(rgb, -1)      # 顺时针 90°
        elif rot == 180:
            rgb = np.rot90(rgb, 2)
        elif rot == 270:
            rgb = np.rot90(rgb, 1)       # 顺时针 270°
        if e["hflip"]:
            rgb = rgb[:, ::-1]
        if e["vflip"]:
            rgb = rgb[::-1, :]

        rgb = np.ascontiguousarray(rgb)
        h2, w2 = rgb.shape[:2]
        out = QImage(rgb.data, w2, h2, rgb.strides[0],
                     QImage.Format_RGB888).copy()
        return out

    # ── 内部 ──
    def _reset_controls(self):
        self.btn_play.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.slider.setEnabled(False)
        self.slider.setValue(0)
        self.lb_time.setText("--:-- / --:--")

    def _toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _seek(self, v):
        dur = self.player.duration()
        if dur > 0:
            self.player.setPosition(int(dur * v / 1000))

    def _fmt(self, ms):
        s = max(0, int(ms / 1000))
        return f"{s // 60:02d}:{s % 60:02d}"

    def _on_state(self, state):
        if state == QMediaPlayer.PlayingState:
            self.btn_play.setIcon(FluentIcon.PAUSE)
        else:
            self.btn_play.setIcon(FluentIcon.PLAY)

    def _on_pos(self, ms):
        dur = self.player.duration()
        if dur > 0:
            self.slider.setValue(int(ms / dur * 1000))
            self.lb_time.setText(f"{self._fmt(ms)} / {self._fmt(dur)}")

    def _on_dur(self, ms):
        if ms > 0:
            self.lb_time.setText(f"00:00 / {self._fmt(ms)}")

    def _on_status(self, status):
        if status == QMediaPlayer.EndOfMedia:
            self.btn_play.setIcon(FluentIcon.PLAY)
            self.player.setPosition(0)
            self.slider.setValue(0)

    def _on_error(self, error, errorString):
        self._reset_controls()
        text = _MEDIA_ERROR_TEXT.get(error, errorString or "无法播放")
        self.lb_rate.setText(text)
        self.lb_rate.setStyleSheet(
            f"font-size: 11px; color: #FF6B6B; background: transparent;")
