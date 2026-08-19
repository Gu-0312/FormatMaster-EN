"""qrcode_panel — 二维码生成面板（阶段2 迁移自 gui/panels/qrcode_panel.py + main.py 生成逻辑）。

将文本/网址/WiFi/名片内容生成二维码图片（qrcode + Pillow），
支持自定义尺寸、边距与前后颜色，实时预览并可保存为图片。
生成为毫秒级纯内存操作，直接在主线程同步执行。
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel,
                               QVBoxLayout, QWidget)
from qfluentwidgets import (FluentIcon, CaptionLabel, ComboBox, LineEdit,
                            PasswordLineEdit, PrimaryPushButton, PushButton,
                            TextEdit)

from gui_qt.i18n import tr
from gui_qt.components import toast
from gui_qt.panels.base_panel import BaseQtPanel

# 预置值（与 tkinter 版 qrcode_panel 一致）
TYPE_VALUES = [tr("文本", "Text"), tr("网址", "URL"), "WiFi", tr("名片", "Card")]
SIZE_VALUES = ["200", "300", "400", "500", "600"]
BORDER_VALUES = ["1", "2", "4", "6"]
DEFAULT_FG = "#000000"
DEFAULT_BG = "#FFFFFF"

VCARD_TPL = tr("BEGIN:VCARD\nFN:姓名\nTEL:13800138000\nEMAIL:email@example.com\nEND:VCARD", "BEGIN:VCARD\nFN:Name\nTEL:13800138000\nEMAIL:email@example.com\nEND:VCARD")


class QrcodePanelPage(BaseQtPanel):
    """二维码生成页。"""

    panel_key = "qrcode"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("二维码生成器", "QR code generator")))
        lay.addWidget(CaptionLabel(tr("将文本、链接、联系方式等生成二维码图片", "Generate QR codes from text, links, contact info")))

        from gui_qt.components.form_widgets import FormSection, FormGrid

        # 内容设置
        sec = FormSection(tr("内容设置", "Content"), FluentIcon.EDIT)
        grid = FormGrid(columns=1)

        self.cb_type = grid.add_field(
            tr("内容类型", "Content type"), self._combo(TYPE_VALUES, tr("文本", "Text")),
            hint=tr("选择要生成的二维码内容类型", "Choose QR content type"))
        self.cb_type.currentTextChanged.connect(self._on_type_changed)

        self.txt_content = TextEdit()
        self.txt_content.setPlainText("Hello World")
        self.txt_content.setFixedHeight(80)
        from gui_qt.components import design_system as _ds
        _ds.apply_text_edit_style(self.txt_content)
        grid.add_field(tr("内容", "Content"), self.txt_content,
                        hint=tr("输入二维码内容", "Enter QR content"))

        # WiFi 区（默认隐藏）
        self.wifi_frame = QHBoxLayout()
        self.wifi_frame.setSpacing(8)
        self.wifi_frame.addWidget(CaptionLabel(tr("WiFi名称", "WiFi name")))
        self.ed_ssid = LineEdit()
        self.ed_ssid.setPlaceholderText(tr("输入WiFi名称", "Enter WiFi name"))
        self.wifi_frame.addWidget(self.ed_ssid)
        self.wifi_frame.addWidget(CaptionLabel(tr("密码", "Password")))
        self.ed_pass = PasswordLineEdit()
        self.ed_pass.setPlaceholderText(tr("输入WiFi密码", "Enter WiFi password"))
        self.wifi_frame.addWidget(self.ed_pass)
        wifi_holder = QWidget()
        wifi_holder.setLayout(self.wifi_frame)
        grid.add_field("WiFi", wifi_holder, colspan=1)
        self._set_wifi_visible(False)
        sec.add_form(grid)
        lay.addWidget(sec)

        # 外观设置
        from gui_qt.components.form_widgets import CollapsibleSection
        sec_style = FormSection(tr("外观设置", "Appearance"), FluentIcon.PALETTE)
        g2 = FormGrid(columns=4)
        self.cb_size = g2.add_field(
            tr("尺寸", "Size"), self._combo(SIZE_VALUES, "400"),
            hint=tr("二维码像素尺寸", "QR pixel size"))
        self.cb_style = g2.add_field(
            tr("模块样式", "Module style"),
            self._combo([tr("经典方块", "Square"),
                         tr("圆角方块", "Rounded"),
                         tr("圆点", "Dots"),
                         tr("菱形", "Diamond")], tr("经典方块", "Square")),
            hint=tr("二维码图案样式", "QR module style"))
        self.cb_grad = g2.add_field(
            tr("渐变", "Gradient"),
            self._combo([tr("无", "None"), tr("垂直", "Vertical"),
                         tr("对角", "Diagonal")], tr("无", "None")),
            hint=tr("前景色渐变（搭配主题色更精致）", "Foreground gradient"))
        sec_style.add_form(g2)

        # Logo 行：选择 Logo 图片（可选，圆形遮罩+白边）
        logo_row = QHBoxLayout()
        logo_row.setSpacing(8)
        self.btn_logo = PushButton(FluentIcon.PHOTO, tr("选择 Logo…", "Pick Logo…"))
        self.btn_logo.clicked.connect(self._pick_logo)
        self.btn_logo_clear = PushButton(FluentIcon.CANCEL, tr("清除", "Clear"))
        self.btn_logo_clear.clicked.connect(self._clear_logo)
        self.btn_logo_clear.setEnabled(False)
        logo_row.addWidget(self.btn_logo)
        logo_row.addWidget(self.btn_logo_clear)
        self.lb_logo = CaptionLabel(tr("未选择（可选）", "None (optional)"))
        logo_row.addWidget(self.lb_logo)
        logo_row.addStretch(1)
        logo_holder = QWidget()
        logo_holder.setLayout(logo_row)
        sec_style.add_widget(logo_holder)

        adv = CollapsibleSection(
            tr("高级设置", "Advanced"),
            hint=tr("边距 / 前景色 / 背景色（通常无需调整）",
                    "Margin / foreground / background (usually leave as-is)"))
        adv_grid = FormGrid(columns=4)
        self.cb_border = adv_grid.add_field(
            tr("边距", "Margin"), self._combo(BORDER_VALUES, "4"),
            hint=tr("二维码空白边距", "QR margin"))
        self.ed_fg = adv_grid.add_field(
            tr("前景色", "Foreground"), self._make_color_edit(DEFAULT_FG),
            hint=tr("二维码图案颜色", "QR foreground color"))
        self.ed_bg = adv_grid.add_field(
            tr("背景色", "Background"), self._make_color_edit(DEFAULT_BG),
            hint=tr("二维码背景颜色", "QR background color"))
        adv.add_layout(adv_grid)
        # 取色按钮行：前景/背景一键取色（qfw ColorDialog）
        color_bar = QHBoxLayout()
        color_bar.setSpacing(8)
        from qfluentwidgets import ToolButton
        self.btn_fg_pick = ToolButton(FluentIcon.PALETTE)
        self.btn_fg_pick.setToolTip(tr("取前景色", "Pick foreground color"))
        self.btn_fg_pick.clicked.connect(lambda: self._pick_color(self.ed_fg))
        color_bar.addWidget(self.btn_fg_pick)
        color_bar.addWidget(CaptionLabel(tr("取前景色", "Foreground")))
        color_bar.addSpacing(12)
        self.btn_bg_pick = ToolButton(FluentIcon.PALETTE)
        self.btn_bg_pick.setToolTip(tr("取背景色", "Pick background color"))
        self.btn_bg_pick.clicked.connect(lambda: self._pick_color(self.ed_bg))
        color_bar.addWidget(self.btn_bg_pick)
        color_bar.addWidget(CaptionLabel(tr("取背景色", "Background")))
        color_bar.addStretch(1)
        _holder = QWidget()
        _holder.setLayout(color_bar)
        adv.add_widget(_holder)
        sec_style.add_widget(adv)
        lay.addWidget(sec_style)

        # 预览区（ImageLabel：平滑缩放 + 圆角；外包居中容器——ImageLabel 自绘
        # 忽略 QLabel alignment，靠左显示，须用布局 stretch 水平垂直居中）
        sec_prev = FormSection(tr("预览", "Preview"), FluentIcon.VIEW)
        from qfluentwidgets import ImageLabel
        from PySide6.QtWidgets import (QHBoxLayout as _HL,
                                       QVBoxLayout as _VL, QWidget as _QW)
        self.lb_preview = ImageLabel(
            tr("点击「生成二维码」预览", "Click \"Generate QR\" to preview"), self)
        self.lb_preview.setMinimumHeight(220)
        self.lb_preview.setBorderRadius(12, 12, 12, 12)
        holder = _QW()
        hv = _VL(holder)
        hv.setContentsMargins(0, 8, 0, 8)
        hv.addStretch(1)
        hh = _HL()
        hh.addStretch(1)
        hh.addWidget(self.lb_preview)
        hh.addStretch(1)
        hv.addLayout(hh)
        hv.addStretch(1)
        holder.setMinimumHeight(260)
        sec_prev.add_widget(holder)
        lay.addWidget(sec_prev)

        # 操作按钮
        brow = QHBoxLayout()
        brow.setSpacing(8)
        self.btn_go = PrimaryPushButton(tr("生成二维码", "Generate QR"))
        self.btn_go.clicked.connect(self._generate)
        self.btn_save = PushButton(tr("保存为图片", "Save as image"))
        self.btn_save.clicked.connect(self._save)
        brow.addWidget(self.btn_go)
        brow.addWidget(self.btn_save)
        brow.addStretch(1)
        self.lb_status = CaptionLabel(tr("就绪", "Ready"))
        brow.addWidget(self.lb_status)
        lay.addLayout(brow)

        self._qr_img = None  # PIL Image，保存用（保持引用）
        self._logo_path = None  # 可选 Logo 图片路径

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

    def _pick_color(self, edit):
        """弹 Qt 原生 QColorDialog 取色并写回输入框。

        为什么弃用 qfw ColorDialog（实测 1.11.3 反复出"选了没变化"）：
        - 依赖遮罩层 + show 淡入 200ms + done 淡出 100ms 动画（异步关闭）；
        - 主类 colorChanged 只在点 OK 且颜色 != oldColor 时发一次；
        - 真实 GUI 环境下取色结果易在动画/时序缝隙丢失。
        Qt 原生 QColorDialog.getColor() 是标准模态对话框，直接返回 QColor，
        取消返回无效色，行为 100% 可预期——功能可靠性优先于 Fluent 外观。
        另注意：DEFAULT_FG 本就是 #000000（标准黑色二维码），未取色时
        输入框显示 #000000 属正常初始状态，并非取色失效。
        """
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QColorDialog
        init = QColor(edit.text().strip()) if edit.text().strip() else QColor("#000000")
        if not init.isValid():
            init = QColor("#000000")
        color = QColorDialog.getColor(init, self.window(), tr("选择颜色", "Pick color"))
        if color.isValid():
            edit.setText(color.name())
            self._generate()
            from gui_qt.components import toast
            toast.show_success(
                self,
                tr("已应用颜色 {}", "Color applied {}").format(color.name()))

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
            self.txt_content.setPlainText(tr("↓ 在上方填写WiFi名称和密码", "↓ Fill in WiFi name and password above"))
            self.ed_ssid.setFocus()
        else:
            self._set_wifi_visible(False)
            self.txt_content.setEnabled(True)
            if t == tr("网址", "URL"):
                self.txt_content.setPlainText("https://")
            elif t == tr("名片", "Card"):
                self.txt_content.setPlainText(VCARD_TPL)
            else:
                self.txt_content.setPlainText("Hello World")

    def _generate(self):
        t = self.cb_type.currentText()
        if t == "WiFi":
            ssid = self.ed_ssid.text().strip()
            pwd = self.ed_pass.text().strip()
            if not ssid:
                toast.show_warning(self, tr("请输入WiFi名称", "Enter WiFi name"))
                return
            content = f"WIFI:T:WPA;S:{ssid};P:{pwd};;"
        else:
            content = self.txt_content.toPlainText().strip()
            if not content:
                toast.show_warning(self, tr("请输入内容", "Enter content"))
                return

        try:
            from core.qr_maker import (make_fancy_qr, GRAD_NONE, GRAD_VERTICAL,
                                       GRAD_DIAGONAL, STYLE_SQUARE,
                                       STYLE_ROUNDED, STYLE_DOT, STYLE_DIAMOND)
            fg = self.ed_fg.text().strip() or DEFAULT_FG
            bg = self.ed_bg.text().strip() or DEFAULT_BG
            size = int(self.cb_size.currentText())
            border = int(self.cb_border.currentText())
            style_map = {tr("经典方块", "Square"): STYLE_SQUARE,
                         tr("圆角方块", "Rounded"): STYLE_ROUNDED,
                         tr("圆点", "Dots"): STYLE_DOT,
                         tr("菱形", "Diamond"): STYLE_DIAMOND}
            grad_map = {tr("无", "None"): GRAD_NONE,
                        tr("垂直", "Vertical"): GRAD_VERTICAL,
                        tr("对角", "Diagonal"): GRAD_DIAGONAL}
            img = make_fancy_qr(
                content, size=size, fg=fg, bg=bg,
                style=style_map.get(self.cb_style.currentText(), STYLE_SQUARE),
                gradient=grad_map.get(self.cb_grad.currentText(), GRAD_NONE),
                logo_path=getattr(self, "_logo_path", None) or "",
                border=border)
        except Exception as e:  # noqa: BLE001
            toast.show_error(self, f"生成失败：{e}")
            self.lb_status.setText(tr("生成失败", "Failed"))
            return

        self._qr_img = img
        self._show_preview(img)
        self.lb_status.setText(tr("已生成 {}×{} 二维码", "QR generated {}x{}").format(size, size))
        self.save_prefs()

    # ── Logo 选择 ─────────────────────────────────
    def _pick_logo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("选择 Logo 图片", "Pick logo image"), "",
            tr("图片文件 (*.png *.jpg *.jpeg *.webp *.bmp);;所有文件 (*.*)",
               "Images (*.png *.jpg *.jpeg *.webp *.bmp);;All files (*.*)"))
        if not path:
            return
        self._logo_path = path
        self.lb_logo.setText(tr("Logo：{}", "Logo: {}").format(
            os.path.basename(path)))
        self.btn_logo_clear.setEnabled(True)
        # 有内容时立即重新生成预览
        if self._has_content():
            self._generate()
        else:
            toast.show_info(self, tr("已选择 Logo，填写内容后生成",
                                     "Logo set, fill content then generate"))

    def _clear_logo(self):
        self._logo_path = None
        self.lb_logo.setText(tr("未选择（可选）", "None (optional)"))
        self.btn_logo_clear.setEnabled(False)
        if self._has_content():
            self._generate()

    def _has_content(self) -> bool:
        """当前是否有可生成的内容（WiFi 或文本）。"""
        if self.cb_type.currentText() == "WiFi":
            return bool(self.ed_ssid.text().strip())
        return bool(self.txt_content.toPlainText().strip())

    def _show_preview(self, img):
        """PIL Image → QPixmap 显示到预览区。"""
        try:
            from PIL.ImageQt import ImageQt
            qimg = ImageQt(img)
            pix = QPixmap.fromImage(qimg)
            self.lb_preview.setPixmap(pix.scaled(
                240, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception as e:  # noqa: BLE001
            toast.show_error(self, tr("预览失败：{}", "Preview failed: {}").format(e))

    def _save(self):
        if self._qr_img is None:
            toast.show_warning(self, tr("请先生成二维码", "Generate a QR code first"))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr("保存二维码", "Save QR"), "qrcode.png",
            tr("PNG 图片 (*.png);;JPEG 图片 (*.jpg);;所有文件 (*.*)", "PNG images (*.png);;JPEG images (*.jpg);;All files (*.*)"))
        if not path:
            return
        try:
            self._qr_img.save(path)
            self.lb_status.setText(tr("已保存: {}", "Saved: {}").format(path.split('/')[-1]))
            toast.show_success(self, tr("二维码已保存: {}", "QR saved: {}").format(path))
        except Exception as e:  # noqa: BLE001
            toast.show_error(self, tr("保存失败：{}", "Save failed: {}").format(e))

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
            "style": self.cb_style.currentText(),
            "gradient": self.cb_grad.currentText(),
            "logo": getattr(self, "_logo_path", None) or "",
        }

    def collect_prefs(self) -> dict:
        return {
            "qr_type": self.cb_type.currentText(),
            "qr_size": self.cb_size.currentText(),
            "qr_border": self.cb_border.currentText(),
            "qr_fg": self.ed_fg.text(),
            "qr_bg": self.ed_bg.text(),
            "qr_style": self.cb_style.currentIndex(),
            "qr_grad": self.cb_grad.currentIndex(),
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
        si = prefs.get("qr_style")
        if isinstance(si, int) and 0 <= si < self.cb_style.count():
            self.cb_style.setCurrentIndex(si)
        gi = prefs.get("qr_grad")
        if isinstance(gi, int) and 0 <= gi < self.cb_grad.count():
            self.cb_grad.setCurrentIndex(gi)
