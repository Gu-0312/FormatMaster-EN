"""url_list_dialog — 收藏/历史链接列表对话框（download 与 m3u8 面板共用）。

v3 表格版：QTableWidget 四列——【时间 | 名称 | 链接 | 信息】，
时间显示在第一列（今天/昨天/完整日期+时分秒 美化），支持：
  - 点击表头排序（时间列按真实时间戳排序）
  - 双击或「使用」选中行
  - 「删除」单行、「清空」全部（二次确认）
  - 空态居中提示
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView,
                               QLabel, QStackedWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from qfluentwidgets import (BodyLabel, MessageBox, PrimaryPushButton,
                            PushButton, TableWidget)

from gui_qt.i18n import tr
from gui_qt.components import design_system as ds
from gui_qt.components.dialog import FluentDialogBase
from utils.format_helpers import format_datetime, format_size, format_time


class _TimeItem(QTableWidgetItem):
    """时间列单元格：显示美化文本，按完整时间戳排序。"""

    def __init__(self, text, ts):
        super().__init__(text)
        self.setData(Qt.UserRole, ts or "")
        self.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)

    def __lt__(self, other):
        a = self.data(Qt.UserRole) or ""
        b = other.data(Qt.UserRole) or ""
        return a < b


class UrlListDialog(FluentDialogBase):
    """收藏/历史链接表格对话框。

    items:   [{"url", "name", "size", "duration", "time", "note", ...}]
    use_fn(url, name): 点击「使用」或双击时的回调。
    kind:    "history" / "favorites"，决定空态文案。
    delete_fn(url): 删除单条（None 则不显示删除按钮）。
    clear_fn():     清空全部（None 则不显示清空按钮）。
    """

    def __init__(self, title, items, use_fn, parent=None, kind="history",
                 delete_fn=None, clear_fn=None):
        super().__init__(title, parent)
        self.resize(760, 460)
        self._items = list(items)
        self._use_fn = use_fn
        self._kind = kind
        self._delete_fn = delete_fn
        self._clear_fn = clear_fn

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # 标题行：标题 + 计数
        head = QHBoxLayout()
        head.setSpacing(8)
        self.title_lbl = BodyLabel(title)
        head.addWidget(self.title_lbl)
        self.count_lbl = QLabel(
            tr("共 {} 条", "{} items").format(len(self._items)))
        self.count_lbl.setStyleSheet(
            f"font-size: 11px border: none;"
            " background: transparent;")
        head.addWidget(self.count_lbl)
        head.addStretch(1)
        root.addLayout(head)

        # 表格 / 空态 切换
        self.stack = QStackedWidget()

        self.table = TableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([
            tr("时间", "Time"), tr("名称", "Name"),
            tr("链接", "Link"), tr("信息", "Info")])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Fixed)       # 时间
        hh.setSectionResizeMode(1, QHeaderView.Stretch)     # 名称
        hh.setSectionResizeMode(2, QHeaderView.Stretch)     # 链接
        hh.setSectionResizeMode(3, QHeaderView.Fixed)       # 信息
        self.table.setColumnWidth(0, 150)
        self.table.setColumnWidth(3, 220)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        self.table.cellDoubleClicked.connect(lambda *_: self._on_use())
        self.stack.addWidget(self.table)

        self.empty_lbl = QLabel(tr("暂无记录", "No records"))
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        self.empty_lbl.setStyleSheet(
            f"font-size: 13px border: none;"
            " background: transparent;")
        self.stack.addWidget(self.empty_lbl)

        root.addWidget(self.stack, 1)
        self._rebuild()

        # 按钮行
        brow = QHBoxLayout()
        brow.setSpacing(8)
        self.btn_use = PrimaryPushButton(tr("使用", "Use"))
        self.btn_use.clicked.connect(self._on_use)
        brow.addWidget(self.btn_use)
        if self._delete_fn is not None:
            self.btn_del = PushButton(tr("删除", "Delete"))
            self.btn_del.clicked.connect(self._on_delete)
            brow.addWidget(self.btn_del)
        brow.addStretch(1)
        if self._clear_fn is not None:
            self.btn_clear = PushButton(tr("清空", "Clear all"))
            self.btn_clear.clicked.connect(self._on_clear)
            brow.addWidget(self.btn_clear)
        self.btn_close = PushButton(tr("关闭", "Close"))
        self.btn_close.clicked.connect(self.reject)
        brow.addWidget(self.btn_close)
        root.addLayout(brow)

    # ── 表格构建 ─────────────────────────────
    def _rebuild(self):
        """按 self._items 重建表格（含空态切换）。"""
        self.table.setSortingEnabled(False)  # 填充期间暂停排序
        self.table.setRowCount(0)
        sec = ds.ink_sec()
        for i, item in enumerate(self._items):
            row = self.table.rowCount()
            self.table.insertRow(row)

            ts = format_datetime(item.get("time", ""))
            t_item = _TimeItem(ts, item.get("time", ""))
            # 存原始 _items 索引：表格排序后 currentRow 与 _items 错位，
            # 选中/删除/使用必须经原始索引取数据
            t_item.setData(Qt.UserRole + 1, i)
            self.table.setItem(row, 0, t_item)

            name = str(item.get("name") or item.get("url") or "?")
            self.table.setItem(row, 1, QTableWidgetItem(name))

            url = str(item.get("url") or "")
            self.table.setItem(row, 2, QTableWidgetItem(url))

            meta = []
            size = item.get("size", 0)
            if size:
                meta.append(format_size(int(size)))
            duration = item.get("duration", 0)
            if duration:
                meta.append(tr("时长 {}", "Duration {}").format(
                    format_time(int(duration))))
            note = str(item.get("note") or "").strip()
            if note:
                meta.append(note)
            self.table.setItem(row, 3, QTableWidgetItem(" · ".join(meta)))

            # 次要文字色（URL/信息列），主题感知
            brush = QBrush(QColor(sec))
            for col in (0, 2, 3):
                self.table.item(row, col).setForeground(brush)
        self.table.setSortingEnabled(True)

        has = len(self._items) > 0
        self.stack.setCurrentWidget(self.table if has else self.empty_lbl)
        self.count_lbl.setText(
            tr("共 {} 条", "{} items").format(len(self._items)))

    def _selected_item(self):
        """当前选中行对应的原始数据（表格排序后行号≠_items 索引）。"""
        row = self.table.currentRow()
        if row < 0:
            return None
        t_item = self.table.item(row, 0)
        if t_item is None:
            return None
        orig = t_item.data(Qt.UserRole + 1)
        if orig is None or orig < 0 or orig >= len(self._items):
            return None
        return self._items[orig]

    # ── 动作 ─────────────────────────────────
    def _on_use(self):
        item = self._selected_item()
        if not item:
            return
        self._use_fn(item.get("url", ""), item.get("name", ""))
        self.accept()

    def _on_delete(self):
        item = self._selected_item()
        if not item:
            return
        url = item.get("url", "")
        try:
            if self._delete_fn:
                self._delete_fn(url)
        except Exception:  # noqa: BLE001
            pass
        self._items = [i for i in self._items if i.get("url") != url]
        self._rebuild()

    def _on_clear(self):
        if not self._items:
            return
        kind_txt = tr("历史记录", "history") if self._kind == "history" \
            else tr("收藏链接", "saved links")
        box = MessageBox(
            tr("确认清空", "Confirm clear"),
            tr("确定要清空全部{}吗？此操作不可恢复。",
               "Clear all {}? This cannot be undone.").format(kind_txt),
            self)
        box.yesButton.setText(tr("清空", "Clear"))
        box.cancelButton.setText(tr("取消", "Cancel"))
        if not box.exec():
            return
        try:
            if self._clear_fn:
                self._clear_fn()
        except Exception:  # noqa: BLE001
            pass
        self._items = []
        self._rebuild()
