"""detect_panel — 格式检测面板（阶段2 迁移自 gui/panels/detect_panel.py + main.py 检测逻辑）。

批量检测文件夹中所有文件的格式：扩展名归类 + 文件头魔数内容识别，
结果按类别分组展示（勾选/全选），支持自动添加到对应面板与批量转换。
扫描在后台线程执行，UI 经 Qt 信号更新。
"""
import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout,
                               QHeaderView, QTableWidget, QTableWidgetItem,
                               QWidget)
from qfluentwidgets import (CaptionLabel, CheckBox,
                            LineEdit, PushButton, FluentIcon)

from gui_qt.i18n import tr
from gui_qt.components import toast
from gui_qt.components.form_widgets import FormSection
from gui_qt.panels.base_panel import BaseQtPanel

VIDEO_EXTS = {'.mp4', '.avi', '.mkv', '.wmv', '.mov', '.flv', '.webm', '.ts', '.3gp'}
AUDIO_EXTS = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.amr', '.opus'}
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.svg'}
DOC_EXTS = {'.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.rtf'}
PDF_EXTS = {'.pdf'}

TYPE_ORDER = ['video', 'audio', 'image', 'doc', 'pdf', 'other']
TYPE_ICONS = {'video': '🎬', 'audio': '🎵', 'image': '🖼️',
              'doc': '📄', 'pdf': '📕', 'other': '📁'}
TYPE_NAMES = {'video': '视频文件', 'audio': '音频文件', 'image': '图片文件',
              'doc': '文档文件', 'pdf': 'PDF文件', 'other': '其他文件'}
# 类别 → Qt 面板页 key（批量转换/自动添加目标）
CAT_PAGE = {'video': 'video', 'audio': 'audio', 'image': 'image',
            'doc': 'document', 'pdf': 'pdf'}


def _fmt_size(n):
    if n <= 0:
        return "--"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TB"


def classify_ext(fp):
    """按扩展名归类文件。"""
    ext = os.path.splitext(fp)[1].lower()
    if ext in VIDEO_EXTS:
        return 'video'
    if ext in AUDIO_EXTS:
        return 'audio'
    if ext in IMAGE_EXTS:
        return 'image'
    if ext in DOC_EXTS:
        return 'doc'
    if ext in PDF_EXTS:
        return 'pdf'
    return 'other'


