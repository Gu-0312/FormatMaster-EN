"""dialog — Fluent 风格对话框基类（Prism 设计系统）。

原生 QDialog 不自动适配深色主题，各面板此前各自 setStyleSheet
手动写死背景色，容易遗漏子控件导致深色下文字/边框看不清。
本模块提供统一基类：背景 / 边框 / 圆角 / 文字色全部跟随主题令牌，
子类只需组织自己的内容布局与按钮行。
"""
from PySide6.QtWidgets import QDialog

from gui_qt.components import design_system as ds
from gui_qt.i18n import tr


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
        # 主题切换时自动刷新（亮/暗即时生效）
        ds.bind_theme(self, self._theme_qss)

    def _theme_qss(self):
        """生成当前主题的 QSS（供 bind_theme 刷新调用）。"""
        t = ds.tokens()
        return (
            f"QDialog {{ background: {t['card_bg']};"
            f" border-radius: 12px; }}"
            f"QDialog QLabel {{ color: {t['ink']};"
            f" background: transparent; }}"
        )

    def _apply_theme_style(self):
        """按当前主题刷新对话框样式（亮暗切换后重新调用可即时生效）。"""
        self.setStyleSheet(self._theme_qss())


class CloseConfirmDialog(QDialog):
    """关闭确认对话框（无边框圆角卡片，跟随 Prism 主题）。

    返回：
    - result: "quit" 直接关闭 / "tray" 最小化到托盘 / None 取消
    - dont_ask_again: 是否勾选“不再提醒”
    """

    RESULT_QUIT = "quit"
    RESULT_TRAY = "tray"

    def __init__(self, parent=None):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
        )
        from PySide6.QtGui import QFont
        from qfluentwidgets import CheckBox

        flags = Qt.Window | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
        super().__init__(parent, flags)
        self.setWindowModality(Qt.ApplicationModal)
        self.setFixedSize(360, 220)
        self.result = None
        self.dont_ask_again = False

        # 外层窗口透明，由内层背景板负责圆角实色背景，避免系统绘制黑色边角
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 内部背景板：实色圆角卡片
        self._card = QWidget(self)
        self._card.setObjectName("closeConfirmCard")

        root = QVBoxLayout(self._card)
        root.setContentsMargins(24, 24, 24, 20)
        root.setSpacing(0)

        self.title_lbl = QLabel(tr("关闭确认", "Close Confirm"), self._card)
        self.title_lbl.setObjectName("closeConfirmTitle")
        self.title_lbl.setAlignment(Qt.AlignCenter)
        font = QFont("Source Han Sans SC", 16, QFont.Bold)
        self.title_lbl.setFont(font)
        root.addWidget(self.title_lbl)

        root.addSpacing(12)

        self.msg_lbl = QLabel(tr("您希望如何关闭应用？",
                                  "How would you like to close the app?"), self._card)
        self.msg_lbl.setObjectName("closeConfirmMsg")
        self.msg_lbl.setAlignment(Qt.AlignCenter)
        root.addWidget(self.msg_lbl)

        root.addStretch()

        btn_lay = QHBoxLayout()
        btn_lay.setSpacing(16)
        self.btn_quit = QPushButton(tr("直接关闭", "Quit"), self._card)
        self.btn_tray = QPushButton(tr("最小化到托盘", "Minimize to tray"), self._card)
        self.btn_quit.clicked.connect(self._on_quit)
        self.btn_tray.clicked.connect(self._on_tray)
        btn_lay.addStretch()
        btn_lay.addWidget(self.btn_quit)
        btn_lay.addWidget(self.btn_tray)
        btn_lay.addStretch()
        root.addLayout(btn_lay)

        root.addSpacing(14)

        # 用 qfluentwidgets.CheckBox：自带对勾 + 主题适配
        self.cb_dont_ask = CheckBox(tr("不再提醒", "Don't ask again"), self._card)
        self.cb_dont_ask.setChecked(False)
        self.cb_dont_ask.stateChanged.connect(self._on_dont_ask)
        root.addWidget(self.cb_dont_ask, alignment=Qt.AlignCenter)

        # 右上角叉号：点按直接取消（不关闭/不缩到托盘）
        self.btn_close = QPushButton("✕", self._card)
        self.btn_close.setObjectName("closeConfirmX")
        self.btn_close.setFixedSize(28, 28)
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.clicked.connect(self.reject)

        # 初始化样式 + 主题切换时自动刷新
        self._apply_qss()
        ds.bind_theme(self, self._apply_qss)

    def resizeEvent(self, event):
        """背景板始终填满透明窗口；叉号钉在右上角。"""
        super().resizeEvent(event)
        if getattr(self, "_card", None):
            self._card.setGeometry(self.rect())
        if getattr(self, "btn_close", None):
            self.btn_close.move(self.width() - self.btn_close.width() - 10, 10)

    def _apply_qss(self):
        """按当前 Prism 主题刷新对话框全部样式。"""
        t = ds.tokens()
        self.setStyleSheet(
            # 背景板：实色圆角 + 细边框（取代阴影，避免透明窗口角落灰边）
            f"QWidget#closeConfirmCard {{ background: {t['card_bg']};"
            f" border-radius: 16px; border: 1px solid {t['border']}; }}"
            f"QLabel {{ background: transparent; }}"
            # 标题（粗体 ink）
            f"QLabel#closeConfirmTitle {{ color: {t['ink']}; font-weight: bold; }}"
            # 提示文案（ink_sec）
            f"QLabel#closeConfirmMsg {{ color: {t['ink_sec']}; }}"
            # 按钮：跟随主题 accent 色
            f"QPushButton {{ background: {t['accent']}; color: #FFFFFF; "
            f"border: none; border-radius: 10px; padding: 10px 18px; "
            f"font-size: 14px; font-weight: 500; min-width: 120px; }}"
            f"QPushButton:hover {{ background: {t['accent_hover']}; }}"
            f"QPushButton:pressed {{ background: {t['accent_deep']}; }}"
            # 右上角叉号：透明背景，hover 变深（覆盖通用按钮 padding/min-width）
            f"QPushButton#closeConfirmX {{ background: transparent;"
            f" color: {t['ink_sec']}; border: none; border-radius: 14px;"
            f" font-size: 15px; padding: 0; min-width: 0; }}"
            f"QPushButton#closeConfirmX:hover {{ background: {t['card_hover']};"
            f" color: {t['ink']}; }}"
            # 复选框交给 qfluentwidgets.CheckBox 自带样式（对勾+主题）
            f"QCheckBox {{ color: {t['ink_sec']}; font-size: 13px; spacing: 6px; }}"
        )

    def _on_dont_ask(self, state):
        # stateChanged 传入的是 int，而 Qt.Checked 是枚举，二者不相等；
        # 直接以实际勾选状态为准
        self.dont_ask_again = self.cb_dont_ask.isChecked()

    def _on_quit(self):
        self.result = self.RESULT_QUIT
        self.accept()

    def _on_tray(self):
        self.result = self.RESULT_TRAY
        self.accept()
