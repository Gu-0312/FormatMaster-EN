"""插件：文本编码转换（UTF-8 / GBK / BIG5 / Shift-JIS 等，文本+文件双模式）。

文件模式只读解码预览，转换后「另存为」新文件，不覆盖原文件。
"""

import os
from plugins._i18n import t

from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QPlainTextEdit,
                               QVBoxLayout, QWidget)
from qfluentwidgets import (CaptionLabel, ComboBox, PrimaryPushButton,
                            SegmentedWidget)

PLUGIN_INFO = {
    "name": "文本编码转换",
    "description": "UTF-8 / GBK / BIG5 / Shift-JIS 等编码互转",
    "version": "1.0.0",
}

_ENCODINGS = ["UTF-8", "UTF-8 (BOM)", "GBK", "GB2312", "GB18030", "BIG5",
              "Shift-JIS", "EUC-JP", "Latin-1", "UTF-16", "UTF-16BE",
              "UTF-16LE", "UTF-32", "ASCII"]
_PREVIEW_LIMIT = 4000

# 显示名 → Python codec 名
_ENCODER_MAP = {"UTF-8 (BOM)": "utf-8-sig"}


def _codec_of(display):
    return _ENCODER_MAP.get(display, display)


class EncodingPanel(QWidget):
    """文本编码转换面板（文本 / 文件双模式）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        self.sg = SegmentedWidget()
        self.sg.addItem("text", t("文本"))
        self.sg.addItem("file", t("文件"))
        self.sg.setCurrentItem("text")
        self.sg.currentItemChanged.connect(self._mode_changed)
        v.addWidget(self.sg)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(CaptionLabel(t("源编码")))
        self.cb_src = ComboBox()
        self.cb_src.addItems(_ENCODINGS)
        row.addWidget(self.cb_src)
        row.addWidget(CaptionLabel(t("目标编码")))
        self.cb_dst = ComboBox()
        self.cb_dst.addItems(_ENCODINGS)
        self.cb_dst.setCurrentText("GBK" if self.cb_src.currentText() == "UTF-8"
                                   else "UTF-8")
        row.addWidget(self.cb_dst)
        self.btn_pick = PrimaryPushButton(t("选择文件"))
        self.btn_pick.clicked.connect(self._pick)
        row.addWidget(self.btn_pick)
        self.btn_run = PrimaryPushButton(t("转换"))
        self.btn_run.clicked.connect(self._convert)
        row.addWidget(self.btn_run)
        self.btn_open_dir = PrimaryPushButton(t("打开输出文件夹"))
        self.btn_open_dir.clicked.connect(self._open_out)
        self.btn_open_dir.setEnabled(False)
        row.addWidget(self.btn_open_dir)
        row.addStretch(1)
        v.addLayout(row)

        self.ed_in = QPlainTextEdit()
        self.ed_in.setPlaceholderText(
            t("输入文本，或切换到「文件」模式选择文件（只读预览）…"))
        v.addWidget(self.ed_in, 1)

        self.ed_out = QPlainTextEdit()
        self.ed_out.setReadOnly(True)
        v.addWidget(self.ed_out, 1)
        self._path = ""
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

    def _mode_changed(self, _k=None):
        is_file = self.sg.currentRouteKey() == "file"
        self.btn_pick.setVisible(is_file)
        if is_file:
            self.ed_in.setReadOnly(True)
            if self._path:
                self._load_preview()
        else:
            self.ed_in.setReadOnly(False)

    def _pick(self):
        path, _ = QFileDialog.getOpenFileName(self, t("选择文本文件"))
        if path:
            self._path = path
            self._load_preview()

    def _load_preview(self):
        text, enc = _read_file(self._path)
        self.ed_in.setPlainText(
            text[:_PREVIEW_LIMIT] + ("\n…（预览截断）" if len(text) > _PREVIEW_LIMIT else ""))
        self.ed_in.setToolTip(t("已按 {enc} 读取").format(enc=enc))

    def _convert(self):
        src = self.cb_src.currentText()
        dst = self.cb_dst.currentText()
        src_enc, dst_enc = _codec_of(src), _codec_of(dst)
        try:
            if self.sg.currentRouteKey() == "file":
                if not self._path:
                    self.ed_out.setPlainText(t("请先选择文件"))
                    return
                data = _read_bytes(self._path)
                text = data.decode(src_enc, errors="replace")
                out_path, _ = QFileDialog.getSaveFileName(
                    self, t("另存为"), os.path.splitext(self._path)[0] + "_converted.txt")
                if not out_path:
                    return
                with open(out_path, "w", encoding=dst_enc) as fh:
                    fh.write(text)
                self._last_out = os.path.dirname(out_path)
                self.btn_open_dir.setEnabled(True)
                self.ed_out.setPlainText(t("已转换保存：{out_path}").format(out_path=out_path))
            else:
                text = self.ed_in.toPlainText()
                data = text.encode(dst_enc, errors="replace")
                # 展示目标编码的字节 HEX（避免乱码误导；完整转换请用「文件」模式）
                hex_str = " ".join(f"{b:02X}" for b in data)
                self.ed_out.setPlainText(
                    f"「{src}」→「{dst}」共 {len(data)} 字节：\n{hex_str}")
        except Exception as e:  # noqa: BLE001
            self.ed_out.setPlainText(t("转换失败：{e}").format(e=e))

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


def _read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def _read_file(path):
    """自动检测编码读取文本文件，返回 (text, used_encoding)。"""
    data = _read_bytes(path)
    for enc in ("utf-8-sig", "gbk", "big5", "shift_jis", "latin-1"):
        try:
            return data.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace"), "utf-8 (replace)"


PANEL_CLASS = EncodingPanel


def on_load(ctx):
    pass


def on_unload():
    pass
