"""sidebar — FluentWindow 侧边导航构建（Prism 设计系统）。

按 nav_registry.NAV_GROUPS 生成全部导航项：
- 分组标题可点击折叠/展开（箭头前缀，状态持久化）
- 分组间 NavigationSeparator 分隔线
- 选中项左指示条（monkey-patch NavigationPushButton.paintEvent）
- 管理中心独立卡片（底部浅灰圆角容器 + 任务徽标）
- 底部主题切换入口（浅色/深色/跟随系统主题循环切换）
- 键盘快捷键 Ctrl+1~9 切页
- 右键菜单：收藏/固定/关闭
"""
from PySide6.QtCore import Qt, QPoint, QRect, QRectF, Signal
from PySide6.QtGui import QAction, QColor, QCursor, QKeySequence, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, FluentIcon, NavigationItemPosition,
                            NavigationWidget, TransparentToolButton, isDarkTheme)

from gui_qt import nav_registry
from gui_qt.i18n import tr
from gui_qt.components.theme_manager import MODES

# 折叠箭头前缀（几何字符，非 emoji，Qt 正常渲染）
_ARROW_OPEN = "\u25BE "   # ▾ 展开
_ARROW_CLOSED = "\u25B8 "  # ▸ 折叠
# 折叠状态偏好键
_PREF_COLLAPSED = "nav_collapsed_groups"


def _admin_divider_qss():
    """管理中心顶部普通分隔线样式：1px 细实线（主题感知，无阴影）。"""
    color = "rgba(255,255,255,0.22)" if isDarkTheme() else "rgba(0,0,0,0.28)"
    return (f"QFrame#adminDivider {{ border: none; "
            f"border-top: 1px solid {color}; background: transparent; }}")


def _make_admin_divider():
    """创建普通分隔线（插在 bottomLayout 上方）。"""
    d = QFrame()
    d.setObjectName("adminDivider")
    d.setFixedHeight(6)
    d.setStyleSheet(_admin_divider_qss())
    return d


def _admin_card_qss():
    """管理中心卡片样式：浅灰表面 + 圆角（主题感知）。

    用 ID 选择器（#adminRow）而非类型选择器——行继承 NavigationWidget
    （非 QFrame），QFrame#adminRow 不匹配。
    """
    if isDarkTheme():
        bg, hover, badge = ("rgba(255,255,255,0.06)",
                            "rgba(255,255,255,0.10)", "#378ADD")
    else:
        bg, hover, badge = ("rgba(0,0,0,0.06)",
                            "rgba(0,0,0,0.10)", "#185FA5")
    return (f"#adminCard {{ background: {bg}; border-radius: 8px; }}"
            f"#adminRow {{ border-radius: 6px; }}"
            f"#adminRow:hover {{ background: {hover}; }}"
            f"#adminBadge {{ background: {badge}; color: #FFFFFF; "
            f"border-radius: 8px; padding: 1px 7px; font-size: 11px; }}")


class _AdminCard(NavigationWidget):
    """管理中心卡片容器（nav.addWidget 要求 NavigationWidget + clicked 信号）。

    实际点击由内部 _AdminRow 处理，此处信号仅满足库的注册要求。
    """

    clicked = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(False, parent=parent)
        self.setObjectName("adminCard")
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(6, 6, 6, 6)
        self._lay.setSpacing(2)

    def paintEvent(self, e):
        pass  # 背景交给 QSS（#adminCard）

    def add_row(self, row):
        self._lay.addWidget(row)


class _AdminRow(NavigationWidget):
    """管理中心卡片里的功能行（点击切换页面）。

    继承 NavigationWidget（nav.addWidget 要求），视觉由 QSS 控制。
    """

    clicked = Signal(str)  # 页面 key

    def __init__(self, key, icon, text, parent=None):
        super().__init__(False, parent=parent)  # isSelectable=False
        self._key = key
        self.setObjectName("adminRow")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(34)
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 0, 10, 0)
        h.setSpacing(8)
        self._ico = QLabel(self)
        self._ico.setPixmap(icon.icon().pixmap(16, 16))
        self._lbl = BodyLabel(text, self)
        h.addWidget(self._ico)
        h.addWidget(self._lbl)
        h.addStretch(1)

    def paintEvent(self, e):
        pass  # 背景/悬停交给 QSS（#adminRow / :hover）

    def add_badge(self, initial: int = 0):
        """任务行徽标（实时任务数）。返回更新函数。"""
        self._badge = QLabel(self)
        self._badge.setObjectName("adminBadge")
        self.layout().addWidget(self._badge)
        self._badge.setVisible(initial > 0)
        self._badge.setText(str(initial) if initial else "")

        def _set(n: int):
            self._badge.setVisible(n > 0)
            self._badge.setText(str(n) if n else "")

        return _set

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self._key)
        super().mouseReleaseEvent(e)


