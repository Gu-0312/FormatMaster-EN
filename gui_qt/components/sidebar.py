"""sidebar — FluentWindow 侧边导航构建（Prism 设计系统）。

按 nav_registry.NAV_GROUPS 生成全部导航项：
- 内置 NavigationItemHeader 分组标题（自动折叠动画）
- 分组间 NavigationSeparator 分隔线
- 首页置顶、管理中心置底
- 底部主题切换入口（浅色/深色/跟随系统主题循环切换）
- 键盘快捷键 Ctrl+1~9 切页
- 右键菜单：收藏/固定/关闭
- 全局功能搜索（Ctrl+K / 顶部搜索按钮）
- 最近使用 / 收藏 动态置顶组
"""
from PySide6.QtCore import Qt, QPoint, QRect, QRectF
from PySide6.QtGui import QAction, QColor, QCursor, QKeySequence, QPainter
from PySide6.QtWidgets import QFrame, QMenu, QVBoxLayout, QWidget
from qfluentwidgets import (FluentIcon, NavigationItemPosition,
                            isDarkTheme)

from gui_qt import nav_registry
from gui_qt.components import design_system as ds


def _style_nav_header(header, group):
    """分组小标题着色：复用 ds.group_color 色系，增强分组辨识。

    传入 NAV_GROUPS 的「中文原文」分组名，group_key_for_name 按原文匹配
    色板（英文模式下翻译后的标题无法直接匹配，故统一传原文）。
    NavigationItemHeader 用 paintEvent 自绘文字，不走样式表——
    必须设置 lightTextColor / darkTextColor 属性（亮/暗主题两套色）。
    """
    try:
        key = ds.group_key_for_name(group)
        light = ds.GROUP_COLORS.get(key, ("",))[0]
        dark = ds.GROUP_COLORS_DARK.get(key, ("",))[0]
    except Exception:  # noqa: BLE001 - 取色失败保持默认
        light = dark = ""
    if light:
        header.lightTextColor = QColor(light)
    if dark:
        header.darkTextColor = QColor(dark)
    header.update()


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


def _patch_compact_nav_paint():
    """让导航项图标/文字更紧凑（monkey-patch NavigationPushButton.paintEvent）。

    qfluentwidgets 库内硬编码：图标 x=11.5、文字 left=44（Fluent 标准间距）。
    本项目整体收窄后留白仍宽，故把图标左移到 7、文字起点压到 32，
    使导航项内容紧凑、右侧留白最小。仅修改绘制常量，逻辑与原版一致。
    """
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
            elif ((self.isEnter and globalRect.contains(QCursor.pos()))
                  or self.isAboutSelected) and self.isEnabled():
                painter.setBrush(QColor(c, c, c, 6 if self.isAboutSelected else 10))
                painter.drawRoundedRect(self.rect(), 5, 5)
            # 折叠模式：图标水平居中于 40x36 按钮内，与底部主题按钮对齐
            if self.isCompacted:
                iw = 16
                ix = (self.width() - iw) // 2
                iy = (self.height() - iw) // 2
                drawIcon(self._icon, painter, QRectF(ix, iy, iw, iw))
                return
            # 紧凑：图标 11.5 → 7，文字 44 → 32
            drawIcon(self._icon, painter, QRectF(5 + pl, 10, 16, 16))
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


class LazyPage(QWidget):
    """懒加载页面占位：导航注册时只创建空壳，首次显示/访问才构建真面板。

    显著降低启动耗时（不再一次性构建 39 个页面）。
    属性访问（file_card、collect_params 等）自动转发到真页面。
    """

    def __init__(self, factory, window, services):
        super().__init__()
        self._factory = factory
        self._window = window
        self._services = services
        self._real = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._lay = lay

    def _ensure(self):
        """首次访问/显示时构建真面板并加入布局。"""
        if self._real is None:
            self._real = self._factory(self._window, self._services)
            self._lay.addWidget(self._real)
            # 页面构建后立即应用快速滚动（懒加载面板晚于启动时的
            # enable_smooth_scrolling，需在此补上；含页面内嵌套滚动区域）
            try:
                ds.apply_fast_scroll(self)
            except Exception:  # noqa: BLE001 - 滚动优化失败不影响页面
                pass
        return self._real

    def showEvent(self, event):
        super().showEvent(event)
        self._ensure()

    def __getattr__(self, name):
        # 转发到真面板（首次触发构建）；下划线属性不转发避免递归
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._ensure(), name)


