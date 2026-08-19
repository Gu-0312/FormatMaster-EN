"""scene_panel — 场景化一键处理面板。

按「使用场景」选择转换参数（发抖音/发微信/发邮件/传公众号/B站/网课/
存档/极速），对图片/音频/视频批量处理，任务经 TaskManager 执行。
"""

import os

from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import CaptionLabel, ComboBox, FluentIcon

from gui_qt.i18n import tr
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow

MEDIA_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v",
              ".mpg", ".mpeg", ".ts", ".mp3", ".wav", ".aac", ".flac",
              ".ogg", ".m4a", ".wma", ".opus", ".png", ".jpg", ".jpeg",
              ".bmp", ".webp", ".tiff", ".gif"}


class ScenePanelPage(BaseQtPanel, TaskPanelMixin):
    """场景化一键处理页。"""

    panel_key = "scene"

    # ── UI ──────────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("场景化一键处理", "Scene Convert")))
        lay.addWidget(CaptionLabel(
            tr("按使用场景自动匹配格式参数：发抖音 / 发微信 / 发邮件…",
               "Pick a scene, parameters auto-match: Douyin / WeChat / Mail…")))

        from gui_qt.components.form_widgets import FormSection
        sec = FormSection(tr("场景选择", "Scene"), FluentIcon.ALBUM)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(CaptionLabel(tr("使用场景", "Scene")))
        self.cb_scene = ComboBox()
        from core.scene import scene_labels
        self.cb_scene.addItems(scene_labels())
        row.addWidget(self.cb_scene, 1)
        self.lb_hint = CaptionLabel("")
        self.lb_hint.setStyleSheet(
            f"font-size: 12px; color: {self._ink_sec()};")
        row.addWidget(self.lb_hint)
        sec.add_layout(row)
        lay.addWidget(sec)

        self.file_card = FileListCard(tr("媒体文件", "Media files"),
                                      file_exts=MEDIA_EXTS)
        lay.addWidget(self.file_card)

        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        lay.addWidget(self.out_row)

        self.action_bar = ActionBar(tr("开始处理", "Convert"))
        lay.addWidget(self.action_bar)

        self.services.task_manager.register_runner(
            "scene", lambda task: self._runner)
        self._wire_tasks()

    def _ink_sec(self):
        from gui_qt.components import design_system as ds
        return ds.ink_sec()

    # ── 参数/任务 ───────────────────────────────
    def _scene_key(self):
        from core.scene import SCENE_KEYS
        return SCENE_KEYS[self.cb_scene.currentIndex()]

    def collect_params(self) -> dict:
        return {
            "scene": self._scene_key(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def _runner(self, task, prog):
        from core.scene import convert_scene
        return convert_scene(task.file_path, task.output_path,
                             task.params.get("scene", "wechat"),
                             progress_cb=prog)

    def _make_task(self, f):
        params = self.collect_params()
        from core.scene import scene_output_ext
        ext = scene_output_ext(f, params["scene"])
        out = os.path.join(self.out_row.resolve_dir(f),
                           os.path.splitext(os.path.basename(f))[0]
                           + f"_{params['scene']}" + ext)
        return dict(
            name=f"{tr('场景处理', 'Scene')} - {os.path.basename(f)}",
            task_type="scene", file_path=f, output_path=out,
            params=params, runner=self._runner,
            history_type=tr("场景化处理", "Scene Convert"),
            history_target=self._scene_key(), need_ffmpeg=True,
            runner_key="scene")

    def _start(self):
        self._submit_files()

    def _empty_hint(self):
        return tr("请先添加要处理的文件", "Add media files first")

    def collect_prefs(self) -> dict:
        """记忆场景选择，重进面板自动恢复。"""
        return {"scene": self.cb_scene.currentIndex()}

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        idx = prefs.get("scene")
        if isinstance(idx, int) and 0 <= idx < self.cb_scene.count():
            self.cb_scene.setCurrentIndex(idx)