def _make_admin_card(window, services, pages):
    """管理中心独立卡片：任务/历史/设置/关于 + 任务徽标。"""
    card = _AdminCard()
    card.setStyleSheet(_admin_card_qss())
    badge_set = None
    for item in nav_registry.ADMIN_ITEMS:
        row = _AdminRow(item["key"], item["icon"],
                        nav_registry.label(item), card)
        row.clicked.connect(lambda _, k=item["key"]: window.switchTo(pages[k]))
        if item["key"] == "tasks":
            badge_set = row.add_badge()
        card.add_row(row)
    card.setFixedHeight(card.sizeHint().height())
    # 任务徽标联动：任务状态/批次完成时更新活动任务数
    try:
        from gui_qt.task_manager import PAUSED, RUNNING, WAITING

        def _refresh(*_):
            mgr = services.task_manager
            n = sum(1 for t in mgr.all_tasks()
                    if t.state in (WAITING, RUNNING, PAUSED))
            badge_set(n)

        mgr = services.task_manager
        if hasattr(mgr, "sig_state"):
            mgr.sig_state.connect(_refresh)
        if hasattr(mgr, "sig_batch_done"):
            mgr.sig_batch_done.connect(_refresh)
        _refresh()
    except Exception:  # noqa: BLE001 - 徽标失败不影响卡片
        pass
    return card


def _patch_compact_nav_paint():
    """让导航项更紧凑 + 选中项左指示条（monkey-patch NavigationPushButton.paintEvent）。"""
    try:
        import qfluentwidgets.components.navigation.navigation_widget as _nw
        from qfluentwidgets.common.color import autoFallbackThemeColor
        from qfluentwidgets.common.config import isDarkTheme
        from qfluentwidgets.common.icon import drawIcon

        _orig_paint = _nw.NavigationPushButton.paintEvent

        def _compact_paint(self, e):
            painter = QPainter(self)
            painter.setRenderHints(
                QPainter.Antialiasing | QPainter.TextAntialiasing |
                QPainter.SmoothPixmapTransform)
            painter.setPen(Qt.NoPen)
            if self.isPressed:
                painter.setOpacity(0.7)
            if not self.isEnabled():
                painter.setOpacity(0.4)
            c = 255 if isDarkTheme() else 0
            m = self._margins()
            pl, pr = m.left(), m.right()
            globalRect = QRect(self.mapToGlobal(QPoint()), self.size())
            if self._canDrawIndicator():
                painter.setBrush(QColor(c, c, c, 6 if self.isEnter else 10))
                painter.drawRoundedRect(self.rect(), 5, 5)
                painter.setBrush(autoFallbackThemeColor(
                    self.lightIndicatorColor, self.darkIndicatorColor))
                painter.drawRoundedRect(self.indicatorRect(), 1.5, 1.5)
                # 选中左指示条：3px 圆角竖条，垂直居中（方案 A 选中强化）
                if getattr(self, "isSelected", False):
                    painter.drawRoundedRect(
                        QRectF(1, (self.height() - 22) / 2, 3, 22), 1.5, 1.5)
            elif ((self.isEnter and globalRect.contains(QCursor.pos()))
                  or self.isAboutSelected) and self.isEnabled():
                painter.setBrush(QColor(c, c, c, 6 if self.isAboutSelected else 10))
                painter.drawRoundedRect(self.rect(), 5, 5)
            # 紧凑：图标 11.5 → 7，文字 44 → 32
            drawIcon(self._icon, painter, QRectF(5 + pl, 10, 16, 16))
            if self.isCompacted:
                return
            painter.setFont(self.font())
            painter.setPen(self.textColor())
            left = 26 + pl if not self.icon().isNull() else pl + 7
            painter.drawText(
                QRectF(left, 0, self.width() - 13 - left - pr,
                       self.height()), Qt.AlignVCenter, self.text())

        _nw.NavigationPushButton.paintEvent = _compact_paint
    except Exception:  # noqa: BLE001 - 补丁失败不阻塞启动（回退默认间距）
        pass