def _normalize_nav_expanded(v):
    """nav_expanded 偏好归一化：仅真 bool 生效，缺失/损坏（非 bool）按 True。

    修复 2026-08-21 QA 发现：损坏配置（dict/list/字符串）作为 truthy 会
    误判展开态，统一回退默认展开。
    """
    return v if isinstance(v, bool) else True


def build_navigation(window, services, theme_mgr):
    """创建全部页面并注册到 FluentWindow（首页即时加载，其余懒加载）。"""
    pages = {}
    lazy_pages = []
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

        # 分组小标题（首页不显示；应用分组色系，增强分组辨识）
        if idx > 0:
            g_label = nav_registry.group_label(group)
            header = nav.addItemHeader(g_label, pos)
            # 色板匹配用中文原文（group_key_for_name 与 NAV_GROUPS 中文常量比较）
            _style_nav_header(header, group)

        for item in items:
            key = item["key"]
            # 首页立即构建（用户第一眼看到）；其余懒加载到首次切换
            if key == "home":
                page = item["factory"](window, services)
            else:
                page = LazyPage(item["factory"], window, services)
                lazy_pages.append(page)
            if not page.objectName():
                page.setObjectName(f"page_{key}")
            pages[key] = page
            window.addSubInterface(page, item["icon"],
                                   nav_registry.label(item), pos)

        prev_pos = pos

    # 挂载懒加载页面列表，供启动后分帧预热（消除首次点击卡顿）
    window._lazy_pages = lazy_pages

    # ── 键盘快捷键 Ctrl+1~9 切页 ────────────────────────
    _setup_shortcuts(window, pages.keys())

    # 暴露切换函数供外部调用（如首页快捷卡片）
    window._switch_to = lambda key: pages.get(key) and window.switchTo(pages[key])

    # ── 紧凑化：减小导航面板内部间距 + 调优动画 ──
    panel = nav.panel
    panel.vBoxLayout.setContentsMargins(0, 2, 0, 2)
    panel.vBoxLayout.setSpacing(1)
    panel.topLayout.setSpacing(1)
    panel.bottomLayout.setSpacing(1)
    panel.scrollLayout.setSpacing(1)
    # 展开/折叠动画禁用（duration=0 = 即时展开）：
    # 展开期间所有导航项宽度渐变 + 自定义 paintEvent 逐帧重绘
    # （qfluentwidgets FluentIconBase 每次绘制重新渲染 SVG，43 项/帧），
    # 任何动画时长在真实环境都会卡顿（200ms/150ms/80ms 均实测不流畅）。
    # 即时展开一次布局完成、零逐帧重绘，最流畅；无动画过渡是代价。
    from PySide6.QtCore import QEasingCurve
    panel.expandAni.setDuration(0)
    panel.expandAni.setEasingCurve(QEasingCurve.OutCubic)
    # 展开宽度 322 → 200：配合导航项紧凑绘制（图标/文字左移），留白最小化
    nav.setExpandWidth(152)

    # 修复展开阈值错配（2026-08-21）：qfluentwidgets 内部用两套阈值判断
    # 窗口宽度——expand() 用 minimumExpandWidth+expandWidth-322（152 时=838），
    # resize 事件却用原始 minimumExpandWidth（默认 1008）。本项目窗口最小
    # 宽 960，落在 838~1007 时用户展开侧边栏会被 resize 事件强制折叠（且
    # 覆盖记忆的 nav_expanded）。把 minimumExpandWidth 对齐窗口最小宽度：
    # 窗口永远 ≥960 → 不再误折叠，展开/折叠完全由用户手动控制。
    panel.minimumExpandWidth = 960

    # ── 侧边栏展开/折叠状态记忆（2026-08-21）──
    # 用户手动展开（显示文字）/折叠（仅图标）后持久化到偏好，重启恢复
    # 上次状态——不再每次启动都回到默认的「仅图标」折叠模式。
    try:
        from qfluentwidgets import NavigationDisplayMode

        def _save_nav_expanded():
            try:
                services.set_pref(
                    "nav_expanded",
                    panel.displayMode == NavigationDisplayMode.EXPAND)
                # 立即同步落盘：托盘退出/强杀进程不经过 closeEvent flush
                services.prefs.flush()
            except Exception:  # noqa: BLE001 - 保存失败不影响导航
                pass

        # 展开/折叠动画结束（duration=0 即时完成）后记录状态；restore 的
        # expand(useAni=False) 不启动动画、不触发本信号，不会覆盖刚读的值
        panel.expandAni.finished.connect(_save_nav_expanded)
        # 启动恢复：上次为展开态则立即展开（无动画）。损坏配置（非 bool）
        # 按默认 True（展开）处理，避免脏值误判。
        if _normalize_nav_expanded(services.get_pref("nav_expanded", True)):
            nav.expand(useAni=False)
    except Exception:  # noqa: BLE001 - 记忆功能失败不影响启动
        pass

    # ── 管理中心顶部悬浮分割线：把功能区与底部管理区物理切割 ──
    admin_divider = _make_admin_divider()
    panel.vBoxLayout.insertWidget(
        panel.vBoxLayout.indexOf(panel.bottomLayout), admin_divider)
    # 主题变化（设置中心切换）时刷新分割线颜色：亮色黑投影/暗色白微光
    try:
        from qfluentwidgets import qconfig
        qconfig.themeChanged.connect(
            lambda: admin_divider.setStyleSheet(_admin_divider_qss()))
    except Exception:  # noqa: BLE001 - 信号绑定失败不影响启动
        pass

    return pages


