"""card — 统一圆角卡片基类（Prism 设计系统）。

所有卡片（统计卡/工具卡/任务卡/面板区块）继承本类，
保证圆角、背景、阴影与 hover 行为视觉一致。
Prism 风格：圆角 12px + 柔和阴影 + accent 色调 hover 高亮。

主题适配：基类覆盖 SimpleCardWidget 三个 _xxxBackgroundColor()，
让普通卡片（无 Hover）也与主题同步（深浅切换时跟随）。
"""
from PySide6.QtCore import (QEasingCurve, QPropertyAnimation, Qt, Signal,
                            QAbstractAnimation)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect
from qfluentwidgets import SimpleCardWidget

from gui_qt.components import design_system as ds


class Card(SimpleCardWidget):
    """基础圆角卡片：统一圆角 12px + 柔和阴影 + 主题色背景。

    覆盖 SimpleCardWidget 默认的「白色半透明」背景色，按主题令牌取值：
    - _normalBackgroundColor → card_bg
    - _hoverBackgroundColor → card_bg（纯展示卡触碰不高亮，见下）
    - _pressedBackgroundColor → card_bg
    并在主题切换时刷新背景（取代 qfw 默认白色卡，跟随深浅主题）。

    注意：SimpleCardWidget 基类自带 hover 背景渐变动画（鼠标触碰整卡
    变色，视觉上像「被选中」）。纯展示卡（统计卡/信息卡）不可点击，
    高亮会误导用户以为可交互——因此 hover/pressed 一律回落 normal 色。
    可点击卡请用 HoverCard（重新启用高亮）。
    """

    def __init__(self, parent=None, radius=None):
        super().__init__(parent)
        # radius=None 时跟随外观设置（圆角 12 / 直角 0）
        self.setBorderRadius(radius if radius is not None else ds.card_radius())
        ds.apply_subtle_shadow(self)
        # 主题切换时刷新背景色
        try:
            from qfluentwidgets import qconfig
            qconfig.themeChanged.connect(self._on_theme_changed)
        except Exception:  # noqa: BLE001
            pass
        self._updateBackgroundColor()   # 初始背景 = 当前主题 card_bg

    # ── 背景色：覆盖 SimpleCardWidget 的白色半透明，改用主题 tokens ──
    def _normalBackgroundColor(self):
        return QColor(ds.tokens()["card_bg"])

    def _hoverBackgroundColor(self):
        # 纯展示卡：触碰不高亮（与 normal 一致），避免「整个背景像被选中」
        return self._normalBackgroundColor()

    def _pressedBackgroundColor(self):
        return self._normalBackgroundColor()

    def _on_theme_changed(self, *args):
        try:
            self._updateBackgroundColor()
        except Exception:  # noqa: BLE001
            pass


class HoverCard(Card):
    """可点击卡片：hover 时棱镜色调高亮 + 阴影浮起动画，点击发出 clicked。

    背景的 hover/pressed/normal 颜色由 BackgroundAnimationWidget（基类）
    通过 _xxxBackgroundColor() 取值并做 120ms 渐变动画。SimpleCardWidget
    默认返回「白色半透明」，在深色下会让背景闪白后归于透明——
    这里覆盖为当前主题的 card_bg / card_hover / card_active，
    让动画在深浅两种主题下都保持正确的高亮与底色。

    配色三色已上移至基类 Card，此处不需重复 override。
    """

    clicked = Signal()

    def __init__(self, parent=None, radius=None):
        super().__init__(parent, radius=radius)
        self.setCursor(Qt.PointingHandCursor)
        self._shadow = None
        self._lift_ani = None
        self._sh = self.graphicsEffect()
        if isinstance(self._sh, QGraphicsDropShadowEffect):
            self._shadow = self._sh

    # ── 可点击卡重新启用 hover/pressed 高亮（基类 Card 已禁）──
    def _hoverBackgroundColor(self):
        return QColor(ds.tokens()["card_hover"])

    def _pressedBackgroundColor(self):
        return QColor(ds.tokens()["card_active"])

    def _animate_shadow(self, hover):
        """悬停浮起：阴影扩散下移（180ms 缓动），离开回弹。

        注意：不使用 DeleteWhenStopped——动画 stop 时 C++ 对象会被删除，
        而 Python 侧引用仍存在，二次访问会抛 libshiboken 已删除错误。
        对象由 Python 引用持有，替换旧引用时自然被 GC 释放。
        """
        if self._shadow is None:
            return
        target_blur = 26 if hover else 18
        target_off = 6 if hover else 2
        # 动画关闭时直接落位，不做过渡
        if not ds.animations_enabled():
            self._shadow.setOffset(0, target_off)
            self._shadow.setBlurRadius(target_blur)
            return
        if (self._lift_ani is not None
                and self._lift_ani.state() != QAbstractAnimation.Stopped):
            self._lift_ani.stop()
        # 阴影偏移可直接设置，仅对 blurRadius 做平滑动画
        self._shadow.setOffset(0, target_off)
        self._lift_ani = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._lift_ani.setDuration(180)
        self._lift_ani.setStartValue(self._shadow.blurRadius())
        self._lift_ani.setEndValue(target_blur)
        self._lift_ani.setEasingCurve(
            QEasingCurve.OutCubic if hover else QEasingCurve.InOutCubic)
        self._lift_ani.start()

    def enterEvent(self, e):
        self._animate_shadow(True)
        super().enterEvent(e)   # 触发 isHover=True + 背景渐变到 card_hover

    def leaveEvent(self, e):
        self._animate_shadow(False)
        super().leaveEvent(e)   # isHover=False + 背景渐变回 card_bg

    def mouseReleaseEvent(self, e):
        if self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)
