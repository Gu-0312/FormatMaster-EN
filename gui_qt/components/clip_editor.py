"""clip_editor — 专业视频剪辑窗口（独立对话框）。

参考剪映/CapCut 式专业剪辑面板：
- 左侧工具选项卡（剪辑 / 变换 / 调整 / 音频 / 速度 / 时间）
- 顶部快捷工具栏（撤销 / 重做 / 分割 / 删除 / 播放控制）
- 大尺寸视频预览播放器
- 底部带缩略图的时间轴轨道 + 入/出点游标 + 播放头
- 确认后把 (start_sec, end_sec) 回填到主面板

复用 VideoPlayerWidget（可播放）与 TimelineTrackWidget（带缩略图轨道）。
"""

import os
import shutil
import tempfile

from PySide6.QtCore import Qt, QThread, Signal
from gui_qt.components.safe_worker import SafeWorker
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFrame,
                               QHBoxLayout, QSizePolicy, QSlider,
                               QStackedWidget, QVBoxLayout, QWidget)
from qfluentwidgets import (CaptionLabel, FluentIcon, PrimaryPushButton,
                            PushButton, TransparentToolButton)

from gui_qt.components import design_system as ds
from gui_qt.components.video_preview import VideoPlayerWidget
from gui_qt.components.visual_widgets import TimelineTrackWidget
from gui_qt.i18n import tr


