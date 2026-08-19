# -*- coding: utf-8 -*-
"""glass_bar — 毛玻璃横幅组件（PIL 高斯模糊 + 半透明覆盖）。

抓取所在窗口对应区域 → PIL GaussianBlur → 作为背景绘制，再叠半透明
主题色罩。用于弹窗工具条/横幅等小区域毛玻璃质感（大区域实时刷新
有性能开销，仅用于静态内容区）。主窗口标题栏毛玻璃由系统 Mica 提供。
"""
import os

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from gui_qt.components import design_system as ds


class GlassBar(QWidget):
    """毛玻璃横幅：set_glass_enabled(True) 时抓背景模糊，False 时普通透明。"""

    def __init__(self, parent=None, blur_radius=14):
        super().__init__(parent)
        self._blur_radius = blur_radius
        self._blurred = None
        self._enabled = True
        self.setAttribute(Qt.WA_TranslucentBackground)

    def set_glass_enabled(self, on):
        self._enabled = on
        if on:
            self._refresh()
        else:
            self._blurred = None
            self.update()

    def _refresh(self):
        """抓取主窗口对应区域并模糊（静态快照，resize/show 时调用）。"""
        if not self._enabled:
            return
        # offscreen（无真实窗口）下 win.grab() 会原生段错误，必须跳过
        if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
            return
        win = self.window()
        if win is None or win.isHidden():
            return
        pos = self.mapTo(win, QPoint(0, 0))
        if pos.x() < 0 or pos.y() < 0:
            return
        try:
            pix = win.grab(QRect(pos, self.size()))
            img = _blur_pixmap(pix, self._blur_radius)
            self._blurred = img
            self.update()
        except Exception:  # noqa: BLE001
            self._blurred = None

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        if self._blurred is not None:
            painter.drawPixmap(self.rect(), self._blurred)
        # 半透明主题色罩：浅色低透明度白、深色低透明度黑
        try:
            dark = ds.isDarkTheme()
        except Exception:  # noqa: BLE001
            dark = False
        tint = QColor(20, 20, 24, 70) if dark else QColor(255, 255, 255, 88)
        painter.fillRect(self.rect(), tint)

    def showEvent(self, e):
        self._refresh()
        super().showEvent(e)

    def resizeEvent(self, e):
        self._refresh()
        super().resizeEvent(e)


def _blur_pixmap(pix, radius):
    """PIL GaussianBlur 模糊 QPixmap → 返回 QPixmap。"""
    from PIL import Image, ImageFilter
    qimg = pix.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = qimg.width(), qimg.height()
    # PySide6 6.11：bits() 返回 memoryview，直接 bytes() 取数据
    img = Image.frombuffer("RGBA", (w, h), bytes(qimg.constBits()),
                           "raw", "RGBA", 0, 1)
    img = img.filter(ImageFilter.GaussianBlur(radius))
    from PIL.ImageQt import ImageQt
    return QPixmap.fromImage(ImageQt(img))
