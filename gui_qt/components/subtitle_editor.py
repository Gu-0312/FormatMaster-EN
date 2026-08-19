"""subtitle_editor — 字幕时间轴编辑器（独立窗口）。

解析 SRT 字幕，在时间轴轨道上以色块显示，拖动字幕块调整出现时间，
配合视频预览对齐字幕；保存后写回 SRT 文件。

时间格式：SRT 用 HH:MM:SS,mmm。
"""

import os
import re

from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QSizePolicy, QVBoxLayout,
                               QWidget)
from qfluentwidgets import (CaptionLabel, FluentIcon, LineEdit,
                            PrimaryPushButton, PushButton)

from gui_qt.components import design_system as ds
from gui_qt.components.video_preview import VideoPlayerWidget
from gui_qt.i18n import tr

_SRT_BLOCK = re.compile(
    r"(\d+)\s*\n(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*"
    r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*\n(.*?)(?=\n\s*\n|\Z)",
    re.DOTALL)
_TIME_RE = re.compile(r"(\d+):(\d+):(\d+)[,.](\d{1,3})")


def _ts2sec(ts):
    m = _TIME_RE.match(ts.strip())
    if not m:
        return 0.0
    h, mi, s, ms = m.groups()
    return int(h) * 3600 + int(mi) * 60 + int(s) + int(ms) / 1000.0


def _sec2ts(sec):
    s = max(0, int(sec))
    ms = int(round((sec - s) * 1000))
    if ms >= 1000:
        ms = 0
        s += 1
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d},{ms:03d}"


def parse_srt(path):
    """解析 SRT 文件 → [(id, start_sec, end_sec, text), ...]。"""
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        content = f.read()
    items = []
    for m in _SRT_BLOCK.finditer(content):
        sid = int(m.group(1))
        start = _ts2sec(m.group(2))
        end = _ts2sec(m.group(3))
        text = m.group(4).strip()
        items.append((sid, start, max(end, start + 0.05), text))
    return items


def write_srt(path, items):
    """按 [(id, start, end, text)] 写回 SRT。"""
    lines = []
    for i, (sid, start, end, text) in enumerate(items, 1):
        lines.append(f"{i}\n{_sec2ts(start)} --> {_sec2ts(end)}\n{text}\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


class SubtitleTrackWidget(QWidget):
    """字幕色块轨道：点击选中、拖动平移选中块、播放头。"""

    selected = Signal(int)          # 选中块下标（-1 取消）
    moved = Signal(int, float)      # (块下标, 位移秒)
    blank_clicked = Signal(float)   # 点击空白处（秒，用于定位）

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []            # [(sid, start, end, text)]
        self.duration = 0.0
        self.playhead = 0.0
        self._sel = -1
        self._drag = None          # (按下时x, 按下时start)
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_items(self, items, duration):
        self.items = list(items)
        self.duration = float(duration or 0)
        self._sel = -1
        self.update()

    def set_playhead(self, sec):
        self.playhead = max(0.0, float(sec))
        self.update()

    def select(self, idx):
        self._sel = idx
        self.update()

    def _rect_of(self, i):
        start, end = self.items[i][1], self.items[i][2]
        w = max(self.width(), 1)
        x1 = int(start / self.duration * w) if self.duration > 0 else 0
        x2 = int(end / self.duration * w) if self.duration > 0 else w
        return QRectF(x1 + 1, 6, max(6, x2 - x1 - 2), self.height() - 18)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(QPen(QColor(ds.border_color()), 0.5))
        p.setBrush(QColor(ds.card_bg()))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 8, 8)
        if not self.items:
            p.setPen(QPen(QColor(ds.ink_dis()), 0))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter,
                       tr("暂无字幕", "No subtitles"))
            p.end()
            return
        for i, (_sid, start, end, text) in enumerate(self.items):
            rect = self._rect_of(i)
            sel = (i == self._sel)
            p.setBrush(QColor(124, 124, 245) if sel
                       else QColor(70, 92, 160))
            p.setPen(QPen(QColor(165, 167, 255) if sel
                          else QColor(120, 140, 210), 0.5))
            p.drawRoundedRect(rect, 4, 4)
            p.setPen(QPen(QColor(230, 232, 242), 0))
            p.drawText(rect.adjusted(6, 0, -6, 0),
                       Qt.AlignVCenter | Qt.AlignLeft,
                       (text or " ").replace("\n", " ")[:14])
        # 播放头
        if self.duration > 0:
            px = int(self.playhead / self.duration * w)
            p.setPen(QPen(QColor(255, 170, 60), 2))
            p.drawLine(px, 0, px, h)
        p.end()

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        x = e.position().x()
        idx = -1
        for i in range(len(self.items)):
            if self._rect_of(i).contains(e.position()):
                idx = i
                break
        self._sel = idx
        self.selected.emit(idx)
        if idx >= 0:
            self._drag = (x, self.items[idx][1])
        elif self.duration > 0:
            sec = max(0.0, min(x / max(self.width(), 1) * self.duration,
                               self.duration))
            self.blank_clicked.emit(sec)
        self.update()

    def mouseMoveEvent(self, e):
        if self._drag is None or self._sel < 0:
            return
        dx = e.position().x() - self._drag[0]
        if self.duration > 0:
            delta = dx / self.width() * self.duration
        else:
            delta = 0.0
        self.moved.emit(self._sel, delta)


