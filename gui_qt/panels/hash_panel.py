"""hash_panel — 哈希校验面板（阶段2 迁移自 gui/panels/hash_panel.py）。

计算文件 MD5/SHA1/SHA256/SHA512 哈希值（core.hash_tool，纯标准库），
支持批量计算、哈希对比验证、复制与导出 CSV/TXT。
任务经 TaskManager 通用链路逐文件执行（output_path 为空，need_ffmpeg=False）。
"""
import os

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFileDialog, QHBoxLayout
from qfluentwidgets import (FluentIcon, CaptionLabel, ComboBox, LineEdit,
                            PushButton, TextEdit)

from gui_qt.i18n import tr
from gui_qt.components import toast
from gui_qt.components.form_widgets import FormGrid, FormSection
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt import task_manager as tm
from gui_qt.widgets import ActionBar, FileListCard

ALGO_VALUES = ["MD5", "SHA1", "SHA256", "SHA512"]


class _NoOutRow:
    """哈希计算无输出目录；为复用 mixin 校验提供的轻量替身。"""

    MODE_CUSTOM = "custom"

    def mode(self):
        return "same"

    def path(self):
        return ""


class HashPanelPage(BaseQtPanel, TaskPanelMixin):
    """哈希校验页。"""

    panel_key = "hash"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("哈希校验", "Hash check")))
        lay.addWidget(CaptionLabel(
            tr("计算文件 MD5/SHA1/SHA256/SHA512 哈希值，支持对比验证", "Compute MD5/SHA1/SHA256/SHA512 hashes with verification")))

        self.file_card = FileListCard(tr("文件列表", "Files"))  # 不限扩展名
        lay.addWidget(self.file_card)

        # 哈希设置
        sec = FormSection(tr("哈希设置", "Hash settings"), FluentIcon.CODE)
        grid = FormGrid(columns=1)
        self.cb_algo = grid.add_field(
            tr("算法", "Algorithm"), self._algo_combo(),
            hint="MD5 / SHA1 / SHA256 / SHA512")
        sec.add_form(grid)

        # 验证行：哈希输入 + 验证按钮 + 结果提示
        vrow = QHBoxLayout()
        vrow.setContentsMargins(0, 0, 0, 0)
        vrow.setSpacing(8)
        vrow.addWidget(CaptionLabel(tr("验证哈希", "Verify hash")))
        self.ed_verify = LineEdit()
        self.ed_verify.setPlaceholderText(tr("粘贴期望的哈希值进行比对（对首个文件）", "Paste expected hash to compare (first file)"))
        vrow.addWidget(self.ed_verify, 1)
        btn_verify = PushButton(tr("验证", "Verify"))
        btn_verify.clicked.connect(self._verify)
        vrow.addWidget(btn_verify)
        self.lb_verify = CaptionLabel("")
        vrow.addWidget(self.lb_verify)
        sec.add_layout(vrow)
        lay.addWidget(sec)

        # 计算结果区
        res_card = FormSection(tr("计算结果", "Results"), FluentIcon.INFO)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(8)
        head.addStretch(1)
        btn_copy = PushButton(tr("复制", "Copy"))
        btn_copy.clicked.connect(self._copy_result)
        btn_txt = PushButton(tr("导出TXT", "Export TXT"))
        btn_txt.clicked.connect(lambda: self._export("txt"))
        btn_csv = PushButton(tr("导出CSV", "Export CSV"))
        btn_csv.clicked.connect(lambda: self._export("csv"))
        head.addWidget(btn_copy)
        head.addWidget(btn_txt)
        head.addWidget(btn_csv)
        res_card.add_layout(head)
        self.txt_result = TextEdit()
        self.txt_result.setReadOnly(True)
        self.txt_result.setMinimumHeight(120)
        self.txt_result.setPlaceholderText(tr("计算完成后在此显示哈希值…", "Hash values will show here after computing…"))
        from gui_qt.components import design_system as _ds
        _ds.apply_text_edit_style(self.txt_result)
        res_card.add_widget(self.txt_result)
        lay.addWidget(res_card)

        self.action_bar = ActionBar(tr("开始计算", "Compute"))
        lay.addWidget(self.action_bar)

        self.out_row = _NoOutRow()
        self._results = {}     # file_path -> hex hash
        self._wire_tasks()

    def _algo_combo(self):
        cb = ComboBox()
        cb.addItems(ALGO_VALUES)
        cb.setCurrentText("SHA256")
        return cb

    # ── 提交流程（哈希不依赖 FFmpeg，覆盖 mixin 的 FFmpeg 校验）──
    def _submit_files(self):
        files = self.file_card.files()
        if not files:
            toast.show_warning(self, self._empty_hint())
            return False
        self.save_prefs()
        self._results = {}
        self.txt_result.clear()
        mgr = self.services.task_manager
        added = 0
        for f in files:
            kwargs = self._make_task(f)
            if kwargs is None:
                continue
            tid = mgr.add_task(**kwargs)
            if tid is not None:
                self._task_rows[tid] = (f, self.file_card.row_of_file(f))
                added += 1
        if added:
            self.action_bar.set_running(True)
            self.action_bar.set_status(tr("已提交 {} 个任务", "Submitted {} tasks").format(added))
            return True
        toast.show_error(self, tr("任务提交失败", "Submit failed"))
        return False

    # ── 验证 ─────────────────────────────────────
    def _verify(self):
        expected = self.ed_verify.text().strip()
        if not expected:
            self.lb_verify.setText(tr("请输入哈希值", "Enter a hash value"))
            return
        files = self.file_card.files()
        if not files:
            self.lb_verify.setText(tr("请先添加文件", "Add files first"))
            return
        from core.hash_tool import verify_hash
        ok, _computed = verify_hash(files[0], expected,
                                    self.cb_algo.currentText())
        if ok:
            self.lb_verify.setText(tr("✓ 哈希匹配！", "✓ Hash matches!"))
        else:
            self.lb_verify.setText(tr("✗ 不匹配", "✗ No match"))

    # ── 结果操作 ─────────────────────────────────
    def _copy_result(self):
        text = self.txt_result.toPlainText().strip()
        if text:
            QGuiApplication.clipboard().setText(text)
            toast.show_success(self, tr("已复制到剪贴板", "Copied to clipboard"))

    def _export(self, fmt):
        text = self.txt_result.toPlainText().strip()
        if not text:
            toast.show_warning(self, tr("暂无计算结果", "No results yet"))
            return
        if fmt == "csv":
            path, _ = QFileDialog.getSaveFileName(
                self, tr("导出CSV", "Export CSV"), "hash_result.csv", tr("CSV文件 (*.csv)", "CSV files (*.csv)"))
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, tr("导出TXT", "Export TXT"), "hash_result.txt", tr("文本文件 (*.txt)", "Text files (*.txt)"))
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                toast.show_success(self, tr("已导出至：{}", "Exported to: {}").format(os.path.basename(path)))
            except OSError as e:
                toast.show_error(self, tr("导出失败：{}", "Export failed: {}").format(e))

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        return {"algo": self.cb_algo.currentText()}

    def collect_prefs(self) -> dict:
        return self.collect_params()

    def apply_prefs(self, prefs: dict):
        if prefs and prefs.get("algo") in ALGO_VALUES:
            self.cb_algo.setCurrentText(prefs["algo"])

    # ── 任务执行器 ───────────────────────────────
    def _runner(self, task, prog):
        from core.hash_tool import compute_hash
        h = compute_hash(task.file_path, task.params.get("algo", "SHA256"), prog)
        if not h:
            task.error = tr("哈希计算失败", "Hash failed")
            return False
        self._results[task.file_path] = h
        return True

    def _make_task(self, f):
        algo = self.cb_algo.currentText()
        return dict(
            name=f"{tr('哈希计算', 'Hash')} - {os.path.basename(f)}",
            task_type="hash", file_path=f, output_path="",
            params={"algo": algo}, runner=self._runner,
            history_type=tr("哈希校验", "Hash Check"), history_target=algo,
            need_ffmpeg=False)

    def _start(self):
        self._submit_files()

    def _empty_hint(self):
        return tr("请先添加要计算哈希的文件", "Add files to hash first")

    # ── 状态联动：成功后重建结果文本 ────────────
    def _on_state(self, task_id, state):
        task = self.services.task_manager.get_task(task_id)
        if (task and task.task_type == "hash" and state == tm.SUCCESS
                and self._results):
            lines = [f"{h}  {os.path.basename(fp)}"
                     for fp, h in self._results.items()]
            self.txt_result.setPlainText("\n".join(lines))
        super()._on_state(task_id, state)
