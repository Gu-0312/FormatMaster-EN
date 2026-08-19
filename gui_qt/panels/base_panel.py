"""base_panel — Qt 面板基类（Prism 设计系统）。

约定与 tkinter 版 BasePanel 对齐：
- build()：构建 UI（构造时自动调用）
- collect_params()：导出供任务调度使用的参数 dict
- collect_prefs()/apply_prefs(prefs)：偏好持久化导出/恢复
面板只通过 services（QtServices）获取业务能力，不直接依赖主窗口逻辑。
Prism 风格：大留白内容区，统一面板标题样式。
"""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QLineEdit, QSlider,
                               QSpinBox, QVBoxLayout, QWidget)
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
        self.main_window = window
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
        # 快速滚动：面板自身 + 全部嵌套滚动区域关闭 SmoothScroll 动画
        # （NO_SMOOTH + 像素滚动），否则 qfluentwidgets ScrollArea 的
        # LINEAR 400ms 动画引擎会让滚轮每格要 400ms 才滚完（滚得慢）。
        try:
            ds.apply_fast_scroll(self)
        except Exception:  # noqa: BLE001 - 滚动优化失败不影响面板功能
            pass
        self.apply_prefs(self._load_prefs())
        # 统一回填"输出目录"记忆：即使子类 apply_prefs 未覆盖 out_dir，
        # 有 out_row 的面板也自动恢复上次选择的目录（重进面板不用重新浏览）。
        self._apply_out_dir_prefs(self._load_prefs())
        # 应用"默认输出目录"偏好（设置中心配置）：仅兜底，绝不改变
        # 面板当前的"与源文件同目录"选择；只在用户已选"自定义目录"
        # 且路径为空时，用全局默认目录作为初始值。
        self._apply_default_out_dir()
        # 通用实时记忆：面板内控件变化 → 防抖自动保存（所有面板生效）
        self._install_auto_prefs()

    def _install_auto_prefs(self):
        """自动监听面板内常见输入控件变化，防抖保存 collect_prefs()。

        覆盖 QComboBox / QCheckBox / QSlider / QLineEdit / QSpinBox；
        500ms 防抖避免滑块拖动等高频事件频繁写盘；任何面板无需额外接线。
        """
        self._prefs_timer = QTimer(self)
        self._prefs_timer.setSingleShot(True)
        self._prefs_timer.setInterval(500)
        self._prefs_timer.timeout.connect(self.save_prefs)
        for w in self.findChildren(QComboBox):
            w.currentIndexChanged.connect(lambda *_: self._schedule_prefs_save())
        for w in self.findChildren(QCheckBox):
            w.toggled.connect(lambda *_: self._schedule_prefs_save())
        for w in self.findChildren(QSlider):
            w.valueChanged.connect(lambda *_: self._schedule_prefs_save())
        for w in self.findChildren(QLineEdit):
            w.textChanged.connect(lambda *_: self._schedule_prefs_save())
        for w in self.findChildren(QSpinBox):
            w.valueChanged.connect(lambda *_: self._schedule_prefs_save())

    def _schedule_prefs_save(self):
        """防抖：参数变化后 500ms 自动保存到 user_prefs.json（实时记忆）。"""
        timer = getattr(self, "_prefs_timer", None)
        if timer is not None:
            timer.start()

    def _apply_default_out_dir(self):
        """读取设置中心的"默认输出目录"。

        规则：绝不改变面板当前的"与源文件同目录"选择（输出始终跟随
        源文件所在目录）；仅当面板已选"自定义目录"且路径为空时，
        用全局默认目录兜底作为初始值。用户手动设置的自定义路径优先。
        """
        try:
            import os
            orow = getattr(self, "out_row", None)
            if orow is None or not hasattr(orow, "mode"):
                return
            if orow.mode() != orow.MODE_CUSTOM:
                return  # 保持"与源文件同目录"不变
            d = self.services.get_pref("default_out_dir", "")
            if d and os.path.isdir(d) and not orow.path():
                orow.set_state(orow.MODE_CUSTOM, d)
        except Exception:  # noqa: BLE001 - 偏好应用失败不影响面板
            pass

    # ── 输出目录统一记忆（所有有 out_row 的面板自动生效）──
    def _out_dir_prefs(self) -> dict:
        """收集当前输出目录状态（供 save_prefs 自动补存）。

        用 duck-typing 判断真实 OutputDirRow：部分面板（如 hash）的
        out_row 是 _NoOutRow 占位类（无 mode/path），必须跳过。
        """
        orow = getattr(self, "out_row", None)
        if orow is not None and hasattr(orow, "mode") and hasattr(orow, "path"):
            return {"out_dir_combo": orow.mode(),
                    "out_dir_path": orow.path()}
        return {}

    def _apply_out_dir_prefs(self, prefs: dict):
        """回填上次记忆的输出目录（子类 apply_prefs 未覆盖时兜底）。"""
        try:
            orow = getattr(self, "out_row", None)
            if orow is None or not prefs or not hasattr(orow, "set_state"):
                return
            combo = prefs.get("out_dir_combo")
            if combo == orow.MODE_CUSTOM:
                orow.set_state(orow.MODE_CUSTOM, prefs.get("out_dir_path", ""))
            elif combo == orow.MODE_SAME:
                orow.set_state(orow.MODE_SAME)
        except Exception:  # noqa: BLE001 - 回填失败不影响面板
            pass

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
        """创建面板副标题。

        颜色不写死：交给全局 QSS 的 QLabel[sec=true] 规则（ink_sec 令牌），
        主题切换时全局 QSS 自动刷新，避免实例快照残留浅色字。
        """
        from qfluentwidgets import CaptionLabel
        label = CaptionLabel(text)
        label.setProperty("sec", True)
        label.setStyleSheet("font-size: 12px;")
        return label

    def make_section_label(self, text):
        """创建统一风格的区块小标题。

        颜色交给全局 QSS 的 QLabel 规则（ink 令牌），主题切换自动跟随。
        """
        from qfluentwidgets import BodyLabel
        label = BodyLabel(text)
        label.setStyleSheet("font-size: 14px; font-weight: 600;")
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
        p = self.services.prefs.get(QT_PREFS_PANEL, self._prefs_key(), {}) or {}
        # 防御：配置文件被手改/损坏时可能返回非 dict（str/list/int），
        # 直接传给 apply_prefs 会 AttributeError/ValueError 导致面板构建崩溃。
        return p if isinstance(p, dict) else {}

    def save_prefs(self):
        prefs = self.collect_prefs()
        # 自动补存输出目录：子类 collect_prefs 未包含 out_dir 时统一补上，
        # 保证所有有 out_row 的面板输出目录都记忆（重进面板不用重新浏览）。
        od = self._out_dir_prefs()
        if od and "out_dir_combo" not in prefs:
            prefs = {**prefs, **od}
        self.services.prefs.set(QT_PREFS_PANEL, self._prefs_key(), prefs)
