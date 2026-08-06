"""dialog — Fluent 风格对话框基类（Prism 设计系统）。

原生 QDialog 不自动适配深色主题，各面板此前各自 setStyleSheet
手动写死背景色，容易遗漏子控件导致深色下文字/边框看不清。
本模块提供统一基类：背景 / 边框 / 圆角 / 文字色全部跟随主题令牌，
子类只需组织自己的内容布局与按钮行。
"""
from PySide6.QtWidgets import QDialog

from gui_qt.components import design_system as ds


class FluentDialogBase(QDialog):
    """深色主题适配的对话框基类。

    约定：
    - 模态 + 最小宽度 360 + 圆角 12（与卡片体系统一）
    - 背景 card_bg、文字 ink、输入控件交给全局 QSS（design_system 已覆盖）
    - 子类通过 self.result 携带返回值，self.accept()/reject() 关闭
    """

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(360)
        self.result = None
        self._apply_theme_style()

    def _apply_theme_style(self):
        """按当前主题刷新对话框样式（亮暗切换后重新调用可即时生效）。"""
        t = ds.tokens()
        self.setStyleSheet(
            f"QDialog {{ background: {t['card_bg']};" +
            f" border-radius: 12px; }}" +
            f"QDialog QLabel {{ color: {t['ink']};" +
            f" background: transparent; }}")
