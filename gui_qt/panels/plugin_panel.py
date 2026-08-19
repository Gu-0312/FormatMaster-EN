"""plugin_panel — 插件系统管理面板（卡片网格布局）。

扫描 plugins/ 目录（用户数据目录 + 项目目录），以「图标 + 标题 + 简短描述」
的卡片形式排列；点击选中并直接打开面板；支持重新扫描与导入插件
（.py / 压缩包 / 文件夹，成功/失败均有弹窗提示，失败不落地）。
"""

import os

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (QDialog, QFileDialog, QFrame, QHBoxLayout,
                               QMenu, QVBoxLayout, QWidget)
from qfluentwidgets import (CaptionLabel, FlowLayout, FluentIcon, IconWidget,
                            MessageDialog, PushButton, StrongBodyLabel)

from gui_qt.components import toast
from gui_qt.i18n import tr
from gui_qt.panels.base_panel import BaseQtPanel
from plugins._i18n import t

# 插件名关键词 → 图标（全部使用 FluentIcon 内置图标：风格统一、零额外依赖、
# 不会出现因第三方字体库缺失而整排回退成同一个机器人的情况）。
# 规则按「具体优先」排列：先匹配到的关键词即生效，靠后的通用词不抢占
# （如「编码」放在「Unicode」之后，避免误命中「Unicode 编解码」）。
_ICON_RULES = [
    ("查找替换", FluentIcon.SEARCH),
    ("JSON", FluentIcon.CODE),
    ("时间戳", FluentIcon.GLOBE),
    ("Base64", FluentIcon.CERTIFICATE),
    ("正则", FluentIcon.FILTER),
    ("UUID", FluentIcon.DEVELOPER_TOOLS),
    ("Markdown", FluentIcon.DOCUMENT),
    ("字幕", FluentIcon.VIDEO),
    ("反转", FluentIcon.SYNC),
    ("哈希", FluentIcon.FINGERPRINT),
    ("身份证", FluentIcon.PEOPLE),
    ("IP", FluentIcon.CONNECT),
    ("摩斯", FluentIcon.MESSAGE),
    ("九宫格", FluentIcon.TILES),
    ("颜色", FluentIcon.PALETTE),
    ("进制", FluentIcon.UNIT),
    ("对比", FluentIcon.HIGHTLIGHT),
    ("去重", FluentIcon.MOVE),
    ("数字", FluentIcon.LABEL),
    ("ASCII", FluentIcon.PENCIL_INK),
    ("字数", FluentIcon.DICTIONARY),
    ("简繁", FluentIcon.LANGUAGE),
    ("HTML", FluentIcon.LAYOUT),
    ("CSV", FluentIcon.ALIGNMENT),
    ("SQL", FluentIcon.CODE),
    ("图片", FluentIcon.PHOTO),
    ("URL", FluentIcon.LINK),
    ("网页", FluentIcon.PRINT),
    ("JWT", FluentIcon.TAG),
    ("Unicode", FluentIcon.EMOJI_TAB_SYMBOLS),
    ("编码", FluentIcon.FONT),
]
_DEFAULT_ICON = FluentIcon.ROBOT


def _icon_for(name):
    """插件图标：按名称关键词映射 FluentIcon，未命中则回退 ROBOT。"""
    for kw, icon in _ICON_RULES:
        if kw in name:
            return icon
    return _DEFAULT_ICON


