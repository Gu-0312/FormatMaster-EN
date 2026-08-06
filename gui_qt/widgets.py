"""widgets — 面板级原语：FileListCard / OutputDirRow / ActionBar（Prism 设计系统）。

FileListCard：文件列表（添加文件/文件夹、单个移除、批量清空、
拖拽放入、逐文件进度与状态列）。
OutputDirRow：输出目录选择（与源文件同目录 / 自定义目录）。
ActionBar：面板底部操作栏（Prism 风格开始按钮 + 进度条）。
"""
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout,
                               QHeaderView, QLabel, QMenu, QStackedWidget,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)
from qfluentwidgets import (CaptionLabel, ComboBox, FluentIcon, LineEdit,
                            PrimaryPushButton, PushButton, ProgressBar,
                            SubtitleLabel, ToolButton,
                            TransparentToolButton)

from gui_qt.components.card import Card
from gui_qt.components import design_system as ds


def _fmt_size(n):
    """字节数转可读文案。"""
    if n <= 0:
        return "--"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TB"


class FileListCard(Card):
    """文件列表卡片（视频转换等面板共用）。"""

    files_changed = Signal()
    file_double_clicked = Signal(str)  # 双击文件时发射，参数为文件路径

    def __init__(self, title="文件列表", file_exts=None, parent=None):
        """file_exts: 允许添加的扩展名集合（小写，含点），None 表示不限。"""
        super().__init__(parent)
        self._exts = file_exts
        self._fmt_text = ""
        self.setAcceptDrops(True)

        v = QVBoxLayout(self)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(10)

        # ── 标题 + 操作按钮 ────────────────────────
        head = QHBoxLayout()
        title_label = SubtitleLabel(title)
        title_label.setStyleSheet(
            f"font-size: 15px; font-weight: 600; color: {ds.ink()};")
        head.addWidget(title_label)
        self.count_label = CaptionLabel("0 个文件")
        self.count_label.setStyleSheet(
            f"font-size: 12px; color: {ds.ink_sec()};")
        head.addWidget(self.count_label)
        head.addStretch(1)
        self.btn_add = PushButton(FluentIcon.ADD, "添加文件")
        self.btn_add_dir = PushButton(FluentIcon.FOLDER_ADD, "添加文件夹")
        self.btn_rm = PushButton(FluentIcon.REMOVE, "移除选中")
        self.btn_clear = TransparentToolButton(FluentIcon.DELETE)
        self.btn_clear.setToolTip("清空全部")
        for b in (self.btn_add, self.btn_add_dir, self.btn_rm):
            head.addWidget(b)
        head.addWidget(self.btn_clear)
        v.addLayout(head)

        self.btn_add.clicked.connect(self._pick_files)
        self.btn_add_dir.clicked.connect(self._pick_folder)
        self.btn_rm.clicked.connect(self.remove_selected)
        self.btn_clear.clicked.connect(self.clear_files)

        # ── 表格 ─────────────────────────────────
        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(["文件名", "大小", "转换方向", "状态"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._popup_menu)
        self.table.itemDoubleClicked.connect(self._on_double_click)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setMinimumHeight(200)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(38)

        # 空态提示：无文件时用提示页替代空白表格
        self.empty_label = QLabel("拖拽文件到此处，或点击上方「添加文件」")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(
            f"font-size: 13px; color: {ds.ink_dis()};"
            "border: none; background: transparent;")
        self.stack = QStackedWidget()
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.empty_label)
        v.addWidget(self.stack, 1)

        self.table.keyPressEvent = self._on_key

        # 拖拽：表格占据卡片大部分区域，但 QTableWidget 默认不接收拖拽，
        # 文件拖到表格上会被忽略（事件不冒泡到父级）。让表格及 viewport
        # 接受拖拽并转发到 FileListCard 的统一处理，保证全卡片区域可拖入。
        self.table.setAcceptDrops(True)
        self.table.viewport().setAcceptDrops(True)
        self.table.dragEnterEvent = self.dragEnterEvent
        self.table.dropEvent = self.dropEvent
        self.table.viewport().dragEnterEvent = self.dragEnterEvent
        self.table.viewport().dropEvent = self.dropEvent

        # 初始化计数与空态页（无文件时显示拖拽提示）
        self._refresh_count()

    # ── 文件增删 ─────────────────────────────────
    def _pick_files(self):
        ft = "媒体文件 (*)" if not self._exts else \
            "支持的文件 (" + " ".join("*" + e for e in sorted(self._exts)) + ")"
        paths, _ = QFileDialog.getOpenFileNames(self, "选择文件", "", ft)
        if paths:
            self.add_files(paths)

    def _pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if not d:
            return
        found = []
        for root, _, files in os.walk(d):
            for f in files:
                if self._accept(f):
                    found.append(os.path.join(root, f))
        self.add_files(sorted(found))

    def _accept(self, path):
        if not self._exts:
            return True
        return os.path.splitext(path)[1].lower() in self._exts

    def add_files(self, paths):
        """批量添加（自动去重与扩展名过滤），返回实际新增数量。"""
        existed = set(self.files())
        added = 0
        for p in paths:
            p = os.path.normpath(p)
            if not os.path.isfile(p) or not self._accept(p) or p in existed:
                continue
            existed.add(p)
            self._add_row(p)
            added += 1
        if added:
            self._refresh_count()
            self.files_changed.emit()
        return added

    def _add_row(self, path):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(path))
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        self.table.setItem(r, 1, QTableWidgetItem(_fmt_size(size)))
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        direct = f"{ext.upper()} → {self._fmt_text}" if self._fmt_text else ext.upper()
        self.table.setItem(r, 2, QTableWidgetItem(direct))
        self.table.setItem(r, 3, QTableWidgetItem("等待中"))
        self.table.item(r, 0).setForeground(QColor(ds.ink()))
        self.table.item(r, 3).setForeground(QColor(ds.ink_sec()))

    def files(self):
        return [self.table.item(r, 0).text() for r in range(self.table.rowCount())]

    def clear_files(self):
        if self.table.rowCount() == 0:
            return
        self.table.setRowCount(0)
        self._refresh_count()
        self.files_changed.emit()

    def remove_selected(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        for r in rows:
            self.table.removeRow(r)
        self._refresh_count()
        self.files_changed.emit()

    def remove_row(self, row):
        if 0 <= row < self.table.rowCount():
            self.table.removeRow(row)
            self._refresh_count()
            self.files_changed.emit()

    # ── 交互：Delete 键 / 右键菜单 ───────────────
    def _on_key(self, e):
        if e.key() == Qt.Key_Delete:
            self.remove_selected()
            return
        QTableWidget.keyPressEvent(self.table, e)

    def _on_double_click(self, item):
        """双击文件行：发射 file_double_clicked 信号。"""
        row = item.row()
        path_item = self.table.item(row, 0)
        if path_item:
            self.file_double_clicked.emit(path_item.text())

    def _popup_menu(self, pos):
        item = self.table.itemAt(pos)
        menu = QMenu(self)
        if item is not None:
            row = item.row()
            act_rm = menu.addAction("移除此文件")
            act_rm.triggered.connect(lambda: self.remove_row(row))
            menu.addSeparator()
        act_clear = menu.addAction("清空全部")
        act_clear.triggered.connect(self.clear_files)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ── 拖拽放入 ─────────────────────────────────
    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dropEvent(self, e: QDropEvent):
        paths = []
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            if os.path.isdir(p):
                for root, _, files in os.walk(p):
                    for f in files:
                        if self._accept(f):
                            paths.append(os.path.join(root, f))
            elif os.path.isfile(p):
                paths.append(p)
        if paths:
            self.add_files(paths)
            e.acceptProposedAction()
        else:
            super().dropEvent(e)

    # ── 任务进度联动 ─────────────────────────────
    def _refresh_count(self):
        self.count_label.setText(f"{self.table.rowCount()} 个文件")
        # 无文件时显示空态提示，有文件时显示表格
        self.stack.setCurrentIndex(0 if self.table.rowCount() else 1)

    def set_target_fmt(self, fmt_text):
        """目标格式变化时刷新「转换方向」列。"""
        self._fmt_text = fmt_text
        for r in range(self.table.rowCount()):
            p = self.table.item(r, 0).text()
            ext = os.path.splitext(p)[1].lower().lstrip(".")
            direct = f"{ext.upper()} → {fmt_text}" if fmt_text else ext.upper()
            self.table.item(r, 2).setText(direct)

    def row_of_file(self, path):
        path = os.path.normpath(path)
        for r in range(self.table.rowCount()):
            if os.path.normpath(self.table.item(r, 0).text()) == path:
                return r
        return -1

    def set_row_progress(self, row, pct, state_text=""):
        """任务进行时在状态列嵌入进度条。pct>=0 都更新进度（含 0 与 100）。"""
        if row < 0:
            return
        bar = self.table.cellWidget(row, 3)
        if pct >= 0:
            if not isinstance(bar, ProgressBar):
                bar = ProgressBar(self.table)
                bar.setRange(0, 100)
                self.table.setCellWidget(row, 3, bar)
                self.table.setRowHeight(row, 36)
            bar.setValue(min(100, max(0, pct)))
        else:
            # pct < 0：结束，移除进度条显示状态文字
            if isinstance(bar, ProgressBar):
                self.table.setCellWidget(row, 3, None)
            # setCellWidget 会移除原 item，需重建
            item = self.table.item(row, 3)
            if item is None:
                item = QTableWidgetItem()
                self.table.setItem(row, 3, item)
            item.setText(state_text)
            t = ds.tokens()
            if "成功" in state_text:
                item.setForeground(QColor(t["success"]))
            elif "失败" in state_text or "取消" in state_text:
                item.setForeground(QColor(t["error"]))
            else:
                item.setForeground(QColor(t["ink_sec"]))

    def set_row_state(self, row, state_text):
        if 0 <= row < self.table.rowCount():
            bar = self.table.cellWidget(row, 3)
            if isinstance(bar, ProgressBar):
                self.table.setCellWidget(row, 3, None)
            item = self.table.item(row, 3)
            if item is not None:
                item.setText(state_text)
                t = ds.tokens()
                if "成功" in state_text:
                    item.setForeground(QColor(t["success"]))
                elif "失败" in state_text or "取消" in state_text:
                    item.setForeground(QColor(t["error"]))
                else:
                    item.setForeground(QColor(t["ink_sec"]))


class OutputDirRow(QWidget):
    """输出目录选择行：与源文件同目录 / 自定义目录。"""

    changed = Signal()

    MODE_SAME = "与源文件同目录"
    MODE_CUSTOM = "自定义目录"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._open_dir = ""  # 外部可设置的待打开目录
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)

        self.mode_combo = ComboBox(self)
        self.mode_combo.addItems([self.MODE_SAME, self.MODE_CUSTOM])
        self.mode_combo.setCurrentIndex(0)
        self.mode_combo.setFixedWidth(140)
        h.addWidget(self.mode_combo)

        self.path_edit = LineEdit(self)
        self.path_edit.setPlaceholderText("选择输出目录…")
        self.path_edit.setEnabled(False)
        h.addWidget(self.path_edit, 1)

        self.btn_browse = ToolButton(FluentIcon.FOLDER, self)
        self.btn_browse.setToolTip("浏览…")
        self.btn_browse.setEnabled(False)
        h.addWidget(self.btn_browse)

        self.btn_open = PushButton("打开文件夹", self)
        h.addWidget(self.btn_open)

        self.mode_combo.currentIndexChanged.connect(self._on_mode)
        self.btn_browse.clicked.connect(self._browse)
        self.btn_open.clicked.connect(self._open_folder)
        self.path_edit.textChanged.connect(self._on_path_changed)

    def set_open_dir(self, directory):
        """外部设置待打开目录（如源文件所在目录）。"""
        self._open_dir = directory

    def bind_file_list(self, file_card):
        """绑定 FileListCard，自动从文件列表获取源目录。"""
        self._file_card = file_card
        file_card.files_changed.connect(self._sync_open_dir)
        self._sync_open_dir()

    def _sync_open_dir(self):
        import os
        if hasattr(self, '_file_card') and self._file_card:
            files = self._file_card.files()
            if files:
                self._open_dir = os.path.dirname(files[0])

    def _on_mode(self, _idx):
        custom = self.mode_combo.currentText() == self.MODE_CUSTOM
        self.path_edit.setEnabled(custom)
        self.btn_browse.setEnabled(custom)
        self.changed.emit()

    def _on_path_changed(self, text):
        self.changed.emit()

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录",
                                             self.path_edit.text() or "")
        if d:
            self.path_edit.setText(d)

    def _open_folder(self):
        import os
        d = ""
        if self.mode_combo.currentText() == self.MODE_CUSTOM:
            d = self.path_edit.text().strip()
        if not d:
            d = self._open_dir
        if not d:
            d = os.path.expanduser("~/Downloads")
        if d and os.path.isdir(d):
            os.startfile(d)

    # ── 状态读写 ─────────────────────────────────
    def mode(self):
        return self.mode_combo.currentText()

    def path(self):
        return self.path_edit.text().strip()

    def set_state(self, mode, path=""):
        if mode == self.MODE_CUSTOM:
            self.mode_combo.setCurrentIndex(1)
            self.path_edit.setText(path)
        else:
            self.mode_combo.setCurrentIndex(0)

    def resolve_dir(self, source_file):
        """返回任务实际输出目录；自定义目录为空时回退到源目录。"""
        if self.mode() == self.MODE_CUSTOM and self.path():
            return self.path()
        return os.path.dirname(source_file)


