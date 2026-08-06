"""tips_card — 首页「使用小贴士」卡片。

随机展示使用技巧/快捷键提示（中英双语），点击「换一条」切换，
随机顺序不重复。风格与首页其他卡片（Card 基类）一致。
"""
import random

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QVBoxLayout)
from qfluentwidgets import (CaptionLabel, FluentIcon, IconWidget, PushButton)

from gui_qt.components import design_system as ds
from gui_qt.components.card import Card
from gui_qt.i18n import tr

# (中文, English)
_TIPS = [
    (tr("快捷键 Ctrl+1~9 可快速切换页面", "Ctrl+1~9 switch pages quickly"), "Press Ctrl+1~9 to switch pages"),
    (tr("把文件直接拖进面板即可批量添加", "Drag files into the panel to add them"), "Drag files into the panel to batch add"),
    (tr("视频处理「剪辑」默认无损流复制，速度快", "Clip uses lossless stream copy by default for speed"),
     "Video 'Clip' uses lossless stream copy, fast"),
    (tr("文件右键 →「用格式大师转换」一键打开", "Right-click a file → \"Convert with FormatMaster\""),
     "Right-click a file → open with FormatMaster"),
    (tr("界面语言可在设置中切换中英", "Switch between Chinese and English in Settings"), "Switch UI language in Settings"),
    (tr("文件夹监视：新文件放入目录自动转换", "Watch a folder and auto-convert new files"),
     "Folder Watch auto-converts new files"),
    (tr("批量重命名支持 {n}/{name}/{date} 占位符", "Batch rename supports {n}/{name}/{date} placeholders"),
     "Batch rename supports {n}/{name}/{date}"),
    (tr("表格识别可输出 CSV / Excel", "Table OCR exports CSV / Excel"), "Table OCR exports CSV / Excel"),
    (tr("侧边栏底部按钮切换亮/暗/跟随系统", "Sidebar bottom button switches light/dark/system"),
     "Toggle theme at the sidebar bottom"),
    (tr("转换完成后可自动打开输出目录（设置开启）", "Auto-open output folder when done (in Settings)"),
     "Auto-open output folder when done (Settings)"),
    (tr("视频变速支持 0.5x - 2.0x", "Speed supports 0.5x - 2.0x"), "Video speed: 0.5x - 2.0x"),
    (tr("图片支持 AVIF / WebP 等现代格式", "Supports AVIF / WebP and other modern formats"), "Images support AVIF / WebP"),
]


class TipsCard(Card):
    """使用小贴士：随机提示 + 换一条。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._order = list(range(len(_TIPS)))
        random.shuffle(self._order)
        self._idx = 0

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(10)

        # 标题
        header = QHBoxLayout()
        header.setSpacing(8)
        icon = IconWidget(FluentIcon.INFO, self)
        icon.setFixedSize(16, 16)
        icon.setStyleSheet(f"color: {ds.ink()};")
        header.addWidget(icon)
        title = QLabel(tr("使用小贴士", "Tips"))
        title.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {ds.ink()};"
            "border: none; background: transparent;")
        header.addWidget(title)
        header.addStretch(1)
        self.counter_label = CaptionLabel("")
        self.counter_label.setStyleSheet(
            f"font-size: 11px; color: {ds.ink_dis()};"
            "border: none; background: transparent;")
        header.addWidget(self.counter_label)
        v.addLayout(header)

        # 提示内容
        self.tip_label = QLabel()
        self.tip_label.setWordWrap(True)
        self.tip_label.setStyleSheet(
            f"font-size: 13px; color: {ds.ink_sec()};"
            "border: none; background: transparent;")
        v.addWidget(self.tip_label)
        v.addStretch(1)

        # 底部操作行
        footer = QHBoxLayout()
        footer.addStretch(1)
        self.btn_next = PushButton(FluentIcon.SYNC, tr("换一条", "Next tip"))
        self.btn_next.clicked.connect(self.next_tip)
        footer.addWidget(self.btn_next)
        v.addLayout(footer)

        self._show()

    def _show(self):
        i = self._order[self._idx % len(self._order)]
        zh, en = _TIPS[i]
        self.tip_label.setText(tr(zh, en))
        self.counter_label.setText(f"{self._idx % len(_TIPS) + 1}/{len(_TIPS)}")

    def next_tip(self):
        self._idx += 1
        self._show()
