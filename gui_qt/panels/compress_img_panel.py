"""compress_img_panel — 图片压缩面板（阶段2 迁移自 gui/panels/compress_img_panel.py）。

批量压缩图片体积，保持格式不变，支持限制最大分辨率。
任务经 TaskManager 通用链路执行 core.tools.image_compress（不依赖 FFmpeg）。
"""
import os

from qfluentwidgets import CaptionLabel, ComboBox, FluentIcon

from core.tools import image_compress
from gui_qt import task_manager as tm
from gui_qt.i18n import tr
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow

# 预置值（与 tkinter 版 compress_img_panel 一致）
QUALITY_VALUES = ["95", "85", "75", "60", "50", "40", "30"]
SIZE_VALUES = [tr("不限制", "No limit"), "1920x1080", "1280x720", "800x600"]
TARGET_KB_VALUES = ["100", "200", "500", "1024", "2048", "5120"]

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"}


class CompressImgPanelPage(BaseQtPanel, TaskPanelMixin):
    """图片压缩页。"""

    panel_key = "image_compress"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("图片压缩", "Image compress")))
        lay.addWidget(CaptionLabel(
            tr("批量压缩图片体积，保持格式不变，支持限制最大分辨率", "Batch compress images keeping format, with optional max resolution")))

        self.file_card = FileListCard(tr("文件列表", "Files"), file_exts=IMAGE_EXTS)
        lay.addWidget(self.file_card)

        from gui_qt.components.form_widgets import FormSection, FormGrid
        sec = FormSection(tr("压缩设置", "Compress settings"), FluentIcon.ZIP_FOLDER)
        grid = FormGrid(columns=2)

        self.cb_q = grid.add_field(
            tr("输出质量", "Output quality"), self._combo(QUALITY_VALUES, "75"),
            hint=tr("压缩后图片质量，数值越低体积越小", "Output quality, lower = smaller file"))
        self.cb_sz = grid.add_field(
            tr("最大分辨率", "Max resolution"), self._combo(SIZE_VALUES, tr("不限制", "No limit")),
            hint=tr("限制输出图片的最大分辨率", "Limit max output resolution"))
        sec.add_form(grid)
        lay.addWidget(sec)

        # 压缩模式：按质量 / 按目标大小（SegmentedWidget 分段切换）
        from qfluentwidgets import SegmentedWidget
        self.seg_mode = SegmentedWidget(self)
        self.seg_mode.addItem("quality", tr("按质量压缩", "By quality"))
        self.seg_mode.addItem("target", tr("按目标大小", "By target size"))
        self.seg_mode.setCurrentItem("quality")
        self.seg_mode.currentItemChanged.connect(self._on_mode_changed)
        self.seg_mode.setFixedHeight(32)
        lay.addWidget(self.seg_mode)
        self._mode = "quality"  # 当前模式（currentItemChanged 信号携带 key）
        from PySide6.QtWidgets import QHBoxLayout, QWidget
        self._target_row = QWidget()
        tr_lay = QHBoxLayout(self._target_row)
        tr_lay.setContentsMargins(0, 0, 0, 0)
        tr_lay.setSpacing(8)
        self.cb_target = self._combo(TARGET_KB_VALUES, "500")
        self.cb_target.setFixedWidth(140)
        tr_lay.addWidget(self.cb_target)
        tr_lay.addWidget(CaptionLabel(
            tr("KB（5120 = 5MB）", "KB (5120 = 5MB)")))
        tr_lay.addStretch(1)
        lay.addWidget(self._target_row)
        self._target_row.setVisible(False)

        out_card = FormSection(tr("输出目录", "Output folder"), FluentIcon.FOLDER)
        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        out_card.add_widget(self.out_row)
        lay.addWidget(out_card)

        self.action_bar = ActionBar(tr("开始压缩", "Compress"))
        lay.addWidget(self.action_bar)

        self._wire_tasks()

    def _combo(self, items, default):
        cb = ComboBox()
        cb.addItems(items)
        cb.setCurrentText(default)
        return cb

    def _on_mode_changed(self, key: str):
        """模式切换：target=目标大小（展开 KB 行+置灰质量/分辨率），quality=恢复。"""
        self._mode = key
        on = key == "target"
        self._target_row.setVisible(on)
        for w in (self.cb_q, self.cb_sz):
            w.setEnabled(not on)

    def _target_kb(self):
        if self._mode != "target":
            return None
        try:
            return int(self.cb_target.currentText())
        except ValueError:
            return None

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        return {
            "quality": self.cb_q.currentText(),
            "size": self.cb_sz.currentText(),
            "target_kb": self._target_kb(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def collect_prefs(self) -> dict:
        return {
            "quality": self.cb_q.currentText(),
            "size": self.cb_sz.currentText(),
            "target_kb": self._target_kb(),
            "target_on": self._mode == "target",
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        if prefs.get("quality") in QUALITY_VALUES:
            self.cb_q.setCurrentText(prefs["quality"])
        if prefs.get("size") in SIZE_VALUES:
            self.cb_sz.setCurrentText(prefs["size"])
        if prefs.get("target_kb") in TARGET_KB_VALUES:
            self.cb_target.setCurrentText(str(prefs["target_kb"]))
        if prefs.get("target_on"):
            # setCurrentItem 触发 currentItemChanged → _on_mode_changed 自动生效
            self.seg_mode.setCurrentItem("target")
            self._target_row.setVisible(True)
            self.cb_q.setEnabled(False)
            self.cb_sz.setEnabled(False)
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务执行器 ───────────────────────────────
    def _runner(self, task, prog):
        p = task.params
        tkb = p.get("target_kb")
        if tkb:
            from core.tools import image_compress_to_size
            ok, msg, _size = image_compress_to_size(
                task.file_path, task.output_path, int(tkb), prog)
            if not ok:
                task.error = msg or tr("压缩失败", "Compress failed")
                return False
            return True
        q = int(p.get("quality", "75"))
        sz_str = p.get("size", tr("不限制", "No limit"))
        max_sz = None
        if sz_str != tr("不限制", "No limit"):
            w, h = sz_str.split("x")
            max_sz = (int(w), int(h))
        return image_compress(task.file_path, task.output_path,
                              q, max_sz, prog)

    def _make_task(self, f):
        params = self.collect_params()
        nm = os.path.splitext(os.path.basename(f))[0]
        ext = os.path.splitext(f)[1]
        out_dir = self.out_row.resolve_dir(f)
        # 统一走 make_output_path：应用冲突策略（自动改名/覆盖）+ 源目同路径保护
        out_path = tm.make_output_path(f, out_dir, ext, name=nm + "_compressed")
        return dict(
            name=f"{tr('图片压缩', 'Image Compress')} - {os.path.basename(f)}",
            task_type="compress_img", file_path=f, output_path=out_path,
            params=params, runner=self._runner,
            history_type=tr("图片压缩", "Image Compress"),
            history_target=(
                tr("至 {}KB", "to {}KB").format(params.get("target_kb"))
                if params.get("target_kb") else params["quality"]),
            need_ffmpeg=False)

    def _start(self):
        self._submit_files()

    def _empty_hint(self):
        return tr("请先添加要压缩的图片", "Add images to compress first")
