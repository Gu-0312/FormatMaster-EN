"""visual_widgets — 通用可视化组件库（Prism 设计系统，QPainter 自绘）。

提供 5 个可复用组件，支撑全部"高潜力可视化"功能：
- WaveformWidget  音频波形 + 频谱 + 鼠标选区（音频处理/增强）
- CompareSlider   前后对比滑动条（证件照/图片/GIF 转换前后）
- FrameGrid       帧/图网格点选（视频抽帧/缩略图/拼接）
- OverlayCanvas   底图 + 彩色区域框 + 可拖拽矩形（OCR 区域框/水印/裁剪框）
- SizeCompareBar  前后大小对比条（视频/图片压缩）

所有组件自绘、随亮/暗主题自动取令牌色，无第三方依赖。
"""

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from gui_qt.components import design_system as ds


def _as_pixmap(src):
    """路径或 QPixmap → QPixmap；失败返回空 pixmap。"""
    if isinstance(src, QPixmap):
        return src
    if isinstance(src, str):
        pm = QPixmap(src)
        if not pm.isNull():
            return pm
    return QPixmap()


# ─────────────────────────────────────────────────────
#  1. WaveformWidget — 音频波形 + 频谱 + 选区
# ─────────────────────────────────────────────────────
class WaveformWidget(QWidget):
    """音频波形可视化。支持：峰值柱状波形、频谱叠加、鼠标拖选区间。

    信号：
        selection_changed(begin_ratio, end_ratio)  选区变化（0~1 比例）
    方法：
        set_peaks(peaks)        设置波形峰值（-1~1 列表）
        set_spectrum(bins)      设置频谱幅度（0~1 列表，None 关闭）
        set_selection(b0, b1)   程序设置选区
        clear()                 清空
    """

    selection_changed = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._peaks = []
        self._spec = None
        self._sel = (0.0, 1.0)
        self._dragging = False
        self.setMinimumHeight(96)
        self.setMouseTracking(True)
        self._cursor_ratio = -1.0

    def set_peaks(self, peaks):
        self._peaks = list(peaks) if peaks else []
        self.update()

    def set_spectrum(self, bins):
        self._spec = list(bins) if bins else None
        self.update()

    def set_selection(self, b0, b1):
        b0 = max(0.0, min(1.0, b0))
        b1 = max(0.0, min(1.0, b1))
        self._sel = (min(b0, b1), max(b0, b1))
        self.update()

    def selection(self):
        return self._sel

    def clear(self):
        self._peaks = []
        self._spec = None
        self._sel = (0.0, 1.0)
        self.update()

    # ── 交互 ──
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self._peaks:
            self._dragging = True
            r = e.position().x() / max(self.width(), 1)
            self.set_selection(r, r)
            self.selection_changed.emit(*self._sel)

    def mouseMoveEvent(self, e):
        r = e.position().x() / max(self.width(), 1)
        self._cursor_ratio = r
        if self._dragging and self._peaks:
            self.set_selection(self._sel[0], r)
            self.selection_changed.emit(*self._sel)
        else:
            self.update()

    def mouseReleaseEvent(self, e):
        if self._dragging:
            self._dragging = False
            self.selection_changed.emit(*self._sel)

    def leaveEvent(self, e):
        self._cursor_ratio = -1.0
        self.update()

    # ── 绘制 ──
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        if w < 8 or h < 8:
            p.end()
            return
        mid = h / 2
        accent = QColor(ds.accent())
        ink = QColor(ds.ink_sec())
        sel_c = QColor(accent)
        sel_c.setAlpha(38)
        border = QColor(ds.border_color())

        p.setPen(QPen(border, 0.5))
        p.setBrush(QColor(ds.card_bg()))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 8, 8)

        # 选区高亮
        x0 = self._sel[0] * w
        x1 = self._sel[1] * w
        if x1 - x0 > 1:
            p.setPen(Qt.NoPen)
            p.setBrush(sel_c)
            p.drawRect(QRectF(x0, 3, x1 - x0, h - 6))
        # 中线
        p.setPen(QPen(QColor(ink.red(), ink.green(), ink.blue(), 60), 1))
        p.drawLine(QPointF(4, mid), QPointF(w - 4, mid))

        # 频谱（底部 28% 区域，半透明条形）
        if self._spec and len(self._spec) > 1:
            sb = int(h * 0.66)
            sh = int(h * 0.3)
            step = (w - 8) / len(self._spec)
            p.setPen(Qt.NoPen)
            c = QColor(ds.accent())
            c.setAlpha(70)
            p.setBrush(c)
            for i, v in enumerate(self._spec):
                bh = max(2.0, sh * max(0.0, min(1.0, v)))
                p.drawRect(QRectF(4 + i * step, sb + sh - bh, max(1.0, step - 1.2), bh))

        # 波形柱
        if self._peaks:
            n = len(self._peaks)
            step = (w - 8) / n
            bw = max(1.0, step - 1.0)
            p.setPen(Qt.NoPen)
            p.setBrush(accent)
            body_top, body_bot = 4.0, h * 0.62
            for i, v in enumerate(self._peaks):
                v = max(-1.0, min(1.0, v))
                x = 4 + i * step
                amp = (body_bot - body_top) / 2 * abs(v)
                y0 = mid - amp
                y1 = mid + amp
                if y1 - y0 < 0.8:
                    y0 = mid - 0.4
                    y1 = mid + 0.4
                p.drawRect(QRectF(x, y0, bw, max(0.8, y1 - y0)))

        # 选区边界线
        if x1 - x0 > 1:
            p.setPen(QPen(accent, 1))
            p.drawLine(QPointF(x0, 2), QPointF(x0, h - 2))
            p.drawLine(QPointF(x1, 2), QPointF(x1, h - 2))
        # 光标参考线
        if self._cursor_ratio >= 0 and not self._dragging:
            cx = self._cursor_ratio * w
            p.setPen(QPen(QColor(ink.red(), ink.green(), ink.blue(), 70), 0.5))
            p.drawLine(QPointF(cx, 3), QPointF(cx, h - 3))
        p.end()


