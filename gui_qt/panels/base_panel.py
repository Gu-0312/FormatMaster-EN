"""base_panel — Qt 面板基类（Prism 设计系统）。

约定与 tkinter 版 BasePanel 对齐：
- build()：构建 UI（构造时自动调用）
- collect_params()：导出供任务调度使用的参数 dict
- collect_prefs()/apply_prefs(prefs)：偏好持久化导出/恢复
面板只通过 services（QtServices）获取业务能力，不直接依赖主窗口逻辑。
Prism 风格：大留白内容区，统一面板标题样式。
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtGui import QFont
from qfluentwidgets import ScrollArea, SubtitleLabel

from gui_qt.services import QT_PREFS_PANEL
from gui_qt.components.page_header import PageHeader
from gui_qt.components import design_system as ds


class BaseQtPanel(ScrollArea):
    """功能面板基类：外层 ScrollArea，内容挂在 self.content。"""

    panel_key = ""

    def __init__(self, window, services, parent=None):
        super().__init__(parent)
        self.window = window
        self.services = services
        self.setObjectName(f"panel_{self.panel_key}")
        self.setWidgetResizable(True)
        self.setViewportMargins(0, 0, 0, 0)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(24, 24, 24, 24)
        self.content_layout.setSpacing(16)
        self.setWidget(self.content)
        self.content.setAutoFillBackground(False)

        self.build()
        self.content_layout.addStretch(1)
        self.apply_prefs(self._load_prefs())

    # ── 子类约定 ─────────────────────────────────
    def build(self):
        raise NotImplementedError

    def collect_params(self) -> dict:
        return {}

    def collect_prefs(self) -> dict:
        return {}

    def apply_prefs(self, prefs: dict):
        pass

    # ── 面板标题快捷方法 ─────────────────────────
    def make_title(self, text):
        """创建统一风格的面板标题组件。"""
        return PageHeader(text)

    def make_subtitle(self, text):
        """创建面板副标题。"""
        from qfluentwidgets import CaptionLabel
        label = CaptionLabel(text)
        label.setStyleSheet(
            f"font-size: 12px; color: {ds.ink_sec()};")
        return label

    def make_section_label(self, text):
        """创建统一风格的区块小标题。"""
        from qfluentwidgets import BodyLabel
        label = BodyLabel(text)
        label.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {ds.ink()};")
        return label

    def make_section_header(self, text, icon=None):
        """创建带图标的区块标题行（图标 + 文字）。"""
        from PySide6.QtWidgets import QHBoxLayout, QWidget
        from qfluentwidgets import IconWidget
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        if icon:
            iw = IconWidget(icon, row)
            iw.setFixedSize(18, 18)
            iw.setStyleSheet(f"color: {ds.accent()};")
            h.addWidget(iw)
        label = self.make_section_label(text)
        h.addWidget(label)
        h.addStretch(1)
        return row

    def make_divider(self):
        """创建视觉分隔线。"""
        from PySide6.QtWidgets import QFrame
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(
            f"QFrame {{ border: none; border-top: 1px solid {ds.border_color()}; }}")
        line.setFixedHeight(1)
        return line

    # ── 偏好存取（qt_app 面板键下再套 panel_key 命名空间）──
    def _prefs_key(self):
        return f"panel_{self.panel_key}"

    def _load_prefs(self) -> dict:
        return self.services.prefs.get(QT_PREFS_PANEL, self._prefs_key(), {}) or {}

    def save_prefs(self):
        self.services.prefs.set(QT_PREFS_PANEL, self._prefs_key(),
                                self.collect_prefs())
