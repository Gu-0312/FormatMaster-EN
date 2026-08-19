"""插件：Base64 / URL-safe / Base32 / Base16 编解码（文本模式 + 文件模式）。"""

import base64
from plugins._i18n import t
import os

from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QPlainTextEdit,
                               QVBoxLayout, QWidget)
from qfluentwidgets import (CaptionLabel, ComboBox, PrimaryPushButton,
                            SegmentedWidget)

PLUGIN_INFO = {
    "name": "Base64 工具",
    "description": "文本/文件 Base64 / URL-safe / Base32 / Base16 编解码",
    "version": "2.0.0",
}

_FMTS = (
    ("Standard Base64", "b64", "ascii"),
    ("URL-safe Base64", "urlsafe", "ascii"),
    ("Base32", "b32", "ascii"),
    ("Base16 (Hex)", "b16", "ascii"),
)


def _codec(fmt):
    """格式 → (encode_fn, decode_fn)。"""
    if fmt == "b64":
        return base64.b64encode, base64.b64decode
    if fmt == "urlsafe":
        return base64.urlsafe_b64encode, base64.urlsafe_b64decode
    if fmt == "b32":
        return base64.b32encode, base64.b32decode
    return base64.b16encode, base64.b16decode


class Base64Panel(QWidget):
    """Base64 编解码面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        self.sg = SegmentedWidget()
        self.sg.addItem("text", t("文本"))
        self.sg.addItem("file", t("文件"))
        self.sg.setCurrentItem("text")
        v.addWidget(self.sg)

        # 格式选择
        fmt_row = QHBoxLayout()
        fmt_row.setSpacing(8)
        fmt_row.addWidget(CaptionLabel(t("格式")))
        self.cb_fmt = ComboBox()
        self.cb_fmt.addItems([f[0] for f in _FMTS])
        self.cb_fmt.setCurrentIndex(0)
        self.cb_fmt.setFixedWidth(150)
        fmt_row.addWidget(self.cb_fmt)
        fmt_row.addStretch(1)
        v.addLayout(fmt_row)

        self.ed_in = QPlainTextEdit()
        self.ed_in.setPlaceholderText(t("输入要处理的文本或 Base64…"))
        v.addWidget(self.ed_in, 1)

        row = QHBoxLayout()
        row.setSpacing(8)
        btn_enc = PrimaryPushButton(t("编码"))
        btn_enc.clicked.connect(self._encode)
        row.addWidget(btn_enc)
        btn_dec = PrimaryPushButton(t("解码"))
        btn_dec.clicked.connect(self._decode)
        row.addWidget(btn_dec)
        btn_open = PrimaryPushButton(t("选择文件"))
        btn_open.clicked.connect(self._pick_file)
        row.addWidget(btn_open)
        btn_save = PrimaryPushButton(t("保存为文件"))
        btn_save.clicked.connect(self._save_file)
        row.addWidget(btn_save)
        self.btn_open_dir = PrimaryPushButton(t("打开输出文件夹"))
        self.btn_open_dir.clicked.connect(self._open_out)
        self.btn_open_dir.setEnabled(False)
        row.addWidget(self.btn_open_dir)
        row.addStretch(1)
        v.addLayout(row)

        self.ed_out = QPlainTextEdit()
        self.ed_out.setReadOnly(True)
        v.addWidget(self.ed_out, 1)
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

    def _mode(self):
        return self.sg.currentRouteKey()

    def _encode(self):
        enc, _dec = _codec(_FMTS[self.cb_fmt.currentIndex()][1])
        if self._mode() == "text":
            data = self.ed_in.toPlainText().encode("utf-8")
        else:
            path = self.ed_in.toPlainText().strip()
            if not path or not os.path.isfile(path):
                self.ed_out.setPlainText(t("请先选择文件（或直接粘贴文件路径）"))
                return
            with open(path, "rb") as fh:
                data = fh.read()
        self.ed_out.setPlainText(enc(data).decode("ascii"))

    def _decode(self):
        _enc, dec = _codec(_FMTS[self.cb_fmt.currentIndex()][1])
        raw = self.ed_in.toPlainText().strip()
        try:
            data = dec(raw)
        except Exception as e:  # noqa: BLE001
            self.ed_out.setPlainText(t("解码失败：{e}").format(e=e))
            return
        try:
            self.ed_out.setPlainText(data.decode("utf-8"))
        except UnicodeDecodeError:
            self.ed_out.setPlainText(
                f"解码成功（{len(data)} 字节），非文本内容：\n{data!r}")

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(self, t("选择文件"))
        if path:
            self.ed_in.setPlainText(path)

    def _save_file(self):
        """把输出框的编码文本保存为文件。"""
        raw = self.ed_out.toPlainText().strip()
        if not raw:
            self.ed_out.setPlainText(t("请先编码或粘贴 Base64 到输入框再解码"))
            return
        try:
            _enc, dec = _codec(_FMTS[self.cb_fmt.currentIndex()][1])
            data = dec(raw)
        except Exception as e:  # noqa: BLE001
            self.ed_out.setPlainText(t("不是有效的编码：{e}").format(e=e))
            return
        path, _ = QFileDialog.getSaveFileName(self, t("保存为文件"), "output.bin")
        if path:
            with open(path, "wb") as fh:
                fh.write(data)
            self._last_out = os.path.dirname(path)
            self.btn_open_dir.setEnabled(True)
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


PANEL_CLASS = Base64Panel


def on_load(ctx):
    pass


def on_unload():
    pass
