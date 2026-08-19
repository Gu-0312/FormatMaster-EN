"""插件：哈希校验（MD5 / SHA 系列 / SHA3 / BLAKE2 / CRC32 计算 + 对比验证）。

支持文本与文件两种模式：计算哈希后可粘贴期望值进行比对，
结果区显示各算法哈希与匹配状态，可一键复制。
"""

import hashlib
from plugins._i18n import t
import os
import zlib

from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout,
                               QPlainTextEdit, QVBoxLayout, QWidget)
from qfluentwidgets import (CaptionLabel, ComboBox, LineEdit,
                            PrimaryPushButton, SegmentedWidget)

PLUGIN_INFO = {
    "name": "哈希校验",
    "description": "MD5 / SHA1 / SHA2 / SHA3 / BLAKE2 / CRC32 计算与对比验证",
    "version": "3.0.0",
}

# hashlib 内置算法 + CRC32（12 种）
_ALGS = ("MD5", "SHA1", "SHA224", "SHA256", "SHA384", "SHA512",
         "SHA3-224", "SHA3-256", "SHA3-384", "SHA3-512",
         "BLAKE2b", "BLAKE2s", "CRC32")
_BLOCK = 1024 * 1024


def _hashlib_name(algo):
    """界面算法名 → hashlib 构造名。"""
    return {"SHA3-224": "sha3_224", "SHA3-256": "sha3_256",
            "SHA3-384": "sha3_384", "SHA3-512": "sha3_512"}.get(algo, algo.lower())


def hash_text(text, algo="SHA256"):
    """文本 → 指定算法十六进制哈希。"""
    return hash_bytes(text.encode("utf-8"), algo)


def hash_bytes(data, algo):
    """字节 → 指定算法十六进制哈希（CRC32 特殊处理）。"""
    if algo == "CRC32":
        return f"{zlib.crc32(data) & 0xffffffff:08x}"
    return getattr(hashlib, _hashlib_name(algo))(data).hexdigest()


def hash_file(path, algo="SHA256"):
    """文件（分块）→ 指定算法十六进制哈希。"""
    if algo == "CRC32":
        crc = 0
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(_BLOCK)
                if not chunk:
                    break
                crc = zlib.crc32(chunk, crc)
        return f"{crc & 0xffffffff:08x}"
    h = getattr(hashlib, _hashlib_name(algo))()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(_BLOCK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


class HashPanel(QWidget):
    """哈希校验面板（文本 / 文件双模式 + 对比验证）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setSpacing(8)
        self.sg = SegmentedWidget()
        self.sg.addItem("text", t("文本"))
        self.sg.addItem("file", t("文件"))
        self.sg.setCurrentItem("text")
        self.sg.currentItemChanged.connect(self._mode_changed)
        v.addWidget(self.sg)

        # 操作行：算法 + 选择文件 + 计算 + 复制
        row = QHBoxLayout()
        self.cb_algo = ComboBox()
        self.cb_algo.addItems(_ALGS)
        self.cb_algo.setCurrentText("SHA256")
        self.cb_algo.setFixedWidth(110)
        row.addWidget(CaptionLabel(t("算法")))
        row.addWidget(self.cb_algo)
        self.btn_pick = PrimaryPushButton(t("选择文件"))
        self.btn_pick.clicked.connect(self._pick)
        self.btn_pick.hide()
        row.addWidget(self.btn_pick)
        row.addStretch(1)
        self.btn_run = PrimaryPushButton(t("计算"))
        self.btn_run.clicked.connect(self._run)
        row.addWidget(self.btn_run)
        self.btn_copy = PrimaryPushButton(t("复制结果"))
        self.btn_copy.clicked.connect(self._copy)
        row.addWidget(self.btn_copy)
        v.addLayout(row)

        # 输入区
        self.ed_in = QPlainTextEdit()
        self.ed_in.setPlaceholderText(t("输入文本，或切换到「文件」模式选择文件…"))
        v.addWidget(self.ed_in, 1)

        # 验证行：期望哈希 + 验证按钮 + 结果提示
        vrow = QHBoxLayout()
        vrow.addWidget(CaptionLabel(t("验证哈希")))
        self.ed_verify = LineEdit()
        self.ed_verify.setPlaceholderText(t("粘贴期望的哈希值进行比对"))
        vrow.addWidget(self.ed_verify, 1)
        self.btn_verify = PrimaryPushButton(t("验证"))
        self.btn_verify.clicked.connect(self._verify)
        vrow.addWidget(self.btn_verify)
        self.lb_verify = CaptionLabel("")
        vrow.addWidget(self.lb_verify)
        v.addLayout(vrow)

        # 输出区
        self.ed_out = QPlainTextEdit()
        self.ed_out.setReadOnly(True)
        v.addWidget(self.ed_out, 1)
        self._path = ""
        self._last_result = ""      # 最近一次哈希（供验证/复制）
        self._apply_theme()
        from gui_qt.components import design_system as ds
        ds.bind_theme(self, self._apply_theme)
        self._mode_changed()

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
        self.ed_in.setReadOnly(is_file)
        if is_file and self._path:
            self.ed_in.setPlainText(self._path)
        elif not is_file:
            self.ed_in.setReadOnly(False)

    def _pick(self):
        path, _ = QFileDialog.getOpenFileName(self, t("选择文件"))
        if path:
            self._path = path
            self.ed_in.setPlainText(path)

    def _algo(self):
        return self.cb_algo.currentText()

    def _run(self):
        algo = self._algo()
        if self.sg.currentRouteKey() == "file":
            if not self._path:
                self.ed_out.setPlainText(t("请先选择文件"))
                return
            try:
                value = hash_file(self._path, algo)
            except OSError as e:
                self.ed_out.setPlainText(t("读取失败：{e}").format(e=e))
                return
            head = f"文件：{os.path.basename(self._path)}"
        else:
            value = hash_text(self.ed_in.toPlainText(), algo)
            head = t("文本哈希")
        self._last_result = value
        self.lb_verify.setText("")
        self.ed_out.setPlainText(f"{head}\n{algo}：{value}")

    def _verify(self):
        expected = self.ed_verify.text().strip().lower()
        if not expected:
            self.lb_verify.setText(t("请输入期望哈希值"))
            return
        # 未计算过 → 先自动计算
        if not self._last_result:
            self._run()
            if not self._last_result:
                self.lb_verify.setText(t("请先计算哈希"))
                return
        if self._last_result.lower() == expected:
            self.lb_verify.setText(t("✓ 哈希匹配！"))
        else:
            self.lb_verify.setText(t("✗ 不匹配"))

    def _copy(self):
        text = self.ed_out.toPlainText()
        if text:
            QApplication.clipboard().setText(text)


PANEL_CLASS = HashPanel


def on_load(ctx):
    pass


def on_unload():
    pass
