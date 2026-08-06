"""monitor_panel — 文件夹监视自动转换面板。

用 QTimer 轮询监视目录（无第三方依赖），发现新文件自动提交
TaskManager 转换任务（视频→MP4 / 音频→MP3 / 图片→PNG）。
"""
import os

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel)
from qfluentwidgets import (CaptionLabel, ComboBox, FluentIcon, LineEdit,
                            PrimaryPushButton, PushButton)

from gui_qt.components import toast
from gui_qt.i18n import tr
from gui_qt.components.form_widgets import FormSection
from gui_qt.panels.base_panel import BaseQtPanel

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"}
AUDIO_EXTS = {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".webp"}

TARGETS = [
    ("视频 → MP4", "video", VIDEO_EXTS),
    ("音频 → MP3", "audio", AUDIO_EXTS),
    ("图片 → PNG", "image", IMAGE_EXTS),
]


class MonitorPanelPage(BaseQtPanel):
    """文件夹监视页。"""

    panel_key = "monitor"

    def __init__(self, window, services, parent=None):
        self._timer = QTimer()
        self._seen = set()
        self._converted = 0
        self._running = False
        super().__init__(window, services, parent)

    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("文件夹监视", "Folder Watch")))
        lay.addWidget(CaptionLabel(
            "监视指定文件夹，新放入的文件自动转换为目标格式"))

        # 监视目录 + 目标格式
        sec = FormSection(tr("监视设置", "Watch Settings"), FluentIcon.FOLDER_ADD)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(CaptionLabel(tr("监视目录", "Watch folder")))
        self.ed_dir = LineEdit()
        self.ed_dir.setPlaceholderText("选择要监视的文件夹…")
        self.ed_dir.setReadOnly(True)
        self.btn_browse = PushButton(FluentIcon.FOLDER, tr("浏览", "Browse"))
        self.btn_browse.clicked.connect(self._pick_dir)
        row.addWidget(self.ed_dir, 1)
        row.addWidget(self.btn_browse)
        sec.add_layout(row)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(CaptionLabel(tr("目标格式", "Target format")))
        self.cb_target = ComboBox()
        self.cb_target.addItems([t[0] for t in TARGETS])
        row2.addWidget(self.cb_target)
        row2.addStretch(1)
        sec.add_layout(row2)
        lay.addWidget(sec)

        # 开始/停止 + 状态
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)
        self.btn_toggle = PrimaryPushButton(FluentIcon.PLAY, tr("开始监视", "Start"))
        self.btn_toggle.clicked.connect(self._toggle)
        ctrl.addWidget(self.btn_toggle)
        self.status_label = CaptionLabel("未监视")
        self.status_label.setStyleSheet(
            f"color: {self._ink_sec()};")
        ctrl.addWidget(self.status_label)
        ctrl.addStretch(1)
        lay.addLayout(ctrl)

        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._scan)

    def _ink_sec(self):
        from gui_qt.components import design_system as ds
        return ds.ink_sec()

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择监视目录")
        if d:
            self.ed_dir.setText(d)

    def _toggle(self):
        d = self.ed_dir.text().strip()
        if not d or not os.path.isdir(d):
            toast.show_warning(self, tr("请先选择有效的监视目录", "Pick a valid folder first"))
            return
        if self._running:
            self._stop()
        else:
            self._start(d)

    def _start(self, d):
        self._running = True
        self._dir = d
        # 初始快照：已存在的文件不转换
        _, exts = self._target()
        self._seen = {f for f in self._list_files(d) if f.lower().endswith(tuple(exts))}
        self._timer.start()
        self.btn_toggle.setText(tr("停止监视", "Stop watch"))
        self.btn_toggle.setIcon(FluentIcon.CANCEL)
        self.status_label.setText(f"监视中：{os.path.basename(d)}")
        toast.show_success(self, "开始监视文件夹")

    def _stop(self):
        self._running = False
        self._timer.stop()
        self.btn_toggle.setText(tr("开始监视", "Start watch"))
        self.btn_toggle.setIcon(FluentIcon.PLAY)
        self.status_label.setText(f"已停止（本次转换 {self._converted} 个文件）")

    def _target(self):
        idx = self.cb_target.currentIndex()
        return TARGETS[idx][1], TARGETS[idx][2]

    def _list_files(self, d):
        try:
            return [os.path.join(d, f) for f in os.listdir(d)
                    if os.path.isfile(os.path.join(d, f))]
        except OSError:
            return []

    def _scan(self):
        if not self._running:
            return
        kind, exts = self._target()
        now = {f for f in self._list_files(self._dir)
               if f.lower().endswith(tuple(exts))}
        new = now - self._seen
        for f in sorted(new):
            self._convert(f)
        self._seen = now

    def _convert(self, path):
        kind, _ = self._target()
        mgr = self.services.task_manager
        out_dir = self._dir
        if kind == "video":
            out = os.path.join(out_dir, os.path.splitext(os.path.basename(path))[0] + ".mp4")

            def runner(task, prog):
                return self.services.video_conv.convert(
                    task.file_path, task.output_path, "mp4", progress_callback=prog)
            mgr.add_task(name="监视转换", task_type="monitor",
                         file_path=path, output_path=out, params={},
                         runner=runner, need_ffmpeg=True,
                         history_type="文件夹监视", history_target="MP4")
        elif kind == "audio":
            out = os.path.join(out_dir, os.path.splitext(os.path.basename(path))[0] + ".mp3")

            def runner(task, prog):
                return self.services.audio_conv.convert(
                    task.file_path, task.output_path, "mp3", progress_callback=prog)
            mgr.add_task(name="监视转换", task_type="monitor",
                         file_path=path, output_path=out, params={},
                         runner=runner, need_ffmpeg=True,
                         history_type="文件夹监视", history_target="MP3")
        else:
            out = os.path.join(out_dir, os.path.splitext(os.path.basename(path))[0] + ".png")

            def runner(task, prog):
                return self.services.image_conv.convert(
                    task.file_path, task.output_path, progress_callback=prog)
            mgr.add_task(name="监视转换", task_type="monitor",
                         file_path=path, output_path=out, params={},
                         runner=runner, need_ffmpeg=False,
                         history_type="文件夹监视", history_target="PNG")
        self._converted += 1
