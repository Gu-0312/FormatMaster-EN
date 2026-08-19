# -*- coding: utf-8 -*-
"""gif_filmstrip — 视频转 GIF 胶片视图（独立窗口）。

预览播放 + 胶片条（按时间均匀抽帧缩略图）+ in/out 游标：
拖动 in/out 游标或播放头即可选定要转成 GIF 的时间段；
点「应用此区间」把 (起点, 时长) 回填到 GIF 面板。

复用 VideoPlayerWidget（预览）与 TimelineTrackWidget（胶片条）。
"""
import os
import tempfile

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QSizePolicy,
                               QVBoxLayout)
from qfluentwidgets import (CaptionLabel, FluentIcon, PrimaryPushButton,
                            PushButton)

from core.video_frame_extract import duration_of, extract_strip_frames
from gui_qt.components import design_system as ds
from gui_qt.components.video_preview import VideoPlayerWidget
from gui_qt.components.visual_widgets import TimelineTrackWidget
from gui_qt.i18n import tr


def _fmt(sec):
    sec = max(0.0, float(sec or 0))
    return f"{int(sec // 60):02d}:{int(sec % 60):02d}"


class GifFilmstripDialog(QDialog):
    """GIF 胶片视图：预览 + 胶片条选区间。

    确认后通过 range_secs() 返回 (start, end)；取消返回 None。
    缩略图在后台线程生成（不阻塞弹窗打开）。
    """

    def __init__(self, video_path, parent=None):
        super().__init__(parent)
        self._path = video_path or ""
        self._range = None          # (start, end) 确认结果
        self._tmpdir = tempfile.mkdtemp(prefix="fm_strip_")
        self._thumb_jobs = set()    # 保活后台线程

        self.setWindowTitle(tr("GIF 胶片视图 · 选择时间段",
                               "GIF Filmstrip · pick a range"))
        self.resize(920, 640)
        self.setMinimumSize(760, 520)
        self._tokens = ds.tokens()
        self._apply_theme_style()
        ds.bind_theme(self, self._refresh_theme)

        main = QVBoxLayout(self)
        main.setContentsMargins(14, 14, 14, 14)
        main.setSpacing(12)
        main.addLayout(self._build_top_bar())
        main.addWidget(self._build_player(), 1)
        main.addLayout(self._build_bottom())

        player = self.player.player
        player.durationChanged.connect(self._on_duration)
        player.positionChanged.connect(self._on_position)
        self.timeline.in_changed.connect(self._on_in_changed)
        self.timeline.out_changed.connect(self._on_out_changed)
        self.timeline.seek_requested.connect(
            lambda sec: player.setPosition(int(sec * 1000)))
        self.btn_play.clicked.connect(self.player.toggle_play)
        self.player.player.playbackStateChanged.connect(self._sync_play)
        self.btn_apply.clicked.connect(self._apply)
        self.btn_cancel.clicked.connect(self.reject)

        if os.path.isfile(self._path):
            self.player.audio_out.setVolume(0)
            self.player.set_source(self._path, autoplay=True)
            self._load_thumbnails()
        self._sync_play(self.player.player.playbackState())
        self._apply_theme_style()

    # ── UI ──────────────────────────────────────
    def _build_top_bar(self):
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_play = PushButton(FluentIcon.PLAY, tr("播放", "Play"))
        self.btn_play.setFixedSize(88, 32)
        bar.addWidget(self.btn_play)
        self.lb_status = CaptionLabel(
            tr("拖动 in/out 游标选定区间，或点轨道跳转",
               "Drag in/out handles to pick a range, or click the track"))
        bar.addWidget(self.lb_status)
        bar.addStretch(1)
        self.lb_time = CaptionLabel("--:-- / --:--")
        bar.addWidget(self.lb_time)
        return bar

    def _build_player(self):
        self.player = VideoPlayerWidget(self)
        self.player.setMinimumHeight(280)
        self.player.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return self.player

    def _build_bottom(self):
        root = QVBoxLayout()
        root.setSpacing(8)
        self.timeline = TimelineTrackWidget(self)
        self.timeline.setMinimumHeight(130)
        root.addWidget(self.timeline)
        # superqt 双滑块：与 in/out 游标双向同步
        from gui_qt.components.range_slider_row import RangeSliderRow
        self.range_slider = RangeSliderRow(self)
        self.range_slider.setMinimumHeight(30)
        if self.range_slider.available():
            self.range_slider.valueChanged.connect(self._on_slider_range)
        root.addWidget(self.range_slider)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.lb_range = CaptionLabel("--:-- — --:--")
        bar.addWidget(self.lb_range)
        bar.addStretch(1)
        self.btn_apply = PrimaryPushButton(
            FluentIcon.ACCEPT, tr("应用此区间", "Apply range"))
        self.btn_apply.setFixedHeight(32)
        bar.addWidget(self.btn_apply)
        self.btn_cancel = PushButton(tr("取消", "Cancel"))
        self.btn_cancel.setFixedHeight(32)
        bar.addWidget(self.btn_cancel)
        root.addLayout(bar)
        return root

    # ── 缩略图（后台线程）────────────────────────
    def _load_thumbnails(self):
        import threading
        path, tmpdir = self._path, self._tmpdir
        dur = duration_of(path)

        def _gen():
            try:
                ok, count = extract_strip_frames(path, tmpdir, 12)
                if not ok:
                    return
                items = []
                for i in range(count):
                    fp = os.path.join(tmpdir, f"strip_{i:03d}.jpg")
                    if os.path.isfile(fp):
                        pm = QPixmap(fp)
                        items.append((dur * i / max(count - 1, 1), pm))
                QTimer.singleShot(0, lambda: self._set_thumbs(items))
            except Exception:  # noqa: BLE001
                pass

        t = threading.Thread(target=_gen, daemon=True)
        self._thumb_jobs.add(t)
        t.start()

    def _set_thumbs(self, items):
        self._thumb_jobs.clear()
        self.timeline.set_thumbnails(items)

    # ── 联动 ────────────────────────────────────
    def _on_duration(self, ms):
        sec = ms / 1000.0
        self.timeline.set_duration(sec)
        if self.range_slider.available():
            self.range_slider.set_range(0, max(1, sec))
        self._update_time()
        self._update_range_label()

    def _on_slider_range(self, start, end):
        """双滑块拖动 → 同步游标 + 播放头。"""
        self.timeline.set_range(start, end)
        self._update_range_label()

    def _on_position(self, ms):
        self.timeline.set_playhead(ms / 1000.0)
        self._update_time()

    def _on_in_changed(self, sec):
        self._sync_slider()
        self._update_range_label()

    def _on_out_changed(self, sec):
        self._sync_slider()
        self._update_range_label()

    def _sync_slider(self):
        """游标拖动 → 双滑块跟随（blockSignals 防回环）。"""
        if not self.range_slider.available():
            return
        ins, outs = self.timeline.range()
        self.range_slider.set_values(ins, outs)

    def _update_time(self):
        p = self.player.player
        self.lb_time.setText(
            f"{_fmt(p.position() / 1000)} / {_fmt(p.duration() / 1000)}")

    def _update_range_label(self):
        ins, outs = self.timeline.range()
        self.lb_range.setText(
            tr("区间：{} — {}（时长 {}s）", "Range: {} — {} ({}s)")
            .format(_fmt(ins), _fmt(outs), round(max(0.0, outs - ins), 1)))

    def _sync_play(self, state):
        if state == QMediaPlayer.PlayingState:
            self.btn_play.setIcon(FluentIcon.PAUSE)
            self.btn_play.setText(tr("暂停", "Pause"))
        else:
            self.btn_play.setIcon(FluentIcon.PLAY)
            self.btn_play.setText(tr("播放", "Play"))

    # ── 确认 ────────────────────────────────────
    def _apply(self):
        ins, outs = self.timeline.range()
        if outs - ins < 0.2:
            from gui_qt.components import toast
            toast.show_warning(self, tr("区间太短，请重新选择",
                                        "Range too short, pick again"))
            return
        self._range = (round(ins, 2), round(outs, 2))
        self.accept()

    def range_secs(self):
        """返回 (start, end) 秒；未确认返回 None。"""
        return self._range

    def done(self, r):
        self._release_media()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        super().done(r)

    def closeEvent(self, e):
        self._release_media()
        super().closeEvent(e)

    def _release_media(self):
        try:
            self.player.shutdown()
        except RuntimeError:
            pass

    # ── 主题 ────────────────────────────────────
    def _apply_theme_style(self):
        t = self._tokens
        qss = f"""
            QDialog {{ background: {t['page_bg']}; }}
            PushButton {{
                background: {t['card_hover']}; color: {t['ink']};
                border: 1px solid {t['border']}; border-radius: 6px;
                padding: 5px 12px; font-size: 12px;
            }}
            PushButton:hover {{ background: {t['card_active']}; }}
            PrimaryPushButton {{
                background: {t['accent']}; color: #FFFFFF; border: none;
                border-radius: 6px; padding: 5px 14px; font-size: 12px;
                font-weight: 500;
            }}
            PrimaryPushButton:hover {{ background: {t['accent_hover']}; }}
        """
        self.setStyleSheet(qss)
        for name in ("lb_status", "lb_time", "lb_range"):
            lb = getattr(self, name, None)
            if lb is not None:
                lb.setStyleSheet(
                    f"font-size: 12px; color: {t['ink_sec']};"
                    " background: transparent;")
        return qss

    def _refresh_theme(self):
        self._tokens = ds.tokens()
        return self._apply_theme_style()
