"""插件：图片转 ASCII 字符画（Pillow 灰度映射）。"""

import os
from plugins._i18n import t

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QHBoxLayout,
                               QPlainTextEdit, QVBoxLayout, QWidget)
from qfluentwidgets import (CaptionLabel, PrimaryPushButton, SpinBox)

PLUGIN_INFO = {
    "name": "ASCII 字符画",
    "description": "图片转 ASCII 字符画",
    "version": "1.0.0",
}

_CHARS = "@%#*+=-:. "          # 暗 → 亮


def img_to_ascii(path, width=80, invert=False):
    """图片 → 字符画文本。失败抛异常。"""
    from PIL import Image
    with Image.open(path) as _f:
        img = _f.convert("L")
    h = max(1, int(width * img.height / img.width * 0.5))
    img = img.resize((width, h))
    chars = list(_CHARS[::-1] if invert else _CHARS)
    n = len(chars)
    lines = []
    for y in range(h):
        row = "".join(
            chars[min(n - 1, img.getpixel((x, y)) * n // 256)]
            for x in range(width))
        lines.append(row)
    return "\n".join(lines)


class AsciiPanel(QWidget):
    """ASCII 字符画面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_pick = PrimaryPushButton(t("选择图片"))
        self.btn_pick.clicked.connect(self._pick)
        row.addWidget(self.btn_pick)
        row.addWidget(CaptionLabel(t("宽度")))
        self.sb_width = SpinBox()
        self.sb_width.setRange(30, 200)
        self.sb_width.setValue(80)
        row.addWidget(self.sb_width)
        self.cb_invert = QCheckBox(t("反色"))
        row.addWidget(self.cb_invert)
        self.btn_run = PrimaryPushButton(t("生成字符画"))
        self.btn_run.clicked.connect(self._run)
        row.addWidget(self.btn_run)
        self.btn_save = PrimaryPushButton(t("保存 txt"))
        self.btn_save.clicked.connect(self._save)
        row.addWidget(self.btn_save)
        self.btn_open = PrimaryPushButton(t("打开输出文件夹"))
        self.btn_open.clicked.connect(self._open_out)
        self.btn_open.setEnabled(False)
        row.addWidget(self.btn_open)
        row.addStretch(1)
        v.addLayout(row)

        self.ed_out = QPlainTextEdit()
        self.ed_out.setReadOnly(True)
        self.ed_out.setFont(QFont("Consolas", 8))
        v.addWidget(self.ed_out, 1)
        self._src = ""
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
            f" border-radius: 6px; padding: 4px; }}")

    def _pick(self):
        path, _ = QFileDialog.getOpenFileName(
            self, t("选择图片"), "", "图片 (*.png *.jpg *.jpeg *.webp *.bmp)")
        if path:
            self._src = path
            self.ed_out.setPlainText(t("已选择：{path}").format(path=path))

    def _run(self):
        if not self._src:
            self.ed_out.setPlainText(t("请先选择图片"))
            return
        try:
            art = img_to_ascii(self._src, self.sb_width.value(),
                               self.cb_invert.isChecked())
            self.ed_out.setPlainText(art)
        except Exception as e:  # noqa: BLE001
            self.ed_out.setPlainText(t("生成失败：{e}").format(e=e))

    def _save(self):
        if not self.ed_out.toPlainText():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, t("保存为 txt"), "ascii_art.txt", t("文本 (*.txt)"))
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.ed_out.toPlainText())
            self._last_out = os.path.dirname(path)
            self.btn_open.setEnabled(True)
            self.ed_out.setPlainText(t("已保存：{path}").format(path=path))

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


PANEL_CLASS = AsciiPanel


def on_load(ctx):
    pass


def on_unload():
    pass