def _fmt(sec):
    """秒 → 'HH:MM:SS.mmm'（剪辑精度毫秒）。"""
    if sec is None:
        return "--:--:--"
    s = max(0, float(sec))
    ms = int(round((s - int(s)) * 1000))
    h = int(s // 3600)
    m = int(s % 3600 // 60)
    sec_int = int(s % 60)
    return f"{h}:{m:02d}:{sec_int:02d}.{ms:03d}"


class ThumbnailWorker(SafeWorker):
    """后台为视频生成等间隔缩略图。"""

    progress = Signal(int, str)
    finished_ok = Signal(list)  # [(sec, pixmap_path), ...]
    finished_fail = Signal(str)

    def __init__(self, video_path, count=40, parent=None):
        super().__init__(parent)
        self._path = video_path
        self._count = max(4, int(count))
        self._tmp_dir = tempfile.mkdtemp(prefix="fm_clip_thumbs_")

    def tmp_dir(self):
        return self._tmp_dir

    def work(self):
        try:
            from core import video_frame_extract
            from utils.config import get_ffmpeg_path

            ffmpeg = get_ffmpeg_path()
            if not ffmpeg or not os.path.isfile(self._path):
                self.finished_fail.emit("找不到 FFmpeg 或视频文件")
                return

            duration = video_frame_extract.duration_of(self._path)
            if duration <= 0:
                self.finished_fail.emit("无法读取视频时长")
                return

            interval = duration / self._count
            fps = max(0.001, 1.0 / interval) if interval > 0 else 1.0
            out_tpl = os.path.join(self._tmp_dir, "thumb_%05d.jpg")
            cmd = [ffmpeg, "-y", "-i", self._path, "-vf",
                   f"fps={fps:.4f},scale=120:-1",
                   "-q:v", "3", "-frames:v", str(self._count),
                   out_tpl]

            import subprocess
            subprocess.run(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=False,
                creationflags=(subprocess.CREATE_NO_WINDOW
                               if os.name == "nt" else 0))

            files = sorted([
                f for f in os.listdir(self._tmp_dir)
                if f.lower().startswith("thumb_") and
                f.lower().endswith(".jpg")])
            items = []
            for i, name in enumerate(files):
                sec = min(duration, i * interval)
                items.append((sec, os.path.join(self._tmp_dir, name)))
            self.finished_ok.emit(items)
        except Exception as exc:  # noqa: BLE001
            self.finished_fail.emit(str(exc))



class ClipEditorDialog(QDialog):
    """专业剪辑窗口：预览 + 时间轴 + 入出点。

    属性（确认后有效）：
        start_sec / end_sec   剪辑区间（秒，end 可能为 None=到结尾）
    方法：
        clip_range()          返回 (start_sec, end_sec)
    """

    def __init__(self, video_path, start=0.0, end=None, parent=None):
        super().__init__(parent)
        self._path = video_path or ""
        self._in_sec = float(start or 0)
        self._out_sec = float(end) if end is not None else None
        self._thumb_worker = None
        self._thumb_dir = None

        self.setWindowTitle(tr("视频剪辑", "Video Clip Editor"))
        self.resize(1100, 720)
        self.setMinimumSize(820, 560)

        # 整体专业面板（跟随应用当前主题）
        self._tokens = ds.tokens()
        self._apply_theme_style()
        ds.bind_theme(self, self._refresh_theme)

        main = QHBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # ── 左侧工具栏 ────────────────────────────
        self.sidebar = self._build_sidebar()
        main.addWidget(self.sidebar)

        # ── 右侧工作区 ────────────────────────────
        workspace = QVBoxLayout()
        workspace.setContentsMargins(14, 14, 14, 14)
        workspace.setSpacing(12)

        # 顶部工具条
        workspace.addLayout(self._build_top_bar())

        # 大预览区
        self.player = VideoPlayerWidget(self)
        self.player.setMinimumHeight(320)
        self.player.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        workspace.addWidget(self.player, 1)

        # 底部时间轴区（先构建以创建 self.timeline，供工具面板引用）
        timeline_area = self._build_timeline_area()

        # 工具参数面板（跟随左侧工具切换）
        workspace.addWidget(self._build_tool_panels())

        workspace.addLayout(timeline_area)

        wrap = QWidget(self)
        wrap.setLayout(workspace)
        main.addWidget(wrap, 1)

        # ── 联动 ──────────────────────────────────
        player = self.player.player
        player.durationChanged.connect(self._on_duration)
        player.positionChanged.connect(self._on_position)
        player.errorOccurred.connect(self._on_player_error)
        self.timeline.seek_requested.connect(
            lambda sec: player.setPosition(int(sec * 1000)))
        self.timeline.in_changed.connect(self._on_in)
        self.timeline.out_changed.connect(self._on_out)

        self.btn_prev.clicked.connect(self._goto_in)
        self.btn_next.clicked.connect(self._goto_out)
        self.btn_reset.clicked.connect(self._reset_range)
        self.btn_set_in.clicked.connect(self._set_in_at_playhead)
        self.btn_set_out.clicked.connect(self._set_out_at_playhead)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self.accept)
        self.btn_top_play.clicked.connect(self.player.toggle_play)
        self.player.player.playbackStateChanged.connect(self._sync_top_play)
        self._sync_top_play(self.player.player.playbackState())

        # 工具参数（变换/调整，导出时经 vf 滤镜应用）
        self._tool_params = {
            "transform": {"rotate": 0, "hflip": False, "vflip": False},
            "adjust": {"brightness": 0.0, "contrast": 1.0, "saturation": 1.0},
        }

        # 加载视频（默认带声音，可经「音频」工具调音量/静音）
        if os.path.isfile(self._path):
            self.player.audio_out.setVolume(0.8)
            self.player.set_source(self._path, autoplay=True)
            self._start_thumbnails()
        # 子控件全部就绪后按当前主题统一刷新
        self._apply_theme_style()

    # ── 构建 UI 部件 ─────────────────────────────
    def _build_sidebar(self):
        bar = QFrame(self)
        bar.setFixedWidth(170)
        bar.setObjectName("clipSidebar")

        v = QVBoxLayout(bar)
        v.setContentsMargins(10, 14, 10, 14)
        v.setSpacing(14)

        self.lb_side_title = CaptionLabel(tr("视频剪辑", "Video Clip"))
        v.addWidget(self.lb_side_title)

        # 垂直工具按钮列表（SegmentedWidget 不支持垂直方向）
        self._tool_btns = {}
        self._tool_group = QWidget(self)
        tv = QVBoxLayout(self._tool_group)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.setSpacing(6)
        tools = [
            ("clip", tr("剪辑", "Clip"), FluentIcon.CUT),
            ("transform", tr("变换", "Transform"), FluentIcon.ROTATE),
            ("adjust", tr("调整", "Adjust"), FluentIcon.BRIGHTNESS),
            ("audio", tr("音频", "Audio"), FluentIcon.MUSIC),
            ("speed", tr("速度", "Speed"), FluentIcon.SPEED_HIGH),
            ("time", tr("时间", "Time"), FluentIcon.DATE_TIME),
        ]
        for key, label, icon in tools:
            btn = PushButton(icon, label)
            btn.setFixedHeight(34)
            btn.setCheckable(True)
            btn.setChecked(key == "clip")
            btn.setProperty("toolKey", key)
            btn.clicked.connect(lambda _checked, k=key: self._select_tool(k))
            self._tool_btns[key] = btn
            tv.addWidget(btn)
        v.addWidget(self._tool_group)

        v.addStretch(1)

        self.lb_tool_hint = CaptionLabel(
            tr("当前模式：剪辑片段", "Current: clip"))
        self.lb_tool_hint.setWordWrap(True)
        v.addWidget(self.lb_tool_hint)

        return bar

    def _build_top_bar(self):
        bar = QHBoxLayout()
        bar.setSpacing(8)

        self.btn_undo = TransparentToolButton(FluentIcon.LEFT_ARROW, self)
        self.btn_undo.setToolTip(tr("撤销", "Undo"))
        self.btn_redo = TransparentToolButton(FluentIcon.RIGHT_ARROW, self)
        self.btn_redo.setToolTip(tr("重做", "Redo"))
        self.btn_split = TransparentToolButton(FluentIcon.SCROLL, self)
        self.btn_split.setToolTip(tr("分割", "Split at playhead"))
        self.btn_delete = TransparentToolButton(FluentIcon.CLOSE, self)
        self.btn_delete.setToolTip(tr("删除", "Delete"))

        for btn in (self.btn_undo, self.btn_redo, self.btn_split,
                    self.btn_delete):
            btn.setFixedSize(32, 32)
            bar.addWidget(btn)

        bar.addSpacing(12)

        self.lb_status = CaptionLabel(tr("准备就绪", "Ready"))
        bar.addWidget(self.lb_status)
        bar.addStretch(1)

        # 大号播放/暂停按钮
        self.btn_top_play = PushButton(FluentIcon.PLAY, tr("播放", "Play"))
        self.btn_top_play.setFixedSize(88, 32)
        bar.addWidget(self.btn_top_play)

        self.lb_top_time = CaptionLabel("--:-- / --:--")
        bar.addWidget(self.lb_top_time)

        return bar

    # ── 工具参数面板（左侧 6 个工具对应的可操作设置）────
    def _build_tool_panels(self):
        """QStackedWidget：剪辑/变换/调整/音频/速度/时间 各一页。"""
        t = self._tokens
        self.tool_stack = QStackedWidget(self)
        self.tool_stack.setFixedHeight(118)

        # ① 剪辑：操作提示
        p = QWidget()
        h = QHBoxLayout(p)
        h.setContentsMargins(14, 8, 14, 8)
        lb = CaptionLabel(
            tr("拖动下方时间轴上的入点/出点游标，或点击「设置入点/出点」"
               "以当前播放位置标记区间", "Drag in/out cursors on the timeline, or set them at the playhead"))
        lb.setWordWrap(True)
        lb.setStyleSheet(f"font-size: 12px; color: {t['ink_sec']};")
        h.addWidget(lb)
        h.addStretch(1)
        self.tool_stack.addWidget(p)

        # ② 变换：旋转 + 翻转
        p = QWidget()
        h = QHBoxLayout(p)
        h.setContentsMargins(14, 8, 14, 8)
        h.setSpacing(10)
        h.addWidget(self._panel_label(tr("旋转", "Rotate")))
        self.cb_rotate = QComboBox()
        self.cb_rotate.addItems(["0°", "90°", "180°", "270°"])
        self.cb_rotate.setFixedWidth(90)
        self._style_combo(self.cb_rotate)
        self.cb_rotate.currentIndexChanged.connect(self._apply_transform)
        h.addWidget(self.cb_rotate)
        h.addSpacing(18)
        self.cb_hflip = QCheckBox(tr("水平翻转", "Flip H"))
        self.cb_vflip = QCheckBox(tr("垂直翻转", "Flip V"))
        for cb in (self.cb_hflip, self.cb_vflip):
            cb.toggled.connect(self._apply_transform)
        h.addWidget(self.cb_hflip)
        h.addWidget(self.cb_vflip)
        h.addStretch(1)
        self.lb_xf_hint = CaptionLabel(
            tr("实时预览生效", "Live preview"))
        h.addWidget(self.lb_xf_hint)
        self.tool_stack.addWidget(p)

        # ③ 调整：亮度/对比度/饱和度
        p = QWidget()
        h = QHBoxLayout(p)
        h.setContentsMargins(14, 8, 14, 8)
        h.setSpacing(8)
        self._box_bright, self._sl_bright, self.lb_bright = self._make_slider(
            tr("亮度", "Brightness"), -50, 50, 0, self._apply_adjust)
        self._box_contrast, self._sl_contrast, self.lb_contrast = \
            self._make_slider(tr("对比度", "Contrast"), 0, 200, 100,
                              self._apply_adjust)
        self._box_satur, self._sl_satur, self.lb_satur = self._make_slider(
            tr("饱和度", "Saturation"), 0, 200, 100, self._apply_adjust)
        for w in (self._box_bright, self._box_contrast, self._box_satur):
            w.setFixedWidth(150)
            h.addWidget(w)
        h.addStretch(1)
        self.lb_adj_hint = CaptionLabel(
            tr("实时预览生效", "Live preview"))
        h.addWidget(self.lb_adj_hint)
        self.tool_stack.addWidget(p)

        # ④ 音频：音量（实时生效）
        p = QWidget()
        h = QHBoxLayout(p)
        h.setContentsMargins(14, 8, 14, 8)
        h.setSpacing(8)
        self._box_volume, self._sl_volume, self.lb_volume = self._make_slider(
            tr("音量", "Volume"), 0, 100, 80, self._apply_volume)
        self._box_volume.setFixedWidth(280)
        h.addWidget(self._box_volume)
        self.cb_mute = QCheckBox(tr("静音", "Mute"))
        self.cb_mute.toggled.connect(self._apply_volume)
        h.addWidget(self.cb_mute)
        h.addStretch(1)
        self.tool_stack.addWidget(p)

        # ⑤ 速度：播放倍速（实时生效）
        p = QWidget()
        h = QHBoxLayout(p)
        h.setContentsMargins(14, 8, 14, 8)
        h.setSpacing(10)
        h.addWidget(self._panel_label(tr("播放倍速", "Playback rate")))
        self.cb_rate = QComboBox()
        self.cb_rate.addItems(
            [f"{x:g}x" for x in (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0)])
        self.cb_rate.setCurrentText("1x")
        self.cb_rate.setFixedWidth(90)
        self._style_combo(self.cb_rate)
        self.cb_rate.currentTextChanged.connect(self._apply_rate)
        h.addWidget(self.cb_rate)
        h.addStretch(1)
        self.tool_stack.addWidget(p)

        # ⑥ 时间：区间/时长信息
        p = QWidget()
        h = QHBoxLayout(p)
        h.setContentsMargins(14, 8, 14, 8)
        h.setSpacing(20)
        self.lb_t_in = self._panel_label("")
        self.lb_t_out = self._panel_label("")
        self.lb_t_dur = self._panel_label("")
        h.addWidget(self.lb_t_in)
        h.addWidget(self.lb_t_out)
        h.addWidget(self.lb_t_dur)
        h.addStretch(1)
        self.tool_stack.addWidget(p)

        self.tool_stack.setCurrentIndex(0)
        return self.tool_stack

    def _panel_label(self, text):
        lb = CaptionLabel(text)
        lb.setStyleSheet(
            f"font-size: 12px; color: {self._tokens['ink_sec']};"
            " background: transparent;")
        return lb

    def _style_combo(self, combo):
        t = self._tokens
        combo.setStyleSheet(
            f"QComboBox {{ background: {t['card_hover']}; color: {t['ink']};"
            f" border: 1px solid {t['border']}; border-radius: 6px;"
            " padding: 4px 8px; font-size: 12px; }"
            f"QComboBox::drop-down {{ border: none; width: 18px; }}")

    def _slider_qss(self, t=None):
        """滑杆 QSS（跟随主题，供构造与主题刷新共用）。"""
        t = t or self._tokens
        return (f"QSlider::groove:horizontal {{ height: 4px;"
                f" background: {t['card_active']}; border-radius: 2px; }}"
                f"QSlider::handle:horizontal {{ width: 12px; height: 12px;"
                f" margin: -4px 0; border-radius: 6px;"
                f" background: {t['accent']}; }}")

    def _slider_val_qss(self, t=None):
        """滑杆数值标签 QSS（跟随主题，供构造与主题刷新共用）。"""
        t = t or self._tokens
        return (f"font-size: 11px; color: {t['accent_soft']};"
                "background: transparent; min-width: 26px;")

    def _make_slider(self, title, lo, hi, val, slot):
        """返回 (box, slider, value_label)，box 内含标题+滑杆+数值。"""
        t = self._tokens
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        h.addWidget(self._panel_label(title))
        s = QSlider(Qt.Horizontal)
        s.setRange(lo, hi)
        s.setValue(val)
        s.setFixedHeight(20)
        s.setStyleSheet(self._slider_qss(t))
        lb = CaptionLabel(str(val))
        lb.setStyleSheet(self._slider_val_qss(t))
        h.addWidget(s)
        h.addWidget(lb)
        s.valueChanged.connect(slot)
        return box, s, lb

    # ── 工具参数应用（全部实时生效）────────────────
    def _apply_transform(self, *_a):
        self._tool_params["transform"] = {
            "rotate": int(self.cb_rotate.currentIndex()) * 90,
            "hflip": self.cb_hflip.isChecked(),
            "vflip": self.cb_vflip.isChecked(),
        }
        self._update_preview_effects()

    def _apply_adjust(self, *_a):
        self._tool_params["adjust"] = {
            "brightness": self._sl_bright.value() / 50.0,
            "contrast": self._sl_contrast.value() / 100.0,
            "saturation": self._sl_satur.value() / 100.0,
        }
        self.lb_bright.setText(str(self._sl_bright.value()))
        self.lb_contrast.setText(str(self._sl_contrast.value()))
        self.lb_satur.setText(str(self._sl_satur.value()))
        self._update_preview_effects()

    def _update_preview_effects(self):
        """把变换/调整参数实时应用到预览画面。"""
        t = self._tool_params.get("transform", {})
        a = self._tool_params.get("adjust", {})
        self.player.set_effects(
            rotate=t.get("rotate", 0),
            hflip=t.get("hflip", False),
            vflip=t.get("vflip", False),
            brightness=a.get("brightness", 0.0),
            contrast=a.get("contrast", 1.0),
            saturation=a.get("saturation", 1.0),
        )

    def _apply_volume(self, *_a):
        if self.cb_mute.isChecked():
            self.player.audio_out.setVolume(0)
        else:
            self.player.audio_out.setVolume(self._sl_volume.value() / 100.0)
        self.lb_volume.setText(str(self._sl_volume.value()))

    def _apply_rate(self, text):
        try:
            rate = float(str(text).replace("x", ""))
        except (TypeError, ValueError):
            rate = 1.0
        self.player.set_playback_rate(rate)

    def _update_time_panel(self):
        if not hasattr(self, "lb_t_in"):
            return
        self.lb_t_in.setText(
            tr("入点", "In") + f"  {_fmt(self._in_sec)}")
        self.lb_t_out.setText(
            tr("出点", "Out") + f"  {_fmt(self._out_sec)}")
        dur = self.timeline._duration or 0
        self.lb_t_dur.setText(
            tr("时长", "Duration") + f"  {_fmt(dur)}")

    # ── 对外：变换/调整参数 ──
    def tool_params(self) -> dict:
        """返回工具参数 dict（变换/调整），供导出时应用 vf 滤镜。"""
        self._apply_transform()
        self._apply_adjust()
        return dict(self._tool_params)

    def _build_timeline_area(self):
        root = QVBoxLayout()
        root.setSpacing(8)

        # 时间轴工具条
        bar = QHBoxLayout()
        bar.setSpacing(8)

        self.btn_set_in = PushButton(
            FluentIcon.PIN, tr("设置入点", "Set In"))
        self.btn_set_out = PushButton(
            FluentIcon.PIN, tr("设置出点", "Set Out"))
        self.btn_prev = PushButton(
            FluentIcon.LEFT_ARROW, tr("跳转入点", "Go In"))
        self.btn_next = PushButton(
            FluentIcon.RIGHT_ARROW, tr("跳转出点", "Go Out"))
        self.btn_reset = PushButton(
            FluentIcon.CANCEL, tr("重置区间", "Reset"))

        for btn in (self.btn_set_in, self.btn_set_out, self.btn_prev,
                    self.btn_next, self.btn_reset):
            btn.setFixedHeight(30)
            bar.addWidget(btn)

        bar.addStretch(1)

        # 时间信息
        info = QHBoxLayout()
        info.setSpacing(16)
        self.lb_in = CaptionLabel("")
        self.lb_out = CaptionLabel("")
        info.addWidget(self.lb_in)
        info.addWidget(self.lb_out)
        bar.addLayout(info)

        root.addLayout(bar)

        # 时间轴轨道
        self.timeline = TimelineTrackWidget(self)
        self.timeline.setMinimumHeight(130)
        root.addWidget(self.timeline)

        # 底部操作按钮
        btns = QHBoxLayout()
        btns.setSpacing(8)
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
            QDialog {{
                background: {t['page_bg']};
            }}
            #clipSidebar {{
                background: {t['card_bg']};
                border-right: 1px solid {t['border']};
            }}
            SegmentedWidget {{
                background: transparent;
            }}
            PushButton {{
                background: {t['card_hover']};
                color: {t['ink']};
                border: 1px solid {t['border']};
                border-radius: 6px;
                padding: 5px 12px;
                font-size: 12px;
            }}
            PushButton:hover {{
                background: {t['card_active']};
                border-color: {t['accent_soft']};
            }}
            PrimaryPushButton {{
                background: {t['accent']};
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 5px 14px;
                font-size: 12px;
                font-weight: 600;
            }}
            PrimaryPushButton:hover {{
                background: {t['accent_hover']};
            }}
            TransparentToolButton {{
                background: transparent;
                border: 1px solid {t['border']};
                border-radius: 6px;
            }}
            TransparentToolButton:hover {{
                background: {t['card_hover']};
                border-color: {t['accent_soft']};
            }}
        """
        self.setStyleSheet(qss)
        # 子控件样式（构造完成后才创建，用 getattr 保护）
        if hasattr(self, "lb_side_title"):
            self.lb_side_title.setStyleSheet(
                f"font-size: 15px; font-weight: 700; color: {t['ink']};")
        for name in ("lb_tool_hint", "lb_status", "lb_in", "lb_out",
                     "lb_t_in", "lb_t_out", "lb_t_dur"):
            w = getattr(self, name, None)
            if w is not None:
                w.setStyleSheet(
                    f"font-size: 12px; color: {t['ink_sec']};"
                    " background: transparent;")
        if hasattr(self, "lb_top_time"):
            self.lb_top_time.setStyleSheet(
                f"font-size: 13px; color: {t['ink']};"
                " font-family: Consolas; background: transparent;")
        for name in ("lb_xf_hint", "lb_adj_hint"):
            w = getattr(self, name, None)
            if w is not None:
                w.setStyleSheet(f"font-size: 11px; color: {t['success']};")
        if hasattr(self, "tool_stack"):
            self.tool_stack.setStyleSheet(
                f"QStackedWidget {{ background: {t['card_bg']};"
                f" border: 1px solid {t['border']}; border-radius: 8px; }}")
        for name in ("cb_rotate", "cb_rate"):
            w = getattr(self, name, None)
            if w is not None:
                self._style_combo(w)
        for name in ("cb_hflip", "cb_vflip", "cb_mute"):
            w = getattr(self, name, None)
            if w is not None:
                w.setStyleSheet(
                    f"color: {t['ink_sec']}; font-size: 12px;"
                    "QCheckBox::indicator { width: 14px; height: 14px; }")
        for name in ("_sl_bright", "_sl_contrast", "_sl_satur", "_sl_volume"):
            w = getattr(self, name, None)
            if w is not None:
                w.setStyleSheet(self._slider_qss(t))
        for name in ("lb_bright", "lb_contrast", "lb_satur", "lb_volume"):
            w = getattr(self, name, None)
            if w is not None:
                w.setStyleSheet(self._slider_val_qss(t))
        return qss

    def _refresh_theme(self):
        """主题切换时刷新颜色令牌与对话框样式。"""
        self._tokens = ds.tokens()
        return self._apply_theme_style()

    # ── 对外 ──
    def clip_range(self):
        return (self._in_sec, self._out_sec)

    @property
    def start_sec(self):
        return self._in_sec

    @property
    def end_sec(self):
        return self._out_sec

    # ── 缩略图 ──
    def _start_thumbnails(self):
        """启动后台线程生成时间轴缩略图。"""
        self._cleanup_thumbs()
        self._thumb_worker = ThumbnailWorker(self._path, count=40, parent=self)
        self._thumb_worker.progress.connect(
            lambda p, msg: self.lb_status.setText(f"{msg} ({p}%)"))
        self._thumb_worker.finished_ok.connect(self._on_thumbs_ready)
        self._thumb_worker.finished_fail.connect(
            lambda msg: self.lb_status.setText(msg))
        self._thumb_dir = self._thumb_worker.tmp_dir()
        self._thumb_worker.start()

    def _on_thumbs_ready(self, items):
        """items: [(sec, path), ...]"""
        pixmaps = [(sec, QPixmap(path)) for sec, path in items]
        self.timeline.set_thumbnails(pixmaps)
        self.lb_status.setText(
            tr(f"已加载 {len(pixmaps)} 张缩略图", f"{len(pixmaps)} thumbnails loaded"))

    def _cleanup_thumbs(self):
        if self._thumb_worker and self._thumb_worker.isRunning():
            self._thumb_worker.quit()
            self._thumb_worker.wait(2000)
        if self._thumb_dir and os.path.isdir(self._thumb_dir):
            try:
                shutil.rmtree(self._thumb_dir)
            except OSError:
                pass
        self._thumb_dir = None

    # ── 联动 ──
    def _on_player_error(self, error, errorString):
        text = errorString or "无法播放视频"
        self.lb_status.setText(tr("播放错误", "Playback error") + f": {text}")
        self.lb_status.setStyleSheet(
            "font-size: 12px; color: #FF6B6B; background: transparent;")

    def _sync_top_play(self, state):
        if state == QMediaPlayer.PlayingState:
            self.btn_top_play.setIcon(FluentIcon.PAUSE)
            self.btn_top_play.setText(tr("暂停", "Pause"))
        else:
            self.btn_top_play.setIcon(FluentIcon.PLAY)
            self.btn_top_play.setText(tr("播放", "Play"))

    def _on_duration(self, ms):
        dur = ms / 1000.0
        self.timeline.set_duration(dur)
        if self._out_sec is None or self._out_sec <= 0 or self._out_sec > dur:
            self._out_sec = dur
            self.timeline.set_range(self._in_sec, self._out_sec)
        self._refresh_labels()
        self._update_top_time()
        self._update_time_panel()

    def _on_position(self, ms):
        sec = ms / 1000.0
        self.timeline.set_playhead(sec)
        self._update_top_time()

    def _on_in(self, sec):
        self._in_sec = sec
        self._refresh_labels()

    def _on_out(self, sec):
        self._out_sec = sec
        self._refresh_labels()

    def _goto_in(self):
        self.player.player.setPosition(int(self._in_sec * 1000))

    def _goto_out(self):
        out = self._out_sec if self._out_sec is not None else self.timeline._duration
        self.player.player.setPosition(int(out * 1000))

    def _set_in_at_playhead(self):
        sec = self.player.player.position() / 1000.0
        out = self._out_sec if self._out_sec is not None else self.timeline._duration
        if sec < out:
            self._in_sec = sec
            self.timeline.set_range(self._in_sec, out)
            self._refresh_labels()

    def _set_out_at_playhead(self):
        sec = self.player.player.position() / 1000.0
        if sec > self._in_sec:
            out = sec
            if self._out_sec is None:
                self._out_sec = out
            else:
                self._out_sec = out
            self.timeline.set_range(self._in_sec, out)
            self._refresh_labels()

    def _reset_range(self):
        self._in_sec = 0.0
        self._out_sec = self.timeline._duration or 0.0
        self.timeline.set_range(0.0, self._out_sec)
        self.player.player.setPosition(0)
        self._refresh_labels()

    def _refresh_labels(self):
        self.lb_in.setText(tr("入点", "In") + f"  {_fmt(self._in_sec)}")
        self.lb_out.setText(tr("出点", "Out") + f"  {_fmt(self._out_sec)}")
        self._update_time_panel()

    def _update_top_time(self):
        ms = self.player.player.position()
        dur = self.player.player.duration()
        self.lb_top_time.setText(f"{_fmt(ms/1000.0)} / {_fmt(dur/1000.0)}")

    def _select_tool(self, key):
        for k, btn in self._tool_btns.items():
            btn.setChecked(k == key)
        idx = {"clip": 0, "transform": 1, "adjust": 2,
               "audio": 3, "speed": 4, "time": 5}.get(key, 0)
        if hasattr(self, "tool_stack"):
            self.tool_stack.setCurrentIndex(idx)
        hints = {
            "clip": tr("剪辑：拖动时间轴游标设置入/出点", "Clip: drag timeline cursors"),
            "transform": tr("变换：旋转/翻转，导出时应用", "Transform: rotate / flip"),
            "adjust": tr("调整：亮度/对比度/饱和度，导出时应用", "Adjust: brightness / contrast / saturation"),
            "audio": tr("音频：音量实时生效", "Audio: volume (live)"),
            "speed": tr("速度：播放倍速实时生效", "Speed: playback rate (live)"),
            "time": tr("时间：查看区间与时长信息", "Time: range & duration info"),
        }
        self.lb_tool_hint.setText(hints.get(key, ""))

    def done(self, r):
        """所有关闭路径（确定/取消/ESC/点 X）都释放媒体，避免残留声音。"""
        self._release_media()
        super().done(r)

    def closeEvent(self, e):
        self._release_media()
        self._cleanup_thumbs()
        super().closeEvent(e)

    def _release_media(self):
        """幂等释放：停止播放器（含声音）并清理帧节流器。"""
        try:
            self.player.shutdown()
        except RuntimeError:
            pass
        self._cleanup_thumbs()
