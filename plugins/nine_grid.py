"""插件：九宫格切图（一张图切成 3x3 九张，Pillow，带缩略预览）。"""

import os
from plugins._i18n import t

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QFileDialog, QGridLayout, QHBoxLayout, QLabel,
                               QPlainTextEdit, QScrollArea, QVBoxLayout,
                               QWidget)
from qfluentwidgets import PrimaryPushButton

PLUGIN_INFO = {
    "name": "九宫格切图",
    "description": "一张图切成 3x3 九张，带预览与打开输出目录",
    "version": "1.1.0",
}


def nine_grid(src, out_dir):
    """切图，返回 (ok, 文件列表或错误)。"""
    try:
        from PIL import Image
    except ImportError:
        return False, t("缺少 Pillow（pip install Pillow）")
    try:
        with Image.open(src) as _f:
            img = _f.copy()
        w, h = img.size
        tw, th = w // 3, h // 3
        if tw < 1 or th < 1:
            return False, t("图片太小，无法切九宫格")
        base = os.path.splitext(os.path.basename(src))[0]
        out = os.path.join(out_dir, f"{base}_九宫格")
        os.makedirs(out, exist_ok=True)
        saved = []
        for i in range(3):
            for j in range(3):
                box = (j * tw, i * th, (j + 1) * tw, (i + 1) * th)
                piece = img.crop(box)
                name = os.path.join(out, f"{base}_{i+1}_{j+1}.jpg")
                piece.convert("RGB").save(name, quality=95)
                saved.append(name)
        return True, saved
    except Exception as e:  # noqa: BLE001
        return False, t("切图失败：{e}").format(e=e)


class NineGridPanel(QWidget):
    """九宫格切图面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        row = QHBoxLayout()
        self.btn_pick = PrimaryPushButton(t("选择图片"))
        self.btn_pick.clicked.connect(self._pick)
        row.addWidget(self.btn_pick)
        self.btn_dir = PrimaryPushButton(t("选择输出文件夹"))
        self.btn_dir.clicked.connect(self._pick_dir)
        row.addWidget(self.btn_dir)
        self.btn_run = PrimaryPushButton(t("开始切图"))
        self.btn_run.clicked.connect(self._run)
        row.addWidget(self.btn_run)
        self.btn_open_dir = PrimaryPushButton(t("打开输出文件夹"))
        self.btn_open_dir.clicked.connect(self._open_out)
        self.btn_open_dir.setEnabled(False)
        row.addWidget(self.btn_open_dir)
        row.addStretch(1)
        v.addLayout(row)

        # 结果缩略预览（3x3 网格，可滚动）
        self.preview_area = QScrollArea()
        self.preview_area.setWidgetResizable(True)
        self.preview_area.setMinimumHeight(150)
        self.preview_host = QWidget()
        self.preview_grid = QGridLayout(self.preview_host)
        self.preview_grid.setContentsMargins(4, 4, 4, 4)
        self.preview_grid.setSpacing(4)
        self.preview_area.setWidget(self.preview_host)
        self.preview_area.hide()
        v.addWidget(self.preview_area, 1)

        self.ed_out = QPlainTextEdit()
        self.ed_out.setReadOnly(True)
        self.ed_out.setMaximumHeight(120)
        v.addWidget(self.ed_out)
        self._src = ""
        self._out = ""
        self._last_out = ""
        self._apply_theme()
        from gui_qt.components import design_system as ds
        ds.bind_theme(self, self._apply_theme)

    def _apply_theme(self):
        from gui_qt.components import design_system as ds
        t = ds.tokens()
        self.setStyleSheet(
            f"QPlainTextEdit {{ background: {t['card_bg']};"
            f" color: {t['ink']}; border: 1px solid {t['border']};"
            f" border-radius: 6px; padding: 4px; font-size: 13px; }}")

    def _pick(self):
        path, _ = QFileDialog.getOpenFileName(
            self, t("选择图片"), "", "图片 (*.png *.jpg *.jpeg *.webp *.bmp)")
        if path:
            self._src = path
            self.ed_out.setPlainText(t("已选择：{path}").format(path=path))

    def _pick_dir(self):
        path = QFileDialog.getExistingDirectory(self, t("选择输出文件夹"))
        if path:
            self._out = path
            self.ed_out.setPlainText(t("输出目录：{path}").format(path=path))

    def _run(self):
        if not self._src:
            self.ed_out.setPlainText(t("请先选择图片"))
            return
        out = self._out or os.path.dirname(self._src)
        ok, result = nine_grid(self._src, out)
        if not ok:
            self.ed_out.setPlainText(f"✗ {result}")
            return
        self._last_out = os.path.dirname(result[0])
        lines = [f"✓ 已生成 {len(result)} 张 → {self._last_out}"]
        lines += [f"  {f}" for f in result]
        self.ed_out.setPlainText("\n".join(lines))
        self.btn_open_dir.setEnabled(True)
        self._show_preview(result)

    def _show_preview(self, files):
        """清空并重建 3x3 缩略预览。"""
        while self.preview_grid.count():
            item = self.preview_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        for idx, fp in enumerate(files):
            pix = _thumb(fp, 140)
            lab = QLabel()
            lab.setAlignment(Qt.AlignCenter)
            if pix is not None:
                lab.setPixmap(pix)
            else:
                lab.setText("?")
            self.preview_grid.addWidget(lab, idx // 3, idx % 3)
        self.preview_area.show()

    def _open_out(self):
        if self._last_out and os.path.isdir(self._last_out):
            try:
                os.startfile(self._last_out)   # noqa: S606
                return
            except Exception:  # noqa: BLE001
                import subprocess
                try:
                    subprocess.Popen(["explorer", self._last_out])
                    return
                except Exception:  # noqa: BLE001
                    pass
        self.ed_out.setPlainText(t("输出目录不存在"))


def _thumb(path, size):
    """图片文件 → 缩放后的 QPixmap；失败返回 None。"""
    try:
        from PIL import Image
        with Image.open(path) as _f:
            img = _f.copy()
        img.thumbnail((size, size))
        data = img.convert("RGBA").tobytes("raw", "RGBA")
        qimg = QImage(data, img.width, img.height, QImage.Format_RGBA8888)
        return QPixmap.fromImage(qimg)
    except Exception:  # noqa: BLE001
        return None


PANEL_CLASS = NineGridPanel


def on_load(ctx):
    pass


def on_unload():
    pass