# ─────────────────────────────────────────────────────
#  2. CompareSlider — 前后对比滑动条
# ─────────────────────────────────────────────────────
class CompareSlider(QWidget):
    """原图/结果图滑动对比。左 = 前（原图），右 = 后（处理结果）。

    方法：
        set_before(src) / set_after(src)   设置两张图（路径或 QPixmap）
        set_images(before, after)          一并设置
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._before = QPixmap()
        self._after = QPixmap()
        self._pos = 0.5
        self._dragging = False
        self.setMinimumHeight(140)
        self.setMouseTracking(True)

    def set_before(self, src):
        self._before = _as_pixmap(src)
        self.update()

    def set_after(self, src):
        self._after = _as_pixmap(src)
        self.update()

    def set_images(self, before, after):
        self.set_before(before)
        self.set_after(after)

    def has_images(self):
        return not self._before.isNull() and not self._after.isNull()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.has_images():
            self._dragging = True
            self._pos = e.position().x() / max(self.width(), 1)
            self.update()

    def mouseMoveEvent(self, e):
        if self._dragging:
            self._pos = e.position().x() / max(self.width(), 1)
            self.update()

    def mouseReleaseEvent(self, e):
        self._dragging = False

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        if w < 8 or h < 8:
            p.end()
            return
        p.setBrush(QColor(ds.card_bg()))
        p.setPen(QPen(QColor(ds.border_color()), 0.5))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 10, 10)

        clip = QRectF(2, 2, w - 4, h - 4)
        p.save()
        p.setClipRect(clip)
        if self.has_images():
            # 背景 = 棋盘格（透明图兜底）
            ck = QColor(200, 200, 200, 60)
            for r in range(0, int(h), 10):
                for c in range(0, int(w), 10):
                    p.fillRect(QRectF(c, r, 10, 10),
                               ck if (c // 10 + r // 10) % 2 == 0 else QColor(0, 0, 0, 0))
            # 结果图铺满
            p.drawPixmap(clip, self._after.scaled(
                int(w), int(h), Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation),
                QRectF(0, 0, w, h))
            # 分割线左侧显示原图
            sx = self._pos * w
            left = QRectF(0, 0, sx, h)
            p.setClipRect(left)
            p.drawPixmap(clip, self._before.scaled(
                int(w), int(h), Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation),
                QRectF(0, 0, w, h))
        p.restore()

        # 分割线 + 手柄
        if self.has_images():
            sx = self._pos * w
            p.setPen(QPen(QColor(ds.accent()), 2))
            p.drawLine(QPointF(sx, 2), QPointF(sx, h - 2))
            hw = 18
            p.setBrush(QColor(ds.accent()))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(sx, h / 2), hw, hw)
            p.setPen(QPen(QColor(255, 255, 255), 1.5))
            p.drawLine(QPointF(sx - 5, h / 2), QPointF(sx + 5, h / 2))
            # 标签
            p.end()
            return
        # 空状态
        p.setPen(QPen(QColor(ds.ink_dis()), 0))
        p.drawText(clip, Qt.AlignCenter, "拖动滑块对比前后效果")
        p.end()


# ─────────────────────────────────────────────────────
#  3. FrameGrid — 帧/图网格点选
# ─────────────────────────────────────────────────────
class FrameGrid(QWidget):
    """图片网格：多行自动换行缩略图，点击选中，支持鼠标拖拽换位排序。

    信号：
        frame_clicked(index)       点击选中（index 为当前顺序索引）
        order_changed(paths)       拖拽换位后返回新顺序的路径列表
    方法：
        set_images(paths)          设置图片列表
        set_selected(index)        程序选中
        selected_index() / count() / image_path(index)
        set_cell_size(w, h)        设置缩略图格子尺寸
    """

    frame_clicked = Signal(int)
    order_changed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._images = []
        self._selected = -1
        self._thumbs = []
        self._cell_w = 110
        self._cell_h = 78
        self._gap = 8
        self._drag_index = -1
        self._drag_pos = None
        self.setMinimumHeight(self._cell_h + self._gap + 4)

    def set_cell_size(self, w, h):
        self._cell_w = max(48, int(w))
        self._cell_h = max(36, int(h))
        self._reload_thumbs()
        self.update()

    def set_images(self, paths):
        self._images = list(paths) if paths else []
        self._selected = -1
        self._reload_thumbs()
        self.update()

    def _reload_thumbs(self):
        self._thumbs = []
        for path in self._images:
            pm = QPixmap(path)
            if pm.isNull():
                self._thumbs.append(QPixmap())
            else:
                self._thumbs.append(pm.scaled(
                    self._cell_w - 6, self._cell_h - 6,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self._update_height()

    def _update_height(self):
        rows = self._rows()
        self.setFixedHeight(rows * (self._cell_h + self._gap) + self._gap + 2)

    def _cols(self):
        w = self.width()
        if w <= 0:
            return 1
        return max(1, (w - self._gap) // (self._cell_w + self._gap))

    def _rows(self):
        cols = self._cols()
        if not self._images or cols <= 0:
            return 1
        return (len(self._images) + cols - 1) // cols

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._update_height()

    def set_selected(self, index):
        self._selected = index
        self.update()

    def selected_index(self):
        return self._selected

    def count(self):
        return len(self._images)

    def image_path(self, index):
        return self._images[index] if 0 <= index < len(self._images) else ""

    def images(self):
        return list(self._images)

    # ── 交互：点击选中 + 拖拽换位 ──
    def _index_at(self, pos):
        cols = self._cols()
        x, y = int(pos.x()), int(pos.y())
        if x < self._gap or y < self._gap:
            return -1
        c = (x - self._gap) // (self._cell_w + self._gap)
        r = (y - self._gap) // (self._cell_h + self._gap)
        if c >= cols:
            return -1
        idx = r * cols + c
        return idx if 0 <= idx < len(self._images) else -1

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            idx = self._index_at(e.position())
            if idx >= 0:
                self._selected = idx
                self._drag_index = idx
                self._drag_pos = e.position()
                self.update()
                self.frame_clicked.emit(idx)
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag_index >= 0 and self._drag_pos is not None:
            moved = (e.position() - self._drag_pos).manhattanLength() > 6
            if moved:
                target = self._index_at(e.position())
                if target >= 0 and target != self._drag_index:
                    item = self._images.pop(self._drag_index)
                    self._images.insert(target, item)
                    self._drag_index = target
                    self._reload_thumbs()
                    self._selected = target
                    self.order_changed.emit(list(self._images))
                    self.update()
                self._drag_pos = e.position()
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag_index = -1
        self._drag_pos = None
        super().mouseReleaseEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w = self.width()
        accent = QColor(ds.accent())
        border = QColor(ds.border_color())
        cols = self._cols()
        for i, pm in enumerate(self._thumbs):
            r, c = divmod(i, cols)
            x = self._gap + c * (self._cell_w + self._gap)
            y = self._gap + r * (self._cell_h + self._gap)
            sel = (i == self._selected)
            p.setPen(QPen(accent if sel else border, 1.5 if sel else 0.5))
            p.setBrush(QColor(ds.card_bg()))
            p.drawRoundedRect(QRectF(x, y, self._cell_w, self._cell_h), 6, 6)
            if not pm.isNull():
                ox = x + (self._cell_w - pm.width()) // 2
                oy = y + (self._cell_h - pm.height()) // 2
                p.drawPixmap(QRectF(ox, oy, pm.width(), pm.height()),
                             pm, QRectF(0, 0, pm.width(), pm.height()))
            if sel:
                p.setPen(QPen(accent, 0))
                p.drawText(QRectF(x, y + self._cell_h - 18, self._cell_w, 16),
                           Qt.AlignCenter, f"{i + 1}")
        p.end()


# ─────────────────────────────────────────────────────
#  4. OverlayCanvas — 底图 + 区域框 + 可拖拽矩形
# ─────────────────────────────────────────────────────
class OverlayCanvas(QWidget):
    """叠加画布：显示底图 + 彩色区域框（OCR 框选/参考线），
    或一个可拖拽矩形（水印框/裁剪框）。

    信号：
        rect_moved(x0, y0, x1, y1)   拖拽矩形结束时（归一化 0~1 坐标）
    方法：
        set_image(src)                     设置底图
        set_overlays(rects, color)         rects: [(x0,y0,x1,y1) 归一化]，静态彩色框
        set_draggable(rect, color)         设置可拖拽矩形（归一化），None 取消
    """

    rect_moved = Signal(float, float, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._img = QPixmap()
        self._overlays = []
        self._ov_color = QColor(238, 221, 130)
        self._drag_rect = None
        self._drag_color = QColor(ds.accent())
        self._dragging = False
        self._drag_start = None
        self.setMinimumSize(120, 120)
        self.setMouseTracking(True)

    def set_image(self, src):
        self._img = _as_pixmap(src)
        self.update()

    def set_overlays(self, rects, color="#EEDD82"):
        self._overlays = [(tuple(r), QColor(color)) for r in rects] if rects else []
        self.update()

    def set_draggable(self, rect, color=None):
        self._drag_rect = tuple(rect) if rect else None
        if color:
            self._drag_color = QColor(color)
        self.update()

    def draggable_rect(self):
        return self._drag_rect

    # 像素↔归一化
    def _norm(self, x, y):
        w, h = max(self.width(), 1), max(self.height(), 1)
        return (x / w, y / h)

    def _to_px(self, r):
        w, h = max(self.width(), 1), max(self.height(), 1)
        return (r[0] * w, r[1] * h, r[2] * w, r[3] * h)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self._drag_rect:
            x0, y0, x1, y1 = self._to_px(self._drag_rect)
            px, py = e.position().x(), e.position().y()
            # 命中判定：矩形内部或边缘 8px 内
            if x0 - 8 <= px <= x1 + 8 and y0 - 8 <= py <= y1 + 8:
                self._dragging = True
                self._drag_start = (px - x0, py - y0)

    def mouseMoveEvent(self, e):
        if self._dragging and self._drag_rect:
            x0, y0, x1, y1 = self._to_px(self._drag_rect)
            dx, dy = self._drag_start
            nw = x1 - x0
            nh = y1 - y0
            nx = e.position().x() - dx
            ny = e.position().y() - dy
            nx = max(0, min(self.width() - nw, nx))
            ny = max(0, min(self.height() - nh, ny))
            self._drag_rect = (*self._norm(nx, ny),
                               *self._norm(nx + nw, ny + nh))
            self.update()

    def mouseReleaseEvent(self, e):
        if self._dragging:
            self._dragging = False
            self.rect_moved.emit(*self._drag_rect)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setBrush(QColor(ds.card_bg()))
        p.setPen(QPen(QColor(ds.border_color()), 0.5))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 8, 8)
        if self._img.isNull():
            p.setPen(QPen(QColor(ds.ink_dis()), 0))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, "加载图片后显示")
            p.end()
            return
        clip = QRectF(2, 2, w - 4, h - 4)
        p.save()
        p.setClipRect(clip)
        p.drawPixmap(clip, self._img.scaled(
            int(w), int(h), Qt.KeepAspectRatio, Qt.SmoothTransformation),
            QRectF(0, 0, w, h))
        # 静态区域框
        for r, c in self._overlays:
            x0, y0, x1, y1 = self._to_px(r)
            p.setPen(QPen(c, 1.5))
            p.setBrush(QColor(c.red(), c.green(), c.blue(), 26))
            p.drawRect(QRectF(x0, y0, x1 - x0, y1 - y0))
        # 可拖拽矩形
        if self._drag_rect:
            x0, y0, x1, y1 = self._to_px(self._drag_rect)
            p.setPen(QPen(self._drag_color, 1.8))
            p.setBrush(QColor(self._drag_color.red(), self._drag_color.green(),
                              self._drag_color.blue(), 20))
            p.drawRect(QRectF(x0, y0, x1 - x0, y1 - y0))
            # 四角手柄
            for cx, cy in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
                p.setBrush(self._drag_color)
                p.setPen(Qt.NoPen)
                p.drawRect(QRectF(cx - 3, cy - 3, 6, 6))
        p.restore()
        p.end()


# ─────────────────────────────────────────────────────
#  5. SizeCompareBar — 前后大小对比条
# ─────────────────────────────────────────────────────
class SizeCompareBar(QWidget):
    """压缩前后大小对比：两条横向比例条 + 数值 + 节省百分比。

    方法：
        set_sizes(before_bytes, after_bytes, before_label="", after_label="")
            传入 after=0 时显示"待处理"（仅展示源文件大小）。
        clear()  清空并显示空状态。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._before = 0
        self._after = 0
        self._bl = ""
        self._al = ""
        self._empty = True
        self.setMinimumHeight(64)

    def set_sizes(self, before_bytes, after_bytes, before_label="", after_label=""):
        self._before = max(0, int(before_bytes))
        self._after = max(0, int(after_bytes))
        self._bl = before_label
        self._al = after_label
        self._empty = (self._before <= 0 and self._after <= 0)
        self.update()

    def clear(self):
        self._before = 0
        self._after = 0
        self._bl = ""
        self._al = ""
        self._empty = True
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(QPen(QColor(ds.border_color()), 0.5))
        p.setBrush(QColor(ds.card_bg()))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 8, 8)
        if self._empty:
            p.setPen(QPen(QColor(ds.ink_dis()), 0))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter,
                       "添加视频后显示压缩前后大小对比")
            p.end()
            return
        from core.audio_utils import format_size
        mx = max(self._before, 1)
        y0 = 6
        # 前
        self._draw_bar(p, 6, y0, self._before, mx, QColor(ds.ink_sec()),
                       f"{self._bl or '原始'}  {format_size(self._before)}")
        # 后（未处理时显示待处理）
        if self._after > 0:
            self._draw_bar(p, 6, y0 + 26, self._after, mx,
                           QColor(ds.accent()),
                           f"{self._al or '压缩后'}  {format_size(self._after)}")
        else:
            self._draw_bar(p, 6, y0 + 26, 0, mx, QColor(ds.ink_dis()),
                           f"{self._al or '压缩后'}  待处理")
        # 节省（仅在有实际结果时显示）
        if self._before > 0 and self._after > 0:
            saved = (1 - self._after / self._before) * 100
            txt = (f"节省 {saved:.1f}%" if saved >= 0
                   else f"增大 {-saved:.1f}%")
            c = QColor("#0F6E56") if saved >= 0 else QColor("#A32D2D")
            p.setPen(QPen(c, 0))
            p.drawText(QRectF(6, y0 + 44, w - 12, 18),
                       Qt.AlignLeft | Qt.AlignVCenter, txt)
        p.end()

    def _draw_bar(self, p, x, y, val, mx, color, label):
        w = self.width() - 12
        bar_w = max(2.0, w * val / mx)
        p.setPen(QPen(QColor(ds.border_color()), 0.5))
        p.setBrush(QColor(ds.card_bg()))
        p.drawRoundedRect(QRectF(x, y, w, 14), 7, 7)
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        if bar_w > 2:
            p.drawRoundedRect(QRectF(x, y, bar_w, 14), 7, 7)
        p.setPen(QPen(QColor(ds.ink()), 0))
        p.drawText(QRectF(x + 6, y, w - 12, 14),
                   Qt.AlignLeft | Qt.AlignVCenter, label)


