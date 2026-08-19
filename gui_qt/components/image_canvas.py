"""image_canvas — 图片画布编辑器（独立窗口）。

画布式操作：拖拽裁剪框、拖拽定位文字水印、压缩质量实时预览。
全部用 Qt 原生 QImage/QPainter 处理，不依赖外部库。

工具切换：裁剪 / 水印 / 压缩；底部「保存图片」输出到指定目录。
"""

import os

from PySide6.QtCore import Qt, QBuffer, QIODevice, QPoint, QRectF
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout,
                               QSizePolicy, QSlider, QVBoxLayout, QWidget)
from qfluentwidgets import (CaptionLabel, ComboBox, FluentIcon, LineEdit,
                            PrimaryPushButton, PushButton)

from gui_qt.components import design_system as ds
from gui_qt.i18n import tr

TOOLS = [("crop", tr("裁剪", "Crop")),
         ("watermark", tr("水印", "Watermark")),
         ("compress", tr("压缩", "Compress"))]


class CanvasView(QWidget):
    """图片画布：等比居中显示 + 裁剪框 / 水印框叠加。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pm = QPixmap()          # 当前显示图（缩放后）
        self._img = QImage()          # 原分辨率图
        self.mode = "crop"
        self.crop_rect = QRectF()     # 画布坐标下的裁剪框
        self.wm_pos = QPoint(60, 60)  # 画布坐标下的水印位置
        self.wm_text = "水印"
        self.wm_size = 36
        self.wm_opacity = 0.6
        self.setMinimumHeight(360)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._dragging = None         # "crop" | "wm" | None
        self._drag_start = QPoint()

    def load(self, img):
        self._img = img
        self._pm = QPixmap.fromImage(img)
        self.crop_rect = QRectF(self.width() * 0.08, self.height() * 0.08,
                                self.width() * 0.84, self.height() * 0.84)
        self.update()

    def _draw_rect(self):
        """返回图片在画布中居中的绘制矩形。"""
        w, h = self.width(), self.height()
        if self._pm.isNull():
            return QRectF(0, 0, w, h)
        pm = self._pm
        ratio = min(w / pm.width(), h / pm.height())
        dw, dh = pm.width() * ratio, pm.height() * ratio
        return QRectF((w - dw) / 2, (h - dh) / 2, dw, dh)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(QPen(QColor(ds.border_color()), 0.5))
        p.setBrush(QColor(ds.card_bg()))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 8, 8)
        if self._pm.isNull():
            p.setPen(QPen(QColor(ds.ink_dis()), 0))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter,
                       tr("加载图片后显示", "Load an image first"))
            p.end()
            return
        rect = self._draw_rect()
        p.drawPixmap(rect, self._pm, QRectF(0, 0, self._pm.width(),
                                            self._pm.height()))
        if self.mode == "crop":
            p.setPen(QPen(QColor(255, 170, 60), 2, Qt.DashLine))
            p.setBrush(QColor(255, 170, 60, 40))
            p.drawRect(self.crop_rect)
            p.setPen(QPen(QColor(ds.ink_sec()), 0))
            p.drawText(self.crop_rect.topLeft() + QPoint(4, 14),
                       tr("拖拽框选裁剪区域", "Drag to select crop area"))
        elif self.mode == "watermark":
            f = QFont(ds.FONT_BODY, int(self.wm_size))
            p.setFont(f)
            p.setPen(QColor(255, 255, 255, int(255 * self.wm_opacity)))
            p.drawText(self.wm_pos, self.wm_text or "水印")
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(self.wm_text or "水印")
            p.setPen(QPen(QColor(80, 200, 120), 1, Qt.DashLine))
            p.setBrush(QColor(0, 0, 0, 0))
            p.drawRect(QRectF(self.wm_pos.x(), self.wm_pos.y() - fm.ascent(),
                              tw, fm.height()))
        p.end()

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton or self._pm.isNull():
            return
        if self.mode == "crop":
            self._dragging = "crop"
            self._drag_start = e.position().toPoint()
            self.crop_rect = QRectF(e.position().x(), e.position().y(), 0, 0)
        elif self.mode == "watermark":
            self._dragging = "wm"
            self._drag_start = e.position().toPoint()
        self.update()

    def mouseMoveEvent(self, e):
        if self._dragging == "crop":
            pt = e.position()
            x0 = min(self._drag_start.x(), int(pt.x()))
            y0 = min(self._drag_start.y(), int(pt.y()))
            w = abs(int(pt.x()) - self._drag_start.x())
            h = abs(int(pt.y()) - self._drag_start.y())
            self.crop_rect = QRectF(x0, y0, w, h)
            self.update()
        elif self._dragging == "wm":
            self.wm_pos = e.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, e):
        self._dragging = None
        if self.mode == "crop" and self.crop_rect.width() < 8:
            r = self._draw_rect()
            self.crop_rect = QRectF(r.x() + r.width() * 0.05,
                                    r.y() + r.height() * 0.05,
                                    r.width() * 0.9, r.height() * 0.9)
            self.update()

    def crop_to_image(self):
        """把画布裁剪框换算成原图像素矩形，返回裁剪后的 QImage。"""
        rect = self._draw_rect()
        if self._img.isNull() or rect.width() <= 1:
            return self._img
        sx = self._img.width() / rect.width()
        sy = self._img.height() / rect.height()
        x = max(0, int((self.crop_rect.x() - rect.x()) * sx))
        y = max(0, int((self.crop_rect.y() - rect.y()) * sy))
        w = max(1, min(int(self.crop_rect.width() * sx),
                       self._img.width() - x))
        h = max(1, min(int(self.crop_rect.height() * sy),
                       self._img.height() - y))
        return self._img.copy(x, y, w, h)

    def wm_to_image(self, img):
        """在图片上按画布位置叠加文字水印，返回新 QImage。"""
        out = img.copy()
        p = QPainter(out)
        p.setRenderHint(QPainter.Antialiasing)
        f = QFont(ds.FONT_BODY, int(self.wm_size))
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, int(255 * self.wm_opacity)))
        rect = self._draw_rect()
        sx = img.width() / rect.width() if rect.width() > 0 else 1
        sy = img.height() / rect.height() if rect.height() > 0 else 1
        p.drawText(QPoint(int((self.wm_pos.x() - rect.x()) * sx),
                          int((self.wm_pos.y() - rect.y()) * sy)),
                   self.wm_text or "水印")
        p.end()
        return out


class ImageCanvasDialog(QDialog):
    """图片画布编辑器：裁剪 / 水印 / 压缩。"""

    def __init__(self, image_path, out_dir="", parent=None):
        super().__init__(parent)
        self._path = image_path or ""
        self._out_dir = out_dir or os.path.dirname(self._path) or "."
        self._img = QImage()
        self._result = QImage()     # 当前处理结果

        self.setWindowTitle(tr("图片画布编辑器", "Image Canvas Editor"))
        self.resize(920, 640)
        self.setMinimumSize(760, 520)
        self._tokens = ds.tokens()
        self._apply_theme_style()
        ds.bind_theme(self, self._refresh_theme)

        main = QVBoxLayout(self)
        main.setContentsMargins(14, 14, 14, 14)
        main.setSpacing(12)

        main.addLayout(self._build_toolbar())

        self.canvas = CanvasView(self)
        main.addWidget(self.canvas, 1)

        main.addLayout(self._build_settings())
        main.addLayout(self._build_footer())

        self._wire()
        if os.path.isfile(self._path):
            self._img = QImage(self._path)
            if self._img.isNull():
                self._img = QImage()
            else:
                self.canvas.load(self._img)
                self._result = self._img
        self._on_tool_changed()
        self._update_size_hint()
        # 子控件全部就绪后按当前主题统一刷新
        self._apply_theme_style()

    # ── UI ──────────────────────────────────────
    def _build_toolbar(self):
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.cb_tool = ComboBox()
        for key, label in TOOLS:
            self.cb_tool.addItem(label)
        self.cb_tool.setCurrentIndex(0)
        bar.addWidget(self.cb_tool)
        self.lb_file = CaptionLabel(os.path.basename(self._path) or "")
        bar.addWidget(self.lb_file, 1)
        return bar

    def _build_settings(self):
        root = QHBoxLayout()
        root.setSpacing(8)

        # 水印设置（仅水印模式可见）
        self.wm_box = QWidget()
        wh = QHBoxLayout(self.wm_box)
        wh.setContentsMargins(0, 0, 0, 0)
        wh.setSpacing(8)
        wh.addWidget(self._label(tr("文字", "Text")))
        self.ed_wm = LineEdit()
        self.ed_wm.setText(tr("水印", "Watermark"))
        self.ed_wm.setFixedWidth(140)
        wh.addWidget(self.ed_wm)
        wh.addWidget(self._label(tr("字号", "Size")))
        self.cb_wm_size = ComboBox()
        self.cb_wm_size.addItems(["24", "36", "48", "64", "80"])
        self.cb_wm_size.setCurrentText("36")
        self.cb_wm_size.setFixedWidth(70)
        wh.addWidget(self.cb_wm_size)
        wh.addWidget(self._label(tr("不透明度", "Opacity")))
        self.sl_wm = QSlider(Qt.Horizontal)
        self.sl_wm.setRange(10, 100)
        self.sl_wm.setValue(60)
        self.sl_wm.setFixedWidth(120)
        wh.addWidget(self.sl_wm)
        self.lb_wm = self._label("60%")
        wh.addWidget(self.lb_wm)
        wh.addStretch(1)
        root.addWidget(self.wm_box)

        # 压缩设置（仅压缩模式可见）
        self.cp_box = QWidget()
        ch = QHBoxLayout(self.cp_box)
        ch.setContentsMargins(0, 0, 0, 0)
        ch.setSpacing(8)
        ch.addWidget(self._label(tr("质量", "Quality")))
        self.sl_q = QSlider(Qt.Horizontal)
        self.sl_q.setRange(10, 100)
        self.sl_q.setValue(80)
        self.sl_q.setFixedWidth(200)
        ch.addWidget(self.sl_q)
        self.lb_q = self._label("80%")
        ch.addWidget(self.lb_q)
        ch.addWidget(self._label(tr("格式", "Format")))
        self.cb_fmt = ComboBox()
        self.cb_fmt.addItems(["JPG", "PNG"])
        self.cb_fmt.setFixedWidth(80)
        ch.addWidget(self.cb_fmt)
        ch.addStretch(1)
        root.addWidget(self.cp_box)
        return root

    def _build_footer(self):
        root = QHBoxLayout()
        root.setSpacing(8)
        self.lb_size = CaptionLabel("")
        root.addWidget(self.lb_size, 1)
        self.btn_preview = PushButton(FluentIcon.PLAY, tr("预览效果", "Preview"))
        self.btn_preview.setFixedHeight(32)
        root.addWidget(self.btn_preview)
        self.btn_save = PrimaryPushButton(
            FluentIcon.SAVE, tr("保存图片", "Save Image"))
        self.btn_save.setFixedHeight(32)
        root.addWidget(self.btn_save)
        self.btn_close = PushButton(tr("关闭", "Close"))
        self.btn_close.setFixedHeight(32)
        root.addWidget(self.btn_close)
        return root

    def _label(self, text):
        lb = CaptionLabel(text)
        lb.setStyleSheet(
            f"font-size: 12px; color: {self._tokens['ink_sec']};"
            " background: transparent;")
        return lb

    def _apply_theme_style(self):
        """按当前主题应用对话框与子控件样式（返回 QSS 供 bind_theme 刷新）。"""
        t = self._tokens
        qss = f"""
            QDialog {{ background: {t['page_bg']}; }}
            PushButton {{
                background: {t['card_hover']}; color: {t['ink']};
                border: 1px solid {t['border']}; border-radius: 6px;
                padding: 5px 12px; font-size: 12px;
            }}
            PushButton:hover {{ background: {t['card_active']};
                border-color: {t['accent_soft']}; }}
            PrimaryPushButton {{
                background: {t['accent']}; color: #FFFFFF; border: none;
                border-radius: 6px; padding: 5px 14px; font-size: 12px;
                font-weight: 500;
            }}
            PrimaryPushButton:hover {{ background: {t['accent_hover']}; }}
            LineEdit {{
                background: {t['card_hover']}; color: {t['ink']};
                border: 1px solid {t['border']}; border-radius: 6px;
                padding: 4px 8px; font-size: 12px;
            }}
            QSlider::groove:horizontal {{ height: 4px;
                background: {t['card_active']}; border-radius: 2px; }}
            QSlider::handle:horizontal {{ width: 12px; height: 12px;
                margin: -4px 0; border-radius: 6px;
                background: {t['accent']}; }}
        """
        self.setStyleSheet(qss)
        # 子控件样式（构造完成后才创建，用 hasattr 保护）
        if hasattr(self, "lb_file"):
            self.lb_file.setStyleSheet(
                f"font-size: 12px; color: {t['ink_sec']};"
                " background: transparent;")
        if hasattr(self, "lb_size"):
            self.lb_size.setStyleSheet(
                f"font-size: 11px; color: {t['ink_dis']};"
                " background: transparent;")
        return qss

    def _refresh_theme(self):
        """主题切换时刷新颜色令牌与对话框样式。"""
        self._tokens = ds.tokens()
        return self._apply_theme_style()

    # ── 逻辑 ────────────────────────────────────
    def _wire(self):
        self.cb_tool.currentIndexChanged.connect(self._on_tool_changed)
        self.btn_preview.clicked.connect(self._apply_preview)
        self.btn_save.clicked.connect(self._save)
        self.btn_close.clicked.connect(self.accept)
        self.sl_wm.valueChanged.connect(
            lambda v: (self.lb_wm.setText(f"{v}%"),
                       self._refresh_wm_preview()))
        self.sl_q.valueChanged.connect(
            lambda v: (self.lb_q.setText(f"{v}%"),
                       self._update_size_hint()))
        self.ed_wm.textChanged.connect(self._refresh_wm_preview)
        self.cb_wm_size.currentTextChanged.connect(self._refresh_wm_preview)

    def _on_tool_changed(self):
        idx = self.cb_tool.currentIndex()
        key = TOOLS[idx][0]
        self.canvas.mode = key
        self.wm_box.setVisible(key == "watermark")
        self.cp_box.setVisible(key == "compress")
        self.btn_preview.setVisible(key != "compress")
        self.canvas.update()

    def _refresh_wm_preview(self):
        if self.canvas.mode != "watermark":
            return
        self.canvas.wm_text = self.ed_wm.text().strip() or "水印"
        try:
            self.canvas.wm_size = int(self.cb_wm_size.currentText())
        except ValueError:
            pass
        self.canvas.wm_opacity = self.sl_wm.value() / 100.0
        self.canvas.update()

    def _apply_preview(self):
        if self._img.isNull():
            return
        if self.canvas.mode == "crop":
            self._result = self.canvas.crop_to_image()
            self.canvas.load(self._result)
        elif self.canvas.mode == "watermark":
            self._refresh_wm_preview()
            self._result = self.canvas.wm_to_image(self._img)
            self.canvas.load(self._result)
        self._update_size_hint()

    def _update_size_hint(self):
        img = self._result
        if img.isNull():
            self.lb_size.setText("")
            return
        w, h = img.width(), img.height()
        # 估算输出文件大小
        quality = self.sl_q.value() if self.canvas.mode == "compress" else 90
        fmt = self.cb_fmt.currentText().lower()
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        img.save(buf, fmt, quality)
        size = buf.size()
        buf.close()
        self.lb_size.setText(
            f"{w}×{h} · {size / 1024:.1f} KB"
            + (f" · {tr('质量', 'quality')} {quality}%"
               if self.canvas.mode == "compress" else ""))

    def _save(self):
        if self._result.isNull():
            from gui_qt.components import toast
            toast.show_warning(self, tr("没有可保存的图片", "Nothing to save"))
            return
        quality = self.sl_q.value() if self.canvas.mode == "compress" else 90
        fmt = self.cb_fmt.currentText().lower()
        ext = "jpg" if fmt == "jpg" else "png"
        name = os.path.splitext(os.path.basename(self._path))[0]
        default = os.path.join(self._out_dir, f"{name}_编辑.{ext}")
        path, _ = QFileDialog.getSaveFileName(
            self, tr("保存图片", "Save image"), default,
            tr("图片文件 (*.{})", "Images (*.{})").format(ext))
        if not path:
            return
        if not self._result.save(path, fmt, quality):
            from gui_qt.components import toast
            toast.show_error(self, tr("保存失败", "Save failed"))
            return
        from gui_qt.components import toast
        toast.show_success(self, tr("已保存", "Saved") + f" {os.path.basename(path)}")