class ActionBar(QWidget):
    """面板底部操作栏：开始按钮 + 取消按钮 + 总进度条 + 状态文本。

    Prism 风格：开始按钮使用 accent 色，进度条 accent 填充。
    按钮间距统一 8px（与全站规范一致）。
    """

    def __init__(self, go_text="开始转换", parent=None):
        super().__init__(parent)
        self.setObjectName("actionBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        # 背景色由全局 QSS 的 #actionBar 规则提供（design_system.py），
        # 主题切换时自动刷新，避免这里用 tokens() 硬编码导致切换后残留旧色。
        h = QHBoxLayout(self)
        h.setContentsMargins(16, 12, 16, 12)
        h.setSpacing(12)

        self.btn_go = PrimaryPushButton(FluentIcon.PLAY, go_text, self)
        self.btn_go.setMinimumHeight(34)
        self.btn_cancel = PushButton(FluentIcon.CANCEL, "取消", self)
        self.btn_cancel.setMinimumHeight(34)
        self.btn_cancel.setEnabled(False)
        self.bar_total = ProgressBar(self)
        self.bar_total.setRange(0, 100)
        self.bar_total.setValue(0)
        self.bar_total.setMinimumWidth(200)
        self.bar_total.setFixedHeight(12)
        self.status_label = CaptionLabel("就绪", self)
        self.status_label.setStyleSheet(
            f"font-size: 12px; color: {ds.ink_sec()};")

        # 进度条随窗口宽度伸缩（stretch=1），状态文本右对齐
        h.addWidget(self.btn_go)
        h.addWidget(self.btn_cancel)
        h.addWidget(self.bar_total, 1)
        h.addWidget(self.status_label)

    # ── 状态便捷读写 ───────────────────────────
    def set_running(self, running: bool):
        """任务进行中：禁用开始、启用取消；开始/结束时总进度条均归零。

        进度条只在任务批次进行中显示实际进度：开始时清零，
        全部结束后重置为 0，避免残留满格（100%）进度条误导用户。
        """
        self.btn_go.setEnabled(not running)
        self.btn_cancel.setEnabled(running)
        self.bar_total.setValue(0)

    def set_status(self, text: str):
        self.status_label.setText(text)

    def set_total(self, pct: int):
        self.bar_total.setValue(max(0, min(100, pct)))
