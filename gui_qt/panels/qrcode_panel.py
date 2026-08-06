"""qrcode_panel — 二维码生成面板（阶段2 迁移自 gui/panels/qrcode_panel.py + main.py 生成逻辑）。

将文本/网址/WiFi/名片内容生成二维码图片（qrcode + Pillow），
支持自定义尺寸、边距与前后颜色，实时预览并可保存为图片。
生成为毫秒级纯内存操作，直接在主线程同步执行。
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel,
                               QVBoxLayout, QWidget)
from qfluentwidgets import (FluentIcon, CaptionLabel, ComboBox, LineEdit,
                            PasswordLineEdit, PrimaryPushButton, PushButton,
                            TextEdit)

from gui_qt.components import toast
from gui_qt.panels.base_panel import BaseQtPanel

# 预置值（与 tkinter 版 qrcode_panel 一致）
TYPE_VALUES = ["文本", "网址", "WiFi", "名片"]
SIZE_VALUES = ["200", "300", "400", "500", "600"]
BORDER_VALUES = ["1", "2", "4", "6"]
DEFAULT_FG = "#000000"
DEFAULT_BG = "#FFFFFF"

VCARD_TPL = "BEGIN:VCARD\nFN:姓名\nTEL:13800138000\nEMAIL:email@example.com\nEND:VCARD"


class QrcodePanelPage(BaseQtPanel):
    """二维码生成页。"""

    panel_key = "qrcode"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title("二维码生成器"))
        lay.addWidget(CaptionLabel("将文本、链接、联系方式等生成二维码图片"))

        from gui_qt.components.form_widgets import FormSection, FormGrid

        # 内容设置
        sec = FormSection("内容设置", FluentIcon.EDIT)
        grid = FormGrid(columns=1)

        self.cb_type = grid.add_field(
            "内容类型", self._combo(TYPE_VALUES, "文本"),
            hint="选择要生成的二维码内容类型")
        self.cb_type.currentTextChanged.connect(self._on_type_changed)

        self.txt_content = TextEdit()
        self.txt_content.setPlainText("Hello World")
        self.txt_content.setFixedHeight(80)
        from gui_qt.components import design_system as _ds
        _ds.apply_text_edit_style(self.txt_content)
        grid.add_field("内容", self.txt_content, hint="输入二维码内容")

        # WiFi 区（默认隐藏）
        self.wifi_frame = QHBoxLayout()
        self.wifi_frame.setSpacing(8)
        self.wifi_frame.addWidget(CaptionLabel("WiFi名称"))
        self.ed_ssid = LineEdit()
        self.ed_ssid.setPlaceholderText("输入WiFi名称")
        self.wifi_frame.addWidget(self.ed_ssid)
        self.wifi_frame.addWidget(CaptionLabel("密码"))
        self.ed_pass = PasswordLineEdit()
        self.ed_pass.setPlaceholderText("输入WiFi密码")
        self.wifi_frame.addWidget(self.ed_pass)
        wifi_holder = QWidget()
        wifi_holder.setLayout(self.wifi_frame)
        grid.add_field("WiFi", wifi_holder, colspan=1)
        self._set_wifi_visible(False)
        sec.add_form(grid)
        lay.addWidget(sec)

        # 外观设置
        sec_style = FormSection("外观设置", FluentIcon.PALETTE)
        g2 = FormGrid(columns=4)

        self.cb_size = g2.add_field(
            "尺寸", self._combo(SIZE_VALUES, "400"),
            hint="二维码像素尺寸")
        self.cb_border = g2.add_field(
            "边距", self._combo(BORDER_VALUES, "4"),
            hint="二维码空白边距")
        self.ed_fg = g2.add_field(
            "前景色", self._make_color_edit(DEFAULT_FG),
            hint="二维码图案颜色")
        self.ed_bg = g2.add_field(
            "背景色", self._make_color_edit(DEFAULT_BG),
            hint="二维码背景颜色")
        sec_style.add_form(g2)
        lay.addWidget(sec_style)

        # 预览区
        sec_prev = FormSection("预览", FluentIcon.VIEW)
        self.lb_preview = QLabel("点击「生成二维码」预览")
        self.lb_preview.setAlignment(Qt.AlignCenter)
        self.lb_preview.setMinimumHeight(220)
        sec_prev.add_widget(self.lb_preview)
        lay.addWidget(sec_prev)

        # 操作按钮
        brow = QHBoxLayout()
        brow.setSpacing(8)
        self.btn_go = PrimaryPushButton("生成二维码")
        self.btn_go.clicked.connect(self._generate)
        self.btn_save = PushButton("保存为图片")
        self.btn_save.clicked.connect(self._save)
        brow.addWidget(self.btn_go)
        brow.addWidget(self.btn_save)
        brow.addStretch(1)
        self.lb_status = CaptionLabel("就绪")
        brow.addWidget(self.lb_status)
        lay.addLayout(brow)

        self._qr_img = None  # PIL Image，保存用（保持引用）

    # ── 表单辅助 ─────────────────────────────────
    def _combo(self, items, default):
        cb = ComboBox()
        cb.addItems(items)
        cb.setCurrentText(default)
        return cb

    def _make_color_edit(self, text):
        ed = LineEdit()
        ed.setText(text)
        ed.setFixedWidth(90)
        return ed

    # ── 交互 ─────────────────────────────────────
    def _set_wifi_visible(self, visible):
        for i in range(self.wifi_frame.count()):
            w = self.wifi_frame.itemAt(i).widget()
            if w is not None:
                w.setVisible(visible)

    def _on_type_changed(self, t):
        if t == "WiFi":
            self._set_wifi_visible(True)
            self.txt_content.setEnabled(False)
            self.txt_content.setPlainText("↓ 在上方填写WiFi名称和密码")
            self.ed_ssid.setFocus()
        else:
            self._set_wifi_visible(False)
            self.txt_content.setEnabled(True)
            if t == "网址":
                self.txt_content.setPlainText("https://")
            elif t == "名片":
                self.txt_content.setPlainText(VCARD_TPL)
            else:
                self.txt_content.setPlainText("Hello World")

    def _generate(self):
        try:
            import qrcode
        except ImportError:
            toast.show_error(self, "缺少 qrcode 库，请先执行 pip install qrcode[pil]")
            return

        t = self.cb_type.currentText()
        if t == "WiFi":
            ssid = self.ed_ssid.text().strip()
            pwd = self.ed_pass.text().strip()
            if not ssid:
                toast.show_warning(self, "请输入WiFi名称")
                return
            content = f"WIFI:T:WPA;S:{ssid};P:{pwd};;"
        else:
            content = self.txt_content.toPlainText().strip()
            if not content:
                toast.show_warning(self, "请输入内容")
                return

        try:
            fg = self.ed_fg.text().strip() or DEFAULT_FG
            bg = self.ed_bg.text().strip() or DEFAULT_BG
            size = int(self.cb_size.currentText())
            border = int(self.cb_border.currentText())

            qr = qrcode.QRCode(version=None,
                               error_correction=qrcode.constants.ERROR_CORRECT_H,
                               box_size=10, border=border)
            qr.add_data(content)
            qr.make(fit=True)
            img = qr.make_image(fill_color=fg, back_color=bg).convert("RGB")
            img = img.resize((size, size), resample=0)
        except Exception as e:  # noqa: BLE001
            toast.show_error(self, f"生成失败：{e}")
            self.lb_status.setText("生成失败")
            return

        self._qr_img = img
        self._show_preview(img)
        self.lb_status.setText(f"已生成 {size}×{size} 二维码")
        self.save_prefs()

    def _show_preview(self, img):
        """PIL Image → QPixmap 显示到预览区。"""
        try:
            from PIL.ImageQt import ImageQt
            qimg = ImageQt(img)
            pix = QPixmap.fromImage(qimg)
            self.lb_preview.setPixmap(pix.scaled(
                240, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception as e:  # noqa: BLE001
            toast.show_error(self, f"预览失败：{e}")

    def _save(self):
        if self._qr_img is None:
            toast.show_warning(self, "请先生成二维码")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "保存二维码", "qrcode.png",
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg);;所有文件 (*.*)")
        if not path:
            return
        try:
            self._qr_img.save(path)
            self.lb_status.setText(f"已保存: {path.split('/')[-1]}")
            toast.show_success(self, f"二维码已保存: {path}")
        except Exception as e:  # noqa: BLE001
            toast.show_error(self, f"保存失败：{e}")

    # ── 参数/偏好（5 键与 tkinter 版一致）─────────
    def collect_params(self) -> dict:
        return {
            "type": self.cb_type.currentText(),
            "text": self.txt_content.toPlainText().strip(),
            "wifi_ssid": self.ed_ssid.text(),
            "wifi_pass": self.ed_pass.text(),
            "size": self.cb_size.currentText(),
            "border": self.cb_border.currentText(),
            "fg": self.ed_fg.text(),
            "bg": self.ed_bg.text(),
        }

    def collect_prefs(self) -> dict:
        return {
            "qr_type": self.cb_type.currentText(),
            "qr_size": self.cb_size.currentText(),
            "qr_border": self.cb_border.currentText(),
            "qr_fg": self.ed_fg.text(),
            "qr_bg": self.ed_bg.text(),
        }

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        if prefs.get("qr_type") in TYPE_VALUES:
            self.cb_type.setCurrentText(prefs["qr_type"])
            # 切换类型会重置内容文本，恢复后保持默认提示
        if prefs.get("qr_size") in SIZE_VALUES:
            self.cb_size.setCurrentText(prefs["qr_size"])
        if prefs.get("qr_border") in BORDER_VALUES:
            self.cb_border.setCurrentText(prefs["qr_border"])
        if prefs.get("qr_fg"):
            self.ed_fg.setText(prefs["qr_fg"])
        if prefs.get("qr_bg"):
            self.ed_bg.setText(prefs["qr_bg"])
