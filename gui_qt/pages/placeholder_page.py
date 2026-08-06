"""placeholder_page — 未迁移功能的占位页。"""
from qfluentwidgets import FluentIcon, ScrollArea

from gui_qt.components.empty_state import EmptyState


class PlaceholderPage(ScrollArea):
    """尚未迁移到 Qt 的功能页：居中显示「即将上线」空态。"""

    def __init__(self, feature_name, window, services=None, parent=None):
        super().__init__(parent)
        self.setObjectName(f"placeholder_{feature_name}")
        self.window = window
        self.services = services
        self.setWidgetResizable(True)
        self.setViewportMargins(0, 0, 0, 0)

        from PySide6.QtWidgets import QWidget
        from PySide6.QtWidgets import QVBoxLayout
        container = QWidget()
        container.setAutoFillBackground(False)
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.addLayout(EmptyState(
            icon=FluentIcon.CONSTRACT,
            title=feature_name,
            desc=f"「{feature_name}」正在从旧界面迁移到 Fluent Design，敬请期待。"))
        self.setWidget(container)
