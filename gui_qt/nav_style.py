"""nav_style — 侧边导航选中态样式（跟随主题色）。

qfluentwidgets 导航项（NavigationPushButton 系列）为自绘控件（paintEvent），
QSS 无法覆盖其选中背景/图标颜色。这里局部替换 paintEvent：
- 选中背景：主题色淡色（浅色主题高亮、深色主题暗底）
- 选中图标/指示条：主题色（浅色偏深、深色偏亮）
- 未选中保持 qfluentwidgets 默认主题色
颜色基于 qconfig.themeColor 动态派生，跟随「外观 → 主题色」切换。
切换主题色时用 QVariantAnimation 做 260ms 颜色插值过渡，避免瞬时跳变生硬。
不修改 qfluentwidgets 源码，运行时补丁，窗口构造时调用 apply()。
"""
from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QPainter, QPen

from qfluentwidgets import Theme
from qfluentwidgets.common.config import isDarkTheme
from qfluentwidgets.common.icon import drawIcon, toQIcon
from qfluentwidgets.common.style_sheet import themeColor
from qfluentwidgets.components.navigation.navigation_widget import (
    NavigationPushButton)

_ORIG_PAINT = NavigationPushButton.paintEvent

# ── 颜色过渡动画状态（模块级，供 paintEvent 读取中间色）──
_cur_bg = None          # 当前动画中的选中背景色
_cur_ic = None          # 当前动画中的选中图标色
_anim = None            # 进行中的 QVariantAnimation
_win = None             # 主窗口引用（用于重绘导航）


def _accent_variants():
    """基于当前主题色派生选中态颜色，返回 (背景, 图标/指示条)。"""
    base = themeColor()
    h, s, l, _ = base.getHslF()
    if isDarkTheme():
        bg = QColor.fromHslF(h, min(s * 0.65, 1.0), 0.30)
        ic = QColor.fromHslF(h, min(s * 0.95, 1.0), 0.85)
    else:
        bg = QColor.fromHslF(h, min(s * 0.6, 1.0), 0.86)
        ic = QColor.fromHslF(h, min(s, 1.0), 0.36)
    return bg, ic


def _current_variants():
    """返回当前应绘制的 (背景, 图标) —— 动画中取插值中间色，否则直接派生。"""
    if _cur_bg is not None:
        return _cur_bg, _cur_ic
    return _accent_variants()


def _refresh_nav():
    """重绘侧边栏所有导航项，让 paintEvent 重新读取当前过渡色。"""
    if _win is None:
        return
    try:
        from qfluentwidgets.components.navigation.navigation_widget import (
            NavigationWidget)
        panel = _win.navigationInterface.panel
        for w in panel.findChildren(NavigationWidget):
            w.update()
    except Exception:  # noqa: BLE001
        pass


def _mix_color(a, b, t):
    """RGB 线性插值。"""
    return QColor(int(a.red() + (b.red() - a.red()) * t),
                  int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t))


def _animate_to(target_bg, target_ic):
    """把导航选中态颜色从当前色平滑过渡到目标色（260ms OutCubic）。"""
    global _cur_bg, _cur_ic, _anim
    from PySide6.QtCore import QEasingCurve, QVariantAnimation
    if _cur_bg is None:
        _cur_bg = QColor(target_bg)
        _cur_ic = QColor(target_ic)
        return
    if _anim is not None:
        _anim.stop()
    sbg, sic = QColor(_cur_bg), QColor(_cur_ic)
    tbg, tic = QColor(target_bg), QColor(target_ic)

    _anim = QVariantAnimation()
    _anim.setDuration(260)
    _anim.setEasingCurve(QEasingCurve.OutCubic)
    _anim.setStartValue(0.0)
    _anim.setEndValue(1.0)

    def _step(t):
        global _cur_bg, _cur_ic
        _cur_bg = _mix_color(sbg, tbg, t)
        _cur_ic = _mix_color(sic, tic, t)
        _refresh_nav()

    _anim.valueChanged.connect(_step)
    _anim.start()


def _paint(self, e):
    painter = QPainter(self)
    # 去掉 SmoothPixmapTransform：16px 图标/文本无需高质量采样，
    # 该提示会显著抬高每帧绘制成本（展开动画期间 43 项全量重绘，
    # 是侧边栏展开卡顿的来源之一）。
    painter.setRenderHints(QPainter.Antialiasing |
                           QPainter.TextAntialiasing)
    painter.setPen(Qt.NoPen)

    if self.isPressed:
        painter.setOpacity(0.7)
    if not self.isEnabled():
        painter.setOpacity(0.4)

    c = 255 if isDarkTheme() else 0
    m = self._margins()
    pl, pr = m.left(), m.right()
    globalRect = QRect(self.mapToGlobal(QPoint()), self.size())

    if self._canDrawIndicator():   # 选中态 → 跟随主题色（过渡中间色）
        bg, ic = _current_variants()
        painter.setBrush(bg)
        painter.drawRoundedRect(self.rect(), 5, 5)
        painter.setBrush(ic)
        painter.drawRoundedRect(self.indicatorRect(), 1.5, 1.5)
        icon = self._icon
        if hasattr(icon, "icon"):   # FluentIconBase → 染主题色
            try:
                icon = icon.icon(Theme.AUTO, color=ic)
            except Exception:  # noqa: BLE001
                pass
        drawIcon(icon, painter, QRectF(11.5 + pl, 10, 16, 16))
    else:
        if ((self.isEnter and globalRect.contains(QCursor.pos()))
                or self.isAboutSelected) and self.isEnabled():
            painter.setBrush(QColor(c, c, c, 6 if self.isAboutSelected else 10))
            painter.drawRoundedRect(self.rect(), 5, 5)
        drawIcon(self._icon, painter, QRectF(11.5 + pl, 10, 16, 16))

    # 文本
    if self.isCompacted:
        return
    painter.setFont(self.font())
    painter.setPen(self.textColor())
    left = 44 + pl if not toQIcon(self._icon).isNull() else pl + 16
    painter.drawText(QRectF(left, 0, self.width() - 13 - left - pr,
                            self.height()), Qt.AlignVCenter, self.text())


_applied = False
_refresh_wired = False


def apply(window=None):
    """应用导航选中态样式（幂等，运行时补丁）。

    window: 可选 MainWindow，关闭导航指示条滑动动画（选中态即时高亮，
    无过渡延迟；实测滑动动画在展开侧边栏/导航项密集时会引入卡顿），
    并监听主题色变化触发颜色过渡动画 + 重绘。
    """
    global _applied, _refresh_wired
    if not _applied:
        NavigationPushButton.paintEvent = _paint
        _applied = True
    if window is not None:
        try:
            panel = window.navigationInterface.panel
            panel.setIndicatorAnimationEnabled(False)
        except Exception:  # noqa: BLE001
            pass
        if not _refresh_wired:
            _wire_theme_color_refresh(window)
            _refresh_wired = True


def _wire_theme_color_refresh(window):
    """主题色切换后启动导航选中态颜色过渡动画（paintEvent 读中间色）。"""
    global _win, _cur_bg, _cur_ic
    from qfluentwidgets import qconfig
    _win = window
    if _cur_bg is None:
        _cur_bg, _cur_ic = _accent_variants()

    def _on_changed(_color=None):
        _animate_to(*_accent_variants())

    try:
        qconfig.themeColorChanged.connect(_on_changed)
    except Exception:  # noqa: BLE001
        pass
