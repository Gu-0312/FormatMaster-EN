"""pdf_editor_panel — PDF 可视化编辑面板（阶段3 迁移自 gui/pdf_editor_panel.py）。

缩略图网格（QListWidget IconMode）+ Ctrl/Shift 多选 + 拖拽排序，
页面操作工具栏：旋转/删除/复制/插入PDF/插入图片/空白页/水印/页码/元数据/撤销。
业务全部复用 core.pdf_editor.PdfEditor；缩略图由后台线程渲染，
用 _render_gen 代数守卫防止过期结果回填。
"""
import os

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QFileDialog,
                               QFormLayout, QHBoxLayout, QListWidget,
                               QListWidgetItem, QVBoxLayout)
from qfluentwidgets import (FluentIcon, BodyLabel, CaptionLabel, ComboBox, LineEdit,
                            MessageBox, PrimaryPushButton, PushButton,
                            SpinBox, SubtitleLabel)

from gui_qt.components import design_system as ds

from core.pdf_editor import PdfEditor
from gui_qt.components import toast
from gui_qt.components.card import Card
from gui_qt.components.dialog import FluentDialogBase
from gui_qt.panels.base_panel import BaseQtPanel

THUMB_W = 150
THUMB_H = 200


def _pil_to_pixmap(pil_img):
    """PIL.Image → QPixmap（主线程调用）。"""
    from PIL.ImageQt import ImageQt
    qimg = ImageQt(pil_img.convert("RGB"))
    return QPixmap.fromImage(qimg)


class _ThumbWorker(QThread):
    """后台逐页渲染缩略图，通过信号回传 PIL.Image（主线程转 QPixmap）。"""

    sig_thumb = Signal(int, object)  # (行号, PIL.Image)
    sig_done = Signal()

    def __init__(self, editor, is_stale, parent=None):
        super().__init__(parent)
        self._editor = editor
        self._is_stale = is_stale

    def run(self):
        try:
            n = self._editor.page_count
            for i in range(n):
                if self._is_stale():
                    return
                try:
                    img = self._editor.get_thumbnail(i)
                except Exception:  # noqa: BLE001 - 单页失败不中断整体
                    img = None
                if img is not None and not self._is_stale():
                    self.sig_thumb.emit(i, img)
        finally:
            self.sig_done.emit()


class _PageGrid(QListWidget):
    """页面缩略图网格：图标模式 + 自适应换行 + 内部拖拽排序。"""

    dropped = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.IconMode)
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setWrapping(True)
        self.setSpacing(10)
        self.setIconSize(QSize(THUMB_W, THUMB_H))
        self.setGridSize(QSize(THUMB_W + 20, THUMB_H + 44))
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setUniformItemSizes(True)

    def dropEvent(self, e):
        super().dropEvent(e)
        self.dropped.emit()


# ═══════════════════════════════════════════════
#  Dialog Windows
# ═══════════════════════════════════════════════

class _DialogBase(FluentDialogBase):
    """对话框基类：表单区 + 取消/确定按钮行（深色适配继承自 FluentDialogBase）。"""

    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(20, 16, 20, 16)
        self._outer.setSpacing(10)

        self._form = QFormLayout()
        self._form.setSpacing(10)
        self._outer.addLayout(self._form)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch(1)
        btn_cancel = PushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        self.btn_ok = PrimaryPushButton("确定")
        self.btn_ok.clicked.connect(self._on_ok)
        btn_row.addWidget(self.btn_ok)
        self._outer.addLayout(btn_row)

    def _on_ok(self):
        raise NotImplementedError


