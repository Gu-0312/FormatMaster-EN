"""sidebar — FluentWindow 侧边导航构建（Prism 设计系统）。

按 nav_registry.NAV_GROUPS 生成全部导航项：
- 内置 NavigationItemHeader 分组标题（自动折叠动画）
- 分组间 NavigationSeparator 分隔线
- 首页置顶、管理中心置底
- 底部主题切换入口（浅色/深色/跟随系统主题循环切换）
- 键盘快捷键 Ctrl+1~9 切页
- 右键菜单：收藏/固定/关闭
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMenu
from qfluentwidgets import (FluentIcon, NavigationItemPosition,
                            TransparentToolButton)

from gui_qt import nav_registry
from gui_qt.components.theme_manager import MODES


def build_navigation(window, services, theme_mgr):
    """创建全部页面并注册到 FluentWindow（即时加载，增加视觉优化）。"""
    pages = {}
    nav = window.navigationInterface
    prev_pos = None  # 用于判断是否需要加分隔线

    for idx, (group, items) in enumerate(nav_registry.NAV_GROUPS):
        is_bottom = (group == "管理中心")
        pos = (NavigationItemPosition.BOTTOM if is_bottom
               else (NavigationItemPosition.TOP if idx == 0
                     else NavigationItemPosition.SCROLL))

        # 分组间加分隔线（同区域且非首页时添加）
        if idx > 0 and pos == prev_pos:
            nav.addSeparator(pos)

        # 分组小标题（首页不显示）
        if idx > 0:
            nav.addItemHeader(nav_registry.group_label(group), pos)

        for item in items:
            page = item["factory"](window, services)
            if not page.objectName():
                page.setObjectName(f"page_{item['key']}")
            pages[item["key"]] = page
            window.addSubInterface(page, item["icon"],
                                   nav_registry.label(item), pos)

        prev_pos = pos

    # ── 键盘快捷键 Ctrl+1~9 切页 ────────────────────────
    _setup_shortcuts(window, pages.keys())

    # ── 主题切换入口（导航底部）──────────────────────
    theme_btn = TransparentToolButton(FluentIcon.BRIGHTNESS, nav)
    theme_btn.isSelectable = False
    theme_btn.setToolTip(f"主题：{theme_mgr.current_mode()}")
    theme_btn.setFixedSize(40, 40)

    def _cycle_theme():
        # 立即切换，不延迟：此前 QTimer 150ms 延迟导致连点时
        # current_mode() 仍是旧值、模式被跳过（"点两次才切换"），
        # 且切换体感迟缓。
        cur = theme_mgr.current_mode()
        nxt = MODES[(MODES.index(cur) + 1) % len(MODES)] \
            if cur in MODES else MODES[0]
        theme_btn.setToolTip(f"主题：{nxt}")
        _do_theme_switch(theme_mgr, nxt, theme_btn)

    def _do_theme_switch(theme_mgr, mode, btn):
        theme_mgr.set_mode(mode)
        btn.setToolTip(f"主题：{theme_mgr.current_mode()}")

    theme_btn.clicked.connect(_cycle_theme)
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

    return pages


def _setup_shortcuts(window, keys):
    """为前 9 个功能页注册 Ctrl+1~9 快捷键。"""
    key_list = list(keys)
    for i, key in enumerate(key_list[:9], 1):
        act = QAction(window)
        act.setShortcut(QKeySequence(f"Ctrl+{i}"))
        act.triggered.connect(lambda _, k=key: window.switchTo(k))
        window.addAction(act)


def _setup_context_menu(window, pages):
    """给导航界面添加右键菜单：收藏/固定/关闭。"""
    nav = window.navigationInterface
    nav.setContextMenuPolicy(Qt.CustomContextMenu)

    def _show_menu(pos):
        widget = nav.childAt(pos)
        if not widget:
            return
        route_key = widget.objectName().replace("page_", "")
        if route_key not in pages:
            return
        menu = QMenu(window)
        fav_act = menu.addAction(FluentIcon.HEART, "收藏")
        pin_act = menu.addAction(FluentIcon.PIN, "固定到顶部")
        close_act = menu.addAction(FluentIcon.CLOSE, "关闭")
        act = menu.exec(nav.mapToGlobal(pos))
        if act == fav_act:
            pass  # TODO: 收藏
        elif act == pin_act:
            nav.setItemPosition(route_key, NavigationItemPosition.TOP)
        elif act == close_act:
            nav.removeWidget(route_key)

    nav.customContextMenuRequested.connect(_show_menu)
