"""task_mixin — 面板任务提交/进度联动的通用混入。

阶段2 起各转换面板共享同一套「文件列表 + TaskManager」联动逻辑：
- _wire_tasks()：接入 TaskManager 信号
- _submit_files()：公共校验 + 逐文件入队
- _on_progress / _on_state / _cancel_all：进度、状态与按钮恢复
混入方需提供：self.services / self.file_card / self.action_bar / self.out_row，
并实现 _make_task(f) 返回入队 kwargs（name/task_type/output_path/runner 等）。
"""
import os

from gui_qt import task_manager as tm
from gui_qt.i18n import tr
from gui_qt.components import toast
from gui_qt.widgets import OutputDirRow


class TaskPanelMixin:
    """文件列表型转换面板的通用任务逻辑。"""

    def _wire_tasks(self):
        mgr = self.services.task_manager
        mgr.sig_progress.connect(self._on_progress)
        mgr.sig_state.connect(self._on_state)
        self.action_bar.btn_go.clicked.connect(self._start)
        self.action_bar.btn_cancel.clicked.connect(self._cancel_all)
        self._task_rows = {}   # task_id -> (file_path, row)

    # ── 子类实现 ─────────────────────────────────
    def _make_task(self, f: str) -> dict:
        """返回 mgr.add_task 的 kwargs（name/task_type/output_path/runner…）。"""
        raise NotImplementedError

    def _empty_hint(self) -> str:
        return "请先添加要处理的文件"

    # ── 提交 ─────────────────────────────────────
    def _submit_files(self):
        """公共提交流程；成功入队至少 1 个任务返回 True。"""
        files = self.file_card.files()
        if not files:
            toast.show_warning(self, self._empty_hint())
            return False
        if not self.services.ffmpeg_ready():
            toast.show_error(self, tr("FFmpeg 未就绪，请稍后重试", "FFmpeg not ready"))
            return False
        if self.out_row.mode() == OutputDirRow.MODE_CUSTOM and not self.out_row.path():
            toast.show_warning(self, tr("请先选择自定义输出目录", "Choose an output folder first"))
            return False

        self.save_prefs()
        mgr = self.services.task_manager
        # 从偏好读取失败重试次数（设置中心可配置）
        max_retries = int(self.services.get_pref("max_retries", 0) or 0)
        added = 0
        for f in files:
            kwargs = self._make_task(f)
            if kwargs is None:
                continue
            kwargs.setdefault("max_retries", max_retries)
            tid = mgr.add_task(**kwargs)
            if tid is not None:
                self._task_rows[tid] = (f, self.file_card.row_of_file(f))
                added += 1
        if added:
            self.action_bar.set_running(True)
            self.action_bar.set_status(f"已提交 {added} 个任务")
            return True
        toast.show_error(self, "任务提交失败：FFmpeg 未就绪")
        return False

    def _cancel_all(self):
        mgr = self.services.task_manager
        for tid in list(self._task_rows):
            mgr.cancel_task(tid)
        self.action_bar.btn_cancel.setEnabled(False)

    # ── 进度/状态联动 ────────────────────────────
    def _on_progress(self, task_id, pct, msg, speed):
        row = self._task_rows.get(task_id)
        if not row:
            return
        _file, idx = row
        # 终态后忽略迟到的进度信号
        task = self.services.task_manager.get_task(task_id)
        if task and task.state in (tm.SUCCESS, tm.FAILED, tm.CANCELLED):
            return
        self.file_card.set_row_progress(idx, pct)
        self.action_bar.set_status(msg)
        self._update_total()

    def _on_state(self, task_id, state):
        row = self._task_rows.get(task_id)
        if row:
            _file, idx = row
            if state in (tm.SUCCESS, tm.FAILED, tm.CANCELLED):
                # 终态：移除行内进度条，改为显示状态文字（成功/失败/取消）
                self.file_card.set_row_progress(idx, -1,
                                                tm.state_text(state))
            self.file_card.set_row_state(idx, tm.state_text(state))
        task = self.services.task_manager.get_task(task_id)
        if state == tm.SUCCESS and task:
            toast.show_success(self, f"处理完成：{os.path.basename(task.file_path)}")
        elif state == tm.FAILED and task:
            toast.show_error(self,
                             f"处理失败：{os.path.basename(task.file_path)}"
                             f"（{task.error or '未知错误'}）")
        if state in (tm.SUCCESS, tm.FAILED, tm.CANCELLED):
            self._task_rows.pop(task_id, None)
            self._update_total()
        active = [self.services.task_manager.get_task(t)
                  for t in self._task_rows]
        if not any(t and t.state in (tm.WAITING, tm.RUNNING, tm.PAUSED)
                   for t in active):
            self.action_bar.set_running(False)

    def _update_total(self):
        tasks = [self.services.task_manager.get_task(t) for t in self._task_rows]
        tasks = [t for t in tasks if t]
        if not tasks:
            return
        self.action_bar.set_total(sum(t.progress for t in tasks) // len(tasks))