def start_prewarm(window):
    """启动后分帧预热所有懒加载页面，消除首次点击侧边栏功能时的卡顿。

    首次点击某功能页时，LazyPage 会在 showEvent 里现场构建整个面板
    （控件多者达数百 ms），造成「卡一下」的观感。这里用 QTimer 在
    启动后、事件循环空闲时逐帧构建（每 ~120ms 一个），把构建开销
    平滑分摊到启动后的几秒内；用户点到时目标页通常已就绪。
    """
    from PySide6.QtCore import QTimer
    lazy = list(getattr(window, "_lazy_pages", []) or [])
    # 重面板优先预热：构建耗时 >100ms 的面板（实测 2026-08-21：audio 203ms /
    # video 156ms / pdf 141ms / settings-pdf_editor-video_tools 125ms 等）
    # 先构建，降低"点击到未预热重面板"时的卡顿概率；轻面板按原顺序靠后。
    # audio 曾遗漏（最重面板最后预热，用户快速点音频转换仍卡 200ms）。
    _HEAVY = {"video", "audio", "settings", "pdf_editor", "pdf", "plugins",
              "m3u8", "lan_transfer", "download", "watermark", "image",
              "video_tools", "id_photo", "ocr"}
    queue = sorted(
        lazy,
        key=lambda p: 0 if p.objectName().replace("page_", "") in _HEAVY else 1)

    timer = QTimer(window)
    # 150ms 间隔 + 低精度定时器：原 100ms 会在启动后数秒内占 ~50% CPU
    # （每帧构建一个 ~50ms 面板），期间用户操作偶发卡顿。放宽到 150ms
    # 后 CPU 占用降到 ~30%，13 个重面板仍在前 ~2 秒内完成（重面板优先），
    # 轻面板随点随建（<50ms）不感知。
    timer.setInterval(150)
    timer.setTimerType(Qt.TimerType.CoarseTimer)

    def _tick():
        if not queue:
            timer.stop()
            timer.deleteLater()
            return
        page = queue.pop(0)
        try:
            page._ensure()
        except Exception:  # noqa: BLE001 - 单个面板构建失败不影响其余预热
            pass

    timer.timeout.connect(_tick)
    timer.start()
    # 挂到 window 防 GC；预热完成前保持引用
    window._prewarm_timer = timer


def _setup_shortcuts(window, keys):
    """为前 9 个功能页注册 Ctrl+1~9 快捷键。

    注意：window.switchTo 期望页面对象（不是 key 字符串），
    需先经 window.pages 解析——直接传 key 会静默失效。
    """
    key_list = list(keys)
    for i, key in enumerate(key_list[:9], 1):
        act = QAction(window)
        act.setShortcut(QKeySequence(f"Ctrl+{i}"))
        act.triggered.connect(
            lambda _, k=key: window.pages.get(k)
            and window.switchTo(window.pages[k]))
        window.addAction(act)