_patch_compact_nav_paint()


def build_navigation(window, services, theme_mgr):
    """创建全部页面并注册到 FluentWindow（即时加载，增加视觉优化）。"""
    pages = {}
    nav = window.navigationInterface
    prev_pos = None  # 用于判断是否需要加分隔线

    # ── 分组折叠状态（持久化）──────────────────
    collapsed = set(services.get_pref(_PREF_COLLAPSED, []) or [])
    group_meta = {}  # group -> (header, [item_keys])

    for idx, (group, items) in enumerate(nav_registry.NAV_GROUPS):
        pos = (NavigationItemPosition.TOP if idx == 0
               else NavigationItemPosition.SCROLL)

        # 分组间加分隔线（同区域且非首页时添加）
        if idx > 0 and pos == prev_pos:
            nav.addSeparator(pos)

        # 分组小标题（首页不显示；可点击折叠/展开）
        header = None
        if idx > 0:
            header = nav.addItemHeader(
                nav_registry.group_label(group), pos)
            header.setCursor(Qt.PointingHandCursor)

        keys = []
        for item in items:
            page = item["factory"](window, services)
            if not page.objectName():
                page.setObjectName(f"page_{item['key']}")
            pages[item["key"]] = page
            window.addSubInterface(page, item["icon"],
                                   nav_registry.label(item), pos)
            keys.append(item["key"])
        if header is not None:
            group_meta[group] = (header, keys)

        prev_pos = pos

    # ── 折叠逻辑：点击 header 切换组可见性 ──────
    def _set_group_expanded(group, expanded):
        header, keys = group_meta[group]
        header.setText((_ARROW_OPEN if expanded else _ARROW_CLOSED)
                       + nav_registry.group_label(group))
        for k in keys:
            # BaseQtPanel 自行设置 objectName=panel_{panel_key}，routeKey 即 panel_ 前缀
            w = nav.widget("panel_" + k)
            if w is not None:
                w.setVisible(expanded)

    def _toggle_group(group):
        expanded = group not in collapsed
        if expanded:  # 当前展开 → 折叠
            collapsed.add(group)
        else:
            collapsed.discard(group)
        _set_group_expanded(group, group not in collapsed)
        try:
            services.set_pref(_PREF_COLLAPSED, sorted(collapsed))
        except Exception:  # noqa: BLE001 - 持久化失败不影响交互
            pass

    for group, (header, _keys) in group_meta.items():
        if group in collapsed:
            _set_group_expanded(group, False)
        else:
            header.setText(_ARROW_OPEN + nav_registry.group_label(group))
        header.clicked.connect(lambda _=None, g=group: _toggle_group(g))

    # ── 管理中心独立卡片（底部）────────────────
    # ── 管理中心页面（只进堆栈，不进导航；卡片按钮接管切换）──
    # 注意：不能 addSubInterface + removeWidget——removeWidget 的 deleteLater
    # 延迟删除会让导航项残留布局（与管理卡片重复显示/重叠）
    for item in nav_registry.ADMIN_ITEMS:
        page = item["factory"](window, services)
        page.setObjectName(f"page_{item['key']}")
        pages[item["key"]] = page
        window.stackedWidget.addWidget(page)

    # ── 键盘快捷键 Ctrl+1~9 切页 ────────────────────────
    _setup_shortcuts(window, pages.keys())

    # ── 主题切换入口（导航底部，管理卡片下方）────
    theme_btn = TransparentToolButton(FluentIcon.BRIGHTNESS, nav)
    theme_btn.isSelectable = False
    # 兼容：qfluentwidgets setCurrentItem 会遍历所有导航项调 setSelected，
    # TransparentToolButton 无此方法，补一个空实现避免切页时崩溃
    theme_btn.setSelected = lambda *a, **k: None
    theme_btn.setToolTip(tr("主题", "Theme") + f": {theme_mgr.current_mode()}")
    theme_btn.setFixedSize(40, 40)

    def _cycle_theme():
        cur = theme_mgr.current_mode()
        nxt = MODES[(MODES.index(cur) + 1) % len(MODES)] \
            if cur in MODES else MODES[0]
        theme_btn.setToolTip(tr("主题", "Theme") + f": {nxt}")
        _do_theme_switch(theme_mgr, nxt, theme_btn)

    def _do_theme_switch(theme_mgr, mode, btn):
        theme_mgr.set_mode(mode)
        btn.setToolTip(tr("主题", "Theme") + f": {theme_mgr.current_mode()}")
        # 分割线/管理卡片颜色随主题刷新
        try:
            admin_divider.setStyleSheet(_admin_divider_qss())
            admin_card.setStyleSheet(_admin_card_qss())
        except Exception:  # noqa: BLE001 - 刷新失败不影响主题切换
            pass

    theme_btn.clicked.connect(_cycle_theme)

    # 顺序：管理卡片在上，主题按钮在下（bottomLayout 竖排）
    admin_card = _make_admin_card(window, services, pages)
    nav.addWidget(routeKey="admin_card", widget=admin_card,
                  position=NavigationItemPosition.BOTTOM)
    nav.addWidget(routeKey="theme_toggle", widget=theme_btn,
                  position=NavigationItemPosition.BOTTOM)

    # ── 右键菜单：收藏/固定/关闭 ──────────────────────
    _setup_context_menu(window, pages)

    # 暴露切换函数供外部调用（如首页快捷卡片）
    window._switch_to = lambda key: pages.get(key) and window.switchTo(pages[key])

    # ── 紧凑化：减小导航面板内部间距 + 调优动画 ──
    panel = nav.panel
    panel.vBoxLayout.setContentsMargins(0, 2, 0, 2)
    panel.vBoxLayout.setSpacing(1)
    panel.topLayout.setSpacing(1)
    panel.bottomLayout.setSpacing(1)
    panel.scrollLayout.setSpacing(1)
    panel.expandAni.setDuration(200)  # 展开/折叠动画 200ms
    # 展开宽度 322 → 200：配合导航项紧凑绘制（图标/文字左移），留白最小化
    nav.setExpandWidth(152)

    # ── 管理中心顶部悬浮分割线：把功能区与底部管理区物理切割 ──
    admin_divider = _make_admin_divider()
    panel.vBoxLayout.insertWidget(
        panel.vBoxLayout.indexOf(panel.bottomLayout), admin_divider)

    return pages