# ─────────────────────────────────────────────────────
#  6. TrendChart — 近 N 天转换量趋势条图
# ─────────────────────────────────────────────────────
class TrendChart(QWidget):
    """近 N 天每日转换量条形图（成功绿 / 失败红双色堆叠）。

    方法：
        set_data(days, ok_counts, fail_counts)
        days: [str] 日期标签（如 08-01）；ok/fail 与 days 等长
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._days = []
        self._ok = []
        self._fail = []
        self.setMinimumHeight(150)

    def set_data(self, days, ok_counts, fail_counts):
        self._days = list(days or [])
        self._ok = list(ok_counts or [])
        self._fail = list(fail_counts or [])
        self.update()

    def clear(self):
        self._days, self._ok, self._fail = [], [], []
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        if w < 20 or h < 30:
            p.end()
            return
        n = len(self._days)
        p.setPen(QPen(QColor(ds.border_color()), 0.5))
        p.setBrush(QColor(ds.card_bg()))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 8, 8)
        if n == 0:
            p.setPen(QPen(QColor(ds.ink_dis()), 0))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter,
                       "暂无数据，完成转换后显示趋势")
            p.end()
            return
        plot_h = h - 26
        max_v = max([max(self._ok[i], self._fail[i]) for i in range(n)] or [1])
        max_v = max(max_v, 1)
        slot = w / n
        bw = min(slot * 0.55, 34.0)
        ok_c = QColor(ds.tokens()["success"])
        fail_c = QColor(ds.tokens()["error"])
        for i in range(n):
            x = i * slot + (slot - bw) / 2
            ok_h = plot_h * self._ok[i] / max_v
            fl_h = plot_h * self._fail[i] / max_v
            y_base = h - 18
            if fl_h > 0.5:
                p.setPen(Qt.NoPen)
                p.setBrush(fail_c)
                p.drawRoundedRect(QRectF(x, y_base - fl_h, bw, fl_h), 2, 2)
            if ok_h > 0.5:
                p.setPen(Qt.NoPen)
                p.setBrush(ok_c)
                p.drawRoundedRect(QRectF(x, y_base - fl_h - ok_h, bw, ok_h),
                                  2, 2)
            if n <= 14 or i % 2 == 0:
                p.setPen(QPen(QColor(ds.ink_sec()), 0))
                p.drawText(QRectF(x - slot / 2, h - 16, slot, 14),
                           Qt.AlignCenter, self._days[i])
        p.end()


# ─────────────────────────────────────────────────────
#  7. TypeChart — 类型分布横向条形图
# ─────────────────────────────────────────────────────
class TypeChart(QWidget):
    """功能类型分布：横向条形 + 数值标签（Top N）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []
        self.setMinimumHeight(150)

    def set_data(self, items):
        self._items = [(str(k), int(v)) for k, v in items if v > 0]
        self.update()

    def clear(self):
        self._items = []
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        if w < 20 or h < 30:
            p.end()
            return
        p.setPen(QPen(QColor(ds.border_color()), 0.5))
        p.setBrush(QColor(ds.card_bg()))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 8, 8)
        if not self._items:
            p.setPen(QPen(QColor(ds.ink_dis()), 0))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter,
                       "暂无类型数据")
            p.end()
            return
        top = self._items[:7]
        mx = max(v for _, v in top) or 1
        row_h = min((h - 12) / len(top), 22.0)
        y = 6
        accent = QColor(ds.accent())
        for label, v in top:
            p.setPen(QPen(QColor(ds.ink_sec()), 0))
            p.drawText(QRectF(10, y, w * 0.34, row_h),
                       Qt.AlignLeft | Qt.AlignVCenter, label)
            bar_x = w * 0.38
            bar_w = max(2.0, (w - bar_x - 46) * v / mx)
            p.setPen(Qt.NoPen)
            p.setBrush(accent)
            p.drawRoundedRect(QRectF(bar_x, y + row_h * 0.25, bar_w,
                                     row_h * 0.5), 3, 3)
            p.setPen(QPen(QColor(ds.ink()), 0))
            p.drawText(QRectF(bar_x + bar_w + 6, y, w - bar_x - bar_w - 14,
                              row_h), Qt.AlignLeft | Qt.AlignVCenter, str(v))
            y += row_h
        p.end()


