"""history_page — 转换历史（Prism 设计系统）。

搜索 + 筛选 + 统计概览：顶部统计卡（总数/成功/失败/今日），
工具栏含搜索框、类型与结果筛选，表格展示记录。
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)
from qfluentwidgets import (CaptionLabel, ComboBox, FluentIcon, LineEdit,
                            PushButton, ScrollArea)

from gui_qt.components import toast
from gui_qt.components import design_system as ds
from gui_qt.components.card import Card
from gui_qt.components.empty_state import EmptyState
from gui_qt.components.page_header import PageHeader

_COLS = ["时间", "类型", "源文件", "目标格式", "结果"]
_RESULTS = ["全部", "成功", "失败"]


class _StatChip(Card):
    """顶部统计小卡片：数值 + 标题。"""

    def __init__(self, title, accent, parent=None):
        super().__init__(parent, radius=12)
        self.setMinimumHeight(64)
        from PySide6.QtWidgets import QVBoxLayout
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 10, 16, 10)
        v.setSpacing(2)
        self.value_label = CaptionLabel("0", self)
        self.value_label.setStyleSheet(
            f"font-size: 20px; font-weight: 700; color: {accent};"
            "border: none; background: transparent;")
        v.addWidget(self.value_label)
        self.title_label = CaptionLabel(title, self)
        self.title_label.setStyleSheet(
            f"font-size: 11px; color: {ds.ink_sec()};"
            "border: none; background: transparent;")
        v.addWidget(self.title_label)

    def set_value(self, v):
        self.value_label.setText(str(v))


class HistoryPage(ScrollArea):
    """转换历史页：搜索 + 筛选 + 统计。"""

    def __init__(self, window, services, parent=None):
        super().__init__(parent)
        self.setObjectName("history")
        self.window = window
        self.services = services
        self._all_records = []
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
            "转换历史", "搜索、筛选并统计所有转换记录",
            icon=FluentIcon.HISTORY))

        # ── 统计概览 ───────────────────────────────
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self.stat_total = _StatChip("累计转换", ds.accent())
        self.stat_ok = _StatChip("成功", ds.tokens()["success"])
        self.stat_fail = _StatChip("失败", ds.tokens()["error"])
        self.stat_today = _StatChip("今日转换", ds.tokens()["warn"])
        for c in (self.stat_total, self.stat_ok, self.stat_fail,
                  self.stat_today):
            stats_row.addWidget(c, 1)
        v.addLayout(stats_row)

        # ── 工具栏（搜索 + 筛选）──────────────────
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.search_edit = LineEdit(self)
        self.search_edit.setPlaceholderText("搜索文件名 / 类型…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._refresh)
        toolbar.addWidget(self.search_edit, 1)

        self.type_combo = ComboBox(self)
        self.type_combo.addItem("全部类型")
        self.type_combo.currentTextChanged.connect(self._refresh)
        toolbar.addWidget(self.type_combo)

        self.result_combo = ComboBox(self)
        self.result_combo.addItems(_RESULTS)
        self.result_combo.currentTextChanged.connect(self._refresh)
        toolbar.addWidget(self.result_combo)

        self.count_label = CaptionLabel("")
        self.count_label.setStyleSheet(
            f"font-size: 12px; color: {ds.ink_sec()};")
        toolbar.addWidget(self.count_label)

        self.btn_clear = PushButton(FluentIcon.DELETE, "清空历史")
        self.btn_clear.clicked.connect(self._clear)
        toolbar.addWidget(self.btn_clear)
        v.addLayout(toolbar)

        # ── 空态 ───────────────────────────────────
        self.empty_widget = QWidget()
        self.empty_widget.setLayout(EmptyState(
            icon=FluentIcon.HISTORY, title="暂无转换记录",
            desc="完成一次转换后，记录将在此显示",
            btn_text="前往视频转换",
            btn_clicked=lambda: self._goto("video")))
        v.addWidget(self.empty_widget, 1)

        # ── 表格 ───────────────────────────────────
        self.table = QTableWidget(0, len(_COLS))
        self.table.setHorizontalHeaderLabels(_COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        v.addWidget(self.table, 1)

        self._load_types()
        self._refresh()

    def _load_types(self):
        """从历史记录收集类型列表填充筛选下拉。"""
        seen = []
        for r in self.services.history.get_all():
            t = r.get("type", "")
            if t and t not in seen:
                seen.append(t)
        self.type_combo.blockSignals(True)
        self.type_combo.clear()
        self.type_combo.addItem("全部类型")
        self.type_combo.addItems(seen)
        self.type_combo.blockSignals(False)

    def _filtered(self):
        """按搜索词 + 类型 + 结果筛选记录。"""
        kw = self.search_edit.text().strip().lower()
        type_f = self.type_combo.currentText()
        result_f = self.result_combo.currentText()
        out = []
        for r in self._all_records:
            if kw:
                src = str(r.get("source", "")).lower()
                typ = str(r.get("type", "")).lower()
                tgt = str(r.get("target", "")).lower()
                if kw not in src and kw not in typ and kw not in tgt:
                    continue
            if type_f != "全部类型" and r.get("type") != type_f:
                continue
            if result_f == "成功" and r.get("status") != "success":
                continue
            if result_f == "失败" and r.get("status") == "success":
                continue
            out.append(r)
        return out

    def _refresh(self):
        records = self.services.history.get_all()
        self._all_records = records
        self._update_stats(records)
        filtered = self._filtered()

        self.table.setRowCount(0)
        for r in filtered:
            row = self.table.rowCount()
            self.table.insertRow(row)
            status = "成功" if r.get("status") == "success" else "失败"
            values = [r.get("time", ""), r.get("type", ""),
                      r.get("source", ""), r.get("target", ""), status]
            for c, val in enumerate(values):
                item = QTableWidgetItem(str(val))
                if c == 4:
                    t = ds.tokens()
                    fg = t["success"] if status == "成功" else t["error"]
                    item.setForeground(QColor(fg))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                elif c == 0:
                    item.setForeground(QColor(ds.ink_sec()))
                self.table.setItem(row, c, item)

        shown = len(filtered)
        total = len(records)
        self.count_label.setText(
            f"共 {total} 条" + (f"（筛选 {shown}）" if shown != total else ""))
        has = total > 0
        self.empty_widget.setVisible(not has)
        self.table.setVisible(has)

    def _update_stats(self, records):
        ok = sum(1 for r in records if r.get("status") == "success")
        fail = len(records) - ok
        today = __import__("datetime").date.today().isoformat()
        today_n = sum(1 for r in records
                      if str(r.get("time", ""))[:10] == today)
        self.stat_total.set_value(len(records))
        self.stat_ok.set_value(ok)
        self.stat_fail.set_value(fail)
        self.stat_today.set_value(today_n)

    def _clear(self):
        if self.table.rowCount() == 0:
            return
        self.services.history.clear()
        self._load_types()
        self._refresh()
        toast.show_success(self, "历史记录已清空")

    def _goto(self, nav_key):
        pages = getattr(self.window, "pages", {})
        page = pages.get(nav_key)
        if page is not None:
            self.window.switchTo(page)

    def showEvent(self, e):
        self._load_types()
        self._refresh()
        super().showEvent(e)
