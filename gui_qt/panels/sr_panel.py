"""sr_panel — AI 画质增强面板（Real-ESRGAN x4 超分）。

模型首次使用需下载（约 20MB，后台线程），下载后即可批量超分。
"""
import os

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import (CaptionLabel, FluentIcon, PrimaryPushButton,
                            PushButton)

from gui_qt import task_manager as tm
from gui_qt.components import toast
from gui_qt.i18n import tr
from gui_qt.components.form_widgets import FormSection
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}


class SrPanelPage(BaseQtPanel, TaskPanelMixin):
    """AI 画质增强页。"""

    panel_key = "super_resolution"

    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("画质增强", "Enhance")))
        lay.addWidget(CaptionLabel(
            "AI 4 倍超分 · 基于 Real-ESRGAN（本地 ONNX 推理，无需联网上传）"))

        self.file_card = FileListCard("文件列表", file_exts=IMAGE_EXTS)
        lay.addWidget(self.file_card)
        self.file_card.set_target_fmt("4x 超分")

        lay.addWidget(self._build_model_card())

        from gui_qt.components.form_widgets import FormSection
        out_card = FormSection("输出目录", FluentIcon.FOLDER)
        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        out_card.add_widget(self.out_row)
        lay.addWidget(out_card)

        self.action_bar = ActionBar("开始增强")
        lay.addWidget(self.action_bar)

        self._wire_tasks()

    def _build_model_card(self):
        from core import super_resolution as sr
        sec = FormSection(tr("模型", "Model"), FluentIcon.CODE)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.model_label = CaptionLabel(
            tr("已就绪", "Ready") if sr.model_ready()
            else tr("未下载（约 20MB，需联网一次）", "Not downloaded (~20MB)"))
        row.addWidget(self.model_label, 1)
        self.btn_model = PushButton(
            FluentIcon.DOWNLOAD,
            tr("重新下载", "Re-download") if sr.model_ready() else tr("下载模型", "Download"))
        self.btn_model.clicked.connect(self._download_model)
        row.addWidget(self.btn_model)
        sec.add_layout(row)
        self.dl_label = CaptionLabel("")
        sec.add_widget(self.dl_label)
        return sec

    def _download_model(self):
        from core import super_resolution as sr
        if sr.model_ready():
            return
        self.btn_model.setEnabled(False)
        self.dl_label.setText("正在下载…")

        def _progress(pct, msg):
            if pct >= 0:
                self.dl_label.setText(f"{msg} {pct}%")
            else:
                self.dl_label.setText(msg)

        def _done(ok):
            QTimer.singleShot(0, lambda: self._model_done(ok))

        sr.download_model_async(progress_cb=_progress, done_cb=_done)

    def _model_done(self, ok):
        from core import super_resolution as sr
        self.btn_model.setEnabled(True)
        if ok:
            self.model_label.setText(tr("已就绪", "Ready"))
            self.btn_model.setText(tr("重新下载", "Re-download"))
            toast.show_success(self, "模型下载完成，可以开始增强")
        else:
            self.dl_label.setText("")
            toast.show_error(self, "模型下载失败，请检查网络后重试")

    def _start(self):
        from core import super_resolution as sr
        if not sr.model_ready():
            toast.show_warning(self, tr("请先下载模型", "Download the model first"))
            return
        self._submit_files()

    def _empty_hint(self) -> str:
        return "请先添加要增强的图片"

    def _make_task(self, f: str) -> dict:
        ext = os.path.splitext(f)[1] or ".png"
        out = tm.make_output_path(f, self.out_row.path(), ext)
        return dict(name="画质增强", task_type="super_resolution",
                    file_path=f, output_path=out, params={},
                    runner=self._runner,
                    history_type="画质增强", history_target="4x",
                    need_ffmpeg=False)

    def _runner(self, task, prog):
        from core import super_resolution as sr
        return sr.super_resolve(task.file_path, task.output_path,
                                progress_cb=prog)
