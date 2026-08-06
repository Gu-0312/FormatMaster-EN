"""task_card — 任务行卡片（Prism 设计系统）。

任务中心列表项：类型图标 / 文件名 / 目标格式 / 进度条 / 实时速度 /
状态徽章 / 操作按钮（暂停/恢复/取消），随 TaskManager 信号刷新。
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, FluentIcon, IconWidget,
                            ProgressBar, ToolButton, TransparentToolButton)

from gui_qt.i18n import tr
from gui_qt.components.card import Card
from gui_qt.components import design_system as ds
from gui_qt import task_manager as tm


# Prism 色系状态徽章（背景 + 文字）
_BADGE_STYLE = {
    tm.WAITING:  ("#9AA0AC", "#FFFFFF"),
    tm.RUNNING:  ("#5B5BD6", "#FFFFFF"),
    tm.PAUSED:   ("#D98324", "#FFFFFF"),
    tm.SUCCESS:  ("#0FA47A", "#FFFFFF"),
    tm.FAILED:   ("#E5484D", "#FFFFFF"),
    tm.CANCELLED: ("#9AA0AC", "#FFFFFF"),
}

_TASK_ICONS = {
    "video": FluentIcon.VIDEO,
    "audio": FluentIcon.MUSIC,
    "image": FluentIcon.PHOTO,
    "pdf": FluentIcon.SCROLL,
    "doc": FluentIcon.DOCUMENT,
    "download": FluentIcon.DOWNLOAD,
    "ocr": FluentIcon.FONT,
    "hash": FluentIcon.FINGERPRINT,
    "qrcode": FluentIcon.QRCODE,
}

_TASK_COLORS = {
    "video": ("#0284C7", "#E0F2FE"),
    "audio": ("#8B5CF6", "#F3E8FF"),
    "image": ("#0FA47A", "#DDF5EC"),
    "pdf":   ("#D98324", "#FEF1DE"),
    "doc":   ("#D98324", "#FEF1DE"),
    "download": ("#EA7A23", "#FFF1E5"),
    "ocr":   ("#5B5BD6", "#EDEEFF"),
    "hash":  ("#5F6472", "#F0F1F5"),
    "qrcode": ("#0FA47A", "#DDF5EC"),
}


def _badge_qss(state):
    bg, fg = _BADGE_STYLE.get(state, _BADGE_STYLE[tm.WAITING])
    return f"""
        background: {bg};
        color: {fg};
        border-radius: 12px;
        padding: 3px 12px;
        font-size: 11px;
        font-weight: 600;
    """


class _TaskIconBox(QWidget):
    """带任务类型色系圆角背景的图标方块。"""

    def __init__(self, task_type, parent=None):
        super().__init__(parent)
        self._fg, self._bg = _TASK_COLORS.get(
            task_type, _TASK_COLORS["doc"])
        self.setFixedSize(42, 42)
        icon = _TASK_ICONS.get(task_type, FluentIcon.DOCUMENT)
        self._icon = IconWidget(icon, self)
        self._icon.setFixedSize(24, 24)
        self._icon.setStyleSheet(f"color: {self._fg};")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._icon, 0, Qt.AlignCenter)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing)
        bg = QColor(self._bg)
        p.setBrush(bg)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(self.rect(), 12, 12)


class TaskCard(Card):
    """单个任务的行卡片。"""

    def __init__(self, task, parent=None):
        super().__init__(parent)
        self.task = task

        h = QHBoxLayout(self)
        h.setContentsMargins(18, 14, 18, 14)
        h.setSpacing(14)

        self.icon_box = _TaskIconBox(task.task_type, self)
        h.addWidget(self.icon_box)

        # 左：文件名 + 格式 + 错误信息
        left = QVBoxLayout()
        left.setSpacing(3)
        self.name_label = BodyLabel(task.name, self)
        self.name_label.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {ds.ink()};")
        self.meta_label = CaptionLabel(self._meta_text(), self)
        self.meta_label.setStyleSheet(
            f"font-size: 11px; color: {ds.ink_sec()};")
        left.addWidget(self.name_label)
        left.addWidget(self.meta_label)
        left.setAlignment(Qt.AlignLeft)
        h.addLayout(left, 1)

        # 中：进度条 + 速度
        mid = QVBoxLayout()
        mid.setSpacing(4)
        self.bar = ProgressBar(self)
        self.bar.setRange(0, 100)
        self.bar.setValue(max(0, task.progress))
        self.bar.setMinimumWidth(340)
        self.bar.setMaximumWidth(560)
        self.bar.setFixedHeight(12)
        self.speed_label = CaptionLabel(task.speed or "", self)
        self.speed_label.setStyleSheet(
            f"font-size: 11px; color: {ds.ink_sec()};")
        mid.addWidget(self.bar)
        mid.addWidget(self.speed_label)
        mid.setAlignment(Qt.AlignRight)
        h.addLayout(mid, 1)

        # 右：状态徽章 + 操作按钮
        self.badge = CaptionLabel(tm.state_text(task.state), self)
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setFixedHeight(24)
        self.badge.setMinimumWidth(62)
        self.badge.setStyleSheet(_badge_qss(task.state))
        h.addWidget(self.badge)

        self.btn_pause = ToolButton(FluentIcon.PAUSE, self)
        self.btn_pause.setToolTip(tr("暂停", "Pause"))
        self.btn_cancel = TransparentToolButton(FluentIcon.CLOSE, self)
        self.btn_cancel.setToolTip(tr("取消", "Cancel"))
        h.addWidget(self.btn_pause)
        h.addWidget(self.btn_cancel)
        self._sync_buttons()

    def _meta_text(self):
        p = self.task.params
        fmt = p.get('fmt', '') or self.task.history_target
        base = fmt or tr("通用任务", "General task")
        return tr("{} · 优先级 {}", "{} · priority {}").format(base, self.task.priority)

    def _sync_buttons(self):
        s = self.task.state
        running_like = s in (tm.RUNNING, tm.PAUSED, tm.WAITING)
        self.btn_pause.setVisible(s in (tm.RUNNING, tm.PAUSED, tm.WAITING))
        self.btn_cancel.setVisible(running_like)
        if s == tm.PAUSED:
            self.btn_pause.setIcon(FluentIcon.PLAY)
            self.btn_pause.setToolTip(tr("恢复", "Resume"))
        else:
            self.btn_pause.setIcon(FluentIcon.PAUSE)
            self.btn_pause.setToolTip(tr("暂停", "Pause"))

    # ── 供页面连接的外部动作 ───────────────────────
    def wire(self, on_pause, on_cancel):
        """连接按钮动作；on_pause 由页面根据状态分发暂停/恢复。"""
        self.btn_pause.clicked.connect(lambda: on_pause(self.task.task_id))
        self.btn_cancel.clicked.connect(lambda: on_cancel(self.task.task_id))

    # ── 信号刷新 ─────────────────────────────────
    def on_progress(self, pct, msg, speed):
        if self.task.state in (tm.SUCCESS, tm.FAILED, tm.CANCELLED):
            return
        if pct >= 0:
            self.bar.setValue(pct)
        if speed:
            self.speed_label.setText(speed)

    def on_state(self, state):
        self.badge.setText(tm.state_text(state))
        self.badge.setStyleSheet(_badge_qss(state))
        if state == tm.FAILED and self.task.error:
            self.meta_label.setText(self.task.error)
        # 终态不清零：成功显示 100%，失败/取消保留已有进度便于回看
        if state == tm.SUCCESS:
            self.bar.setValue(100)
        self._sync_buttons()
