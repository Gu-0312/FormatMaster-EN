"""url_list_dialog — 收藏/历史链接列表对话框（download 与 m3u8 面板共用）。

对齐 tkinter 版 _show_dl_fav_hist_win：列表展示 + 选中后「使用」回调。
"""
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout

from qfluentwidgets import BodyLabel, ListWidget, PrimaryPushButton, PushButton

from gui_qt.i18n import tr
from gui_qt.components.dialog import FluentDialogBase


class UrlListDialog(FluentDialogBase):
    """链接列表选择对话框。

    items: [{"url":..., "name":..., "size":..., "time":..., "note":...}]
    use_fn(url, name): 点击「使用」时的回调。
    """

    def __init__(self, title, items, use_fn, parent=None):
        super().__init__(title, parent)
        self.resize(640, 420)
        self._items = list(items)
        self._use_fn = use_fn

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)
        lay.addWidget(BodyLabel(title))

        self.list_w = ListWidget()
        for item in self._items:
            nm = item.get("name", "?")
            size = item.get("size", 0)
            sz = f"  {size / 1024 / 1024:.0f}MB" if size else ""
            note = item.get("note", "")
            text = f"{nm}{sz}  {item.get('time', '')}"
            if note:
                text += f"  [{note}]"
            self.list_w.addItem(text)
        if not self._items:
            self.list_w.addItem(tr("暂无记录", "No records"))
        lay.addWidget(self.list_w, 1)

        brow = QHBoxLayout()
        brow.setSpacing(8)
        btn_use = PrimaryPushButton(tr("使用", "Use"))
        btn_use.clicked.connect(self._on_use)
        btn_close = PushButton(tr("关闭", "Close"))
        btn_close.clicked.connect(self.reject)
        brow.addWidget(btn_use)
        brow.addStretch(1)
        brow.addWidget(btn_close)
        lay.addLayout(brow)

    def _on_use(self):
        row = self.list_w.currentRow()
        if row < 0 or row >= len(self._items):
            return
        item = self._items[row]
        self._use_fn(item.get("url", ""), item.get("name", ""))
        self.accept()