# ─────────────────────────────────────────────────────
#  8. TimelineWidget — 剪辑时间轴（剪映式：播放头 + in/out 标记）
# ─────────────────────────────────────────────────────
class TimelineWidget(QWidget):
    """专业剪辑时间轴：轨道 + 播放头 + 起止标记(in/out) + 高亮区间。

    信号：
        in_changed(sec) / out_changed(sec)   拖动起止游标
        seek_requested(sec)                   拖动播放头
    方法：
        set_duration(sec)   设置总时长
        set_playhead(sec)   播放进度同步（外部播放器回调）
        set_range(in, out)  程序设置起止区间
        range()             返回 (in_sec, out_sec)
    """

    in_changed = Signal(float)
    out_changed = Signal(float)
    seek_requested = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._duration = 0.0
        self._playhead = 0.0
        self._in = 0.0
        self._out = 0.0
        self._drag = None   # None | 'in' | 'out' | 'playhead' | 'seek'
        self.setMinimumHeight(62)
        self.setMouseTracking(True)

    # ── 数据接口 ──
    def set_duration(self, sec):
        self._duration = max(0.0, float(sec or 0))
        if self._out <= 0 or self._out > self._duration:
            self._out = self._duration
        self.update()

    def set_playhead(self, sec):
        self._playhead = max(0.0, min(float(sec), self._duration or 1e9))
        self.update()

    def set_range(self, in_sec, out_sec):
        self._in = max(0.0, min(float(in_sec), self._duration or 1e9))
        self._out = max(self._in, min(float(out_sec),
                                      self._duration or 1e9))
        self.update()

    def range(self):
        return (self._in, self._out)

    def clear(self):
        self._duration = self._playhead = self._in = self._out = 0.0
        self._drag = None
        self.update()

    # ── 坐标换算 ──
    def _x_to_sec(self, x):
        if self._duration <= 0:
            return 0.0
        return max(0.0, min(self._duration, x / max(self.width(), 1)
                            * self._duration))

    def _sec_to_x(self, sec):
        if self._duration <= 0:
            return 0
        return int(sec / self._duration * max(self.width(), 1))

    # ── 交互 ──
    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton or self._duration <= 0:
            return
        x = e.position().x()
        # 命中优先：in/out 游标（±6px）→ 播放头（±5px）→ 轨道内默认 seek
        if abs(x - self._sec_to_x(self._in)) <= 6:
            self._drag = "in"
        elif abs(x - self._sec_to_x(self._out)) <= 6:
            self._drag = "out"
        elif abs(x - self._sec_to_x(self._playhead)) <= 5:
            self._drag = "playhead"
        else:
            self._drag = "seek"
        self._update_from_x(x)

    def mouseMoveEvent(self, e):
        if self._drag and self._duration > 0:
            self._update_from_x(e.position().x())

    def mouseReleaseEvent(self, e):
        self._drag = None

    def _update_from_x(self, x):
        sec = self._x_to_sec(x)
        if self._drag == "in":
            if sec < self._out:
                self._in = sec
                self.in_changed.emit(round(self._in, 2))
        elif self._drag == "out":
            if sec > self._in:
                self._out = sec
                self.out_changed.emit(round(self._out, 2))
        elif self._drag in ("playhead", "seek"):
            self._playhead = sec
            self.seek_requested.emit(round(self._playhead, 2))
        self.update()

    # ── 绘制 ──
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        accent = QColor(ds.accent())
        border = QColor(ds.border_color())
        ink_sec = QColor(ds.ink_sec())

        if self._duration <= 0:
            p.setPen(QPen(QColor(ds.ink_dis()), 0))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter,
                       "加载视频后显示时间轴，可拖动设置起止剪辑区间")
            p.end()
            return

        track_y = 10
        track_h = 16
        x0, x1 = 6, w - 6
        p.setPen(QPen(border, 0.5))
        p.setBrush(QColor(ds.card_bg()))
        p.drawRoundedRect(QRectF(x0, track_y, x1 - x0, track_h), 6, 6)
        # 已播放进度（浅色）
        px = x0 + (x1 - x0) * self._playhead / self._duration
        if px > x0 + 2:
            c = QColor(ds.ink_sec())
            c.setAlpha(70)
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(QRectF(x0, track_y, px - x0, track_h), 6, 6)
        # in-out 高亮区间
        ix0 = x0 + (x1 - x0) * self._in / self._duration
        ix1 = x0 + (x1 - x0) * self._out / self._duration
        if ix1 - ix0 > 2:
            c = QColor(accent)
            c.setAlpha(70)
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(QRectF(ix0, track_y, ix1 - ix0, track_h), 6, 6)
        # 刻度线（每 1/10 时长一条细线）
        p.setPen(QPen(QColor(ink_sec.red(), ink_sec.green(), ink_sec.blue(),
                             60), 0.5))
        step = max(1.0, self._duration / 10.0)
        t = 0.0
        while t <= self._duration:
            tx = x0 + (x1 - x0) * t / self._duration
            p.drawLine(QPointF(tx, track_y + track_h),
                       QPointF(tx, track_y + track_h + 4))
            t += step

        # in/out 游标（竖线 + 三角）
        for sec, name in ((self._in, "in"), (self._out, "out")):
            cxx = x0 + (x1 - x0) * sec / self._duration
            c = QColor("#0F6E56") if name == "in" else QColor("#A32D2D")
            p.setPen(QPen(c, 2))
            p.drawLine(QPointF(cxx, track_y - 4),
                       QPointF(cxx, track_y + track_h + 4))
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            tri = QPainterPath()
            tri.moveTo(cxx - 5, track_y + track_h + 6)
            tri.lineTo(cxx + 5, track_y + track_h + 6)
            tri.lineTo(cxx, track_y + track_h + 12)
            tri.closeSubpath()
            p.drawPath(tri)

        # 播放头（橙红线）
        if px >= x0:
            p.setPen(QPen(QColor("#D85A30"), 1.5))
            p.drawLine(QPointF(px, track_y - 6),
                       QPointF(px, track_y + track_h + 6))

        # 时间文本
        def _fmt(s):
            s = max(0, int(s))
            return f"{s // 60:02d}:{s % 60:02d}"
        p.setPen(QPen(ink_sec, 0))
        p.drawText(QRectF(x0, track_y + track_h + 14, 60, 16),
                   Qt.AlignLeft, f"入 {_fmt(self._in)}")
        p.drawText(QRectF(x1 - 110, track_y + track_h + 14, 110, 16),
                   Qt.AlignRight, f"出 {_fmt(self._out)}")
        p.end()