def _setup_shortcuts(window, keys):
    """为前 9 个功能页注册 Ctrl+1~9 快捷键。"""
    key_list = list(keys)
    for i, key in enumerate(key_list[:9], 1):
        act = QAction(window)
        act.setShortcut(QKeySequence(f"Ctrl+{i}"))
        act.triggered.connect(
            lambda _, k=key: window.pages.get(k)
            and window.switchTo(window.pages[k]))
        window.addAction(act)


def _setup_context_menu(window, pages):
    """给导航界面添加右键菜单：收藏/固定/关闭。"""
    nav = window.navigationInterface
    nav.setContextMenuPolicy(Qt.CustomContextMenu)

    def _show_menu(pos):
        widget = nav.childAt(pos)
        if not widget:
            return
        # routeKey = 页面 objectName：BaseQtPanel 为 panel_xxx，首页为 page_home
        route_key = widget.objectName()
        if route_key.startswith("panel_"):
            route_key = route_key[len("panel_"):]
        elif route_key.startswith("page_"):
            route_key = route_key[len("page_"):]
        if route_key not in pages:
            return
        menu = QMenu(window)
        fav_act = menu.addAction(FluentIcon.HEART, tr("收藏", "Favorite"))
        pin_act = menu.addAction(FluentIcon.PIN, tr("固定到顶部", "Pin to top"))
        close_act = menu.addAction(FluentIcon.CLOSE, tr("关闭", "Close"))
        act = menu.exec(nav.mapToGlobal(pos))
        if act == fav_act:
            pass  # TODO: 收藏
        elif act == pin_act:
            nav.setItemPosition(route_key, NavigationItemPosition.TOP)
        elif act == close_act:
            nav.removeWidget(route_key)

    nav.customContextMenuRequested.connect(_show_menu)