class _WatermarkDialog(_DialogBase):
    POSITIONS = ["左上角", "右上角", "左下角", "右下角", "居中"]

    def __init__(self, parent=None):
        super().__init__("水印设置", parent)
        self.ed_text = LineEdit()
        self.ed_text.setText("格式大师")
        self.cb_pos = ComboBox()
        self.cb_pos.addItems(self.POSITIONS)
        self.cb_pos.setCurrentText(self.POSITIONS[3])
        self.cb_opacity = ComboBox()
        self.cb_opacity.addItems(["0.1", "0.2", "0.3", "0.4", "0.5",
                                  "0.6", "0.7", "0.8", "0.9", "1.0"])
        self.cb_opacity.setCurrentText("0.3")

        self._form.addRow("水印文字", self.ed_text)
        self._form.addRow("位置", self.cb_pos)
        self._form.addRow("不透明度", self.cb_opacity)

    def _on_ok(self):
        text = self.ed_text.text().strip()
        if not text:
            toast.show_warning(self, "水印文字不能为空")
            return
        self.result = (text, self.cb_pos.currentText(),
                       round(float(self.cb_opacity.currentText()), 1))
        self.accept()


class _PageNumDialog(_DialogBase):
    POSITIONS = ["底部居中", "底部左对齐", "底部右对齐", "顶部居中"]

    def __init__(self, parent=None):
        super().__init__("页码设置", parent)
        self.sb_start = SpinBox()
        self.sb_start.setRange(1, 99999)
        self.sb_start.setValue(1)
        self.cb_pos = ComboBox()
        self.cb_pos.addItems(self.POSITIONS)
        self.cb_pos.setCurrentIndex(0)
        self.ed_fmt = LineEdit()
        self.ed_fmt.setText("— {n} —")

        self._form.addRow("起始编号", self.sb_start)
        self._form.addRow("位置", self.cb_pos)
        self._form.addRow("格式（{n}=页码）", self.ed_fmt)

    def _on_ok(self):
        self.result = (self.sb_start.value(), self.cb_pos.currentText(),
                       self.ed_fmt.text() or "{n}")
        self.accept()


class _MetadataDialog(_DialogBase):
    FIELDS = [("标题", "title"), ("作者", "author"),
              ("主题", "subject"), ("关键词", "keywords")]

    def __init__(self, current: dict, parent=None):
        super().__init__("文档属性", parent)
        self._entries = {}
        for label, key in self.FIELDS:
            ed = LineEdit()
            ed.setText(current.get(key, "") or "")
            self._form.addRow(label, ed)
            self._entries[key] = ed

    def _on_ok(self):
        self.result = {key: ed.text() for key, ed in self._entries.items()}
        self.accept()


# ═══════════════════════════════════════════════
#  Main Panel
# ═══════════════════════════════════════════════

