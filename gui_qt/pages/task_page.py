"""task_page — 任务中心（Prism 设计系统）。

任务列表（task_card：进度/速度/状态/暂停/取消）+ 底部只读日志流。
空态时显示引导提示。
"""
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QVBoxLayout, QWidget)
from qfluentwidgets import (CaptionLabel, FluentIcon, ScrollArea, TextBrowser)

from gui_qt import task_manager as tm
from gui_qt.i18n import tr
from gui_qt.components import design_system as ds
from gui_qt.components.card import Card
from gui_qt.components.empty_state import EmptyState
from gui_qt.components.page_header import PageHeader
from gui_qt.components.task_card import TaskCard


class TaskPage(ScrollArea):
    """任务中心页。"""

    def __init__(self, window, services, parent=None):
        super().__init__(parent)
        self.setObjectName("tasks")
        self.main_window = window
        self.services = services
        self.setWidgetResizable(True)
        self.setViewportMargins(0, 0, 0, 0)

        content = QWidget()
        v = QVBoxLayout(content)
        v.setContentsMargins(24, 20, 24, 24)
        v.setSpacing(14)
        self.setWidget(content)
        content.setAutoFillBackground(False)

        # ── 页面标题 ───────────────────────────────
        v.addWidget(PageHeader(
            tr("任务中心", "Tasks"), tr("管理所有进行中、等待中和已完成的任务", "Manage all running, waiting and finished tasks"),
            icon=FluentIcon.CHECKBOX))

        # ── 任务列表章节头 ─────────────────────────
        list_header = QWidget()
        list_header.setStyleSheet("background: transparent;")
        lh = QHBoxLayout(list_header)
        lh.setContentsMargins(4, 0, 4, 0)
        lh.setSpacing(8)
        self.list_title = CaptionLabel(tr("任务列表", "Task list"))
        self.list_title.setStyleSheet(
            f"font-size: 13px; font-weight: 600;")
        lh.addWidget(self.list_title)
        lh.addStretch(1)
        v.addWidget(list_header)

        # ── 空态 ───────────────────────────────────
        self.empty_widget = QWidget()
        empty_layout = EmptyState(
            icon=FluentIcon.PLAY, title=tr("暂无任务", "No tasks"),
            desc=tr("去「视频转换」或「音频转换」面板添加一个转换任务吧", "Add a task in the Video or Audio panel"),
            btn_text=tr("前往视频转换", "Go to Video Convert"),
            btn_clicked=lambda: self._goto("video"))
        self.empty_widget.setLayout(empty_layout)
        v.addWidget(self.empty_widget, 1)

        # ── 任务列表 ───────────────────────────────
        self.list_layout = QVBoxLayout()
        self.list_layout.setSpacing(10)
        v.addLayout(self.list_layout)

        # ── 日志 ───────────────────────────────────
        log_card = Card()
        lc = QVBoxLayout(log_card)
        lc.setContentsMargins(18, 14, 18, 14)
        lc.setSpacing(10)
        log_title = CaptionLabel(tr("运行日志", "Run log"))
        log_title.setStyleSheet(
            f"font-size: 13px; font-weight: 600;")
        lc.addWidget(log_title)
        self.log_view = TextBrowser()
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        self.log_view.setFixedHeight(190)
        # 环形日志缓冲：超过 1000 行自动丢弃最旧行，防止长期运行
        # 导致 QTextDocument 无限增长（日志流是后台内存累积点之一）
        self.log_view.document().setMaximumBlockCount(1000)
        self.log_view.setPlaceholderText(tr("任务日志将在此显示…", "Task log will appear here…"))
        lc.addWidget(self.log_view)
        v.addWidget(log_card)

        self._cards = {}   # task_id -> TaskCard
        mgr = services.task_manager
        mgr.sig_progress.connect(self._on_progress)
        mgr.sig_state.connect(self._on_state)
        mgr.sig_log.connect(self._on_log)
        mgr.sig_task_pruned.connect(self._on_task_pruned)
        self._sync_empty()

    # ── 信号处理 ─────────────────────────────────
    def _on_progress(self, task_id, pct, msg, speed):
        card = self._cards.get(task_id)
        if card is not None:
            card.on_progress(pct, msg, speed)

    def _on_state(self, task_id, state):
        if state == tm.WAITING and task_id not in self._cards:
            task = self.services.task_manager.get_task(task_id)
            if task is not None:
                self._add_card(task)
        card = self._cards.get(task_id)
        if card is not None:
            card.on_state(state)
        self._sync_empty()

    def _on_log(self, msg, level):
        """日志行富文本着色（TextBrowser）：时间戳灰、info 普通、
        success 绿 / warning 橙 / error 红。"""
        ts = time.strftime("%H:%M:%S")
        color = {"success": "#2FC99A", "warning": "#F0A63A",
                 "error": "#F26D6D"}.get(level, "#9AA3B8")
        self.log_view.append(
            f'<span style="color:{color}">[{ts}] {msg}</span>')

    def _on_task_pruned(self, task_id):
        """任务记录被 TaskManager 清理：同步移除对应卡片并释放 widget。"""
        card = self._cards.pop(task_id, None)
        if card is not None:
            self.list_layout.removeWidget(card)
            card.deleteLater()
        self._sync_empty()

    # ── 卡片管理 ─────────────────────────────────
    def _add_card(self, task):
        card = TaskCard(task)
        card.wire(on_pause=self._toggle_pause,
                  on_cancel=self.services.task_manager.cancel_task,
                  on_retry=self._retry_task)
        self._cards[task.task_id] = card
        self.list_layout.addWidget(card)

    def _retry_task(self, task_id):
        self.services.task_manager.retry_task(task_id)

    def _toggle_pause(self, task_id):
        mgr = self.services.task_manager
        task = mgr.get_task(task_id)
        if task is None:
            return
        if task.state == tm.PAUSED:
            mgr.resume_task(task_id)
        else:
            mgr.pause_task(task_id)

    def _sync_empty(self):
        has = bool(self._cards)
        self.empty_widget.setVisible(not has)

    def _goto(self, nav_key):
        pages = getattr(self.main_window, "pages", {})
        page = pages.get(nav_key)
        if page is not None:
            self.main_window.switchTo(page)

    def showEvent(self, e):
        mgr = self.services.task_manager
        for task in mgr.all_tasks():
            if task.task_id not in self._cards:
                self._add_card(task)
        self._sync_empty()
        super().showEvent(e)