# ─────────────────────────────────────────────────────
#  9. TimelineTrackWidget — 带缩略图的专业剪辑时间轴
# ─────────────────────────────────────────────────────
class TimelineTrackWidget(QWidget):
    """剪映式时间轴轨道：连续缩略图 + 刻度 + in/out 游标 + 播放头。

    信号：
        in_changed(sec) / out_changed(sec)   拖动起止游标
        seek_requested(sec)                   拖动播放头或点击轨道
    方法：
        set_duration(sec)      设置总时长
        set_playhead(sec)      同步播放头
        set_range(in, out)     程序设置起止区间
        set_thumbnails(items)  设置缩略图 [(sec, QPixmap), ...]
        clear_thumbnails()     清空缩略图
    """

    in_changed = Signal(float)
    out_changed = Signal(float)
    seek_requested = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._duration = 0.0
        self._playhead = 0.0
        self._in = 0.0
        self._out = 0.0
        self._drag = None
        self._thumbs = []  # [(sec, QPixmap)]
        self.setMinimumHeight(112)
        self.setMouseTracking(True)

    # ── 数据接口 ──
    def set_duration(self, sec):
        self._duration = max(0.0, float(sec or 0))
        if self._out <= 0 or self._out > self._duration:
            self._out = self._duration
        self.update()

    def set_playhead(self, sec):
        self._playhead = max(0.0, min(float(sec), self._duration or 1e9))
        self.update()

    def set_range(self, in_sec, out_sec):
        self._in = max(0.0, min(float(in_sec), self._duration or 1e9))
        self._out = max(self._in, min(float(out_sec),
                                      self._duration or 1e9))
        self.update()

    def set_thumbnails(self, items):
        """items: [(sec, QPixmap)]，sec 按升序。"""
        self._thumbs = [(float(s), pm) for s, pm in items
                        if pm and not pm.isNull()]
        self._thumbs.sort(key=lambda x: x[0])
        self.update()

    def clear_thumbnails(self):
        self._thumbs = []
        self.update()

    def range(self):
        return (self._in, self._out)

    def clear(self):
        self._duration = self._playhead = self._in = self._out = 0.0
        self._drag = None
        self._thumbs = []
        self.update()

    # ── 坐标换算 ──
    def _track_rect(self):
        w = self.width()
        return (6, 26, w - 12, 52)

    def _x_to_sec(self, x):
        x0, _y0, tw, _th = self._track_rect()
        if self._duration <= 0 or tw <= 0:
            return 0.0
        return max(0.0, min(self._duration,
                            (x - x0) / tw * self._duration))

    def _sec_to_x(self, sec):
        x0, _y0, tw, _th = self._track_rect()
        if self._duration <= 0 or tw <= 0:
            return x0
        return x0 + int(sec / self._duration * tw)

    # ── 交互 ──
    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton or self._duration <= 0:
            return
        x = e.position().x()
        xi, xo = self._sec_to_x(self._in), self._sec_to_x(self._out)
        xp = self._sec_to_x(self._playhead)
        if abs(x - xi) <= 7:
            self._drag = "in"
        elif abs(x - xo) <= 7:
            self._drag = "out"
        elif abs(x - xp) <= 5:
            self._drag = "playhead"
        else:
            self._drag = "seek"
        self._update_from_x(x)

    def mouseMoveEvent(self, e):
        if self._drag and self._duration > 0:
            self._update_from_x(e.position().x())

    def mouseReleaseEvent(self, e):
        self._drag = None

    def _update_from_x(self, x):
        sec = self._x_to_sec(x)
        if self._drag == "in":
            if sec < self._out:
                self._in = sec
                self.in_changed.emit(round(self._in, 2))
        elif self._drag == "out":
            if sec > self._in:
                self._out = sec
                self.out_changed.emit(round(self._out, 2))
        elif self._drag in ("playhead", "seek"):
            self._playhead = sec
            self.seek_requested.emit(round(self._playhead, 2))
        self.update()

    # ── 绘制 ──
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        accent = QColor(ds.accent())
        border = QColor(ds.border_color())
        ink_sec = QColor(ds.ink_sec())
        page_bg = QColor(ds.page_bg())
        card_bg = QColor(ds.card_bg())

        # 背景
        p.fillRect(self.rect(), page_bg)

        if self._duration <= 0:
            p.setPen(QPen(QColor(ds.ink_dis()), 0))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter,
                       "加载视频后显示时间轴")
            p.end()
            return

        x0, y0, tw, th = self._track_rect()
        x1 = x0 + tw

        # 轨道底板
        p.setPen(QPen(border, 0.5))
        p.setBrush(card_bg)
        p.drawRoundedRect(QRectF(x0, y0, tw, th), 6, 6)

        # 缩略图铺满轨道
        if self._thumbs:
            thumb_w = max(40, tw / max(len(self._thumbs), 1))
            for sec, pm in self._thumbs:
                tx = x0 + (sec / self._duration) * tw
                # 单张缩略图宽度按相邻两张中点估算
                scaled = pm.scaled(int(max(thumb_w, 40)), th - 4,
                                   Qt.KeepAspectRatioByExpanding,
                                   Qt.SmoothTransformation)
                p.drawPixmap(QRectF(tx, y0 + 2, scaled.width(), th - 4),
                             scaled, QRectF(0, 0, scaled.width(), th - 4))

        # in-out 区间遮罩（区间外变暗）
        ix0 = self._sec_to_x(self._in)
        ix1 = self._sec_to_x(self._out)
        dim = QColor("#000000")
        dim.setAlpha(90)
        p.setPen(Qt.NoPen)
        p.setBrush(dim)
        if ix0 > x0:
            p.drawRect(QRectF(x0, y0, ix0 - x0, th))
        if ix1 < x1:
            p.drawRect(QRectF(ix1, y0, x1 - ix1, th))

        # 区间高亮边框
        if ix1 - ix0 > 2:
            c = QColor(accent)
            c.setAlpha(120)
            p.setPen(QPen(c, 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(ix0, y0, ix1 - ix0, th), 6, 6)

        # 时间刻度（每 1/10 一条短线 + 时间）
        p.setPen(QPen(ink_sec, 0.5))
        step = max(1.0, self._duration / 10.0)
        t = 0.0
        while t <= self._duration:
            tx = self._sec_to_x(t)
            p.drawLine(QPointF(tx, y0 - 6), QPointF(tx, y0))
            p.drawText(QRectF(tx - 24, y0 - 22, 48, 14),
                       Qt.AlignCenter, self._fmt(t))
            t += step

        # in/out 游标（三角 + 竖线 + 标签）
        for sec, name in ((self._in, "in"), (self._out, "out")):
            cxx = self._sec_to_x(sec)
            c = QColor("#2FC99A") if name == "in" else QColor("#F26D6D")
            p.setPen(QPen(c, 2))
            p.drawLine(QPointF(cxx, y0 - 4), QPointF(cxx, y0 + th + 4))
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            tri = QPainterPath()
            tri.moveTo(cxx - 5, y0 + th + 6)
            tri.lineTo(cxx + 5, y0 + th + 6)
            tri.lineTo(cxx, y0 + th + 12)
            tri.closeSubpath()
            p.drawPath(tri)
            p.setPen(QPen(c, 0))
            label = "入点" if name == "in" else "出点"
            p.drawText(QRectF(cxx - 28, y0 + th + 14, 56, 16),
                       Qt.AlignCenter, f"{label} {self._fmt(sec)}")

        # 播放头
        px = self._sec_to_x(self._playhead)
        p.setPen(QPen(QColor("#D85A30"), 1.5))
        p.drawLine(QPointF(px, y0 - 8), QPointF(px, y0 + th + 8))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#D85A30"))
        p.drawEllipse(QPointF(px, y0 - 8), 3, 3)

        p.end()

    def _fmt(self, s):
        s = max(0, int(s))
        return f"{s // 60:02d}:{s % 60:02d}"