class PdfEditorPanelPage(BaseQtPanel):
    """PDF 可视化编辑页。"""

    panel_key = "pdf_editor"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title("PDF编辑"))
        lay.addWidget(CaptionLabel("缩略图网格：选中页面 → 点击工具栏操作 → 完成后保存"))

        self.editor = PdfEditor()
        self._render_gen = 0
        self._worker = None
        home = os.path.expanduser("~")
        self._last_dirs = {"open": home, "save": home, "insert": home}

        lay.addWidget(self._build_file_card())
        lay.addWidget(self._build_toolbar_card())

        # 缩略图网格卡片
        grid_card = Card()
        gl = QVBoxLayout(grid_card)
        gl.setContentsMargins(18, 16, 18, 16)
        gl.setSpacing(8)
        gl.addWidget(self.make_section_header("页面预览", FluentIcon.PHOTO))
        self.grid = _PageGrid()
        self.grid.setFixedHeight(460)
        gl.addWidget(self.grid)
        lay.addWidget(grid_card)

        self.grid.dropped.connect(self._on_grid_dropped)
        self.grid.itemSelectionChanged.connect(self._update_status)

        # 引导 + 状态栏
        guide_card = Card()
        gl2 = QVBoxLayout(guide_card)
        gl2.setContentsMargins(16, 10, 16, 10)
        self.lb_guide = CaptionLabel(
            "💡 操作即时生效 — Ctrl/Shift 多选页面，拖拽缩略图可调整顺序")
        gl2.addWidget(self.lb_guide)
        self.lb_status = CaptionLabel("就绪")
        gl2.addWidget(self.lb_status)
        lay.addWidget(guide_card)

        self._blank_pm = self._make_blank_pixmap()

    def _make_blank_pixmap(self):
        pm = QPixmap(THUMB_W, THUMB_H)
        pm.fill(Qt.lightGray)
        return pm

    def _build_file_card(self):
        card = Card()
        hl = QHBoxLayout(card)
        hl.setContentsMargins(18, 16, 18, 16)
        hl.setSpacing(8)

        btn_open = PushButton("📂 打开文件")
        btn_open.clicked.connect(self._open_file)
        hl.addWidget(btn_open)
        btn_save = PrimaryPushButton("💾 保存")
        btn_save.clicked.connect(self._save_file)
        hl.addWidget(btn_save)
        btn_save_as = PushButton("另存为")
        btn_save_as.clicked.connect(self._save_as)
        hl.addWidget(btn_save_as)

        hl.addStretch(1)
        self.lb_info = CaptionLabel("未打开文件")
        hl.addWidget(self.lb_info)
        return card

    def _build_toolbar_card(self):
        card = Card()
        hl = QHBoxLayout(card)
        hl.setContentsMargins(16, 10, 16, 10)
        hl.setSpacing(8)

        groups = [
            [("🔀 旋转", self._rotate_90),
             ("🗑 删除", self._delete_selected),
             ("📋 复制", self._duplicate_selected)],
            [("📄 插入PDF", self._insert_pdf),
             ("🖼 插入图片", self._insert_image),
             ("⬜ 空白页", self._insert_blank)],
            [("🏷 水印", self._add_watermark),
             ("🔢 页码", self._add_page_numbers),
             ("📝 元数据", self._edit_metadata)],
            [("↩ 撤销", self._undo)],
        ]
        for gi, group in enumerate(groups):
            if gi > 0:
                sep = BodyLabel("|")
                hl.addWidget(sep)
            for text, slot in group:
                btn = PushButton(text)
                btn.clicked.connect(slot)
                hl.addWidget(btn)
        hl.addStretch(1)
        btn_all = PushButton("全选")
        btn_all.clicked.connect(self._toggle_select_all)
        hl.addWidget(btn_all)
        btn_inv = PushButton("反选")
        btn_inv.clicked.connect(self._invert_selection)
        hl.addWidget(btn_inv)
        return card

    # ── 偏好 ────────────────────────────────────
    def collect_prefs(self) -> dict:
        return dict(self._last_dirs)

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        for key in ("open", "save", "insert"):
            val = prefs.get(key)
            if val and os.path.isdir(val):
                self._last_dirs[key] = val

    def collect_params(self) -> dict:
        return {}

    # ── 文件操作 ────────────────────────────────
    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "打开 PDF 文件", self._last_dirs["open"],
            "PDF 文件 (*.pdf);;所有文件 (*.*)")
        if not path:
            return
        self._last_dirs["open"] = os.path.dirname(path) or path
        self._load_pdf(path)

    def _load_pdf(self, path):
        """打开并渲染指定 PDF（_open_file 与外部调用共用）。"""
        try:
            self.editor.open(path)
        except RuntimeError as e:
            MessageBox("打开失败", str(e), self).exec()
            return
        self.lb_info.setText(os.path.basename(path))
        self._refresh()

    def _save_file(self):
        if not self.editor.page_count:
            return
        path = self.editor.file_path
        if path:
            self._do_save(path)
        else:
            self._save_as()

    def _save_as(self):
        if not self.editor.page_count:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "另存为", self._last_dirs["save"],
            "PDF 文件 (*.pdf);;所有文件 (*.*)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        self._last_dirs["save"] = os.path.dirname(path) or path
        self._do_save(path)

    def _do_save(self, path):
        self._render_gen += 1  # 停止旧缩略图线程
        try:
            self.editor.compact()
            self.editor.save(path)
        except RuntimeError as e:
            MessageBox("保存失败", str(e), self).exec()
            return
        self.lb_info.setText(os.path.basename(path))
        self._refresh()
        toast.show_success(self, f"已保存：{path}")

    # ── 缩略图渲染 ──────────────────────────────
    def _refresh(self):
        """按 editor 当前状态重建网格并启动缩略图渲染。"""
        self._render_gen += 1
        gen = self._render_gen
        self.grid.blockSignals(True)
        self.grid.clear()
        n = self.editor.page_count
        for i in range(n):
            it = QListWidgetItem(f"第 {i + 1} 页")
            it.setData(Qt.UserRole, i)
            it.setIcon(QIcon(self._blank_pm))
            it.setToolTip(f"第 {i + 1} 页")
            self.grid.addItem(it)
        self.grid.blockSignals(False)
        self._update_status()
        if n:
            self._worker = _ThumbWorker(
                self.editor, lambda: self._render_gen != gen, self)
            self._worker.sig_thumb.connect(self._place_thumb)
            self._worker.start()

    def _place_thumb(self, row, pil_img):
        if row < 0 or row >= self.grid.count():
            return
        try:
            pm = _pil_to_pixmap(pil_img)
        except Exception:  # noqa: BLE001 - 图像转换失败保留占位图
            return
        pm = pm.scaled(THUMB_W - 6, THUMB_H - 6,
                       Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.grid.item(row).setIcon(QIcon(pm))

    # ── 选择 ────────────────────────────────────
    def _selected_indices(self):
        return sorted(self.grid.row(it) for it in self.grid.selectedItems())

    def _require_doc(self) -> bool:
        if not self.editor.page_count:
            toast.show_warning(self, "请先打开 PDF 文件")
            return False
        return True

    def _require_selection(self):
        """要求已打开文档且有选中页；返回排序后的页号列表或 None。"""
        if not self._require_doc():
            return None
        indices = self._selected_indices()
        if not indices:
            toast.show_info(self, "请先选择要操作的页面")
            return None
        return indices

    def _toggle_select_all(self):
        if not self._require_doc():
            return
        if len(self._selected_indices()) == self.editor.page_count:
            self.grid.clearSelection()
        else:
            self.grid.selectAll()

    def _invert_selection(self):
        if not self._require_doc():
            return
        sel = set(self._selected_indices())
        self.grid.blockSignals(True)
        self.grid.clearSelection()
        for i in range(self.grid.count()):
            if i not in sel:
                self.grid.item(i).setSelected(True)
        self.grid.blockSignals(False)
        self._update_status()

    def _select_indices(self, indices):
        self.grid.clearSelection()
        for i in indices:
            if 0 <= i < self.grid.count():
                self.grid.item(i).setSelected(True)

    # ── 拖拽排序提交 ─────────────────────────────
    def _on_grid_dropped(self):
        order = [self.grid.item(r).data(Qt.UserRole)
                 for r in range(self.grid.count())]
        if order == sorted(order):
            return  # 顺序未变
        if self.editor.reorder_pages(order):
            self._refresh()
            toast.show_success(self, "页面顺序已调整")

    # ── 工具栏动作 ──────────────────────────────
    def _rotate_90(self):
        indices = self._require_selection()
        if indices is None:
            return
        if self.editor.rotate_pages(indices, 90):
            keep = list(indices)
            self._refresh()
            self._select_indices(keep)
            toast.show_success(self, f"已旋转 {len(indices)} 页")

    def _delete_selected(self):
        indices = self._require_selection()
        if indices is None:
            return
        dlg = MessageBox("确认删除", f"确定要删除选中的 {len(indices)} 页吗？", self)
        dlg.yesButton.setText("删除")
        if not dlg.exec():
            return
        if self.editor.delete_pages(indices):
            self._refresh()
            toast.show_success(self, f"已删除 {len(indices)} 页")

    def _duplicate_selected(self):
        indices = self._require_selection()
        if indices is None:
            return
        at = max(indices) + 1
        if self.editor.duplicate_pages(indices, at):
            self._refresh()
            self._select_indices(list(range(at, at + len(indices))))
            toast.show_success(self, f"已复制 {len(indices)} 页")

    def _insert_pdf(self):
        if not self._require_doc():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "插入 PDF 文件", self._last_dirs["insert"],
            "PDF 文件 (*.pdf);;所有文件 (*.*)")
        if not path:
            return
        self._last_dirs["insert"] = os.path.dirname(path) or path
        at = self._insert_at()
        if self.editor.insert_pdf(at, path):
            self._refresh()
            toast.show_success(self, f"已在位置 {at + 1} 插入 PDF")
        else:
            toast.show_error(self, "插入失败：文件无法打开或已加密")

    def _insert_image(self):
        if not self._require_doc():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "插入图片", self._last_dirs["insert"],
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.tiff *.webp);;所有文件 (*.*)")
        if not path:
            return
        self._last_dirs["insert"] = os.path.dirname(path) or path
        at = self._insert_at()
        if self.editor.insert_image(at, path):
            self._refresh()
            toast.show_success(self, f"已在位置 {at + 1} 插入图片")
        else:
            toast.show_error(self, "插入失败：图片无法解析")

    def _insert_blank(self):
        if not self._require_doc():
            return
        at = self._insert_at()
        if self.editor.insert_blank(at):
            self._refresh()
            toast.show_success(self, f"已在位置 {at + 1} 插入空白页")

    def _insert_at(self):
        sel = self._selected_indices()
        return min(sel) if sel else self.editor.page_count

    def _add_watermark(self):
        if not self._require_doc():
            return
        dlg = _WatermarkDialog(self)
        if not dlg.exec() or not dlg.result:
            return
        text, pos, opacity = dlg.result
        if self.editor.add_watermark(text, pos, opacity):
            # core 的注释类操作不清缩略图缓存，此处手动清理保证预览同步
            self.editor._clear_thumb_cache()
            self._refresh()
            toast.show_success(self, "已添加水印")

    def _add_page_numbers(self):
        if not self._require_doc():
            return
        dlg = _PageNumDialog(self)
        if not dlg.exec() or not dlg.result:
            return
        start, pos, fmt = dlg.result
        if self.editor.add_page_numbers(start, pos, fmt):
            self.editor._clear_thumb_cache()
            self._refresh()
            toast.show_success(self, "已添加页码")

    def _edit_metadata(self):
        if not self._require_doc():
            return
        dlg = _MetadataDialog(self.editor.metadata, self)
        if not dlg.exec() or dlg.result is None:
            return
        if self.editor.set_metadata(dlg.result):
            self._update_status()
            toast.show_success(self, "元数据已更新")

    def _undo(self):
        if not self._require_doc():
            return
        if self.editor.undo():
            self._refresh()
            toast.show_success(self, "已撤销")
        else:
            toast.show_info(self, "没有可撤销的操作")

    # ── 状态栏 ──────────────────────────────────
    def _update_status(self):
        n = self.editor.page_count
        if not n:
            self.lb_status.setText("就绪")
            return
        parts = [f"共 {n} 页"]
        sel = len(self._selected_indices())
        if sel:
            parts.append(f"选中 {sel} 页")
        if self.editor.modified:
            parts.append("● 未保存")
        self.lb_status.setText("  |  ".join(parts))

    # ── 公共 API ────────────────────────────────
    def is_modified(self) -> bool:
        return self.editor.modified

    def is_open(self) -> bool:
        return self.editor.page_count > 0

    def cleanup(self):
        """关闭文档并等待缩略图线程收尾（主窗口关闭时调用）。"""
        self._render_gen += 1
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(3000)
        self.editor.close()
