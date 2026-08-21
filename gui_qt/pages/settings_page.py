"""settings_page — 设置中心（Fluent SettingsCard 分组）。

分组：常规 / 主题 / 转换 / 高级 / 快捷键。全部持久化到 USER_PREFS 的
qt_app 面板键（与 tkinter 旧偏好隔离）。开机启动走 Windows 注册表 Run 键。
"""
import os
import re
import sys

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QFileDialog, QInputDialog, QLineEdit, \
    QPushButton, QVBoxLayout, QHBoxLayout, QWidget, QFrame
from PySide6.QtGui import QIcon
from qfluentwidgets import (ComboBox, ExpandLayout, FluentIcon,
                            PushButton, PushSettingCard, ScrollArea,
                            SettingCard, SettingCardGroup, SwitchSettingCard)

from gui_qt.i18n import tr
from gui_qt.components.page_header import PageHeader
from gui_qt.components.card import Card
from gui_qt.components.theme_manager import (ACCENT_COLORS, MODE_AUTO,
                                             MODE_DARK, MODE_LIGHT, MODES)
from gui_qt.components import design_system as ds
from gui_qt.components.design_system import FONT_BODY
from utils.config import (APP_VERSION, get_ffmpeg_path, get_resource_path,
                          SUPPORTED_VIDEO, VIDEO_CODECS)


class _ShortcutButton(QPushButton):
    """快捷键录制按钮：点击进入录制态，按下组合键完成。

    要求至少一个修饰键（Ctrl/Alt/Shift）加一个主键，避免与系统单键冲突；
    Esc 取消录制。
    """

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(160)
        self._recording = False
        self._qs = ""
        self.clicked.connect(self._toggle)
        self.setStyleSheet("text-align: center;")

    def _toggle(self):
        self._recording = not self._recording
        self.setText(tr("按下新快捷键…", "Press new keys…") if self._recording
                     else (self._qs or tr("未设置", "Not set")))

    def set_shortcut(self, qs):
        self._qs = qs or ""
        self._recording = False
        self.setText(self._qs or tr("未设置", "Not set"))

    def keyPressEvent(self, e):
        if not self._recording:
            return super().keyPressEvent(e)
        if e.key() == Qt.Key_Escape:
            self._recording = False
            self.setText(self._qs or tr("未设置", "Not set"))
            return
        if e.key() in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            return   # 单独按修饰键不结束录制
        # Qt6：keyCombination 组合修饰键（modifiers() 是枚举 flags 不可直接 int）
        combo = e.keyCombination()
        if combo.keyboardModifiers() == Qt.KeyboardModifier.NoModifier:
            self.setText(tr("需要组合键（如 Ctrl+Shift+P）",
                            "Need a combo (e.g. Ctrl+Shift+P)"))
            return
        self._qs = QKeySequence(combo).toString()
        self._recording = False
        self.setText(self._qs)
        self.changed.emit()


class _ComboSettingCard(SettingCard):
    """带下拉框的设置卡（偏好存 USER_PREFS，不依赖 qconfig）。"""

    def __init__(self, icon, title, content, texts, parent=None):
        super().__init__(icon, title, content, parent)
        self.comboBox = ComboBox(self)
        self.comboBox.addItems(texts)
        self.comboBox.setFixedWidth(170)
        self.hBoxLayout.addWidget(self.comboBox, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)


class _SvgNavIcon:
    """包装 SVG 图标，提供与 FluentIcon 一致的 .icon() 接口。

    按亮/暗主题对 SVG 重着色（替换 stroke="currentColor"），
    深色模式下不再显示黑色图标。
    """

    def __init__(self, svg_path):
        self._svg_path = svg_path
        self._cache = {}

    def icon(self):
        try:
            from qfluentwidgets import isDarkTheme
            dark = isDarkTheme()
        except Exception:  # noqa: BLE001
            dark = False
        if dark not in self._cache:
            self._cache[dark] = self._render(dark)
        return self._cache[dark]

    def _render(self, dark):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPainter, QPixmap
        from PySide6.QtSvg import QSvgRenderer
        try:
            with open(self._svg_path, encoding="utf-8") as f:
                svg = f.read()
            color = "#E6E8F2" if dark else "#1D1F2E"
            svg = svg.replace("currentColor", color)
            renderer = QSvgRenderer(svg.encode("utf-8"))
            size = renderer.defaultSize()
            w = max(size.width(), 32)
            h = max(size.height(), 32)
            pm = QPixmap(w, h)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            renderer.render(p)
            p.end()
            return QIcon(pm)
        except Exception:  # noqa: BLE001 - 渲染失败回退静态图标
            return QIcon(self._svg_path)