class _PluginCard(QFrame):
    """插件卡片：图标 + 标题 + 简短描述，点击选中，右键菜单。"""

    clicked = Signal(int)
    delete_requested = Signal(int)
    edit_requested = Signal(int)

    def __init__(self, idx, name, desc, parent=None):
        super().__init__(parent)
        self.idx = idx
        self.setObjectName("pluginCard")
        self.setAttribute(Qt.WA_Hover, True)
        self.setFixedWidth(184)
        self.setMinimumHeight(112)
        self.setCursor(Qt.PointingHandCursor)

        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 10)
        v.setSpacing(6)
        # 图标匹配用中文原名（_ICON_RULES 为中文关键词），显示文本走翻译
        self.ic = IconWidget(_icon_for(name), self)
        self.ic.setFixedSize(30, 30)
        v.addWidget(self.ic)
        self.lb_name = StrongBodyLabel(t(name), self)
        self.lb_name.setStyleSheet("font-size: 14px;")
        v.addWidget(self.lb_name)
        self.lb_desc = CaptionLabel(t(desc or ""), self)
        self.lb_desc.setWordWrap(True)
        self.lb_desc.setStyleSheet("font-size: 12px;")
        # 描述最多两行（40px ≈ 2×行高）：更长的描述在此截断，防止文字溢出卡片
        # 下边框（长描述 + 用户 DPI/字体偏大时原布局会把文字顶出卡片）。
        self.lb_desc.setMaximumHeight(40)
        v.addWidget(self.lb_desc)
        v.addStretch(1)

        # 右键菜单：删除插件（左键仍为打开面板）
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

    def _on_context_menu(self, pos):
        from gui_qt.i18n import tr
        menu = QMenu(self)
        act_edit = menu.addAction(
            FluentIcon.CODE.icon(), tr("编辑源码", "Edit source"))
        act_del = menu.addAction(
            FluentIcon.DELETE.icon(), tr("删除插件", "Delete plugin"))
        act = menu.exec(self.mapToGlobal(pos))
        if act == act_edit:
            self.edit_requested.emit(self.idx)
        elif act == act_del:
            self.delete_requested.emit(self.idx)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.idx)
        super().mousePressEvent(e)


