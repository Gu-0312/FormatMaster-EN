"""recent_tasks_table — 首页「最近任务」表格（按参考截图设计）。

表头：文件 → 格式 | 状态 | 时间。行内展示文件名 / 目标格式 /
状态徽章 / 时间。底部操作行：「打开历史记录」「清空列表」。
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                               QWidget)
from qfluentwidgets import CaptionLabel

from gui_qt.components import design_system as ds
from gui_qt.components.card import Card

# 状态 → 颜色 / 文字
_STATE_STYLE = {
    "success":   ("#2FC99A", "成功"),
    "failed":    ("#F26D6D", "失败"),
    "running":   ("#38BDF8", "处理中"),
    "waiting":   ("#F0A63A", "等待中"),
    "paused":    ("#F0A63A", "已暂停"),
    "cancelled": ("#9BA1B4", "已取消"),
}
_DEFAULT = ("#9BA1B4", "未知")


def _fmt_ext(task):
    """从输出路径推断目标格式（大写，无点）。"""
    try:
        ext = os.path.splitext(task.output_path)[1].lstrip(".").upper()
        return ext or "—"
    except Exception:
        return "—"


def _time_str(ts):
    """把 float 时间戳转 '今天 HH:MM' 或 'MM-DD HH:MM'。"""
    import datetime
    try:
        dt = datetime.datetime.fromtimestamp(float(ts))
    except Exception:
        return ""
    today = datetime.date.today()
    hhmm = dt.strftime("%H:%M")
    if dt.date() == today:
        return f"今天 {hhmm}"
    return dt.strftime("%m-%d %H:%M")


class RecentTasksTable(Card):
    """最近任务表格卡。"""

    def __init__(self, parent=None):
        super().__init__(parent, radius=12)
        self._rows = []
        self._empty_widget = None

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 16, 16, 12)
        v.setSpacing(6)

        # 标题 —— L2 区块标题 15px/700
        header = QHBoxLayout()
        title = QLabel("最近任务")
        title.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {ds.ink()};"
            "border: none; background: transparent;")
        header.addWidget(title)
        header.addStretch(1)
        v.addLayout(header)

        # 表头行
        self._add_header(v)

        self.list_box = QVBoxLayout()
        self.list_box.setSpacing(2)
        v.addLayout(self.list_box)

        # 底部操作行
        footer = QHBoxLayout()
        footer.addStretch(1)
        self.btn_history = QPushButton("打开历史记录", self)
        self.btn_history.setStyleSheet(
            "font-size: 12px; background: transparent; color: %s;"
            "border: none; padding: 4px 8px;"
            "font-weight: 600;" % ds.accent())
        self.btn_history.setCursor(Qt.PointingHandCursor)
        footer.addWidget(self.btn_history)
        self.btn_clear = QPushButton("清空列表", self)
        self.btn_clear.setStyleSheet(
            "font-size: 12px; background: transparent; color: %s;"
            "border: none; padding: 4px 8px;" % ds.ink_sec())
        self.btn_clear.setCursor(Qt.PointingHandCursor)
        footer.addWidget(self.btn_clear)
        v.addLayout(footer)

    def _clear_list(self):
        """彻底清空 list_box：所有动态子项 + stretch，供重建。"""
        while self.list_box.count():
            item = self.list_box.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            elif item.spacerItem() is not None:
                pass
        self._rows = []
        self._empty_widget = None

    def _add_header(self, v):
        h = QHBoxLayout()
        h.setContentsMargins(12, 0, 12, 0)
        h.setSpacing(10)
        for text, stretch in (("文件", 1), ("格式", 0), ("状态", 0), ("时间", 0)):
            lbl = CaptionLabel(text, self)
            lbl.setStyleSheet(
                f"font-size: 11px; color: {ds.ink_dis()}; font-weight: 600;"
                "border: none; background: transparent;")
            if stretch:
                h.addWidget(lbl, 1)
            else:
                lbl.setFixedWidth(56)
                h.addWidget(lbl)
        v.addLayout(h)

    def set_tasks(self, tasks):
        self._clear_list()
        tasks = tasks or []
        if not tasks:
            self._empty_widget = self._empty_hint()
            self.list_box.addWidget(self._empty_widget)
            return
        for task in tasks[:6]:
            row = _TaskTableRow(task, self)
            self._rows.append(row)
            self.list_box.addWidget(row)
        # 底部留白，让内容区不挤压卡片高度
        self.list_box.addStretch(1)

    def _empty_hint(self):
        box = QWidget(self)
        box.setFixedHeight(64)
        from PySide6.QtWidgets import QHBoxLayout as _QHL
        from qfluentwidgets import FluentIcon, IconWidget
        lay = _QHL(box)
        lay.setSpacing(8)
        icon = IconWidget(FluentIcon.ACCEPT, box)
        icon.setFixedSize(16, 16)
        icon.setStyleSheet(f"color: {ds.ink_dis()};")
        lbl = CaptionLabel("暂无任务记录，完成一次转换后会自动显示在这里", box)
        lbl.setStyleSheet(
            f"font-size: 12px; color: {ds.ink_dis()};"
            "border: none; background: transparent;")
        lay.addStretch(1)
        lay.addWidget(icon)
        lay.addWidget(lbl)
        lay.addStretch(1)
        return box


class _TaskTableRow(QWidget):
    """单行任务：文件 | 格式 | 状态 | 时间。"""

    def __init__(self, task, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)

        h = QHBoxLayout(self)
        h.setContentsMargins(12, 4, 12, 4)
        h.setSpacing(10)

        name = os.path.basename(task.file_path) if task.file_path else task.name
        if len(name) > 30:
            name = name[:29] + "…"
        self.name_label = CaptionLabel(name, self)
        self.name_label.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {ds.ink()};"
            "border: none; background: transparent;")
        h.addWidget(self.name_label, 1)

        ext = _fmt_ext(task)
        self.ext_label = CaptionLabel(ext, self)
        self.ext_label.setFixedWidth(56)
        self.ext_label.setStyleSheet(
            f"font-size: 12px; color: {ds.ink_sec()};"
            "border: none; background: transparent;")
        h.addWidget(self.ext_label)

        color, text = _STATE_STYLE.get(task.state, _DEFAULT)
        self.status_label = CaptionLabel(text, self)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFixedWidth(56)
        self.status_label.setFixedHeight(22)
        self.status_label.setStyleSheet(
            f"font-size: 11px; font-weight: 700; color: {color};"
            f"background: {ds.with_alpha(color, 14)};"
            "border-radius: 11px; padding: 2px 4px;")
        h.addWidget(self.status_label)

        self.time_label = CaptionLabel(_time_str(task.created_at) or "—", self)
        self.time_label.setFixedWidth(72)
        self.time_label.setStyleSheet(
            f"font-size: 11px; color: {ds.ink_dis()};"
            "border: none; background: transparent;")
        h.addWidget(self.time_label)

    def enterEvent(self, e):
        self.setStyleSheet(
            f"background: {ds.tokens()['card_hover']}; border-radius: 8px;")
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.setStyleSheet("background: transparent;")
        super().leaveEvent(e)