class _AccentColorCard(Card):
    """主题色选择面板：与 SettingCardGroup 内其他卡片同样有圆角白底，
    但内容是整张面板式布局（参考图）：

        [palette] 预设颜色
        ●●●●●●●●
        ─────────
        自定义颜色
        ● #HEX              [恢复默认]
    """

    def __init__(self, services, theme_mgr, parent=None):
        from PySide6.QtGui import QFont
        from qfluentwidgets import CaptionLabel, IconWidget
        super().__init__(parent)
        self.services = services
        self.theme_mgr = theme_mgr
        self._buttons = []

        # ── 容器主布局 ──
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(12)
        v.setAlignment(Qt.AlignTop)

        # ── 预设颜色标题行（图标 + 标题） ──
        preset_hdr = QWidget()
        ph = QHBoxLayout(preset_hdr)
        ph.setContentsMargins(0, 0, 0, 0)
        ph.setSpacing(6)
        ph.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        icon = IconWidget(FluentIcon.PALETTE)
        icon.setFixedSize(16, 16)
        ph.addWidget(icon, 0, Qt.AlignVCenter)
        preset_title = CaptionLabel(tr("预设颜色", "Preset colors"))
        f = QFont(preset_title.font())
        f.setPointSize(11)
        f.setWeight(QFont.Weight.Medium)
        preset_title.setFont(f)
        preset_title.setStyleSheet(f"")
        ph.addWidget(preset_title, 0, Qt.AlignVCenter)
        v.addWidget(preset_hdr)

        # ── 预设色块行 ──
        preset_row = QWidget()
        preset_row.setMinimumHeight(36)   # 防止卡片高度不足时色块被压缩裁切
        h = QHBoxLayout(preset_row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        h.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        for name, hexv in ACCENT_COLORS:
            btn = QPushButton(preset_row)
            btn.setFixedSize(36, 36)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setProperty("color_hex", hexv or "")
            btn.setToolTip(name)
            btn.clicked.connect(
                lambda _checked, c=hexv or "": self._set_accent(c))
            h.addWidget(btn)
            self._buttons.append(btn)
        h.addStretch(1)
        v.addWidget(preset_row)

        # ── 分隔线 ──
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet(
            f"QFrame{{background:{ds.border_color()};border:none;}}")
        v.addWidget(line)

        # ── 自定义颜色标题行 ──
        custom_title = CaptionLabel(tr("自定义颜色", "Custom color"))
        f = QFont(custom_title.font())
        f.setPointSize(11)
        f.setWeight(QFont.Weight.Medium)
        custom_title.setFont(f)
        custom_title.setStyleSheet(f"")
        v.addWidget(custom_title)

        # ── 自定义颜色控件行：色块 + 输入框 + stretch + 恢复默认 ──
        custom_row = QWidget()
        custom_row.setMinimumHeight(36)   # 防止色块/输入框被压缩裁切
        h2 = QHBoxLayout(custom_row)
        h2.setContentsMargins(0, 0, 0, 0)
        h2.setSpacing(10)
        h2.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # 自定义颜色预览色块：点击弹出取色器
        self.custom_preview = QPushButton(custom_row)
        self.custom_preview.setFixedSize(36, 36)
        self.custom_preview.setCursor(Qt.PointingHandCursor)
        self.custom_preview.setToolTip(tr("点击选择颜色", "Click to pick color"))
        self.custom_preview.clicked.connect(self._pick_custom_color)

        self.custom_edit = QLineEdit(custom_row)
        self.custom_edit.setFixedWidth(110)
        self.custom_edit.setMaxLength(7)
        self.custom_edit.setPlaceholderText("#5B5BD6")
        self.custom_edit.textChanged.connect(self._on_custom_text_changed)
        self.custom_edit.editingFinished.connect(self._apply_custom_text)

        self.reset_btn = PushButton(
            tr("恢复默认", "Reset default"), custom_row)
        self.reset_btn.clicked.connect(self._on_reset)

        h2.addWidget(self.custom_preview)
        h2.addWidget(self.custom_edit)
        h2.addStretch(1)
        h2.addWidget(self.reset_btn)
        v.addWidget(custom_row)

        # Card 没有锁高度；SettingCardGroup 用 ExpandLayout（直接用 w.height()
        # 而不是 sizeHint）布局，Card 默认 30px 高会被压扁。固定为内容实际
        # 高度（margins 36 + 标题行×2 + spacing×5 + 色块行 36×2 + 分隔线 1）。
        # 真实字体（微软雅黑）行高比 offscreen 默认字体更高，留足缓冲避免
        # 色块下半部分被裁切。
        self.setFixedHeight(224)

        self._refresh(self.theme_mgr.current_accent())

    def _set_accent(self, color_hex):
        self.theme_mgr.set_accent(color_hex)
        self._refresh(color_hex)

    def _refresh(self, color_hex):
        """同步刷新色块选中态、自定义预览、输入框。"""
        color_hex = (color_hex or "").strip().upper()
        default_hex = ds.tokens()["accent"].upper()
        display_hex = color_hex if color_hex else default_hex

        self.custom_edit.blockSignals(True)
        self.custom_edit.setText(display_hex)
        self.custom_edit.blockSignals(False)
        self.custom_preview.setStyleSheet(
            f"QPushButton{{background:{display_hex};border-radius:8px;"
            f"border:1px solid {ds.border_color()};}}"
            f"QPushButton:hover{{border:1px solid {ds.ink_sec()};}}")

        ink = ds.ink()
        ink_sec = ds.ink_sec()
        border_col = ds.border_color()
        for btn in self._buttons:
            btn_hex = (btn.property("color_hex") or "").upper()
            actual = btn_hex if btn_hex else default_hex
            selected = (not color_hex and not btn_hex) or (
                bool(color_hex) and color_hex == actual)
            # 选中态：2px ink；未选中态：1px 边框（与自定义色块样式一致，
            # 避免看起来"裸色点"，保持整张面板视觉一致）
            border = f"2px solid {ink}" if selected \
                else f"1px solid {border_col}"
            btn.setStyleSheet(
                f"QPushButton{{border-radius:8px;background:{actual};"
                f"border:{border};padding:0;outline:none;}}"
                f"QPushButton:hover{{border:2px solid {ink_sec};}}")

    def _on_custom_text_changed(self, text):
        text = text.strip().upper()
        if re.fullmatch(r"^#[0-9A-F]{6}$", text):
            self.custom_preview.setStyleSheet(
                f"QPushButton{{background:{text};border-radius:8px;"
                f"border:1px solid {ds.border_color()};}}"
                f"QPushButton:hover{{border:1px solid {ds.ink_sec()};}}")

    def _pick_custom_color(self):
        """点击自定义颜色色块 → 弹出取色器选任意颜色。"""
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QColorDialog
        cur = QColor(self.theme_mgr.current_accent()) \
            if self.theme_mgr.current_accent() else QColor(ds.accent())
        c = QColorDialog.getColor(cur, self, tr("选择主题色", "Pick accent color"))
        if c.isValid():
            self._set_accent(c.name())

    def _apply_custom_text(self):
        text = self.custom_edit.text().strip().upper()
        if re.fullmatch(r"^#[0-9A-F]{6}$", text):
            self._set_accent(text)
        else:
            self._refresh(self.theme_mgr.current_accent())

    def _on_reset(self):
        self._set_accent("")

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_NAME = "FormatMaster"


def _autostart_enabled():
    """读取注册表判断开机启动是否开启。"""
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            val, _ = winreg.QueryValueEx(k, _RUN_NAME)
            return bool(val)
    except OSError:
        return False


def _set_autostart(enable):
    """写入/删除注册表 Run 键。"""
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
            if enable:
                exe = sys.executable
                script = os.path.abspath(os.path.join(
                    os.path.dirname(__file__), "..", "..", "main_qt.py"))
                # 打包后 sys.executable 即 exe，直接启动自身
                cmd = f'"{exe}" "{script}"' if exe.endswith("python.exe") \
                    else f'"{exe}"'
                winreg.SetValueEx(k, _RUN_NAME, 0, winreg.REG_SZ, cmd)
            else:
                winreg.DeleteValue(k, _RUN_NAME)
        return True
    except OSError:
        return False


def _make_preset_store():
    """延迟导入避免循环依赖。"""
    from utils.panel_presets import PanelPresetStore
    return PanelPresetStore()


class SettingsPage(ScrollArea):
    """设置中心页。"""

    def __init__(self, window, services, parent=None):
        super().__init__(parent)
        self.setObjectName("settings")
        self.main_window = window
        self.services = services
        self.theme_mgr = services.theme_mgr
        self.setWidgetResizable(True)
        self.setViewportMargins(0, 0, 0, 0)

        # ── 双栏骨架：左侧 Pivot 导航 + 右侧 SegmentedWidget 卡片表单 ──
        self.root = QWidget()
        self.root.setAutoFillBackground(False)
        root_lay = QVBoxLayout(self.root)
        root_lay.setContentsMargins(24, 20, 24, 0)
        root_lay.setSpacing(16)
        self.setWidget(self.root)

        # 页面标题
        self._build_header(root_lay)

        # 主体：左导航 + 右表单
        body = QHBoxLayout()
        body.setSpacing(20)

        # 左侧导航（垂直图标列表，Fluent 风格卡片）
        from PySide6.QtWidgets import QListWidget, QListWidgetItem, QStackedWidget
        self.pivot = QListWidget(self.root)
        self.pivot.setObjectName("settingsNav")
        self.pivot.setFixedWidth(188)
        self.pivot.setSpacing(4)
        self.pivot.setIconSize(QSize(18, 18))
        self.pivot.setStyleSheet(self._nav_style())
        ds.bind_theme(self.pivot, self._nav_style)
        # 不设垂直对齐，让导航卡片列垂直铺满整列（否则只占内容高度，下方悬空）
        body.addWidget(self.pivot, 0)

        # 右侧表单（QStackedWidget 分页，每页是 ScrollArea 承载卡片分组）
        self.sg = QStackedWidget(self.root)
        self.sg.setObjectName("settingsStack")
        body.addWidget(self.sg, 1)

        # 面包屑：设置 / 当前分区（点击分区名可跳转）
        from qfluentwidgets import BreadcrumbBar
        self.breadcrumb = BreadcrumbBar(self.root)
        self.breadcrumb.setSpacing(6)
        self.breadcrumb.currentItemChanged.connect(self._on_crumb_changed)
        root_lay.addWidget(self.breadcrumb)

        root_lay.addLayout(body)
        # 注意：这里不能加 addStretch——它会把可用空间推给空 stretch，
        # 导致右侧表单区只占内容高度（页面一半高）；body 本身会拉伸铺满。

        # 分组页面注册表：导航 key → (列表项, 分页容器)
        self._sections = {}
        # 导航 key → FluentIcon（主题色切换时重新渲染图标）
        self._section_icons = {}
        # 当前挂载目标（_build_xxx 通过 _group 落到这里）
        self._active_group = None

        # 分区 key → 显示名（面包屑用）
        self._section_titles = {}

        # 分区构建注册表（懒构建：默认只建「常规」，其余分区在导航切换时
        # 按需构建——避免打开设置页一次性构建 11 个分区卡顿 ~170ms）
        self._section_order = [
            "general", "appearance", "convert", "advanced", "network",
            "presets", "shortcuts", "backup", "log", "sponsor", "about",
        ]
        self._section_builders = {
            "general": self._build_general,
            "appearance": self._build_appearance,
            "convert": self._build_convert,
            "advanced": self._build_advanced,
            "network": self._build_network,
            "presets": self._build_presets,
            "shortcuts": self._build_shortcuts,
            "backup": self._build_backup,
            "log": self._build_log,
            "sponsor": self._build_sponsor,
            "about": self._build_about,
        }
        # 预创建全部分区骨架（列表项+空分页），保证导航索引稳定；
        # 卡片内容懒构建——打开设置页只构建「常规」分区卡片，
        # 其余分区在导航切换时按需构建（避免一次性构建 11 分区卡顿 ~170ms）
        self._precreate_sections()
        self._build_general()

        # 导航切换联动：点击列表项 → 切换右侧分页
        self.pivot.currentRowChanged.connect(self._on_nav_changed)
        # 默认选中第一项
        if self._sections:
            self.pivot.setCurrentRow(0)
            self._on_nav_changed(0)

        # 主题色/明暗切换时重新渲染导航图标（FluentIcon.icon() 用 qconfig.themeColor
        # 渲染；SVG 图标按明暗重着色，需在切换后重新生成）
        try:
            from qfluentwidgets import qconfig
            qconfig.themeColorChanged.connect(self._refresh_nav_icons)
            qconfig.themeChangedFinished.connect(self._refresh_nav_icons)
        except Exception:  # noqa: BLE001
            pass

    def _nav_style(self):
        """左侧导航 Fluent 样式：图标 + 圆角 + 选中强调背景。"""
        # 用 _accent_tokens 覆盖默认 accent 系列，选中背景/文字色跟随用户主题色
        t = ds._accent_tokens(ds.tokens())
        r_card = ds.card_radius()
        r_ctrl = ds.RADIUS_CTRL
        return f"""
        QListWidget#settingsNav {{
            border: none;
            background: {t['card_bg']};
            border-radius: {r_card}px;
            outline: none;
            padding: 6px;
        }}
        QListWidget#settingsNav::item {{
            height: 40px;
            padding-left: 10px;
            padding-right: 12px;
            border-radius: {r_ctrl}px;
            color: {t['ink']};
            font-size: 13px;
        }}
        QListWidget#settingsNav::item:hover {{
            background: {t['card_hover']};
        }}
        QListWidget#settingsNav::item:selected {{
            background: {t['accent_pale']};
            color: {t['accent']};
            font-weight: 600;
        }}
        QListWidget#settingsNav::item:selected:!active {{
            background: {t['accent_pale']};
            color: {t['accent']};
        }}
        QListWidget#settingsNav::item:selected:active {{
            background: {t['accent_pale']};
            color: {t['accent']};
        }}
        """

    def _refresh_nav_icons(self, _color=None):
        """主题色切换后重新渲染导航图标，使图标颜色跟随新主题色。"""
        for key, (item, _scroll) in self._sections.items():
            icon = self._section_icons.get(key)
            if icon is not None:
                try:
                    item.setIcon(icon.icon())
                except Exception:  # noqa: BLE001
                    pass

    def _on_nav_changed(self, row):
        """列表项切换 → 按需构建分区（骨架已预建，卡片懒构建）并显示。"""
        key = self._section_order[row]
        _item, _scroll = self._sections.get(key, (None, None))
        if _scroll is not None:
            w = _scroll.widget()
            # 骨架已建但卡片未建（懒构建未触发过）→ 现场构建卡片内容
            if w is not None and w.layout() is not None and w.layout().count() == 0:
                builder = self._section_builders.get(key)
                if builder is not None:
                    try:
                        builder()
                    except Exception:  # noqa: BLE001 - 单个分区构建失败不阻断导航
                        pass
        self._show_section(key)
        self._update_breadcrumb(key)

    def _update_breadcrumb(self, key):
        """面包屑显示「设置 / 分区名」，当前分区高亮。"""
        self.breadcrumb.clear()
        self.breadcrumb.addItem("root", tr("设置", "Settings"))
        title = self._section_titles.get(key, key)
        self.breadcrumb.addItem(key, title)
        # 防回环：setCurrentItem 会触发 currentItemChanged
        self.breadcrumb.blockSignals(True)
        self.breadcrumb.setCurrentItem(key)
        self.breadcrumb.blockSignals(False)

    def _on_crumb_changed(self, key):
        """点击面包屑分区名 → 跳转对应分区。"""
        if key == "root":
            return
        if key in self._section_order:
            self.pivot.setCurrentRow(self._section_order.index(key))

    def _show_section(self, key):
        """切换右侧分页到指定 key。"""
        page = self._sections.get(key, (None, None))[1]
        if page is not None:
            self.sg.setCurrentWidget(page)

    def _group(self, title):
        """在右侧当前激活的分页里创建一个 SettingCardGroup。"""
        g = SettingCardGroup(title, self._active_page)
        self._active_layout.addWidget(g)
        return g

    def _add_section(self, key, title, icon=None):
        """注册设置分区：创建左侧列表项 + 右侧空分页（骨架）。

        key 已存在（懒构建复用骨架）时只把 _group 挂载目标切到该页，
        不重复创建列表项——保证导航 item 数量与分区顺序恒一致。
        """
        self._section_titles[key] = title  # 面包屑显示名
        if key in self._sections:
            _item, _scroll = self._sections[key]
            page = _scroll.widget()
            self._active_page = page
            self._active_layout = page.layout()
            return _item
        from PySide6.QtWidgets import QListWidgetItem
        if icon is not None:
            item = QListWidgetItem(icon.icon(), title)
            self._section_icons[key] = icon
        else:
            item = QListWidgetItem(title)
        item.setSizeHint(item.sizeHint().expandedTo(QSize(0, 40)))
        self.pivot.addItem(item)

        # 右侧分页：ScrollArea 承载卡片分组
        page = QWidget()
        page_lay = QVBoxLayout(page)
        page_lay.setContentsMargins(0, 0, 4, 0)
        # 组间距对标官方设置页（ExpandLayout spacing=28 的紧凑适配版）：
        # 12 过挤、28 过疏，20 提供清晰分组呼吸感又不失密度
        page_lay.setSpacing(20)
        # 不要在卡片之前 addStretch——它会把卡片顶到页面底部，导致上方大面积留白。
        # 卡片组随后经 _group 依次 append 到 _active_layout，顶部对齐、底部自然留白。

        scroll = ScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setViewportMargins(0, 0, 0, 0)
        scroll.setWidget(page)
        scroll.setAutoFillBackground(False)
        # 去掉滚动区边框，融入背景
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")

        self.sg.addWidget(scroll)
        self._sections[key] = (item, scroll)

        self._active_page = page
        self._active_layout = page_lay
        return item

    def _precreate_sections(self):
        """预创建全部设置分区骨架（列表项 + 空分页）。

        保证 pivot 的 item 数量与 _section_order 恒一致——否则懒构建
        动态 addItem 会与分区顺序索引错位（setCurrentRow 越界 →
        currentRow=-1 → 导航错乱）。卡片内容仍由 _build_xxx 按需懒构建。
        """
        meta = [
            ("general", "常规", "General", FluentIcon.SETTING),
            ("appearance", "外观", "Appearance", None),
            ("convert", "转换", "Convert", FluentIcon.SYNC),
            ("advanced", "高级", "Advanced", FluentIcon.DEVELOPER_TOOLS),
            ("network", "网络", "Network", FluentIcon.GLOBE),
            ("presets", "转换预设", "Presets", FluentIcon.LIBRARY),
            ("shortcuts", "快捷键", "Shortcuts", FluentIcon.COMMAND_PROMPT),
            ("backup", "数据备份", "Backup", FluentIcon.SAVE),
            ("log", "日志", "Log", FluentIcon.DOCUMENT),
            ("sponsor", "赞助", "Sponsor", FluentIcon.HEART),
            ("about", "关于", "About", FluentIcon.INFO),
        ]
        for key, zh, en, icon in meta:
            if key == "appearance":
                icon = _SvgNavIcon(get_resource_path(
                    os.path.join("assets", "icons", "monitor.svg")))
            elif icon is None:
                icon = FluentIcon.SETTING
            self._add_section(key, tr(zh, en), icon)

    def _build_header(self, root_lay):
        """页面标题区域（挂到根布局）。"""
        root_lay.addWidget(PageHeader(
            tr("设置中心", "Settings"), tr("自定义应用行为、主题、编码与高级选项", "Customize behavior, theme, codecs and advanced options"),
            icon=FluentIcon.SETTING))

    # ── 常规 ─────────────────────────────────────
    def _build_general(self):
        self._add_section("general", tr("常规", "General"), FluentIcon.SETTING)
        g = self._group(tr("常规", "General"))

        self.card_autostart = SwitchSettingCard(
            FluentIcon.POWER_BUTTON, tr("开机启动", "Auto start"), tr("登录 Windows 后自动运行格式大师", "Run FormatMaster after logging into Windows"),
            parent=g)
        self.card_autostart.setValue(_autostart_enabled())
        self.card_autostart.checkedChanged.connect(self._on_autostart)
        g.addSettingCard(self.card_autostart)

        self.card_tray = SwitchSettingCard(
            FluentIcon.BACKGROUND_FILL, tr("系统托盘", "System tray"), tr("关闭时最小化到托盘而不是退出", "Minimize to tray on close instead of quitting"),
            parent=g)
        self.card_tray.setValue(bool(self.services.get_pref("tray", False)))
        self.card_tray.checkedChanged.connect(self._on_tray_changed)
        g.addSettingCard(self.card_tray)

        self.card_close_confirm = SwitchSettingCard(
            FluentIcon.CLOSE, tr("关闭时确认", "Confirm on close"),
            tr("点击关闭按钮时询问直接退出或最小化到托盘", "Ask whether to quit or minimize to tray when closing"),
            parent=g)
        self.card_close_confirm.setValue(
            bool(self.services.get_pref("close_confirm", True)))
        self.card_close_confirm.checkedChanged.connect(
            self._on_close_confirm_changed)
        g.addSettingCard(self.card_close_confirm)

        # 关闭动作：仅在“关闭时确认”关闭（不再提醒）时生效
        self.card_close_action = _ComboSettingCard(
            FluentIcon.MINIMIZE, tr("关闭动作", "Close action"),
            tr("不再提醒后，点击叉号执行的动作", "Action when clicking close after \"don't ask again\""),
            [tr("直接退出", "Quit"), tr("最小化到托盘", "Minimize to tray")],
            parent=g)
        self.card_close_action.comboBox.currentIndexChanged.connect(
            self._on_close_action_changed)
        g.addSettingCard(self.card_close_action)
        # 初始联动：开启“关闭时确认”时禁用动作选择
        self.card_close_action.setEnabled(
            not self.services.get_pref("close_confirm", True))
        self.card_close_action.comboBox.setCurrentIndex(
            1 if self.services.get_pref("close_action", "quit") == "tray" else 0)

        self.card_check_update = SwitchSettingCard(
            FluentIcon.SYNC, tr("启动时检查更新", "Check updates on start"),
            tr("每次启动后自动检查新版本，有新版本时弹窗提示（可关闭）",
               "Check for new versions after startup; notify when available"),
            parent=g)
        self.card_check_update.setValue(
            bool(self.services.get_pref("check_update_on_start", True)))
        self.card_check_update.checkedChanged.connect(
            lambda on: self.services.set_pref("check_update_on_start",
                                              bool(on)))
        g.addSettingCard(self.card_check_update)

        # 默认输出目录：显式"浏览…"按钮选择目录，路径显示在卡片内容区
        self.card_outdir = SettingCard(
            FluentIcon.FOLDER, tr("默认输出目录", "Default output folder"),
            tr("自定义目录不存在时会自动创建", "Auto-created if the folder does not exist"), g)
        _d = self.services.get_pref("default_out_dir", "")
        if not isinstance(_d, str):
            _d = ""  # 配置损坏（非字符串）时按未设置处理
        self.card_outdir.setContent(_d or tr("未设置", "Not set"))
        self.btn_browse_outdir = PushButton(
            tr("浏览…", "Browse…"), self.card_outdir)
        self.btn_browse_outdir.clicked.connect(self._pick_outdir)
        self.card_outdir.hBoxLayout.addWidget(
            self.btn_browse_outdir, 0, Qt.AlignRight)
        g.addSettingCard(self.card_outdir)

        from gui_qt import i18n
        self.card_lang = _ComboSettingCard(
            FluentIcon.LANGUAGE, tr("界面语言", "Interface language"),
            tr("简体中文 / English，切换后重启应用生效", "Chinese / English, restart to apply"),
            [tr("简体中文", "简体中文"), "English"], g)
        self.card_lang.comboBox.setCurrentIndex(
            1 if i18n.current() == "en" else 0)
        self.card_lang.comboBox.currentIndexChanged.connect(
            self._on_lang_changed)
        g.addSettingCard(self.card_lang)

        # 更新检查频率（每次启动 / 每天 / 每周）
        self.card_update_freq = _ComboSettingCard(
            FluentIcon.SYNC, tr("更新检查频率", "Update check frequency"),
            tr("启动时自动检查新版本的频率", "How often to auto-check for new versions"),
            [tr("每次启动", "Every launch"), tr("每天一次", "Once a day"),
             tr("每周一次", "Once a week")], g)
        _freq_map = {"always": 0, "daily": 1, "weekly": 2}
        _freq_v = self.services.get_pref("update_check_freq", "always")
        self.card_update_freq.comboBox.setCurrentIndex(
            _freq_map.get(_freq_v if isinstance(_freq_v, str) else "always", 0))
        self.card_update_freq.comboBox.currentIndexChanged.connect(
            lambda i: self.services.set_pref(
                "update_check_freq", ["always", "daily", "weekly"][i]))
        g.addSettingCard(self.card_update_freq)

        # 记住窗口状态
        self.card_remember_window = SwitchSettingCard(
            FluentIcon.MOVE, tr("记住窗口状态", "Remember window state"),
            tr("下次启动时恢复窗口大小、位置和最大化状态",
               "Restore window size, position and maximized state on next launch"),
            parent=g)
        self.card_remember_window.setValue(
            bool(self.services.get_pref("remember_window", True)))
        self.card_remember_window.checkedChanged.connect(
            lambda on: self.services.set_pref("remember_window", bool(on)))
        g.addSettingCard(self.card_remember_window)

        # 通知方式
        self.card_notify_style = _ComboSettingCard(
            FluentIcon.MESSAGE, tr("通知方式", "Notification style"),
            tr("转换完成后的提示方式", "How to notify when conversions finish"),
            [tr("智能（托盘气泡优先）", "Smart (tray bubble first)"),
             tr("窗口内提示", "In-window toast"),
             tr("仅声音", "Sound only")], g)
        _ns_map = {"auto": 0, "toast": 1, "sound": 2}
        _ns_v = self.services.get_pref("notify_style", "auto")
        self.card_notify_style.comboBox.setCurrentIndex(
            _ns_map.get(_ns_v if isinstance(_ns_v, str) else "auto", 0))
        self.card_notify_style.comboBox.currentIndexChanged.connect(
            lambda i: self.services.set_pref(
                "notify_style", ["auto", "toast", "sound"][i]))
        g.addSettingCard(self.card_notify_style)

        # 启动画面（快速启动的机器可关闭）
        self.card_splash = SwitchSettingCard(
            FluentIcon.VIEW, tr("启动画面", "Splash screen"),
            tr("启动时显示品牌启动画面（快速启动的机器可关闭）",
               "Show brand splash on launch (can be disabled for fast startups)"),
            parent=g)
        self.card_splash.setValue(
            bool(self.services.get_pref("show_splash", True)))
        self.card_splash.checkedChanged.connect(
            lambda on: self.services.set_pref("show_splash", bool(on)))
        g.addSettingCard(self.card_splash)

        # 恢复默认设置（清空全部偏好 + 重启）
        self.card_reset_defaults = SettingCard(
            FluentIcon.DELETE, tr("恢复默认设置", "Reset to defaults"),
            tr("清除所有偏好设置并重启，恢复到首次安装状态",
               "Clear all preferences and restart, restoring factory state"),
            g)
        self.btn_reset_defaults = PushButton(
            tr("立即重置", "Reset now"), self.card_reset_defaults)
        self.btn_reset_defaults.clicked.connect(self._on_reset_defaults)
        self.card_reset_defaults.hBoxLayout.addWidget(
            self.btn_reset_defaults, 0, Qt.AlignRight)
        g.addSettingCard(self.card_reset_defaults)

    def _on_reset_defaults(self):
        """恢复默认设置：确认 → 清空全部偏好 → 重启生效。"""
        from gui_qt.components import toast
        from qfluentwidgets import MessageBox
        from utils.config import USER_PREFS

        box = MessageBox(
            tr("恢复默认设置", "Reset to defaults"),
            tr("将清除全部偏好设置（主题、快捷键、转换参数等）并重启。\n\n"
               "此操作不可撤销，确定继续？",
               "All preferences (theme, shortcuts, conversion settings, etc.) "
               "will be cleared and the app will restart.\n\n"
               "This cannot be undone. Continue?"),
            self.main_window)
        box.yesButton.setText(tr("确定重置", "Reset"))
        box.cancelButton.setText(tr("取消", "Cancel"))
        if not box.exec():
            return
        try:
            USER_PREFS.clear()
        except Exception as e:  # noqa: BLE001
            toast.show_error(self, tr("重置失败：{}", "Reset failed: {}").format(e))
            return
        toast.show_success(self, tr("已重置，正在重启…", "Reset, restarting…"))
        try:
            from gui_qt.app import restart_application
            restart_application(self.main_window)
        except Exception:  # noqa: BLE001 - 重启失败不影响（设置已重置）
            pass

    # ── 外观 ─────────────────────────────────────
    def _build_appearance(self):
        """「外观」分区：主题模式 + 主题色 + 圆角/动画。"""
        from gui_qt.components.theme_manager import ACCENT_COLORS
        self._add_section("appearance", tr("外观", "Appearance"),
                          FluentIcon.BRUSH)
        g = self._group(tr("外观", "Appearance"))

        # 应用主题（浅色 / 深色 / 跟随系统）
        self.card_theme = _ComboSettingCard(
            FluentIcon.PALETTE, tr("应用主题", "Apply theme"),
            tr("浅色 / 深色 / 跟随系统", "Light / Dark / System"),
            MODES, g)
        cur = self.theme_mgr.current_mode()
        self.card_theme.comboBox.setCurrentText(
            cur if cur in MODES else MODE_AUTO)
        self.card_theme.comboBox.currentTextChanged.connect(
            self.theme_mgr.set_mode)
        g.addSettingCard(self.card_theme)

        # 主题色（色块面板：预设 + 自定义输入 + 恢复默认）
        self.card_accent = _AccentColorCard(
            self.services, self.theme_mgr, g)
        g.addSettingCard(self.card_accent)

        # 卡片圆角
        self.card_radius_switch = SwitchSettingCard(
            FluentIcon.FULL_SCREEN, tr("卡片圆角", "Rounded cards"),
            tr("关闭后卡片与面板改为直角（重启后完全生效）", "Square corners for cards and panels (fully effective after restart)"),
            parent=g)
        self.card_radius_switch.setValue(
            bool(self.services.get_pref("card_radius", True)))
        self.card_radius_switch.checkedChanged.connect(self._on_card_radius)
        g.addSettingCard(self.card_radius_switch)

        # 界面动画
        self.card_anim = SwitchSettingCard(
            FluentIcon.MOVIE, tr("界面动画", "Animations"),
            tr("页面切换淡入与卡片悬停浮起", "Page fade-in and card hover effects"),
            parent=g)
        self.card_anim.setValue(
            bool(self.services.get_pref("animations", True)))
        self.card_anim.checkedChanged.connect(self._on_animations)
        g.addSettingCard(self.card_anim)

        # 毛玻璃效果（Win11 Mica 云母背景；性能敏感时可关闭）
        self.card_mica = SwitchSettingCard(
            FluentIcon.CLOUD, tr("毛玻璃效果", "Mica effect"),
            tr("Win11 云母背景（关闭后为普通窗口背景，更省资源）",
               "Win11 Mica background (disable for lower GPU/CPU usage)"),
            parent=g)
        self.card_mica.setValue(
            bool(self.services.get_pref("mica", True)))
        self.card_mica.checkedChanged.connect(self._on_mica)
        g.addSettingCard(self.card_mica)

        # 界面缩放（全局字号比例，重启生效）
        self.card_ui_scale = _ComboSettingCard(
            FluentIcon.ZOOM, tr("界面缩放", "UI scale"),
            tr("全局界面字号缩放（重启后生效）", "Global font scale (restart to apply)"),
            [tr("标准 100%", "Standard 100%"), tr("小 90%", "Small 90%"),
             tr("大 110%", "Large 110%"), tr("更大 125%", "Larger 125%"),
             tr("特大 150%", "Extra large 150%")], g)
        _scale_map = {1.0: 0, 0.9: 1, 1.1: 2, 1.25: 3, 1.5: 4}
        cur_scale = float(self.services.get_pref("ui_scale", 1.0))
        self.card_ui_scale.comboBox.setCurrentIndex(
            _scale_map.get(cur_scale, 0))
        self.card_ui_scale.comboBox.currentIndexChanged.connect(
            self._on_ui_scale_changed)
        g.addSettingCard(self.card_ui_scale)

    def _on_card_radius(self, on):
        self.services.set_pref("card_radius", bool(on))
        ds.set_card_radius(bool(on))
        ds.set_app_style()

    def _on_animations(self, on):
        self.services.set_pref("animations", bool(on))
        ds.set_animations(bool(on))

    def _on_mica(self, on):
        """毛玻璃开关：存偏好 + 即时生效（重应用/移除 Mica 效果）。"""
        self.services.set_pref("mica", bool(on))
        try:
            self.main_window._enable_mica()
        except Exception:  # noqa: BLE001 - 特效切换失败不影响设置
            pass

    def _on_ui_scale_changed(self, idx):
        """界面缩放：存偏好 + 提示重启（QSS 启动时生成）。"""
        from gui_qt.components import toast
        scales = [1.0, 0.9, 1.1, 1.25, 1.5]
        v = scales[idx] if 0 <= idx < len(scales) else 1.0
        self.services.set_pref("ui_scale", v)
        toast.show_info(
            self, tr("界面缩放已设置，重启应用后生效", "UI scale set, restart to apply"))

    def _on_lang_changed(self, idx):
        from gui_qt import i18n
        lang = "en" if idx == 1 else "zh"
        if lang == i18n.current():
            return
        i18n.set_language(lang)
        self.services.set_pref("language", lang)
        from gui_qt.components import toast
        toast.show_info(
            self, tr("语言已切换，重启应用后生效", "Language switched, restart to apply")
            if lang == "en" else
            "Language switched, restart to apply")

    def _on_autostart(self, on):
        from gui_qt.components import toast
        if _set_autostart(bool(on)):
            toast.show_success(self, tr("开机启动", "Launch at startup") + ("已开启" if on else "已关闭"))
        else:
            toast.show_error(self, tr("设置开机启动失败（注册表写入被拒绝）", "Failed to enable auto-start (registry write denied)"))
            self.card_autostart.setValue(_autostart_enabled())

    def _on_tray_changed(self, on):
        """系统托盘开关：保存偏好 + 立即创建/移除托盘图标。"""
        self.services.set_pref("tray", bool(on))
        setup = getattr(self.main_window, "_setup_tray", None)
        if callable(setup):
            try:
                setup()
            except Exception:  # noqa: BLE001
                pass

    def _on_close_confirm_changed(self, on):
        """“关闭时确认”开关：保存偏好并联动“关闭动作”卡可用性。"""
        self.services.set_pref("close_confirm", bool(on))
        # 开启确认时动作由弹窗决定，禁用动作选择；关闭时启用
        self.card_close_action.setEnabled(not bool(on))

    def _on_close_action_changed(self, index):
        """“关闭动作”下拉：0=直接退出 / 1=最小化到托盘。"""
        self.services.set_pref(
            "close_action", "tray" if index == 1 else "quit")

    def _pick_outdir(self):
        d = QFileDialog.getExistingDirectory(self, tr("选择默认输出目录", "Pick default output folder"))
        if d:
            self.services.set_pref("default_out_dir", d)
            self.card_outdir.setContent(d)
            self._apply_outdir_to_panels(d)

    def _apply_outdir_to_panels(self, directory):
        """设置"默认输出目录"后立即应用到所有面板（覆盖面板旧自定义，
        否则用户新设置看不到效果——面板会保留之前的选择）。"""
        from gui_qt.widgets import OutputDirRow
        for page in getattr(self.main_window, "pages", {}).values():
            out_row = getattr(page, "out_row", None)
            if isinstance(out_row, OutputDirRow):
                try:
                    out_row.set_state(OutputDirRow.MODE_CUSTOM, directory)
                except Exception:  # noqa: BLE001
                    pass

    # ── 转换 ─────────────────────────────────────
    def _build_convert(self):
        self._add_section("convert", tr("转换", "Convert"), FluentIcon.SYNC)
        g = self._group(tr("转换", "Convert"))

        self.card_fmt = _ComboSettingCard(
            FluentIcon.VIDEO, tr("默认视频格式", "Default video format"), tr("新会话的默认目标格式", "Default format for new sessions"),
            list(SUPPORTED_VIDEO), g)
        self.card_fmt.comboBox.setCurrentText(
            self.services.get_pref("default_fmt", "MP4"))
        self.card_fmt.comboBox.currentTextChanged.connect(
            lambda t: self.services.set_pref("default_fmt", t))
        g.addSettingCard(self.card_fmt)

        self.card_codec = _ComboSettingCard(
            FluentIcon.CODE, tr("默认编码器", "Default encoder"), tr("「默认」表示按容器自动选择", "\"Default\" = auto by container"),
            list(VIDEO_CODECS), g)
        self.card_codec.comboBox.setCurrentText(
            self.services.get_pref("default_codec", tr("默认", "Default")))
        self.card_codec.comboBox.currentTextChanged.connect(
            lambda t: self.services.set_pref("default_codec", t))
        g.addSettingCard(self.card_codec)

        self.card_gpu = SwitchSettingCard(
            FluentIcon.SPEED_HIGH, tr("GPU 加速", "GPU acceleration"), tr("默认启用硬件加速（失败自动降级 CPU）", "Hardware acceleration on by default (falls back to CPU)"),
            parent=g)
        self.card_gpu.setValue(bool(self.services.get_pref("gpu_accel", True)))
        self.card_gpu.checkedChanged.connect(
            lambda on: self.services.set_pref("gpu_accel", bool(on)))
        g.addSettingCard(self.card_gpu)

        # 并发建议值：按 CPU 核数自适应（逻辑核 ≥8 推荐 4，否则 2）
        import os as _os
        _cores = 1
        try:
            _cores = _os.cpu_count() or 1
        except Exception:  # noqa: BLE001
            pass
        _suggest = 4 if _cores >= 8 else 2
        self.card_parallel = _ComboSettingCard(
            FluentIcon.SYNC, tr("并行转换", "Parallel convert"),
            tr("同时执行的任务数（本机 {} 核，建议 {}）", "Concurrent tasks ({} cores, {} recommended)").format(_cores, _suggest),
            ["1", "2", "3", "4", "6", "8"], g)
        # 首次使用（无偏好）时默认采用核数建议值
        self.card_parallel.comboBox.setCurrentText(
            str(self.services.get_pref("parallel", _suggest)))
        self.card_parallel.comboBox.currentTextChanged.connect(
            self._on_parallel_changed)
        g.addSettingCard(self.card_parallel)

        self.card_retry = _ComboSettingCard(
            FluentIcon.RETURN, tr("失败重试", "Retry"), tr("转换失败后自动重试的次数", "Auto-retry count after failure"),
            ["0", "1", "2", "3"], g)
        self.card_retry.comboBox.setCurrentText(
            str(self.services.get_pref("max_retries", 0)))
        self.card_retry.comboBox.currentTextChanged.connect(
            lambda t: self.services.set_pref("max_retries", int(t)))
        g.addSettingCard(self.card_retry)

        self.card_open_dir = SwitchSettingCard(
            FluentIcon.FOLDER, tr("转换后打开输出目录", "Open output folder after converting"),
            tr("所有任务完成后自动打开输出文件夹", "Open output folder when all tasks finish"),
            parent=g)
        self.card_open_dir.setValue(bool(self.services.get_pref("open_dir_on_done", False)))
        self.card_open_dir.checkedChanged.connect(
            lambda on: self.services.set_pref("open_dir_on_done", bool(on)))
        g.addSettingCard(self.card_open_dir)

        self.card_notify_sound = SwitchSettingCard(
            FluentIcon.PLAY, tr("完成提示音", "Completion sound"),
            tr("转换成功后播放系统提示音", "Play system sound on success"),
            parent=g)
        self.card_notify_sound.setValue(bool(self.services.get_pref("notify_sound", True)))
        self.card_notify_sound.checkedChanged.connect(
            lambda on: self.services.set_pref("notify_sound", bool(on)))
        g.addSettingCard(self.card_notify_sound)

        # 输出冲突处理策略
        self.card_conflict = _ComboSettingCard(
            FluentIcon.DELETE, tr("输出文件冲突", "Output conflict"),
            tr("目标目录已存在同名文件时的处理方式", "How to handle existing files with the same name"),
            [tr("自动重命名（_1/_2…）", "Auto rename (_1/_2…)"),
             tr("直接覆盖旧文件", "Overwrite existing")], g)
        _c_map = {"auto_rename": 0, "overwrite": 1}
        _c_v = self.services.get_pref("conflict_policy", "auto_rename")
        self.card_conflict.comboBox.setCurrentIndex(
            _c_map.get(_c_v if isinstance(_c_v, str) else "auto_rename", 0))
        self.card_conflict.comboBox.currentIndexChanged.connect(
            lambda i: self.services.set_pref(
                "conflict_policy", ["auto_rename", "overwrite"][i]))
        g.addSettingCard(self.card_conflict)

    def _on_parallel_changed(self, text):
        n = int(text)
        self.services.set_pref("parallel", n)
        # 运行时调整 TaskManager 并行度
        tm = getattr(self.services, "task_manager", None)
        if tm is not None:
            tm.set_parallel(n)

    # ── 高级 ─────────────────────────────────────
    def _build_advanced(self):
        self._add_section("advanced", tr("高级", "Advanced"), FluentIcon.DEVELOPER_TOOLS)
        g = self._group(tr("高级", "Advanced"))

        from gui_qt import context_menu as _cm
        # 文件右键菜单：右侧按钮按安装状态显示 安装/卸载
        self.card_menu = SettingCard(
            FluentIcon.MENU, tr("文件右键菜单", "Context menu"),
            tr("右键任意文件 →「用格式大师转换」直接打开",
               "Right-click any file → convert with FormatMaster"), g)
        self.btn_menu = PushButton(
            tr("卸载", "Uninstall") if _cm.installed() else tr("安装", "Install"))
        self.btn_menu.clicked.connect(self._toggle_context_menu)
        self.card_menu.hBoxLayout.addWidget(self.btn_menu, 0, Qt.AlignRight)
        self.card_menu.hBoxLayout.addSpacing(16)
        g.addSettingCard(self.card_menu)

        # FFmpeg 路径：路径 + 「浏览…」选择自定义 exe + 「重新检测」
        ffmpeg_path = get_ffmpeg_path() or tr("未找到", "Not found")
        self.card_ffmpeg = SettingCard(
            FluentIcon.COMMAND_PROMPT, tr("FFmpeg 路径", "FFmpeg path"),
            ffmpeg_path, g)
        self.btn_ffmpeg_browse = PushButton(tr("浏览…", "Browse…"))
        self.btn_ffmpeg_browse.clicked.connect(self._browse_ffmpeg)
        self.card_ffmpeg.hBoxLayout.addWidget(
            self.btn_ffmpeg_browse, 0, Qt.AlignRight)
        self.btn_ffmpeg_redetect = PushButton(tr("重新检测", "Re-detect"))
        self.btn_ffmpeg_redetect.clicked.connect(self._redetect_ffmpeg)
        self.card_ffmpeg.hBoxLayout.addWidget(
            self.btn_ffmpeg_redetect, 0, Qt.AlignRight)
        self.card_ffmpeg.hBoxLayout.addSpacing(16)
        g.addSettingCard(self.card_ffmpeg)

        self.card_debug = SwitchSettingCard(
            FluentIcon.DEVELOPER_TOOLS, tr("调试模式", "Debug mode"), tr("输出更详细的调试日志", "Output more detailed debug logs"),
            parent=g)
        self.card_debug.setValue(bool(self.services.get_pref("debug", False)))
        self.card_debug.checkedChanged.connect(
            lambda on: self.services.set_pref("debug", bool(on)))
        g.addSettingCard(self.card_debug)

        # 硬件加速默认引擎
        self.card_hw_engine = _ComboSettingCard(
            FluentIcon.SPEED_HIGH, tr("硬件加速引擎", "HW acceleration engine"),
            tr("视频转换默认使用的硬件引擎（面板可单独覆盖）", "Default HW engine for video conversion (overridable per panel)"),
            [tr("自动检测", "Auto detect"), tr("NVIDIA NVENC", "NVIDIA NVENC"),
             tr("Intel QSV", "Intel QSV"), tr("AMD AMF", "AMD AMF"),
             tr("禁用硬件加速", "Disable HW accel")], g)
        _hw_map = {"auto": 0, "nvidia": 1, "intel": 2, "amd": 3, "off": 4}
        _hw_v = self.services.get_pref("hw_accel_engine", "auto")
        self.card_hw_engine.comboBox.setCurrentIndex(
            _hw_map.get(_hw_v if isinstance(_hw_v, str) else "auto", 0))
        self.card_hw_engine.comboBox.currentIndexChanged.connect(
            lambda i: self.services.set_pref(
                "hw_accel_engine",
                ["auto", "nvidia", "intel", "amd", "off"][i]))
        g.addSettingCard(self.card_hw_engine)

        # 失败自动修复
        self.card_auto_recover = SwitchSettingCard(
            FluentIcon.ROBOT, tr("失败自动修复", "Auto-recover on failure"),
            tr("转换失败时自动修复源文件或降级参数重试（关闭则只报错）",
               "Auto-fix source file or retry with fallback params on failure"),
            parent=g)
        self.card_auto_recover.setValue(
            bool(self.services.get_pref("auto_recover", True)))
        self.card_auto_recover.checkedChanged.connect(
            lambda on: self.services.set_pref("auto_recover", bool(on)))
        g.addSettingCard(self.card_auto_recover)

        # 日志级别
        self.card_log_level = _ComboSettingCard(
            FluentIcon.DOCUMENT, tr("日志级别", "Log level"),
            tr("写入日志的详细程度（调试最详细）", "How detailed the log should be (Debug = most detailed)"),
            [tr("调试", "Debug"), tr("信息", "Info"),
             tr("警告", "Warning"), tr("错误", "Error")], g)
        _ll_map = {"debug": 0, "info": 1, "warning": 2, "error": 3}
        _ll_v = self.services.get_pref("log_level", "debug")
        self.card_log_level.comboBox.setCurrentIndex(
            _ll_map.get(_ll_v if isinstance(_ll_v, str) else "debug", 0))
        self.card_log_level.comboBox.currentIndexChanged.connect(
            self._on_log_level_changed)
        g.addSettingCard(self.card_log_level)

        # 日志保留份数
        self.card_log_backup = _ComboSettingCard(
            FluentIcon.SAVE, tr("日志保留份数", "Log backups to keep"),
            tr("滚动日志的备份份数（每份最大 2MB）", "Rolling log backup count (2MB each)"),
            ["1", "3", "5"], g)
        self.card_log_backup.comboBox.setCurrentText(
            str(self.services.get_pref("log_backup", 1)))
        self.card_log_backup.comboBox.currentIndexChanged.connect(
            self._on_log_backup_changed)
        g.addSettingCard(self.card_log_backup)

        # 退出时清理临时文件
        self.card_cleanup_temp = SwitchSettingCard(
            FluentIcon.CLEAR_SELECTION, tr("退出时清理临时文件", "Clean temp files on exit"),
            tr("关闭程序时清理转换/下载产生的临时文件", "Clean up conversion/download temp files when quitting"),
            parent=g)
        self.card_cleanup_temp.setValue(
            bool(self.services.get_pref("cleanup_temp_on_exit", False)))
        self.card_cleanup_temp.checkedChanged.connect(
            lambda on: self.services.set_pref("cleanup_temp_on_exit", bool(on)))
        g.addSettingCard(self.card_cleanup_temp)

        # 退出清理分类（仅在「退出时清理」开启时有意义；拼接类/更新包轻量默认清理）
        self.card_clean_share = SwitchSettingCard(
            FluentIcon.LINK, tr("清理局域网共享目录", "Clean LAN share dirs"),
            tr("退出时清理 fm_share_* 临时共享目录（空目录）",
               "Remove empty fm_share_* temp share dirs on exit"),
            parent=g)
        self.card_clean_share.setValue(
            bool(self.services.get_pref("cleanup_share_dirs", True)))
        self.card_clean_share.checkedChanged.connect(
            lambda on: self.services.set_pref("cleanup_share_dirs", bool(on)))
        g.addSettingCard(self.card_clean_share)

        self.card_clean_m3u8 = SwitchSettingCard(
            FluentIcon.LIBRARY, tr("清理 M3U8 临时目录", "Clean M3U8 temp dirs"),
            tr("退出时清理 *_m3u8 下载临时目录（空目录）",
               "Remove empty *_m3u8 download temp dirs on exit"),
            parent=g)
        self.card_clean_m3u8.setValue(
            bool(self.services.get_pref("cleanup_m3u8_dirs", True)))
        self.card_clean_m3u8.checkedChanged.connect(
            lambda on: self.services.set_pref("cleanup_m3u8_dirs", bool(on)))
        g.addSettingCard(self.card_clean_m3u8)

        # FFmpeg 全局附加参数（空格分隔，插入到每次转换命令）
        self.card_ffmpeg_args = SettingCard(
            FluentIcon.COMMAND_PROMPT, tr("FFmpeg 附加参数", "FFmpeg extra args"),
            tr("追加到每次转换命令的全局参数（空格分隔，如 -threads 4）",
               "Global args appended to every conversion (space-separated, e.g. -threads 4)"),
            g)
        self.ed_ffmpeg_args = QLineEdit(
            self.services.get_pref("ffmpeg_extra_args", ""),
            self.card_ffmpeg_args)
        self.ed_ffmpeg_args.setPlaceholderText("-threads 4")
        self.ed_ffmpeg_args.setClearButtonEnabled(True)
        self.ed_ffmpeg_args.setFixedWidth(200)
        self.ed_ffmpeg_args.editingFinished.connect(self._on_ffmpeg_args_changed)
        self.card_ffmpeg_args.hBoxLayout.addWidget(
            self.ed_ffmpeg_args, 0, Qt.AlignRight)
        self.card_ffmpeg_args.hBoxLayout.addSpacing(16)
        g.addSettingCard(self.card_ffmpeg_args)

        # 立即清理临时文件
        self.card_cleanup_now = PushSettingCard(
            tr("立即清理", "Clean now"), FluentIcon.BROOM,
            tr("清理临时文件", "Clean temp files"),
            tr("删除本程序遗留的临时文件（进行中的任务不受影响）",
               "Delete leftover temp files (running tasks are not affected)"), g)
        self.card_cleanup_now.clicked.connect(self._on_cleanup_temp_now)
        g.addSettingCard(self.card_cleanup_now)

    # ── 高级回调 ────────────────────────────────
    def _on_log_level_changed(self, i):
        level = ["debug", "info", "warning", "error"][i]
        self.services.set_pref("log_level", level)
        try:
            from app import logger
            logger.configure(level=level)
        except Exception:  # noqa: BLE001
            pass

    def _on_log_backup_changed(self, i):
        count = int(["1", "3", "5"][i])
        self.services.set_pref("log_backup", count)
        try:
            from app import logger
            logger.configure(backup_count=count)
        except Exception:  # noqa: BLE001
            pass

    def _on_cleanup_temp_now(self):
        """立即清理临时文件。"""
        from gui_qt.components import toast
        try:
            from utils.temp_cleanup import cleanup_temp_files
            n = cleanup_temp_files()
            if n:
                toast.show_success(
                    self, tr("已清理 {} 个临时文件/目录", "Cleaned {} temp items").format(n))
            else:
                toast.show_info(self, tr("没有可清理的临时文件", "No temp files to clean"))
        except Exception as e:  # noqa: BLE001
            toast.show_error(self, tr("清理失败：{}", "Cleanup failed: {}").format(e))

    def _on_ffmpeg_args_changed(self):
        """FFmpeg 附加参数：存偏好（空白自动归一）。"""
        text = self.ed_ffmpeg_args.text().strip()
        self.services.set_pref("ffmpeg_extra_args", text)

    # ── 网络 ─────────────────────────────────────
    def _build_network(self):
        """「网络」分区：HTTP/HTTPS 代理设置。"""
        self._add_section("network", tr("网络", "Network"), FluentIcon.GLOBE)
        g = self._group(tr("网络代理", "Network proxy"))
        from PySide6.QtWidgets import QLineEdit as _QLE

        # 代理模式
        self.card_proxy_mode = _ComboSettingCard(
            FluentIcon.GLOBE, tr("代理模式", "Proxy mode"),
            tr("下载类功能（更新/视频下载）的网络代理", "Network proxy for download features (updates, video downloads)"),
            [tr("关闭（直连）", "Off (direct)"), tr("手动代理", "Manual proxy")], g)
        self.card_proxy_mode.comboBox.setCurrentIndex(
            1 if self.services.get_pref("proxy_mode", "off") == "manual" else 0)
        self.card_proxy_mode.comboBox.currentIndexChanged.connect(
            self._on_proxy_mode_changed)
        g.addSettingCard(self.card_proxy_mode)

        # 代理主机
        self.card_proxy_host = SettingCard(
            FluentIcon.CLOUD, tr("代理地址", "Proxy host"),
            tr("如 127.0.0.1 或 proxy.example.com", "e.g. 127.0.0.1 or proxy.example.com"), g)
        self.proxy_host_edit = _QLE(str(self.services.get_pref("proxy_host", "") or ""))
        self.proxy_host_edit.setFixedWidth(170)
        self.proxy_host_edit.textChanged.connect(
            lambda t: self.services.set_pref("proxy_host", t.strip()))
        self.card_proxy_host.hBoxLayout.addWidget(
            self.proxy_host_edit, 0, Qt.AlignRight)
        self.card_proxy_host.hBoxLayout.addSpacing(16)
        g.addSettingCard(self.card_proxy_host)

        # 代理端口
        self.card_proxy_port = SettingCard(
            FluentIcon.CLOUD, tr("代理端口", "Proxy port"),
            tr("如 7890（常见本地代理端口）", "e.g. 7890 (common local proxy port)"), g)
        self.proxy_port_edit = _QLE(str(self.services.get_pref("proxy_port", 0) or ""))
        self.proxy_port_edit.setFixedWidth(170)
        self.proxy_port_edit.textChanged.connect(self._on_proxy_port_changed)
        self.card_proxy_port.hBoxLayout.addWidget(
            self.proxy_port_edit, 0, Qt.AlignRight)
        self.card_proxy_port.hBoxLayout.addSpacing(16)
        g.addSettingCard(self.card_proxy_port)

    def _on_proxy_mode_changed(self, i):
        self.services.set_pref("proxy_mode", "manual" if i == 1 else "off")
        self._apply_proxy_live()

    def _on_proxy_port_changed(self, t):
        try:
            self.services.set_pref("proxy_port", int(t.strip()) if t.strip() else 0)
        except ValueError:
            self.services.set_pref("proxy_port", 0)
        self._apply_proxy_live()

    def _apply_proxy_live(self):
        """立即应用代理设置（环境变量即刻生效，无需重启）。"""
        try:
            from utils.net_proxy import proxy_from_prefs
            proxy_from_prefs(self.services.get_pref)
        except Exception:  # noqa: BLE001
            pass

    # ── 转换预设 ─────────────────────────────────
    def _build_presets(self):
        self._add_section("presets", tr("转换预设", "Presets"), FluentIcon.LIBRARY)
        g = self._group(tr("转换预设", "Convert presets"))

        from gui_qt.components import toast
        self.preset_store = _make_preset_store()

        card = SettingCard(FluentIcon.LIBRARY, tr("应用预设", "Apply preset"),
                           tr("把保存的参数组合一键应用到所有面板", "Apply a saved param combo to all panels"), g)
        self.cb_preset = ComboBox()
        self.cb_preset.setFixedWidth(160)
        self._reload_preset_list()
        card.hBoxLayout.addWidget(self.cb_preset, 0, Qt.AlignRight)
        btn_del = PushButton(tr("删除", "Delete"))
        btn_del.clicked.connect(self._delete_preset)
        btn_apply = PushButton(tr("应用", "Apply"))
        btn_apply.clicked.connect(self._apply_preset)
        card.hBoxLayout.addWidget(btn_del)
        card.hBoxLayout.addWidget(btn_apply)
        card.hBoxLayout.addSpacing(16)
        g.addSettingCard(card)

        self.card_save_preset = PushSettingCard(
            tr("保存预设", "Save preset"), FluentIcon.ADD,
            tr("保存当前所有面板参数", "Save current panel params"),
            tr("把当前各面板的参数组合保存为命名预设，可一键复用", "Save current panel settings as a named preset for reuse"), g)
        self.card_save_preset.clicked.connect(self._save_preset)
        g.addSettingCard(self.card_save_preset)

    def _reload_preset_list(self):
        names = self.preset_store.list()
        self.cb_preset.clear()
        self.cb_preset.addItems(names)
        if names:
            self.cb_preset.setCurrentIndex(0)

    def _save_preset(self):
        from gui_qt.components import toast
        name, ok = QInputDialog.getText(
            self, tr("保存预设", "Save preset"),
            tr("预设名称：", "Preset name:"))
        name = (name or "").strip()
        if not ok or not name:
            return
        panels = {}
        for page in getattr(self.main_window, "pages", {}).values():
            collect = getattr(page, "collect_prefs", None)
            key = getattr(page, "panel_key", None)
            if callable(collect) and key:
                try:
                    panels[key] = collect()
                except Exception:  # noqa: BLE001
                    pass
        self.preset_store.save(name, panels)
        self._reload_preset_list()
        toast.show_success(self, tr("预设已保存：{}", "Preset saved: {}").format(name))

    def _apply_preset(self):
        from gui_qt.components import toast
        name = self.cb_preset.currentText().strip()
        if not name:
            toast.show_warning(self, tr("暂无预设，请先保存", "No presets yet, save one first"))
            return
        panels = self.preset_store.load(name)
        if not panels:
            toast.show_error(self, tr("预设不存在或已损坏", "Preset missing or corrupted"))
            self._reload_preset_list()
            return
        applied = 0
        for page in getattr(self.main_window, "pages", {}).values():
            apply = getattr(page, "apply_prefs", None)
            key = getattr(page, "panel_key", None)
            if callable(apply) and key and key in panels:
                try:
                    apply(panels[key])
                    applied += 1
                except Exception:  # noqa: BLE001
                    pass
        toast.show_success(self, tr("已应用 {} 个面板的参数", "Applied params to {} panels").format(applied))

    def _delete_preset(self):
        from gui_qt.components import toast
        name = self.cb_preset.currentText().strip()
        if not name:
            return
        self.preset_store.delete(name)
        self._reload_preset_list()
        toast.show_info(self, tr("预设已删除：{}", "Preset deleted: {}").format(name))

    def _toggle_context_menu(self):
        from gui_qt import context_menu as cm
        from gui_qt.components import toast
        if cm.installed():
            err = cm.uninstall()
            if err:
                toast.show_error(self, tr("卸载失败：{}", "Uninstall failed: {}").format(err))
                return
            self.btn_menu.setText(tr("安装", "Install"))
            toast.show_info(self, tr("已卸载右键菜单", "Context menu uninstalled"))
        else:
            err = cm.install()
            if err:
                toast.show_error(self, tr("安装失败：{}", "Install failed: {}").format(err))
                return
            self.btn_menu.setText(tr("卸载", "Uninstall"))
            toast.show_success(self, tr("已安装右键菜单", "Context menu installed"))

    def _browse_ffmpeg(self):
        """浏览选择 ffmpeg.exe：后台线程验证可用后保存为自定义路径并生效。"""
        from gui_qt.components import toast
        path, _ = QFileDialog.getOpenFileName(
            self, tr("选择 ffmpeg.exe", "Select ffmpeg.exe"),
            "", "ffmpeg.exe (*.exe);;All files (*)")
        if not path:
            return
        # 禁用按钮防止重复点击
        self.btn_ffmpeg_browse.setEnabled(False)
        self.btn_ffmpeg_browse.setText(tr("验证中…", "Validating…"))

        def _validate():
            """后台线程验证 ffmpeg 可用性。"""
            try:
                import subprocess
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                r = subprocess.run([path, "-version"], capture_output=True,
                                   timeout=8, creationflags=flags)
                ok = (r.returncode == 0
                      and b"ffmpeg" in (r.stdout + r.stderr).lower())
            except Exception:  # noqa: BLE001
                ok = False
            # 回主线程更新 UI
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: _on_result(ok))

        def _on_result(ok):
            self.btn_ffmpeg_browse.setEnabled(True)
            self.btn_ffmpeg_browse.setText(tr("浏览…", "Browse…"))
            if not ok:
                toast.show_error(self, tr("所选文件不是有效的 ffmpeg",
                                          "Selected file is not a valid ffmpeg"))
                return
            self.services.set_pref("ffmpeg_custom_path", path)
            self.card_ffmpeg.setContent(path)
            toast.show_success(self, tr("FFmpeg 路径已更新", "FFmpeg path updated"))

        import threading
        threading.Thread(target=_validate, daemon=True).start()

    def _redetect_ffmpeg(self):
        from gui_qt.components import toast
        if self.services.ffmpeg_ready():
            self.card_ffmpeg.setContent(get_ffmpeg_path() or tr("未找到", "Not found"))
            toast.show_success(self, tr("FFmpeg 已就绪", "FFmpeg ready"))
            return
        toast.show_info(self, tr("FFmpeg 缺失，正在后台下载…", "FFmpeg missing, downloading in background…"))

        def _done(ok):
            # 下载线程回调：通过 QTimer 切回主线程刷新 UI
            from PySide6.QtCore import QTimer

            def _update():
                if ok:
                    self.card_ffmpeg.setContent(get_ffmpeg_path() or tr("未找到", "Not found"))
                    toast.show_success(self, tr("FFmpeg 下载完成", "FFmpeg downloaded"))
                else:
                    toast.show_error(self, tr("FFmpeg 下载失败，请检查网络", "FFmpeg download failed, check network"))
            QTimer.singleShot(0, _update)
        self.services.ffmpeg_mgr.download_async(callback=_done)

    # ── 快捷键 ────────────────────────────────────
    def _build_shortcuts(self):
        """「快捷键」分组：每个动作一行，右侧按钮录制组合键。"""
        self._add_section("shortcuts", tr("快捷键", "Shortcuts"), FluentIcon.COMMAND_PROMPT)
        from gui_qt.shortcuts import SHORTCUT_ACTIONS
        g = self._group(tr("快捷键", "Keyboard shortcuts"))
        saved = dict(self.services.get_pref("shortcuts", {}))
        self._shortcut_buttons = {}
        for key, meta in SHORTCUT_ACTIONS.items():
            card = SettingCard(meta["icon"], meta["title"], meta["desc"],
                               parent=g)
            btn = _ShortcutButton()
            btn.set_shortcut(saved.get(key, meta["default"]))
            btn._action_key = key
            btn.changed.connect(self._on_shortcut_changed)
            card.hBoxLayout.addWidget(btn, 0, Qt.AlignRight)
            g.addSettingCard(card)
            self._shortcut_buttons[key] = btn

        # 重置默认
        reset = SettingCard(FluentIcon.SYNC,
                            tr("恢复默认快捷键", "Reset shortcuts"),
                            tr("将所有快捷键恢复为默认值",
                               "Restore all shortcuts to defaults"),
                            parent=g)
        btn_reset = PushButton(tr("恢复默认", "Reset"))
        btn_reset.clicked.connect(self._reset_shortcuts)
        reset.hBoxLayout.addWidget(btn_reset, 0, Qt.AlignRight)
        g.addSettingCard(reset)

    def _collect_shortcuts(self):
        return {key: (btn._qs or "") for key, btn
                in self._shortcut_buttons.items()}

    def _on_shortcut_changed(self):
        self.services.set_pref("shortcuts", self._collect_shortcuts())
        apply = getattr(self.main_window, "_apply_shortcuts", None)
        if callable(apply):
            apply()

    def _reset_shortcuts(self):
        from gui_qt.shortcuts import SHORTCUT_ACTIONS
        for key, meta in SHORTCUT_ACTIONS.items():
            self._shortcut_buttons[key].set_shortcut(meta["default"])
        self._on_shortcut_changed()

    # ── 数据备份 ────────────────────────────────────
    def _build_backup(self):
        """「数据备份」分组：导出/导入用户数据（偏好/历史/预设）。"""
        self._add_section("backup", tr("数据备份", "Backup"), FluentIcon.SAVE)
        from gui_qt.components import toast
        from utils.backup import export_backup, import_backup

        g = self._group(tr("数据备份", "Backup"))
        self._backup_g = g

        export = PushSettingCard(
            tr("选择位置保存备份文件", "Choose where to save the backup"),
            FluentIcon.SAVE, tr("导出数据备份", "Export backup"),
            tr("打包偏好设置、转换历史、M3U8 记录等用户数据为 zip",
               "Package preferences, history, M3U8 records into a zip"),
            parent=g)
        export.clicked.connect(self._export_backup)
        g.addSettingCard(export)

        imp = PushSettingCard(
            tr("从备份 zip 恢复数据（覆盖当前）", "Restore from backup zip (overwrites)"),
            FluentIcon.DOWNLOAD, tr("导入数据备份", "Import backup"),
            tr("恢复后将覆盖现有偏好与历史记录，请谨慎操作",
               "Restoring overwrites current preferences and history"),
            parent=g)
        imp.clicked.connect(self._import_backup)
        g.addSettingCard(imp)

    def _export_backup(self):
        from gui_qt.components import toast
        from utils.backup import export_backup
        import datetime
        default = os.path.join(
            os.path.expanduser("~"), "Desktop",
            f"FormatMaster_backup_{datetime.date.today():%Y%m%d}.zip")
        path, _ = QFileDialog.getSaveFileName(
            self, tr("导出备份", "Export backup"), default, "备份 (*.zip)")
        if not path:
            return
        try:
            n = export_backup(path)
            toast.show_success(
                self, tr("已导出 {} 个数据文件", "Exported {} data files").format(n))
        except Exception as e:  # noqa: BLE001
            toast.show_error(self, tr("导出失败：{}", "Export failed: {}").format(e))

    def _import_backup(self):
        from gui_qt.components import toast
        from utils.backup import import_backup
        path, _ = QFileDialog.getOpenFileName(
            self, tr("导入备份", "Import backup"), "", "备份 (*.zip)")
        if not path:
            return
        try:
            n = import_backup(path)
            toast.show_success(
                self, tr("已恢复 {} 个数据文件（重启后完全生效）",
                         "Restored {} files (fully effective after restart)").format(n))
        except Exception as e:  # noqa: BLE001
            toast.show_error(self, tr("导入失败：{}", "Import failed: {}").format(e))

    # ── 日志 ────────────────────────────────────
    def _build_log(self):
        """「日志」分区：查看 debug.log 内容，支持刷新/清空/打开文件。"""
        self._add_section("log", tr("日志", "Log"), FluentIcon.DOCUMENT)
        from qfluentwidgets import BodyLabel, CaptionLabel
        from PySide6.QtWidgets import QPlainTextEdit

        g = self._group(tr("运行日志", "Run log"))

        # 日志路径卡片
        from app.logger import get_log_path
        log_path = get_log_path()
        card_path = SettingCard(
            FluentIcon.FOLDER, tr("日志文件", "Log file"),
            log_path, g)
        btn_open = PushButton(tr("打开文件", "Open file"))
        btn_open.clicked.connect(lambda: self._open_log_file(log_path))
        card_path.hBoxLayout.addWidget(btn_open, 0, Qt.AlignRight)
        card_path.hBoxLayout.addSpacing(16)
        g.addSettingCard(card_path)

        # 日志内容区
        log_container = QWidget()
        log_lay = QVBoxLayout(log_container)
        log_lay.setContentsMargins(0, 0, 0, 0)
        log_lay.setSpacing(8)

        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(300)
        self.log_view.setMaximumBlockCount(2000)
        self.log_view.setPlaceholderText(
            tr("日志内容将在此显示…", "Log content will appear here…"))
        self.log_view.setStyleSheet(
            "QPlainTextEdit#logView{font-family:Cascadia Code,Consolas,"
            "Source Han Sans SC;font-size:12px;}")
        # 背景/文字/边框交给全局 QSS 的 #logView 规则（令牌驱动，主题切换自动刷新，
        # 避免实例快照残留浅色背景）
        log_lay.addWidget(self.log_view)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_refresh = PushButton(tr("刷新", "Refresh"))
        btn_refresh.setIcon(FluentIcon.SYNC)
        btn_refresh.clicked.connect(lambda: self._refresh_log(log_path))
        btn_clear = PushButton(tr("清空日志", "Clear log"))
        btn_clear.setIcon(FluentIcon.DELETE)
        btn_clear.clicked.connect(lambda: self._clear_log(log_path))
        btn_row.addWidget(btn_refresh)
        btn_row.addWidget(btn_clear)
        btn_row.addStretch(1)
        log_lay.addLayout(btn_row)

        self._active_layout.addWidget(log_container)

        # 初始加载
        self._refresh_log(log_path)

    def _refresh_log(self, log_path):
        """读取日志文件内容并显示。"""
        try:
            if os.path.isfile(log_path):
                with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                self.log_view.setPlainText(content)
                # 滚动到底部
                sb = self.log_view.verticalScrollBar()
                sb.setValue(sb.maximum())
            else:
                self.log_view.setPlainText(
                    tr("日志文件不存在", "Log file not found"))
        except Exception as e:  # noqa: BLE001
            self.log_view.setPlainText(
                tr("读取日志失败：{}", "Failed to read log: {}").format(e))

    def _clear_log(self, log_path):
        """清空日志文件。"""
        from gui_qt.components import toast
        try:
            if os.path.isfile(log_path):
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write("")
            self.log_view.clear()
            toast.show_success(self, tr("日志已清空", "Log cleared"))
        except Exception as e:  # noqa: BLE001
            toast.show_error(self, tr("清空失败：{}", "Clear failed: {}").format(e))

    def _open_log_file(self, log_path):
        """用系统默认程序打开日志文件。"""
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        if os.path.isfile(log_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(log_path))

    # ── 赞助 ────────────────────────────────────
    def _build_sponsor(self):
        """「赞助」分区：居中标题 + 两张白底圆角收款码卡片 + 感谢语。"""
        self._add_section("sponsor", tr("赞助", "Sponsor"), FluentIcon.HEART)
        from PySide6.QtGui import QFont
        from qfluentwidgets import BodyLabel, CaptionLabel

        def _set_font(widget, size, weight=QFont.Weight.Normal):
            f = QFont(widget.font())
            f.setPointSize(size)
            f.setWeight(weight)
            widget.setFont(f)

        container = QWidget()
        container_lay = QVBoxLayout(container)
        container_lay.setContentsMargins(0, 32, 0, 32)
        container_lay.setSpacing(8)
        container_lay.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        # 标题
        sec = BodyLabel(tr("支持开发者", "Support Developer"))
        _set_font(sec, 16, QFont.Weight.Bold)
        sec.setStyleSheet(f"")
        sec.setAlignment(Qt.AlignCenter)
        container_lay.addWidget(sec, 0, Qt.AlignHCenter)

        # 副标题
        sub = CaptionLabel(
            tr("如果格式大师对您有帮助，欢迎请作者喝杯咖啡 ☕",
               "If FormatMaster helps you, feel free to buy the dev a coffee ☕"),
            container)
        _set_font(sub, 10)
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(f"")
        container_lay.addWidget(sub, 0, Qt.AlignHCenter)
        container_lay.addSpacing(24)

        # 收款码卡片行
        qr_row_widget = QWidget()
        qr_row = QHBoxLayout(qr_row_widget)
        qr_row.setContentsMargins(0, 0, 0, 0)
        qr_row.setSpacing(24)
        qr_row.setAlignment(Qt.AlignCenter)
        img_loaded = False
        for name, label in (("support_wechat.png", tr("微信", "WeChat")),
                            ("support_alipay.png", tr("支付宝", "Alipay"))):
            qr_path = get_resource_path(os.path.join("assets", name))
            if qr_path and os.path.isfile(qr_path):
                qr_row.addWidget(self._make_qr_card(qr_path, label))
                img_loaded = True
        if not img_loaded:
            tip = CaptionLabel(
                tr("（将收款码保存为 assets/support_wechat.png / "
                   "support_alipay.png 即可显示）",
                   "(Save QR codes as assets/support_wechat.png / "
                   "support_alipay.png to display)"), container)
            tip.setWordWrap(True)
            _set_font(tip, 9)
            tip.setStyleSheet(f"")
            qr_row.addWidget(tip)
        container_lay.addWidget(qr_row_widget, 0, Qt.AlignHCenter)
        container_lay.addSpacing(20)

        # 感谢语
        thanks = CaptionLabel(
            tr("感谢您的支持！", "Thank you for your support!"), container)
        _set_font(thanks, 10)
        thanks.setAlignment(Qt.AlignCenter)
        thanks.setStyleSheet(f"")
        container_lay.addWidget(thanks, 0, Qt.AlignHCenter)

        self._active_layout.addWidget(container)

    def _make_qr_card(self, img_path, label_text):
        """单张收款码卡片：固定白底圆角 + 阴影 + QR 图 + 标注文字。"""
        from PySide6.QtGui import QFont
        from qfluentwidgets import CaptionLabel, ImageLabel

        card = QWidget()
        card.setObjectName("qrCard")
        # QR 码需要浅色背景以保证可扫描，固定使用白色；
        # 用 #qrCard 限定只作用于卡片本身，避免子控件（图片、文字）也被加上边框。
        card.setStyleSheet(
            "#qrCard{background:#FFFFFF;border:1px solid #E3E5EC;border-radius:16px;}")
        ds.apply_subtle_shadow(card)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(18, 18, 18, 16)
        cl.setSpacing(12)
        cl.setAlignment(Qt.AlignCenter)

        img = ImageLabel(img_path)
        img.setFixedSize(200, 200)
        img.setBorderRadius(8, 8, 8, 8)
        cl.addWidget(img, 0, Qt.AlignCenter)

        lbl = CaptionLabel(label_text)
        lbl.setAlignment(Qt.AlignCenter)
        f = QFont(lbl.font())
        f.setPointSize(11)
        f.setWeight(QFont.Weight.Medium)
        lbl.setFont(f)
        # 白底卡片上始终使用深色文字
        lbl.setStyleSheet("color: #1D1F2E;")
        cl.addWidget(lbl)

        return card

    # ── 关于 装饰组件 ────────────────────────────
    def _colored_icon(self, fluent_icon, color_hex, size=16):
        """返回已上色的 QWidget：FluentIcon → QImage 像素遍历重染指定色。

        用于把 FluentIcon 默认灰色图标统一改成用户指定颜色（与设计系统
        accent / 调色板保持一致）。size 为图标占位边长（图标本身渲染为
        size-2px，留 1px 边距）。fallback：失败时绘制实色圆角方块。

        着色结果在构造时缓存为 QPixmap，避免每次 paintEvent 重复逐像素计算。
        """
        from PySide6.QtGui import (QColor, QImage, QPainter, QPixmap)
        from PySide6.QtWidgets import QWidget

        # 构造时预渲染着色 pixmap
        inner = max(8, size - 4)
        _cached_pm = QPixmap(inner, inner)
        _cached_pm.fill(Qt.transparent)
        try:
            pm = fluent_icon.icon().pixmap(inner, inner)
            img = pm.toImage().convertToFormat(QImage.Format_ARGB32)
            color = QColor(color_hex)
            for y in range(img.height()):
                for x in range(img.width()):
                    px = img.pixel(x, y)
                    a = (px >> 24) & 0xFF
                    if a > 30:
                        img.setPixelColor(x, y, QColor(
                            color.red(), color.green(), color.blue(), a))
            _cached_pm = QPixmap.fromImage(img)
        except Exception:  # noqa: BLE001
            _cached_pm.fill(QColor(color_hex))

        class _ColoredIcon(QWidget):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setFixedSize(size, size)

            def paintEvent(self, _e):
                p = QPainter(self)
                p.setRenderHints(QPainter.Antialiasing
                                 | QPainter.SmoothPixmapTransform)
                ox = (size - inner) // 2
                p.drawPixmap(ox, ox, _cached_pm)
                p.end()

        return _ColoredIcon(self)

    def _fm_logo_pixmap(self, side=80):
        """加载 FM 徽标图片（assets/1.png），缩放到指定尺寸。"""
        from PySide6.QtGui import QPixmap
        from PySide6.QtCore import Qt
        img_path = get_resource_path(os.path.join("assets", "1.png"))
        pm = QPixmap(img_path)
        if pm.isNull():
            pm = QPixmap(side, side)
            pm.fill(Qt.transparent)
        dpr = self.devicePixelRatioF() or 1.0
        px = max(1, int(side * dpr))
        pm = pm.scaled(px, px, Qt.KeepAspectRatioByExpanding,
                       Qt.SmoothTransformation)
        pm.setDevicePixelRatio(dpr)
        return pm

    def _hero_3d_widget(self):
        """Hero 右侧 3D 装饰插图（自绘，透明背景，避免依赖外部资源）。"""
        from PySide6.QtGui import (QColor, QFont, QPainter, QPainterPath,
                                    QPen, QLinearGradient)
        from PySide6.QtCore import QRectF, QPointF

        # 简单「浮动图标」装饰——4 个彩色圆角方块（视频/音频/图片/文档），
        # #FFFFFF 描边轻微阴影。整体覆盖在很淡的蓝色径向背景上。
        class _Hero3D(QWidget):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setFixedSize(280, 140)

            def paintEvent(self, _e):
                p = QPainter(self)
                p.setRenderHints(QPainter.Antialiasing
                                 | QPainter.SmoothPixmapTransform)

                # 淡蓝色背板（柔和，不抢主视觉）
                bg = QPainterPath()
                bg.addRoundedRect(QRectF(0, 0, 280, 140), 14, 14)
                grad = QLinearGradient(0, 0, 280, 140)
                grad.setColorAt(0.0, QColor("#EEF4FF"))
                grad.setColorAt(1.0, QColor("#F8FAFF"))
                p.fillPath(bg, grad)
                p.setPen(QPen(QColor("#D9E2F5"), 1))
                p.drawPath(bg)

                # 4 个浮动色块（圆角 14，颜色 + emoji 符号）
                chips = [
                    (28, 30,  "#5B5BD6", "🎬"),
                    (84, 60,  "#0FA47A", "🎵"),
                    (148, 22, "#F0A63A", "🖼"),
                    (200, 70, "#EC4899", "📄"),
                ]
                f = QFont(FONT_BODY)
                f.setPointSize(18)
                p.setFont(f)
                for x, y, col, sym in chips:
                    r = QRectF(x, y, 56, 56)
                    cp = QPainterPath()
                    cp.addRoundedRect(r, 14, 14)
                    # 阴影
                    sh = QRectF(r.x() + 2, r.y() + 3, r.width(), r.height())
                    shp = QPainterPath()
                    shp.addRoundedRect(sh, 14, 14)
                    p.fillPath(shp, QColor(0, 0, 0, 18))
                    # 主块
                    p.fillPath(cp, QColor(col))
                    p.setPen(QPen(QColor("#FFFFFF"), 1.4))
                    p.drawPath(cp)
                    # emoji 文字
                    p.setPen(QColor("#FFFFFF"))
                    p.drawText(r, Qt.AlignCenter, sym)
                p.end()

        return _Hero3D(self)

    def _shield_widget(self, size=44):
        """盾牌小图标（自绘 Fluent 蓝盾 + 对勾），用于 footer。"""
        from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
        from PySide6.QtCore import QRectF

        class _Shield(QWidget):
            def __init__(self, parent=None, side=size):
                super().__init__(parent)
                self.setFixedSize(side, side)

            def paintEvent(self, _e):
                p = QPainter(self)
                p.setRenderHints(QPainter.Antialiasing)
                s = float(self.width())
                # 盾形路径
                path = QPainterPath()
                path.moveTo(s * 0.5, s * 0.08)
                path.cubicTo(s * 0.85, s * 0.08, s * 0.92, s * 0.18,
                              s * 0.92, s * 0.32)
                path.cubicTo(s * 0.92, s * 0.60, s * 0.80, s * 0.78,
                              s * 0.50, s * 0.92)
                path.cubicTo(s * 0.20, s * 0.78, s * 0.08, s * 0.60,
                              s * 0.08, s * 0.32)
                path.cubicTo(s * 0.08, s * 0.18, s * 0.15, s * 0.08,
                              s * 0.50, s * 0.08)
                p.fillPath(path, QColor("#3B7EF6"))
                # 对勾
                pen = QPen(QColor("#FFFFFF"), max(2.0, s * 0.10),
                           Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
                p.setPen(pen)
                p.drawLine(s * 0.30, s * 0.52,
                           s * 0.45, s * 0.65)
                p.drawLine(s * 0.45, s * 0.65,
                           s * 0.72, s * 0.38)
                p.end()

        return _Shield(self)

    # ── 关于 ────────────────────────────────────
    def _build_about(self):
        """「关于」分区：完整三段式（Hero + 双栏 + 底部 GitHub 按钮）。"""
        self._add_section("about", tr("关于", "About"), FluentIcon.INFO)
        from qfluentwidgets import (BodyLabel, CaptionLabel, PrimaryPushButton,
                                    HyperlinkButton)
        from PySide6.QtGui import QFont, QPainter, QPainterPath, QColor, QPen
        from PySide6.QtCore import QPointF, QRectF
        from gui_qt.update_checker import RELEASES_URL

        outer = QWidget()
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(14)
        self._active_layout.addWidget(outer)

        # ════════════════════════════════════════════════════
        # ① Hero 卡片：FM 徽标 + 文案 + 3D 装饰 + 4 功能小卡
        # ════════════════════════════════════════════════════
        hero = Card()
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(22, 18, 22, 18)
        hl.setSpacing(14)
        outer_lay.addWidget(hero)

        # 上半：徽标 + 文案 | 3D 装饰
        top_row = QHBoxLayout()
        top_row.setSpacing(16)

        # 左：FM 徽标
        from PySide6.QtWidgets import QLabel as _QL
        from PySide6.QtGui import QPixmap
        logo_lbl = _QL()
        logo_lbl.setPixmap(self._fm_logo_pixmap(120))
        logo_lbl.setFixedSize(120, 120)
        top_row.addWidget(logo_lbl, 0, Qt.AlignVCenter)

        # 中：标题 / 徽章 / 副标题 / 描述
        mid = QVBoxLayout()
        mid.setSpacing(2)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title = BodyLabel(tr("格式大师 FormatMaster", "FormatMaster"))
        f1 = QFont(title.font())
        f1.setPointSize(18)
        f1.setBold(True)
        title.setFont(f1)
        title.setStyleSheet(f"")
        title_row.addWidget(title)
        # 版本徽章
        from PySide6.QtWidgets import QLabel as _QL2
        badge = _QL2(tr("版本 {}", "Version {}").format(APP_VERSION))
        badge.setStyleSheet(
            "background:#EAF1FF;color:#3B7EF6;border:1px solid #C7DBFB;"
            "border-radius:10px;padding:2px 10px;font-size:11px;"
            "font-weight:600;")
        badge.setAlignment(Qt.AlignCenter)
        title_row.addWidget(badge, 0, Qt.AlignVCenter)
        mid.addLayout(title_row)

        mid.addSpacing(2)
        subtitle = BodyLabel(
            tr("Windows 桌面全能格式转换工具",
               "All-in-one desktop format converter for Windows"))
        f2 = QFont(subtitle.font())
        f2.setPointSize(12)
        f2.setWeight(QFont.Weight.Medium)
        subtitle.setFont(f2)
        subtitle.setStyleSheet(f"")
        mid.addWidget(subtitle)
        desc = CaptionLabel(
            tr("视频、音频、图片、文档转换，PDF 处理，下载与 OCR 识别",
               "Video / Audio / Image / Document conversion, PDF tools, downloads and OCR"))
        desc.setStyleSheet(f"font-size:12px;;")
        mid.addWidget(desc)

        top_row.addLayout(mid, 1)
        # 右：3D 装饰
        top_row.addWidget(self._hero_3d_widget(), 0, Qt.AlignVCenter)
        hl.addLayout(top_row)

        # 分隔线
        div1 = QFrame()
        div1.setFrameShape(QFrame.HLine)
        div1.setFixedHeight(1)
        div1.setStyleSheet(
            f"QFrame{{background:{ds.border_color()};border:none;}}")
        hl.addWidget(div1)

        # 下半：4 功能小卡
        feats = QHBoxLayout()
        feats.setSpacing(10)
        feats.setAlignment(Qt.AlignTop)
        feat_defs = [
            (FluentIcon.GAME,    "#5B5BD6", "#EDEEFF",
             tr("40+ 实用功能", "40+ features"),
             tr("一站式解决所有格式问题",
                "All format problems solved in one place")),
            (FluentIcon.CERTIFICATE, "#0FA47A", "#DDF5EC",
             tr("本地安全处理", "Local & safe"),
             tr("文件在本机处理，不依赖云端",
                "Files processed locally, no cloud dependency")),
            (FluentIcon.SPEED_HIGH, "#8B5CF6", "#F3E8FF",
             tr("高效引擎", "Fast engine"),
             tr("基于 FFmpeg 等工具链",
                "Powered by FFmpeg and friends")),
            (FluentIcon.HEART,   "#F0A63A", "#FEF1DE",
             tr("永久免费", "Free forever"),
             tr("开源软件，持续更新",
                "Open source, always evolving")),
        ]
        for icon, fg, bg, t1, t2 in feat_defs:
            feats.addWidget(self._make_about_feature(icon, fg, bg, t1, t2))
        hl.addLayout(feats)

        # ════════════════════════════════════════════════════
        # ② 双栏：关于 FormatMaster | (更新与支持 + 项目生态 + 隐私与安全) 堆叠
        # ════════════════════════════════════════════════════
        two_col = QHBoxLayout()
        two_col.setSpacing(14)
        two_col.addWidget(self._build_about_left_card(), 1)

        # 右侧：3 张卡竖向堆叠（更新与支持 / 项目生态 / 隐私与安全）
        right_col = QVBoxLayout()
        right_col.setSpacing(14)
        right_col.addWidget(self._build_about_right_card())
        right_col.addWidget(self._build_about_ecosystem_card())
        right_col.addWidget(self._build_about_privacy_card())
        right_w = QWidget()
        right_w.setLayout(right_col)
        two_col.addWidget(right_w, 1)

        outer_lay.addLayout(two_col)

        # ════════════════════════════════════════════════════
        # ③ 底部页脚：品牌语 + 单独 GitHub 按钮
        # ════════════════════════════════════════════════════
        outer_lay.addWidget(self._build_about_footer())

    def _make_about_feature(self, icon, fg, bg, title, desc):
        """Hero 内的单个功能小卡（图标 + 标题 + 描述）。"""
        from qfluentwidgets import BodyLabel, CaptionLabel, IconWidget
        from PySide6.QtGui import QColor, QFont, QPainter, QImage, QPixmap
        w = QWidget()
        w.setStyleSheet(
            f"QWidget{{background:{bg};border-radius:10px;}}")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(10)
        lay.setAlignment(Qt.AlignVCenter)

        # 图标方块（自绘，用 FluentIcon 渲染再按主题色重新着色）
        icon_box = QWidget()
        icon_box.setFixedSize(32, 32)
        icon_box.setStyleSheet(
            "QWidget{background:#FFFFFF;border-radius:8px;"
            "border:1px solid rgba(0,0,0,0.04);}")

        # 构造时预渲染着色 pixmap，避免每次 paintEvent 逐像素计算
        _cached_pm = QPixmap(20, 20)
        _cached_pm.fill(Qt.transparent)
        try:
            pm = icon.icon().pixmap(20, 20)
            img = pm.toImage().convertToFormat(QImage.Format_ARGB32)
            color = QColor(fg)
            for y in range(img.height()):
                for x in range(img.width()):
                    px = img.pixel(x, y)
                    a = (px >> 24) & 0xFF
                    if a > 30:
                        img.setPixelColor(x, y, QColor(
                            color.red(), color.green(), color.blue(), a))
            _cached_pm = QPixmap.fromImage(img)
        except Exception:  # noqa: BLE001
            _cached_pm.fill(QColor(fg))

        class _IconPainter(QWidget):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setFixedSize(32, 32)

            def paintEvent(self, _e):
                p = QPainter(self)
                p.setRenderHints(QPainter.Antialiasing
                                 | QPainter.SmoothPixmapTransform)
                p.drawPixmap(6, 6, _cached_pm)
                p.end()

        icon_box_layout = QHBoxLayout(icon_box)
        icon_box_layout.setContentsMargins(0, 0, 0, 0)
        ip = _IconPainter(icon_box)
        icon_box_layout.addWidget(ip)

        txts = QVBoxLayout()
        txts.setSpacing(1)
        tl = BodyLabel(title)
        f = QFont(tl.font())
        f.setPointSize(12)
        f.setBold(True)
        tl.setFont(f)
        tl.setStyleSheet(f"")
        txts.addWidget(tl)
        dl = CaptionLabel(desc)
        dl.setStyleSheet(f"font-size:11px;;")
        txts.addWidget(dl)
        lay.addWidget(icon_box)
        lay.addLayout(txts, 1)
        return w

    def _build_about_left_card(self):
        """「关于 FormatMaster」卡片：描述 + 6 项信息网格 + 底部推荐条。"""
        from qfluentwidgets import (BodyLabel, CaptionLabel)
        from PySide6.QtWidgets import QGridLayout
        from PySide6.QtGui import QFont, QDesktopServices
        from PySide6.QtCore import QUrl
        card = Card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(18, 14, 18, 14)
        cl.setSpacing(10)
        title = BodyLabel(tr("关于 FormatMaster", "About FormatMaster"))
        f = QFont(title.font())
        f.setBold(True)
        f.setPointSize(13)
        title.setFont(f)
        title.setStyleSheet(f"")
        cl.addWidget(title)

        intro = CaptionLabel(
            tr("FormatMaster 是一款轻量、强大、易用且完全免费的本地格式转换工具。\n"
               "我们致力于为用户提供高质量的转换体验，同时保护您的隐私与数据安全。\n"
               "所有文件处理均在本地完成，不上传任何文件。\n"
               "感谢每一位用户的支持与反馈，让 FormatMaster 变得更好！",
               "FormatMaster is a lightweight, powerful, easy-to-use and fully free "
               "local format converter.\n"
               "We strive to deliver high-quality conversions while protecting your "
               "privacy and data.\n"
               "All files are processed locally — nothing is uploaded.\n"
               "Thanks to every user whose feedback makes FormatMaster better!"))
        intro.setWordWrap(True)
        intro.setStyleSheet(f"font-size:12px;;line-height:1.55;")
        cl.addWidget(intro)

        # 6 项信息网格（开发方式/个人开发 + 联系作者/gujh0312@outlook.com）
        # 全部图标统一蓝色 accent（视觉一致）
        grid = QGridLayout()
        grid.setSpacing(14)
        grid.setContentsMargins(0, 4, 0, 0)
        contact_email = "gujh0312@outlook.com"
        info_color = ds.accent()
        items = [
            (FluentIcon.INFO, tr("当前版本", "Version"), APP_VERSION),
            (FluentIcon.CALENDAR, tr("发布日期", "Released"), "2026-08-21"),
            (FluentIcon.PEOPLE, tr("开发方式", "Development"),
             tr("个人开发", "Solo developer")),
            (FluentIcon.GITHUB, tr("项目仓库", "Repository"), "GitHub"),
            (FluentIcon.CERTIFICATE, tr("许可证", "License"), "GPL-3.0 License"),
            (FluentIcon.MAIL, tr("联系作者", "Contact"),
             contact_email),
        ]
        # 重新布局 3 列 × 2 行
        cols = 3
        for i, (icon, label, value) in enumerate(items):
            r, c = divmod(i, cols)
            cell = QWidget()
            cell_lay = QHBoxLayout(cell)
            cell_lay.setContentsMargins(0, 0, 0, 0)
            cell_lay.setSpacing(6)
            cell_lay.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            iw = self._colored_icon(icon, info_color, 18)
            cell_lay.addWidget(iw, 0, Qt.AlignVCenter)
            vbox = QVBoxLayout()
            vbox.setSpacing(0)
            ll = CaptionLabel(label)
            ll.setStyleSheet(f"font-size:11px;;")
            vl = BodyLabel(value)
            fv = QFont(vl.font())
            fv.setPointSize(12)
            fv.setWeight(QFont.Weight.Medium)
            vl.setFont(fv)
            # 联系作者项整行可点击 → 唤起邮件客户端（去掉下划线）
            if label in (tr("联系作者", "Contact"),):
                vl.setStyleSheet(f"")
                vl.setCursor(Qt.PointingHandCursor)
                vl.mousePressEvent = lambda e, em=contact_email: (
                    QDesktopServices.openUrl(QUrl(f"mailto:{em}")))
            else:
                vl.setStyleSheet(f"")
            vbox.addWidget(ll)
            vbox.addWidget(vl)
            cell_lay.addLayout(vbox)
            grid.addWidget(cell, r, c)
        cl.addLayout(grid)

        # 底部推荐条（淡紫底 + 蓝字 + 🙏）
        # 背景交给全局 QSS 的 QWidget#aboutCallout 规则（令牌驱动，主题切换自动刷新）
        callout = QWidget()
        callout.setObjectName("aboutCallout")
        callout_lay = QVBoxLayout(callout)
        callout_lay.setContentsMargins(14, 10, 14, 10)
        callout_lay.setSpacing(2)
        from PySide6.QtWidgets import QLabel as _QL_cb
        cb_row = QHBoxLayout()
        cb_row.setSpacing(6)
        cb_row.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        cb_star = _QL_cb("⭐")
        cb_star.setStyleSheet("font-size:12px;")
        cb_row.addWidget(cb_star, 0, Qt.AlignVCenter)
        cb_text = _QL_cb(
            tr("如果 FormatMaster 对你帮助，不妨推荐给身边的朋友",
               "If FormatMaster helps you, share it with your friends"))
        cb_text.setStyleSheet(
            f"font-size:12px;color:{ds.accent()};font-weight:600;")
        cb_row.addWidget(cb_text)
        cb_row.addStretch(1)
        callout_lay.addLayout(cb_row)
        cb_sub_row = QHBoxLayout()
        cb_sub_row.setSpacing(4)
        cb_sub_row.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        cb_sub = _QL_cb(
            tr("你的支持是我持续更新的最大动力",
               "Your support is my motivation to keep updating"))
        cb_sub.setStyleSheet(f"font-size:11px;;")
        cb_emoji = _QL_cb("🙏")
        cb_emoji.setStyleSheet("font-size:11px;")
        cb_sub_row.addWidget(cb_sub)
        cb_sub_row.addWidget(cb_emoji)
        cb_sub_row.addStretch(1)
        callout_lay.addLayout(cb_sub_row)
        cl.addWidget(callout)
        return card

    def _build_about_right_card(self):
        """「更新与支持」卡片：检查更新 + Releases。"""
        from qfluentwidgets import (BodyLabel, CaptionLabel,
                                    PrimaryPushButton)
        from PySide6.QtGui import QFont
        from gui_qt.update_checker import RELEASES_URL

        card = Card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(18, 14, 18, 14)
        cl.setSpacing(12)

        title = BodyLabel(tr("更新与支持", "Updates & Support"))
        f = QFont(title.font())
        f.setBold(True)
        f.setPointSize(13)
        title.setFont(f)
        title.setStyleSheet(f"")
        cl.addWidget(title)

        # ── 检查更新 ──
        check_row = QHBoxLayout()
        check_row.setSpacing(12)
        check_row.setAlignment(Qt.AlignVCenter)

        # 左：图标 + 标题/状态
        left_box = QHBoxLayout()
        left_box.setSpacing(10)
        left_box.setAlignment(Qt.AlignVCenter)
        iw = self._colored_icon(FluentIcon.SYNC, ds.accent(), 28)
        left_box.addWidget(iw, 0, Qt.AlignVCenter)
        v = QVBoxLayout()
        v.setSpacing(0)
        check_label = BodyLabel(tr("检查更新", "Check for updates"))
        f1 = QFont(check_label.font())
        f1.setPointSize(13)
        f1.setWeight(QFont.Weight.Medium)
        check_label.setFont(f1)
        check_label.setStyleSheet(f"")
        v.addWidget(check_label)
        self._check_status = CaptionLabel(
            tr("当前已是最新版本 {}", "Up to date, v{}").format(APP_VERSION))
        self._check_status.setStyleSheet(f"font-size:11px;;")
        v.addWidget(self._check_status)
        left_box.addLayout(v)
        check_row.addLayout(left_box, 1)

        # 右：检查按钮
        self.btn_check = PrimaryPushButton(
            FluentIcon.SYNC, tr("检查更新", "Check for updates"))
        self.btn_check.setMinimumWidth(110)
        self.btn_check.clicked.connect(self._on_check_update)
        check_row.addWidget(self.btn_check, 0, Qt.AlignVCenter)
        cl.addLayout(check_row)

        # 卡片内分隔线
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setFixedHeight(1)
        div.setStyleSheet(
            f"QFrame{{background:{ds.border_color()};border:none;}}")
        cl.addWidget(div)

        # ── 前往 GitHub Releases（整行可点击） ──
        gh_clickable = QWidget()
        gh_clickable.setCursor(Qt.PointingHandCursor)
        gh_clickable.setStyleSheet("QWidget{background:transparent;}")
        gh_clickable.mousePressEvent = lambda e: self._open_releases(RELEASES_URL)
        gh_row = QHBoxLayout(gh_clickable)
        gh_row.setContentsMargins(0, 0, 0, 0)
        gh_row.setSpacing(10)
        gh_row.setAlignment(Qt.AlignVCenter)
        iw2 = self._colored_icon(FluentIcon.LINK, ds.accent(), 28)
        gh_row.addWidget(iw2, 0, Qt.AlignVCenter)
        v2 = QVBoxLayout()
        v2.setSpacing(0)
        gh_label = BodyLabel(tr("前往 GitHub Releases", "Open GitHub Releases"))
        f2 = QFont(gh_label.font())
        f2.setPointSize(13)
        f2.setWeight(QFont.Weight.Medium)
        gh_label.setFont(f2)
        gh_label.setStyleSheet(f"")
        v2.addWidget(gh_label)
        gh_desc = CaptionLabel(
            tr("查看历史版本与更新日志",
               "View history and changelog"))
        gh_desc.setStyleSheet(f"font-size:11px;;")
        v2.addWidget(gh_desc)
        gh_row.addLayout(v2, 1)
        # 右箭头
        from PySide6.QtWidgets import QLabel as _QL3
        arrow = _QL3("›")
        af = QFont(arrow.font())
        af.setPointSize(20)
        af.setBold(True)
        arrow.setFont(af)
        arrow.setStyleSheet(f"")
        gh_row.addWidget(arrow, 0, Qt.AlignVCenter)
        cl.addWidget(gh_clickable)
        return card

    def _build_about_ecosystem_card(self):
        """「项目生态」卡片：基于开源项目构建 + 技术 chips。"""
        from qfluentwidgets import BodyLabel, CaptionLabel
        from PySide6.QtGui import QFont
        from PySide6.QtWidgets import QLabel as _QL_chip

        card = Card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(18, 14, 18, 14)
        cl.setSpacing(8)

        title = BodyLabel(tr("项目生态", "Ecosystem"))
        f = QFont(title.font())
        f.setBold(True)
        f.setPointSize(13)
        title.setFont(f)
        title.setStyleSheet(f"")
        cl.addWidget(title)

        desc = CaptionLabel(
            tr("FormatMaster 基于以下优秀的开源项目构建",
               "FormatMaster is built on these excellent open-source projects"))
        desc.setStyleSheet(f"font-size:12px;;")
        desc.setWordWrap(True)
        cl.addWidget(desc)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        chips.setAlignment(Qt.AlignLeft)
        # chip 浅/深主题颜色不同：背景 card_hover / 文字 ink_sec / 边框 border
        # （不直接用 ds.tokens() 拍快照，bind_theme 让主题切换时重渲染）
        from gui_qt.components import design_system as ds

        def _chip_qss():
            t = ds.tokens()
            return (
                f"background:{t['card_hover']};color:{t['ink_sec']};"
                f"border:1px solid {t['border']};"
                "border-radius:10px;padding:3px 10px;font-size:11px;"
                "font-weight:600;"
            )
        for nm in ["FFmpeg", "yt-dlp", "RapidOCR", "PySide6", "qfluentwidgets"]:
            cw = _QL_chip(nm)
            cw.setStyleSheet(_chip_qss())
            ds.bind_theme(cw, _chip_qss)
            chips.addWidget(cw)
        chips.addStretch(1)
        cl.addLayout(chips)
        return card

    def _build_about_privacy_card(self):
        """「隐私与安全」卡片：3 项横排小卡（本地处理/数据安全/独立运行）。"""
        from qfluentwidgets import BodyLabel, CaptionLabel
        from PySide6.QtGui import QFont

        card = Card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(18, 14, 18, 14)
        cl.setSpacing(10)

        title = BodyLabel(tr("隐私与安全", "Privacy & Security"))
        f = QFont(title.font())
        f.setBold(True)
        f.setPointSize(13)
        title.setFont(f)
        title.setStyleSheet(f"")
        cl.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(14)
        row.setAlignment(Qt.AlignTop)
        # 三色差异化：本地处理绿 / 数据安全紫 / 独立运行橙
        items = [
            (FluentIcon.CERTIFICATE, "#0FA47A",
             tr("本地处理", "Local processing"),
             tr("文件默认在本机完成处理，不上传任何文件",
                "Files processed locally by default, nothing uploaded")),
            (FluentIcon.SAVE, "#8B5CF6",
             tr("数据安全", "Data safety"),
             tr("不会收集与处理无关的个人数据",
                "We do not collect unrelated personal data")),
            (FluentIcon.GAME, "#F0A63A",
             tr("独立运行", "Standalone"),
             tr("核心功能无需依赖在线服务",
                "Core features need no online service")),
        ]
        for icon, color, t1, t2 in items:
            col = QWidget()
            col_lay = QVBoxLayout(col)
            col_lay.setContentsMargins(0, 0, 0, 0)
            col_lay.setSpacing(2)
            iw = self._colored_icon(icon, color, 22)
            col_lay.addWidget(iw, 0, Qt.AlignLeft)
            tl = BodyLabel(t1)
            f1 = QFont(tl.font())
            f1.setPointSize(12)
            f1.setBold(True)
            tl.setFont(f1)
            tl.setStyleSheet(f"")
            col_lay.addWidget(tl)
            dl = CaptionLabel(t2)
            dl.setWordWrap(True)
            dl.setStyleSheet(f"font-size:11px;;line-height:1.4;")
            col_lay.addWidget(dl)
            row.addWidget(col, 1)
        cl.addLayout(row)
        return card

    def _build_about_footer(self):
        """关于页底部栏：盾牌 + 品牌语 + 右侧仅一个 GitHub 按钮。"""
        from qfluentwidgets import ToolButton, BodyLabel
        from PySide6.QtGui import QFont
        footer = Card()
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(20, 14, 20, 14)
        fl.setSpacing(12)
        fl.setAlignment(Qt.AlignVCenter)

        # 左：盾牌
        fl.addWidget(self._shield_widget(44), 0, Qt.AlignVCenter)

        # 中：品牌标题（去掉副标题「由 FormatMaster 团队用 ❤️ 开发和维护」）
        ft_title = BodyLabel(tr("安全 · 高效 · 开源",
                                "Safe · Fast · Open source"))
        f1 = QFont(ft_title.font())
        f1.setPointSize(12)
        f1.setBold(True)
        ft_title.setFont(f1)
        ft_title.setStyleSheet(f"")
        fl.addWidget(ft_title, 1)

        # 右：仅一个 GitHub 按钮
        from gui_qt.update_checker import RELEASES_URL
        gh_btn = self._colored_icon(FluentIcon.GITHUB, "#5B5BD6", 36)
        gh_btn.setToolTip(tr("在浏览器中打开 GitHub 仓库",
                             "Open GitHub repository in browser"))
        gh_btn.setCursor(Qt.PointingHandCursor)
        gh_btn.mousePressEvent = lambda e: self._open_releases(RELEASES_URL)
        fl.addWidget(gh_btn, 0, Qt.AlignVCenter)
        return footer

    def _make_about_card(self):
        """创建 Prism 风格信息卡片（紧凑边距）。"""
        from gui_qt.components.card import Card
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(4)
        return card, layout

    @staticmethod
    def _open_releases(url):
        """在系统浏览器打开 GitHub Releases 页。"""
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl(url))

    def _on_check_update(self):
        """手动触发检查更新（程序自身版本；发现新版弹「立即更新」自动下载替换）。"""
        from gui_qt.components import toast
        from gui_qt.components.app_update_checker import (
            AppUpdateChecker, prompt_app_update)
        if getattr(self, "_checking", False):
            return
        self._checking = True
        self.btn_check.setEnabled(False)
        self.btn_check.setText(tr("检查中…", "Checking…"))
        toast.show_info(self, tr("正在检查更新，请稍候…", "Checking for updates, please wait…"))

        def _reset():
            self._checking = False
            self.btn_check.setEnabled(True)
            self.btn_check.setText(tr("检查更新", "Check for updates"))

        def _found(latest):
            _reset()
            prompt_app_update(self, latest)

        def _up_to_date():
            _reset()
            toast.show_success(self, tr("当前已是最新版本 v{}",
                   "Already up to date v{}").format(APP_VERSION))

        def _failed():
            _reset()
            toast.show_error(self, tr("检查更新失败，请检查网络后重试",
                   "Update check failed, check your network"))

        self._checker = AppUpdateChecker(self)
        self._checker.found.connect(_found)
        self._checker.up_to_date.connect(_up_to_date)
        self._checker.failed.connect(_failed)
        self._checker.check_async()