def detect_format_by_content(fp):
    """通过文件头魔数检测文件实际格式（与 tkinter 版一致）。"""
    try:
        with open(fp, 'rb') as f:
            header = f.read(16)
    except OSError:
        return None
    if not header or len(header) < 4:
        return None
    if header[:4] == b'%PDF':
        return 'pdf'
    if header[:2] == b'\xff\xd8':
        return 'image'
    if header[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image'
    if header[:3] == b'GIF':
        return 'image'
    if header[:2] == b'BM':
        return 'image'
    if header[:4] == b'RIFF' and len(header) >= 12:
        if header[8:12] == b'WEBP':
            return 'image'
        if header[8:12] == b'AVI ':
            return 'video'
        if header[8:12] == b'WAVE':
            return 'audio'
    if header[:4] in (b'II*\x00', b'MM\x00*'):
        return 'image'
    if header[:4] == b'ftyp':
        return 'video'
    if header[:4] == b'\x1aE\xdf\xa3':
        return 'video'
    if header[:4] == b'\x30\x26\xb2\x75':
        ext = os.path.splitext(fp)[1].lower()
        return 'audio' if ext in ('.wma',) else 'video'
    if header[:3] == b'\x00\x00\x00' and len(header) > 3 and header[3] in (0x18, 0x1C, 0x20):
        return 'video'
    if header[:3] == b'ID3':
        return 'audio'
    if header[:4] == b'fLaC':
        return 'audio'
    if header[:4] == b'OggS':
        return 'audio'
    if header[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
        return 'doc'
    if header[:4] == b'PK\x03\x04':
        low = fp.lower()
        if any(low.endswith(e) for e in ('.docx', '.xlsx', '.pptx', '.docm', '.xlsm', '.pptm')):
            return 'doc'
        return 'other'
    return None


class _ScanWorker(QThread):
    """后台扫描文件夹：归类 + 内容识别。"""

    sig_progress = Signal(int, int)           # (当前, 总数)
    sig_done = Signal(dict, list)             # (detected, file_info)

    def __init__(self, path, stop_flag, parent=None):
        super().__init__(parent)
        self._path = path
        self._stop = stop_flag  # 共享 list，[0]=True 表示取消

    def run(self):
        detected = {k: [] for k in TYPE_ORDER}
        all_files = []
        for root, _dirs, files in os.walk(self._path):
            if self._stop[0]:
                self.sig_done.emit({}, [])
                return
            for f in files:
                all_files.append(os.path.join(root, f))
        total = len(all_files)
        file_info = []
        for i, fp in enumerate(all_files):
            if self._stop[0]:
                self.sig_done.emit({}, [])
                return
            cat = classify_ext(fp)
            detected[cat].append(fp)
            try:
                size = os.path.getsize(fp)
            except OSError:
                size = 0
            file_info.append((fp, cat, _fmt_size(size),
                              detect_format_by_content(fp)))
            if (i + 1) % 20 == 0 or i == total - 1:
                self.sig_progress.emit(i + 1, total)
        self.sig_done.emit(detected, file_info)


class DetectPanelPage(BaseQtPanel):
    """格式检测页。"""

    panel_key = "format_detect"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("格式检测", "Format detect")))
        lay.addWidget(CaptionLabel(
            "批量检测文件夹中所有文件的格式，支持按内容识别、文件详情预览和选择性批量转换"))

        card = FormSection("检测设置", FluentIcon.SEARCH)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(CaptionLabel("目标文件夹"))
        self.ed_path = LineEdit()
        self.ed_path.setPlaceholderText("选择要扫描的文件夹…")
        row.addWidget(self.ed_path, 1)
        btn_browse = PushButton(tr("浏览", "Browse"))
        btn_browse.clicked.connect(self._browse)
        row.addWidget(btn_browse)
        row_wrap = QWidget()
        row_wrap.setLayout(row)
        card.add_widget(row_wrap)
        self.cb_auto_add = CheckBox("自动添加到对应面板")
        self.cb_auto_add.setChecked(True)
        card.add_widget(self.cb_auto_add)
        lay.addWidget(card)

        lay.addWidget(self._build_result_card())

        # 底部操作栏（自定义：检测/批量转换双态）
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_go = PushButton(FluentIcon.SEARCH, tr("开始检测", "Detect"))
        self.btn_go.clicked.connect(self._on_go)
        self.btn_cancel = PushButton(FluentIcon.CANCEL, tr("取消", "Cancel"))
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._stop_scan)
        bar.addWidget(self.btn_go)
        bar.addWidget(self.btn_cancel)
        bar.addStretch(1)
        self.lb_status = CaptionLabel(tr("就绪", "Ready"))
        bar.addWidget(self.lb_status)
        lay.addLayout(bar)

        self._worker = None
        self._stop_flag = [False]
        self._phase = "idle"          # idle / scanning / result
        self._rows = []               # [(file_path, cat, check_item)]

    def _build_result_card(self):
        card = FormSection(tr("检测结果", "Result"), FluentIcon.INFO)

        head = QHBoxLayout()
        head.setSpacing(8)
        head.addStretch(1)
        self.btn_sel_all = PushButton(tr("全选", "Select all"))
        self.btn_sel_all.clicked.connect(lambda: self._set_all(True))
        self.btn_unsel = PushButton(tr("取消全选", "Deselect all"))
        self.btn_unsel.clicked.connect(lambda: self._set_all(False))
        self.btn_reset = PushButton("重新检测")
        self.btn_reset.clicked.connect(self._reset)
        for b in (self.btn_sel_all, self.btn_unsel, self.btn_reset):
            b.setEnabled(False)
            head.addWidget(b)
        head_wrap = QWidget()
        head_wrap.setLayout(head)
        card.add_widget(head_wrap)

        self.table = QTableWidget(0, 5, card)
        self.table.setHorizontalHeaderLabels(["✓", "文件名", "大小", "扩展名", "类型"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setMinimumHeight(260)
        self.table.setAlternatingRowColors(True)
        self.table.itemChanged.connect(self._on_item_changed)
        card.add_widget(self.table)
        return card

    # ── 交互 ─────────────────────────────────────
    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "选择文件夹",
                                             self.ed_path.text() or "")
        if d:
            self.ed_path.setText(d)

    def _on_go(self):
        if self._phase == "result":
            self._batch_convert()
        else:
            self._start_scan()

    def _start_scan(self):
        path = self.ed_path.text().strip()
        if not path or not os.path.isdir(path):
            toast.show_warning(self, "请选择有效的文件夹")
            return
        self.save_prefs()
        self._clear_table()
        self._stop_flag = [False]
        self._phase = "scanning"
        self.btn_go.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.lb_status.setText("正在扫描文件夹...")
        self._worker = _ScanWorker(path, self._stop_flag, self)
        self._worker.sig_progress.connect(self._on_scan_progress)
        self._worker.sig_done.connect(self._on_scan_done)
        self._worker.start()

    def _stop_scan(self):
        self._stop_flag[0] = True
        self.lb_status.setText("正在取消…")

    def _on_scan_progress(self, cur, total):
        self.lb_status.setText(f"正在检测 {cur}/{total} 个文件")

    def _on_scan_done(self, detected, file_info):
        self.btn_cancel.setEnabled(False)
        self.btn_go.setEnabled(True)
        if not detected:
            if self._stop_flag[0]:
                self.lb_status.setText("检测已取消")
            else:
                self.lb_status.setText("文件夹为空，未检测到文件")
            self._phase = "idle"
            return
        self._show_results(detected, file_info)

    # ── 结果展示 ─────────────────────────────────
    def _clear_table(self):
        self.table.itemChanged.disconnect(self._on_item_changed)
        self.table.setRowCount(0)
        self._rows = []
        self.table.itemChanged.connect(self._on_item_changed)

    def _show_results(self, detected, file_info):
        self._clear_table()
        info_map = {fi[0]: fi for fi in file_info}
        processable = {k: v for k, v in detected.items() if k != 'other'}
        total_found = sum(len(v) for v in processable.values())

        for cat in TYPE_ORDER:
            files = detected.get(cat, [])
            if not files:
                continue
            # 分组标题行
            r = self.table.rowCount()
            self.table.insertRow(r)
            hdr = QTableWidgetItem(
                f"{TYPE_ICONS[cat]} {TYPE_NAMES[cat]} ({len(files)}个)")
            f = hdr.font()
            f.setBold(True)
            hdr.setFont(f)
            self.table.setItem(r, 1, hdr)
            self.table.setSpan(r, 1, 1, 4)
            for fp in files:
                info = info_map.get(fp)
                size_str = info[2] if info else _fmt_size(os.path.getsize(fp))
                content_type = info[3] if info else None
                fn = os.path.basename(fp)
                if content_type and content_type != cat:
                    fn += f"  ⚠️ (内容检测: {TYPE_NAMES.get(content_type, content_type)})"
                r = self.table.rowCount()
                self.table.insertRow(r)
                chk = QTableWidgetItem()
                chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                chk.setCheckState(Qt.Checked)
                self.table.setItem(r, 0, chk)
                self.table.setItem(r, 1, QTableWidgetItem(fn))
                self.table.setItem(r, 2, QTableWidgetItem(size_str))
                self.table.setItem(r, 3, QTableWidgetItem(
                    os.path.splitext(fp)[1].upper() or "?"))
                self.table.setItem(r, 4, QTableWidgetItem(TYPE_NAMES[cat]))
                self._rows.append((fp, cat, chk))

        self._phase = "result"
        self.btn_go.setText(f"批量转换选中 ({total_found})")
        for b in (self.btn_sel_all, self.btn_unsel, self.btn_reset):
            b.setEnabled(True)
        self.lb_status.setText(f"检测完成，共 {total_found} 个可处理文件")

        if self.cb_auto_add.isChecked():
            self._add_to_panels({k: list(v) for k, v in processable.items()},
                                submit=False)

    def _on_item_changed(self, item):
        if item.column() != 0:
            return
        n = sum(1 for _f, _c, chk in self._rows
                if chk.checkState() == Qt.Checked)
        if self._phase == "result":
            self.btn_go.setText(f"批量转换选中 ({n})")

    def _set_all(self, checked):
        state = Qt.Checked if checked else Qt.Unchecked
        for _f, _c, chk in self._rows:
            chk.setCheckState(state)

    def _reset(self):
        self._clear_table()
        self._phase = "idle"
        self.btn_go.setText(tr("开始检测", "Detect"))
        for b in (self.btn_sel_all, self.btn_unsel, self.btn_reset):
            b.setEnabled(False)
        self.lb_status.setText(tr("就绪", "Ready"))

    # ── 批量转换 / 自动添加 ──────────────────────
    def _selected_by_cat(self):
        grouped = {}
        for fp, cat, chk in self._rows:
            if chk.checkState() == Qt.Checked and cat != 'other':
                grouped.setdefault(cat, []).append(fp)
        return grouped

    def _add_to_panels(self, grouped, submit=False):
        """把检测结果送入对应面板；submit=True 时直接启动转换。"""
        added = 0
        for cat, files in grouped.items():
            page_key = CAT_PAGE.get(cat)
            page = self.window.pages.get(page_key) if page_key else None
            card = getattr(page, "file_card", None) if page else None
            if card is None:
                continue
            n = card.add_files(files)
            added += n
            if submit and n:
                try:
                    page._start()
                except Exception as ex:  # noqa: BLE001
                    toast.show_error(self, f"{TYPE_NAMES[cat]}转换提交失败：{ex}")
        return added

    def _batch_convert(self):
        grouped = self._selected_by_cat()
        if not grouped:
            toast.show_warning(self, "请先勾选需要转换的文件")
            return
        n = self._add_to_panels(grouped, submit=True)
        toast.show_success(self, f"已提交 {n} 个文件的转换任务，请在对应面板查看")
        self._reset()

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        return {"path": self.ed_path.text().strip(),
                "auto_add": self.cb_auto_add.isChecked()}

    def collect_prefs(self) -> dict:
        return self.collect_params()

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        if prefs.get("path"):
            self.ed_path.setText(prefs["path"])
        if "auto_add" in prefs:
            self.cb_auto_add.setChecked(bool(prefs["auto_add"]))