class PluginPanelPage(BaseQtPanel):
    """插件管理页（卡片网格）。"""

    panel_key = "plugins"

    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("插件系统", "Plugins")))
        lay.addWidget(CaptionLabel(
            tr("扫描 plugins 目录加载扩展插件（Python 文件，支持自定义面板）",
               "Load Python plugins from the plugins folder")))

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_scan = PushButton(FluentIcon.SYNC, tr("重新扫描", "Rescan"))
        self.btn_scan.clicked.connect(self._scan)
        bar.addWidget(self.btn_scan)
        self.btn_import = PushButton(FluentIcon.DOWNLOAD,
                                     tr("导入插件", "Import"))
        self.btn_import.clicked.connect(self._import_menu)
        bar.addWidget(self.btn_import)
        self.lb_path = CaptionLabel("")
        self.lb_path.setStyleSheet(
            f"font-size: 12px; color: {self._ink_sec()};")
        bar.addWidget(self.lb_path)
        bar.addStretch(1)
        lay.addLayout(bar)

        # 导入插件注意事项（常驻提示）
        self.lb_tip = CaptionLabel(
            tr("导入自己的插件：支持 .py 文件 / 压缩包 / 文件夹；"
               "插件须包含 PLUGIN_INFO（name 必填）；可参考项目自带插件"
               "（如 UUID 生成器）作为模板；导入失败会弹窗说明原因且不会"
               "写入任何文件；请只导入可信来源的插件。",
               "Import your plugins: .py / zip / folder; requires "
               "PLUGIN_INFO (name); failures are rejected without writing "
               "files; only import from trusted sources."))
        self.lb_tip.setWordWrap(True)
        self.lb_tip.setStyleSheet(
            f"font-size: 12px; color: {self._ink_sec()};")
        lay.addWidget(self.lb_tip)

        # 卡片网格（FlowLayout 自动换行，高度自适应滚动）
        self.cards_wrap = QWidget()
        self.flow = FlowLayout(self.cards_wrap, needAni=False)
        self.flow.setContentsMargins(0, 6, 0, 6)
        self.flow.setSpacing(10)
        self.flow.setVerticalSpacing(10)
        lay.addWidget(self.cards_wrap)

        self._plugins = []
        self._cards = []
        self._selected = -1
        self._apply_theme()
        from gui_qt.components import design_system as ds
        ds.bind_theme(self, self._apply_theme)
        self._scan()

    def _apply_theme(self):
        """卡片选中/悬停样式按主题刷新。"""
        from gui_qt.components import design_system as ds
        t = ds.tokens()
        qss = (
            f"QFrame#pluginCard {{ background: {t['card_bg']};"
            f" border: 1px solid {t['border']}; border-radius: 10px; }}"
            f"QFrame#pluginCard:hover {{ background: {t['card_hover']};"
            f" border-color: {t['border_hi']}; }}"
            f"QFrame#pluginCard[selected=\"true\"] {{"
            f" border: 2px solid {t['accent']};"
            f" background: {t['accent_pale']}; }}"
            f"QFrame#pluginCard QLabel {{ background: transparent;"
            f" color: {t['ink']}; border: none; }}"
            f"QFrame#pluginCard CaptionLabel {{ color: {t['ink_sec']}; }}"
        )
        self._card_qss = qss
        for c in self._cards:
            c.setStyleSheet(qss)

    def _ink_sec(self):
        from gui_qt.components import design_system as ds
        return ds.ink_sec()

    def _clear_cards(self):
        for c in self._cards:
            self.flow.removeWidget(c)
            c.deleteLater()
        self._cards = []
        self._selected = -1

    def _scan(self):
        from core.plugin_loader import plugin_dirs, scan_plugins
        self._plugins = scan_plugins()
        self._clear_cards()
        for i, p in enumerate(self._plugins):
            card = _PluginCard(i, p.name, p.description or "", self.cards_wrap)
            card.clicked.connect(self._on_card_clicked)
            card.delete_requested.connect(self._delete_plugin)
            card.edit_requested.connect(self._edit_plugin)
            card.setStyleSheet(self._card_qss)
            self.flow.addWidget(card)
            self._cards.append(card)
        self.lb_path.setText(
            tr("共 {} 个插件", "{} plugins").format(len(self._plugins))
            + "  ·  " + os.pathsep.join(plugin_dirs()))
        if not self._plugins:
            toast.show_info(self, tr("未发现插件（检查 plugins 目录）",
                                     "No plugins found (check plugins dir)"))

    def _on_card_clicked(self, idx):
        """点击卡片：选中高亮 + 直接打开插件面板。"""
        self._select(idx)
        self._open_panel(idx)

    def _edit_plugin(self, idx):
        """右键「编辑源码」：QPlainTextEdit+语法高亮查看/编辑插件源码。"""
        if not (0 <= idx < len(self._plugins)):
            return
        p = self._plugins[idx]
        if not os.path.isfile(p.source):
            toast.show_warning(self, tr("插件源码不存在", "Plugin source missing"))
            return
        from gui_qt.components.code_editor import CodeEditorDialog
        dlg = CodeEditorDialog(p.source, self.window())
        dlg.exec()
        # 编辑后重新扫描，让改动立即生效
        self._scan()

    def _delete_plugin(self, idx):
        """右键删除插件：仅用户导入的插件可删（内置插件受保护）。"""
        from core.plugin_loader import plugin_dirs
        if not (0 <= idx < len(self._plugins)):
            return
        p = self._plugins[idx]
        user_dir = os.path.normpath(plugin_dirs()[0])
        src = os.path.normpath(os.path.abspath(p.source))
        # 只有位于用户数据目录（%APPDATA%/FormatMaster/plugins）的插件可删，
        # 项目内置 plugins/ 的插件是程序功能，禁止删除
        try:
            is_user_plugin = os.path.commonpath([src, user_dir]) == user_dir
        except ValueError:  # noqa: BLE001 - 不同盘符无公共路径
            is_user_plugin = False
        if not is_user_plugin:
            toast.show_info(
                self, tr("内置插件不可删除", "Built-in plugins cannot be deleted"))
            return

        # 确认删除
        try:
            from qfluentwidgets import MessageBox
            box = MessageBox(
                tr("删除插件", "Delete plugin"),
                tr("确定删除插件「{}」吗？删除后不可恢复。",
                   "Delete plugin \"{}\"? This cannot be undone.").format(t(p.name)),
                self)
            box.yesButton.setText(tr("删除", "Delete"))
            box.cancelButton.setText(tr("取消", "Cancel"))
            if not box.exec():
                return
        except Exception:  # noqa: BLE001 - 确认框异常按删除处理
            pass

        try:
            os.remove(p.source)
        except OSError as e:
            toast.show_error(self, tr("删除失败：{}", "Delete failed: {}").format(e))
            return
        self._scan()
        toast.show_success(self, tr("已删除插件：{}", "Plugin deleted: {}").format(t(p.name)))

    # ── 导入插件 ────────────────────────────────
    def _import_menu(self):
        """导入按钮菜单：文件/压缩包 or 文件夹。"""
        menu = QMenu(self)
        act_file = menu.addAction(
            FluentIcon.DOCUMENT.icon(), tr("从文件 / 压缩包导入",
                                           "From file / zip"))
        act_dir = menu.addAction(
            FluentIcon.FOLDER.icon(), tr("从文件夹导入", "From folder"))
        act = menu.exec(self.btn_import.mapToGlobal(
            QPoint(0, self.btn_import.height())))
        if act == act_file:
            self._import_file()
        elif act == act_dir:
            self._import_dir()

    def _import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("选择插件文件或压缩包", "Pick plugin file or zip"),
            "", tr("插件文件 (*.py *.zip);;Python (*.py);;压缩包 (*.zip)",
                   "Plugins (*.py *.zip);;Python (*.py);;Zip (*.zip)"))
        if path:
            self._do_import(path)

    def _import_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, tr("选择包含插件的文件夹", "Pick plugin folder"))
        if path:
            self._do_import(path)

    def _do_import(self, source):
        """执行导入：全部有效才落地，结果弹窗提示，成功则重新扫描。"""
        from core.plugin_loader import import_plugin, plugin_dirs
        target = plugin_dirs()[0]   # 用户数据目录，导入即用户私有
        ok, result = import_plugin(source, target)
        if ok:
            self._scan()
        self._show_import_result(ok, result)

    def _show_import_result(self, ok, result):
        """导入成功/失败弹窗。"""
        if ok:
            names = "、".join(result) if isinstance(result, list) \
                else str(result)
            dlg = MessageDialog(
                tr("导入成功", "Imported"),
                tr("已导入并生效：{}", "Imported and active: {}").format(names),
                self)
        else:
            dlg = MessageDialog(tr("导入失败", "Import failed"),
                                str(result), self)
        dlg.yesButton.setText(tr("知道了", "OK"))
        dlg.cancelButton.hide()
        dlg.exec()

    def _select(self, idx):
        """单选高亮。"""
        if not (0 <= idx < len(self._cards)):
            return
        self._selected = idx
        for i, c in enumerate(self._cards):
            sel = (i == idx)
            if c.property("selected") != sel:
                c.setProperty("selected", sel)
                c.style().unpolish(c)
                c.style().polish(c)

    def _open_panel(self, idx):
        if not (0 <= idx < len(self._plugins)):
            return
        p = self._plugins[idx]
        if p.panel_class is None:
            toast.show_info(self, tr("该插件没有界面", "This plugin has no panel"))
            return
        try:
            # FluentDialogBase：自动适配亮/暗主题并跟随切换
            from gui_qt.components import design_system as ds
            from gui_qt.components.dialog import FluentDialogBase
            dlg = FluentDialogBase(
                f"{t(p.name)} · {tr('插件面板', 'Plugin panel')}", self)
            w, h = ds.screen_ratio_size(0.82)
            dlg.resize(w, h)
            from PySide6.QtWidgets import QVBoxLayout
            v = QVBoxLayout(dlg)
            v.addWidget(p.panel_class())
            dlg.exec()
        except Exception as e:  # noqa: BLE001
            toast.show_error(self, f"{tr('插件面板打开失败', 'Open failed')}: {e}")