class SubtitleTimelineDialog(QDialog):
    """字幕时间轴编辑器：视频预览 + 字幕色块轨道。

    用法：SubtitleTimelineDialog(video_path, srt_path)；确认后写回 SRT。
    """

    def __init__(self, srt_path, video_path="", parent=None):
        super().__init__(parent)
        self._srt = srt_path or ""
        self._video = video_path or ""
        self._items = parse_srt(self._srt) if self._srt and os.path.isfile(self._srt) else []
        self._duration = 0.0

        self.setWindowTitle(tr("字幕时间轴编辑器", "Subtitle Timeline Editor"))
        self.resize(980, 620)
        self.setMinimumSize(780, 500)
        self._tokens = ds.tokens()
        self._apply_theme_style()
        ds.bind_theme(self, self._refresh_theme)

        main = QVBoxLayout(self)
        main.setContentsMargins(14, 14, 14, 14)
        main.setSpacing(12)

        main.addLayout(self._build_top_bar())

        # 视频预览（静音，用于对齐）
        self.player = VideoPlayerWidget(self)
        self.player.setMinimumHeight(200)
        self.player.audio_out.setVolume(0)
        main.addWidget(self.player, 1)

        # 字幕轨道
        self.track = SubtitleTrackWidget(self)
        self.track.setMinimumHeight(120)
        main.addWidget(self.track, 1)

        main.addLayout(self._build_bottom())

        # 联动
        p = self.player.player
        p.durationChanged.connect(self._on_duration)
        p.positionChanged.connect(self._on_position)
        self.track.selected.connect(self._on_selected)
        self.track.moved.connect(self._on_moved)
        self.track.blank_clicked.connect(
            lambda sec: self.player.player.setPosition(int(sec * 1000)))
        self.btn_play.clicked.connect(self.player.toggle_play)
        self.player.player.playbackStateChanged.connect(self._sync_play)
        self.btn_set_start.clicked.connect(self._set_start_at_playhead)
        self.btn_set_end.clicked.connect(self._set_end_at_playhead)
        self.btn_offset.clicked.connect(self._apply_offset)
        self.btn_save.clicked.connect(self._save)
        self.btn_close.clicked.connect(self.reject)

        if self._video and os.path.isfile(self._video):
            self.player.set_source(self._video, autoplay=False)
            from core.video_frame_extract import duration_of
            try:
                self._duration = duration_of(self._video) or 0.0
            except Exception:
                self._duration = 0.0
        self.track.set_items(self._items, self._duration)
        self._refresh_status()
        # 子控件全部就绪后按当前主题统一刷新
        self._apply_theme_style()

    # ── UI ──────────────────────────────────────
    def _build_top_bar(self):
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_play = PushButton(FluentIcon.PLAY, tr("播放", "Play"))
        self.btn_play.setFixedSize(88, 32)
        bar.addWidget(self.btn_play)
        self.lb_status = CaptionLabel(
            tr("拖动字幕块调整时间；点「设起点/终点」用播放头对齐",
               "Drag subtitle blocks; use playhead to set start/end"))
        bar.addWidget(self.lb_status)
        bar.addStretch(1)
        self.lb_time = CaptionLabel("--:-- / --:--")
        bar.addWidget(self.lb_time)
        return bar

    def _build_bottom(self):
        root = QVBoxLayout()
        root.setSpacing(8)
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self.lb_sel = CaptionLabel(tr("未选中字幕", "No subtitle selected"))
        row1.addWidget(self.lb_sel)
        row1.addStretch(1)
        self.btn_set_start = PushButton(FluentIcon.PIN, tr("设起点", "Set Start"))
        self.btn_set_end = PushButton(FluentIcon.PIN, tr("设终点", "Set End"))
        for b in (self.btn_set_start, self.btn_set_end):
            b.setFixedHeight(30)
            row1.addWidget(b)
        root.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(CaptionLabel(tr("整体偏移(秒)", "Offset (sec)")))
        self.ed_offset = LineEdit()
        self.ed_offset.setPlaceholderText(tr("如 0.5 或 -1", "e.g. 0.5 or -1"))
        self.ed_offset.setFixedWidth(90)
        row2.addWidget(self.ed_offset)
        self.btn_offset = PushButton(tr("应用偏移", "Apply offset"))
        self.btn_offset.setFixedHeight(30)
        row2.addWidget(self.btn_offset)
        row2.addStretch(1)
        self.lb_count = CaptionLabel("")
        row2.addWidget(self.lb_count)
        self.btn_save = PrimaryPushButton(
            FluentIcon.SAVE, tr("保存字幕", "Save SRT"))
        self.btn_save.setFixedHeight(32)
        row2.addWidget(self.btn_save)
        self.btn_close = PushButton(tr("关闭", "Close"))
        self.btn_close.setFixedHeight(32)
        row2.addWidget(self.btn_close)
        root.addLayout(row2)
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
            LineEdit {{
                background: {t['card_hover']}; color: {t['ink']};
                border: 1px solid {t['border']}; border-radius: 6px;
                padding: 4px 8px; font-size: 12px;
            }}
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
        if hasattr(self, "lb_sel"):
            self.lb_sel.setStyleSheet(
                f"font-size: 12px; color: {t['ink_sec']};"
                " background: transparent;")
        if hasattr(self, "lb_count"):
            self.lb_count.setStyleSheet(
                f"font-size: 11px; color: {t['ink_dis']};"
                " background: transparent;")
        return qss

    def _refresh_theme(self):
        """主题切换时刷新颜色令牌与对话框样式。"""
        self._tokens = ds.tokens()
        return self._apply_theme_style()

    # ── 联动 ──
    def _on_duration(self, ms):
        dur = ms / 1000.0
        if dur > 0:
            self._duration = dur
            self.track.set_items(self._items, dur)
        self._update_time()

    def _on_position(self, ms):
        self.track.set_playhead(ms / 1000.0)
        self._update_time()

    def _update_time(self):
        p = self.player.player
        self.lb_time.setText(
            f"{int(p.position() / 1000) // 60:02d}:{int(p.position() / 1000) % 60:02d}"
            f" / {int(p.duration() / 1000) // 60:02d}:{int(p.duration() / 1000) % 60:02d}")

    def _sync_play(self, state):
        from PySide6.QtMultimedia import QMediaPlayer
        if state == QMediaPlayer.PlayingState:
            self.btn_play.setIcon(FluentIcon.PAUSE)
            self.btn_play.setText(tr("暂停", "Pause"))
        else:
            self.btn_play.setIcon(FluentIcon.PLAY)
            self.btn_play.setText(tr("播放", "Play"))

    def _on_selected(self, idx):
        if idx < 0 or idx >= len(self._items):
            self.lb_sel.setText(tr("未选中字幕", "No subtitle selected"))
            return
        _sid, st, et, text = self._items[idx]
        self.lb_sel.setText(
            tr("选中", "Selected") + f" #{idx + 1}  {_sec2ts(st)} → {_sec2ts(et)}"
            f"  {text[:12]}")
        self._sel_idx = idx

    def _on_moved(self, idx, delta):
        if idx < 0 or idx >= len(self._items):
            return
        sid, st, et, text = self._items[idx]
        dur = max(et - st, 0.05)
        st = max(0.0, st + delta)
        et = st + dur
        self._items[idx] = (sid, st, et, text)
        self.track.set_items(self._items, self._duration)

    def _set_start_at_playhead(self):
        idx = getattr(self, "_sel_idx", -1)
        if idx < 0 or idx >= len(self._items):
            from gui_qt.components import toast
            toast.show_warning(self, tr("请先点击选中一条字幕",
                                        "Select a subtitle first"))
            return
        sec = self.player.player.position() / 1000.0
        sid, _st, et, text = self._items[idx]
        st = min(sec, et - 0.05)
        self._items[idx] = (sid, st, et, text)
        self.track.set_items(self._items, self._duration)
        self._on_selected(idx)

    def _set_end_at_playhead(self):
        idx = getattr(self, "_sel_idx", -1)
        if idx < 0 or idx >= len(self._items):
            from gui_qt.components import toast
            toast.show_warning(self, tr("请先点击选中一条字幕",
                                        "Select a subtitle first"))
            return
        sec = self.player.player.position() / 1000.0
        sid, st, _et, text = self._items[idx]
        et = max(sec, st + 0.05)
        self._items[idx] = (sid, st, et, text)
        self.track.set_items(self._items, self._duration)
        self._on_selected(idx)

    def _apply_offset(self):
        try:
            off = float(self.ed_offset.text().strip())
        except (TypeError, ValueError):
            from gui_qt.components import toast
            toast.show_warning(self, tr("请输入数字偏移量", "Enter a numeric offset"))
            return
        items = []
        for sid, st, et, text in self._items:
            items.append((sid, max(0.0, st + off), max(0.05, et + off), text))
        self._items = items
        self.track.set_items(self._items, self._duration)
        self.lb_count.setText(tr("已整体偏移", "Offset applied") + f" {off:g}s")

    def _save(self):
        if not self._srt:
            from gui_qt.components import toast
            toast.show_error(self, tr("没有 SRT 文件可保存", "No SRT to save"))
            return
        try:
            write_srt(self._srt, self._items)
        except OSError as exc:
            from gui_qt.components import toast
            toast.show_error(self, f"{tr('保存失败', 'Save failed')}: {exc}")
            return
        from gui_qt.components import toast
        toast.show_success(self, tr("字幕已保存", "Subtitles saved"))

    def _refresh_status(self):
        self.lb_count.setText(
            tr("共 {} 条字幕", "{} subtitles").format(len(self._items)))
        self._sel_idx = -1

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
