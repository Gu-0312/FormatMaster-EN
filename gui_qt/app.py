"""app — PySide6 应用引导与主窗口（Prism 设计系统）。

MainWindow：FluentWindow + Mica 云母背景（Win11，Win10 自动降级）
+ 侧边导航（nav_registry 全量注册）+ 亮/暗/跟随系统主题。
启动时应用 Prism 设计系统全局样式。
"""
from gui_qt.i18n import tr
import os
import sys


def _theme_icon(kind, dark):
    """绘制月亮/太阳 QIcon（20×20，与 FluentIcon 同尺寸，图形占满）。

    kind: 'moon'/'sun'；颜色随亮暗主题（浅色深灰、深色浅灰）。
    """
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
    color = QColor("#e8eaed" if dark else "#5f6368")
    pm = QPixmap(20, 20)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    if kind == "moon":
        # 月牙：主圆 r8 - 副圆 r7 偏移 (3.5,-1.5)（OddEvenFill）
        # 副圆略小 + 偏移适中 → 宽度 ~3.5px 的明显弯月，且占满画布
        path = QPainterPath()
        path.addEllipse(QPointF(10.0, 10.0), 8.0, 8.0)
        path.addEllipse(QPointF(13.5, 8.5), 7.0, 7.0)
        path.setFillRule(Qt.OddEvenFill)
        p.fillPath(path, color)
    else:
        p.setPen(QPen(color, 1.8))
        p.setBrush(QColor(color))
        p.drawEllipse(QPointF(10, 10), 3.6, 3.6)        # 太阳
        for i in range(8):                              # 光芒
            import math
            a = i * math.pi / 4
            x1, y1 = 10 + 5.8 * math.cos(a), 10 + 5.8 * math.sin(a)
            x2, y2 = 10 + 8.2 * math.cos(a), 10 + 8.2 * math.sin(a)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    p.end()
    return QIcon(pm)

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QDialog
from qfluentwidgets import FluentWindow, isDarkTheme

from gui_qt.components.sidebar import build_navigation
from gui_qt.components.theme_manager import ThemeManager
from gui_qt.components import design_system as ds
from gui_qt.services import QtServices
from gui_qt.task_manager import TaskManager


def _is_win11():
    try:
        return sys.getwindowsversion().build >= 22000
    except AttributeError:
        return False


class MainWindow(FluentWindow):
    """格式大师 Qt 版主窗口。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(tr("格式大师", "FormatMaster"))
        # 主窗口图标（任务栏/Alt-Tab 显示；应用级图标已设，此处双保险）
        try:
            from PySide6.QtGui import QIcon
            from utils.config import get_resource_path
            _icon_path = get_resource_path(os.path.join("assets", "icon.ico"))
            if os.path.isfile(_icon_path):
                self.setWindowIcon(QIcon(_icon_path))
        except Exception:  # noqa: BLE001
            pass
        self._init_size()  # 按当前屏幕可用区域自适应初始尺寸
        self.setObjectName("FluentWindow")
        self._center_on_screen()

        # ── 服务容器 ─────────────────────────────
        self.services = QtServices()
        self.theme_mgr = ThemeManager(self.services)
        # 窗口状态记忆：设置了记忆开关时恢复上次大小/位置/最大化，
        # 否则用按屏幕自适应初始尺寸（_init_size 已在上面执行，这里覆盖）
        try:
            if self.services.get_pref("remember_window", True):
                if not self._restore_window_state():
                    self._center_on_screen()
        except Exception:  # noqa: BLE001 - 窗口状态恢复失败不影响
            self._center_on_screen()
        self.services.theme_mgr = self.theme_mgr
        self.services.window = self   # 供 theme_mgr 回查主窗口（窗口效果切换等）

        # ── 全局字体 ──
        # 用 setPointSizeF 指定逻辑点数，Qt 在高 DPI 下自动换算物理像素，
        # 保证 1080p / 2K / 4K 等不同缩放下文字大小一致且锐利。
        font = QFont(ds.FONT_BODY)
        QApplication.instance().setFont(font)

        # ── 语言（必须在导航构建前设置，导航文案随语言渲染）──
        from gui_qt import i18n
        i18n.set_language(self.services.get_pref("language", "zh"))

        # ── Prism 窗口注册（必须在 apply_saved 之前，
        #     确保 QSS 作用域为窗口级而非全局 app）──
        ds.set_app_window(self)
        # 外观偏好应用到设计系统（圆角必须在 apply_saved 前，
        # 这样 set_app_style 生成的 QSS 才使用正确取值）
        ds.set_animations(bool(self.services.get_pref("animations", True)))
        ds.set_card_radius(bool(self.services.get_pref("card_radius", True)))
        self.theme_mgr.apply_saved()

        self.task_manager = TaskManager(self.services, self)
        self.services.task_manager = self.task_manager
        self.task_manager.sig_state.connect(self._on_task_state)
        self.task_manager.sig_batch_done.connect(self._on_batch_done)

        # ── 导航与页面（nav_registry 全量注册）────
        self.pages = build_navigation(self, self.services, self.theme_mgr)
        self.switchTo(self.pages["home"])

        # ── Mica 云母背景（Win11；Win10 自动跳过）──
        self._enable_mica()

        # ── 主题切换性能优化：取消 StackedWidget 的主题自动刷新 ──
        self._optimize_theme_switch()

        # ── 系统托盘（偏好开启时创建；关闭窗口最小化到托盘）──
        self.tray = None
        self._force_quit = False
        self._setup_tray()

        # ── 标题栏快捷按钮（最小化左侧：窗口置顶 + 主题切换）──
        self._setup_title_buttons()

        # ── 侧边导航选中态紫色样式（运行时补丁 + 关闭选中动画）──
        from gui_qt import nav_style
        nav_style.apply(self)
        # ── 页面切换动画：原「从下方 76px 弹出 300ms」（弹动感）→
        #    改为「从右侧水平滑入 150ms OutCubic」（更接近 Win11 设置）
        self._patch_page_animation()

    def _patch_page_animation(self):
        """把 FluentWindow 页面切换动画改成「快速弹出」。

        qfluentwidgets PopUpAniStackedWidget 默认 deltaY=76（新页从下往上
        滑入 300ms）。当前采用轻快弹出：从下方轻微 40px 快速弹出
        （100ms OutCubic），干脆利落不拖沓、无重"弹动"感。
        """
        try:
            from PySide6.QtCore import QEasingCurve
            view = self.stackedWidget.view
            for info in view.aniInfos:
                info.deltaX = 0
                info.deltaY = 40
            _orig = self.stackedWidget.setCurrentWidget
            if not getattr(_orig, "_fm_patched", False):
                def _patched(widget, popOut=True):
                    if not popOut:
                        view.setCurrentWidget(
                            widget, needPopOut=False,
                            showNextWidgetDirectly=True,
                            duration=100, easingCurve=QEasingCurve.OutCubic)
                    else:
                        _orig(widget, popOut)
                _patched._fm_patched = True
                self.stackedWidget.setCurrentWidget = _patched
        except Exception:  # noqa: BLE001 - 动画 patch 失败不影响切换
            pass

        # ── 全局快捷键（设置页可自定义）──
        self._shortcut_objs = []
        self._apply_shortcuts()

    def _setup_title_buttons(self):
        """标题栏（最小化图标左侧）加「主题切换」与「窗口置顶」图钉。

        用 TransparentToolButton：无方框背景，仅悬停/选中时显示淡背景；
        尺寸与最小化/最大化/关闭按钮一致（46×32）。
        主题图标随亮暗切换（浅色→月亮，深色→太阳）；图钉置顶/未置顶双图标。
        """
        from qfluentwidgets import FluentIcon, TransparentToolButton, isDarkTheme
        bar = self.titleBar

        # 双击标题栏空白处 最大化/还原（qframelesswindow 内置，
        # 默认开启；此处显式确保开启，防御未来库默认值变化）
        try:
            bar.setDoubleClickEnabled(True)
        except Exception:  # noqa: BLE001 - 库版本差异时静默跳过
            pass

        self.btn_theme = TransparentToolButton(bar)
        self.btn_theme.setToolTip(tr("切换亮暗主题", "Toggle light/dark"))
        self.btn_theme.setFixedSize(46, 32)
        self.btn_theme.clicked.connect(self._toggle_theme)
        self._refresh_theme_icon()

        # 传 FluentIcon 枚举：qfluentwidgets 按钮随主题动态渲染颜色，
        # 避免 .icon() 固定色在主题切换后看不清的问题
        self.btn_pin = TransparentToolButton(FluentIcon.UNPIN, bar)
        self.btn_pin.setCheckable(True)
        self.btn_pin.setToolTip(tr("窗口置顶", "Always on top"))
        self.btn_pin.setFixedSize(46, 32)
        self.btn_pin.clicked.connect(self._toggle_pin)

        # 插到最小化按钮左侧：顺序 [主题][图钉][最小化]…
        lay = bar.buttonLayout
        idx = lay.indexOf(bar.minBtn)
        lay.insertWidget(idx, self.btn_pin)
        lay.insertWidget(idx, self.btn_theme)

    def _refresh_theme_icon(self):
        """主题按钮图标：浅色→月亮（点按切深色），深色→太阳（点按切浅色）。"""
        from qfluentwidgets import isDarkTheme
        dark = isDarkTheme()
        self.btn_theme.setIcon(
            _theme_icon("sun" if dark else "moon", dark))

    def _toggle_pin(self, checked=None):
        """切换窗口置顶（按钮与快捷键共用，状态统一同步）。

        注意：btn_pin 是 checkable 按钮——点击时 Qt 已自动翻转 checked 并把
        新状态作为 clicked(bool) 参数传入；此处**不能再翻转一次**，否则按钮
        视觉回弹、置顶永远不生效（历史 bug）。快捷键路径不经过点击，
        checked 为 None，此时才手动翻转。
        """
        if checked is None:
            checked = not self.btn_pin.isChecked()
            self.btn_pin.setChecked(checked)
        on = bool(checked)
        import ctypes
        hwnd = int(self.winId())
        # HWND_TOPMOST = -1, HWND_NOTOPMOST = -2
        # 用 c_void_p 避免 64 位符号扩展问题
        HWND_TOPMOST = ctypes.c_void_p(-1)
        HWND_NOTOPMOST = ctypes.c_void_p(-2)
        SWP_NOSIZE = 1
        SWP_NOMOVE = 2
        SWP_NOACTIVATE = 0x10
        swp_flags = SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
        ctypes.windll.user32.SetWindowPos(
            hwnd, HWND_TOPMOST if on else HWND_NOTOPMOST,
            0, 0, 0, 0, swp_flags)
        # 验证是否真的置顶成功（防止用户环境失效）
        GWL_EXSTYLE = -20
        WS_EX_TOPMOST = 8
        ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        really_on = bool(ex_style & WS_EX_TOPMOST)
        if really_on != on:
            # 兜底：SetWindowPos 失效时走 Qt setWindowFlag（会闪但能生效）
            self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
            self.show()
        from qfluentwidgets import FluentIcon
        self.btn_pin.setIcon(
            FluentIcon.PIN if on else FluentIcon.UNPIN)
        self.btn_pin.setToolTip(
            tr("取消窗口置顶", "Unpin") if on
            else tr("窗口置顶", "Always on top"))

    def _toggle_theme(self):
        """标题栏主题按钮：浅色 ↔ 深色循环（跳过跟随系统）。"""
        from gui_qt.components import theme_manager as tm
        mode = self.theme_mgr.current_mode()
        self.theme_mgr.set_mode(
            tm.MODE_DARK if mode == tm.MODE_LIGHT else tm.MODE_LIGHT)
        self._refresh_theme_icon()

    def _apply_shortcuts(self):
        """按用户偏好注册全局快捷键（设置页修改后重新调用）。"""
        from PySide6.QtGui import QKeySequence, QShortcut
        from gui_qt.shortcuts import SHORTCUT_ACTIONS
        for sc in self._shortcut_objs:
            sc.deleteLater()
        self._shortcut_objs = []
        saved = dict(self.services.get_pref("shortcuts", {}))
        handlers = {
            "pin": self._toggle_pin,
            "theme": self._toggle_theme,
            "history": lambda: self.switchTo(self.pages["history"]),
            "settings": lambda: self.switchTo(self.pages["settings"]),
            "plugins": lambda: self.switchTo(self.pages["plugins"]),
        }
        for key, meta in SHORTCUT_ACTIONS.items():
            keys = saved.get(key, meta["default"])
            if not keys:
                continue
            try:
                sc = QShortcut(QKeySequence(keys), self)
                sc.activated.connect(handlers[key])
                self._shortcut_objs.append(sc)
            except Exception:  # noqa: BLE001 - 非法快捷键忽略
                pass

    def _setup_tray(self):
        """按"系统托盘"偏好创建/移除托盘图标。"""
        if self.services.get_pref("tray", False):
            self._create_tray()
        elif self.tray is not None:
            self.tray.hide()
            self.tray.deleteLater()
            self.tray = None

    def _create_tray(self):
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QMenu, QSystemTrayIcon
        from utils.config import get_resource_path
        if self.tray is not None:
            return
        icon_path = get_resource_path(os.path.join("assets", "icon.ico"))
        icon = QIcon(icon_path) if os.path.isfile(icon_path) \
            else self.windowIcon()
        self.tray = QSystemTrayIcon(icon, self)
        menu = QMenu(self)
        act_show = menu.addAction(tr("显示主窗口", "Show window"))
        act_quit = menu.addAction(tr("退出", "Quit"))
        act_show.triggered.connect(self._show_from_tray)
        act_quit.triggered.connect(self._quit_from_tray)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip(tr("格式大师 FormatMaster", "FormatMaster"))
        self.tray.activated.connect(
            lambda reason: self._show_from_tray()
            if reason == QSystemTrayIcon.DoubleClick else None)
        self.tray.show()

    def _show_from_tray(self):
        self.show()
        try:
            self.setWindowState(
                (self.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
        except Exception:  # noqa: BLE001 - 无边框窗口在特殊环境下句柄异常
            pass
        self.raise_()
        self.activateWindow()

    def _quit_from_tray(self):
        self._force_quit = True
        if self.tray is not None:
            self.tray.hide()
        self.close()

    def _init_size(self):
        """初始窗口尺寸自适应屏幕。

        以 1080p（1920×1080）下的 1280×820 为基准，按当前屏幕
        可用区域等比放大；屏幕更小时按比例收缩，保证不超过
        可用区域。2K / 4K 等大屏自动获得更大的初始窗口。
        同时设置最小窗口尺寸，避免用户缩得过小导致布局挤压。
        """
        try:
            screen = QApplication.primaryScreen()
            if screen is None:
                self.setMinimumSize(960, 620)
                self.resize(1280, 820)
                return
            sg = screen.availableGeometry()
            # 最小窗口尺寸（逻辑像素，随高 DPI 缩放）；不超过屏幕可用区域，
            # 兼容 1366×768 / 1024×768 等小屏
            min_w = min(960, sg.width())
            min_h = min(620, sg.height())
            self.setMinimumSize(min_w, min_h)
            base_w, base_h = 1280, 820
            # 与 1080p 基准的比例（保护性取 0.7~1.6 区间，避免极端值）
            ratio = min(max(min(sg.width() / 1920, sg.height() / 1080),
                            0.7), 1.6)
            w = int(base_w * ratio)
            h = int(base_h * ratio)
            # 不超过可用区域
            w = min(w, sg.width())
            h = min(h, sg.height())
            self.resize(w, h)
        except Exception:
            self.setMinimumSize(960, 620)
            self.resize(1280, 820)

    def _center_on_screen(self):
        """将窗口居中到主屏幕可用区域。"""
        try:
            screen = QApplication.primaryScreen()
            if screen is None:
                return
            sg = screen.availableGeometry()
            fg = self.frameGeometry()
            x = (sg.width() - fg.width()) // 2 + sg.x()
            y = (sg.height() - fg.height()) // 2 + sg.y()
            self.move(max(x, sg.x()), max(y, sg.y()))
        except Exception:
            pass

    def _restore_window_state(self):
        """从偏好恢复上次窗口大小/位置/最大化；无有效记录返回 False。"""
        try:
            import json
            raw = self.services.get_pref("window_state", "")
            if not raw:
                return False
            st = json.loads(raw) if isinstance(raw, str) else raw
            w, h = int(st.get("w", 0)), int(st.get("h", 0))
            if w < 800 or h < 600:
                return False
            x, y = int(st.get("x", 0)), int(st.get("y", 0))
            sg = None
            try:
                sg = QApplication.primaryScreen().availableGeometry()
            except Exception:
                pass
            if sg is not None:
                # 窗口完全移出屏幕（分辨率变更/拔显示器）：仅恢复尺寸
                if (x + 100 > sg.right() or y + 100 > sg.bottom()
                        or x + w < sg.left() or y + h < sg.top()):
                    self.resize(w, h)
                    return True
            self.resize(w, h)
            self.move(x, y)
            if st.get("maximized"):
                self.showMaximized()
            return True
        except Exception:  # noqa: BLE001
            return False

    def _save_window_state(self):
        """保存当前窗口大小/位置/最大化状态（closeEvent 确认退出时调用）。"""
        try:
            import json
            try:
                ng = self.normalGeometry()
                if ng.width() >= 800 and ng.height() >= 600:
                    x, y, w, h = ng.x(), ng.y(), ng.width(), ng.height()
                else:
                    x, y, w, h = self.x(), self.y(), self.width(), self.height()
            except Exception:
                x, y, w, h = self.x(), self.y(), self.width(), self.height()
            self.services.set_pref("window_state", json.dumps({
                "x": int(x), "y": int(y), "w": int(w), "h": int(h),
                "maximized": bool(self.isMaximized()),
            }))
        except Exception:  # noqa: BLE001 - 保存失败不影响退出
            pass

    def switchTo(self, interface):
        """切换页面时清理当前窗口的 InfoBar 提示，并做内容淡入动画。"""
        from gui_qt.components import toast
        toast.close_all()
        super().switchTo(interface)
        self._fade_in_page(interface)

    def _fade_in_page(self, widget):
        """页面切换显示（原 200ms QGraphicsOpacityEffect 淡入已移除）。

        QGraphicsOpacityEffect 会把整棵控件树强制渲染到离屏缓冲区，
        每次透明度变化全量重绘——面板控件密集时切换页面明显卡顿
        （2026-08-15 性能修复）。切换改为即时显示，页面本身切换成本
        已通过 LazyPage 预热分摊，无动画损失可感知。
        """
        return
        # 以下为历史实现，保留注释供回退参考
        # if widget is None or not widget.isVisible():
        #     return
        # if not ds.animations_enabled():
        #     return
        # try:
        #     from PySide6.QtCore import QEasingCurve, QPropertyAnimation
        #     from PySide6.QtWidgets import QGraphicsOpacityEffect
        #     if getattr(self, "_page_fade_ani", None) is not None:
        #         self._page_fade_ani.stop()
        #     effect = QGraphicsOpacityEffect(widget)
        #     widget.setGraphicsEffect(effect)
        #     ani = QPropertyAnimation(effect, b"opacity", self)
        #     ani.setDuration(200)
        #     ani.setStartValue(0.0)
        #     ani.setEndValue(1.0)
        #     ani.setEasingCurve(QEasingCurve.OutCubic)
        #     def _on_fade_done():
        #         widget.setGraphicsEffect(None)
        #         try:
        #             ani.deleteLater()
        #         except RuntimeError:
        #             pass
        #     ani.finished.connect(_on_fade_done)
        #     self._page_fade_ani = ani
        #     ani.start()
        # except Exception:
        #     try:
        #         widget.setGraphicsEffect(None)
        #     except Exception:
        #         pass

    def _on_task_state(self, task_id, state):
        """任务状态变化时锁定/解锁导航栏与当前面板。"""
        from gui_qt.task_manager import RUNNING, WAITING, PAUSED
        mgr = self.task_manager
        busy = any(
            t.state in (RUNNING, WAITING, PAUSED)
            for t in mgr._tasks.values()
        )
        self._set_nav_enabled(not busy)

    def _on_batch_done(self):
        """所有任务完成后的钩子：提示音（成功/失败不同）+ 失败汇总通知 + 自动打开输出目录。"""
        import os
        import time
        from gui_qt.task_manager import FAILED
        mgr = self.task_manager
        # 只统计本次 batch（近期 60 秒内）失败的，避免把历史失败任务一起误报
        now = time.time()
        failed = [t for t in mgr.all_tasks()
                  if t.state == FAILED and now - getattr(t, "ended_at", 0) < 60]
        if not failed:
            # 本批无失败：仅成功提示音，不弹失败通知
            if self.services.get_pref("notify_sound", True):
                self._play_done_sound(failed)
            self._notify_done(len(mgr.all_tasks()))
            self._open_last_output_dir(mgr)
            return
        # 提示音：全部成功 → 完成"叮"声；有失败 → 错误系统音。
        # Windows 系统事件音异步播放，逐级回退到系统默认提示音。
        if self.services.get_pref("notify_sound", True):
            self._play_done_sound(failed)
        # 失败详情提示由各面板 _on_state 统一发出（处理失败：xxx），
        # 这里不再弹「请到任务中心查看」汇总 toast，避免同一失败双重提示。
        self._open_last_output_dir(mgr)

    def _notify_done(self, count):
        """全部任务完成通知：按设置「通知方式」执行。

        auto：系统托盘气泡优先，窗口内 toast 兜底；
        toast：强制窗口内 toast；
        sound：不弹窗（声音由 _play_done_sound 单独处理）。
        """
        try:
            from gui_qt.components import toast
            style = self.services.get_pref("notify_style", "auto")
            if style == "sound":
                return
            msg = tr("全部转换完成（{} 个任务）",
                     "All conversions done ({} tasks)").format(count)
            if style == "toast":
                toast.show_success(self, msg)
                return
            # auto：托盘气泡优先，否则窗口 toast 兜底
            from PySide6.QtWidgets import QSystemTrayIcon
            tray = getattr(self, "tray", None)
            if tray is not None and tray.isVisible():
                try:
                    tray.showMessage(
                        tr("格式大师", "FormatMaster"), msg,
                        QSystemTrayIcon.Information, 4000)
                    return
                except Exception:  # noqa: BLE001
                    pass
            toast.show_success(self, msg)
        except Exception:  # noqa: BLE001
            pass

    def _play_done_sound(self, failed):
        """Windows 系统事件音（异步、逐级回退）。"""
        try:
            import winsound
            aliases = (["SystemHand", "SystemAsterisk",
                        "SystemExclamation"] if failed else
                       ["SystemNotification", "SystemAsterisk",
                        "SystemExclamation"])

            def _play():
                try:
                    for alias in aliases:
                        try:
                            winsound.PlaySound(
                                alias,
                                winsound.SND_ALIAS | winsound.SND_ASYNC)
                            return
                        except Exception:  # noqa: BLE001 - 单别名失败继续
                            continue
                    winsound.MessageBeep(
                        winsound.MB_ICONERROR if failed else winsound.MB_OK)
                except Exception:  # noqa: BLE001 - 全部失败则静音
                    pass

            _play()
        except Exception:  # noqa: BLE001
            pass

    def _open_last_output_dir(self, mgr):
        """自动打开最后一个成功的输出目录（设置开启时）。"""
        import os
        if not self.services.get_pref("open_dir_on_done", False):
            return
        last_out = ""
        for t in mgr.all_tasks():
            if t.state == "success" and t.output_path:
                last_out = os.path.dirname(t.output_path)
        if last_out and os.path.isdir(last_out):
            try:
                os.startfile(last_out)
            except Exception:
                pass


    def _set_nav_enabled(self, enabled):
        """启用/禁用侧边导航栏所有导航项及当前面板的交互控件。"""
        from qfluentwidgets.components.navigation.navigation_widget import (
            NavigationWidget)
        for w in self.navigationInterface.panel.findChildren(NavigationWidget):
            w.setEnabled(enabled)
        # 禁用/启用当前面板内的所有交互控件
        current = self.stackedWidget.currentWidget()
        if current:
            from PySide6.QtWidgets import (
                QAbstractButton, QComboBox, QLineEdit, QTextEdit,
                QSpinBox, QDoubleSpinBox, QSlider)
            # findChildren 只接受单个类型，逐类查找再统一设置
            for cls in (QAbstractButton, QComboBox, QLineEdit, QTextEdit,
                        QSpinBox, QDoubleSpinBox, QSlider):
                for w in current.findChildren(cls):
                    w.setEnabled(enabled)

    def _enable_mica(self):
        """应用窗口背景效果（Mica 云母，Win11；Win10 自动跳过）。"""
        if not _is_win11():
            return
        try:
            self.windowEffect.setMicaEffect(self.winId(),
                                            isDarkMode=isDarkTheme())
        except Exception:  # noqa: BLE001 - 特效失败不应阻断启动
            pass

    def _optimize_theme_switch(self):
        """取消 StackedWidget 的主题自动刷新，显著加速明暗切换。

        qfluentwidgets 的 setTheme 会遍历 styleSheetManager 逐个刷新控件；
        StackedWidget 是主窗口内容容器，包含全部 40 个懒加载页面，对它
        setStyleSheet 会触发上千子控件的级联 repolish（实测 ~850ms，占
        整个 setTheme 的 80%+）。改为：

        1. deregister：让 setTheme 不再级联刷新它，省 ~850ms；
        2. QPalette 管理背景：深色用 #202020、浅色用 #F0F4F9（匹配
           FluentWindow 默认背景色，与 page_bg 协调），QPalette 不触发
           QSS 级联 repolish，setPalette/update 极快。
        3. themeChanged 触发 setPalette + update，让背景跟随主题。
        """
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QColor, QPalette
            from qfluentwidgets import isDarkTheme, qconfig
            from qfluentwidgets.common.style_sheet import styleSheetManager

            sw = self.stackedWidget
            styleSheetManager.deregister(sw)
            sw.setAttribute(Qt.WA_StyledBackground, False)
            sw.setAutoFillBackground(True)

            def _refresh():
                # 匹配 qfluentwidgets FluentWidget 默认背景色
                # (_lightBackgroundColor / _darkBackgroundColor)
                bg = QColor(32, 32, 32) if isDarkTheme() else QColor(240, 244, 249)
                pal = sw.palette()
                pal.setColor(QPalette.Window, bg)
                sw.setPalette(pal)
                sw.update()

            _refresh()
            qconfig.themeChanged.connect(_refresh)
        except Exception:  # noqa: BLE001 - 库接口差异时静默跳过
            pass

    def closeEvent(self, e):
        # 强制退出（托盘右键/单实例激活等）不弹确认
        if getattr(self, "_force_quit", False):
            super().closeEvent(e)
            return

        # 关闭确认：未勾选"不再提醒"时弹出选择对话框。
        # 决策必须在任何收尾工作（快照/面板保存/资源释放）之前执行，
        # 避免：① 弹窗延迟出现导致白屏；② 取消/缩托盘时误触发耗时收尾。
        decided = None  # None=继续退出 / "tray"=缩托盘 / "cancel"=取消关闭
        try:
            if self.services.get_pref("close_confirm", True):
                from gui_qt.components.dialog import CloseConfirmDialog
                dlg = CloseConfirmDialog(self)
                dlg.move(self.frameGeometry().center() - dlg.rect().center())
                if dlg.exec() != QDialog.Accepted or dlg.result is None:
                    decided = "cancel"
                else:
                    if dlg.dont_ask_again:
                        self.services.set_pref("close_confirm", False)
                        self.services.set_pref("close_action", dlg.result)
                    decided = dlg.result  # "quit" / "tray"
            else:
                # 已设置"不再提醒"：按记住的动作执行
                decided = self.services.get_pref("close_action", "quit")
        except Exception:  # noqa: BLE001 - 决策出错：取消关闭并提示
            from app import logger
            logger.error("[close] close decision error", exc_info=True)
            try:
                from gui_qt.components import toast
                toast.show_error(
                    self, tr("关闭处理出错，已取消关闭",
                             "Error while closing; operation canceled"))
            except Exception:  # noqa: BLE001
                pass
            e.ignore()
            return

        # ── 决策执行 ──
        if decided == "tray":
            try:
                self._ensure_tray()
            except Exception:  # noqa: BLE001
                from app import logger
                logger.error("[close] tray setup error", exc_info=True)
            e.ignore()
            self.hide()
            return
        if decided == "cancel":
            e.ignore()
            return

        # ── 确认退出：现在才做收尾（耗时操作不在弹窗前执行）──
        # 快照立即写盘（防抖定时器在退出时可能尚未触发）
        tm = getattr(self, "task_manager", None)
        if tm and hasattr(tm, "flush_snapshot"):
            try:
                tm.flush_snapshot()
            except Exception:  # noqa: BLE001
                pass
        # 面板偏好收尾保存：只遍历"已实际构建"的面板。
        # 未访问过的面板是 LazyPage 占位（_real 为 None）——访问其属性会
        # 触发真实构造（每个 25-500ms，42 个全触发 = 秒级卡顿）。
        # 未打开的面板没有用户交互，偏好无需收尾；已打开的面板交互时
        # 已通过防抖自动保存，这里只兜底防抖定时器仍挂起的。
        try:
            from gui_qt.services import QT_PREFS_PANEL
            panels = {}
            for page in self.pages.values():
                # LazyPage：只处理已构建的；普通页面（home）直接处理
                real = getattr(page, "_real", page)
                if real is None:
                    continue
                timer = getattr(real, "_prefs_timer", None)
                if timer is not None and not timer.isActive():
                    continue  # 已保存或从未修改
                collect = getattr(real, "collect_prefs", None)
                if not callable(collect):
                    continue
                try:
                    prefs = collect()
                except Exception:  # noqa: BLE001
                    prefs = {}
                if prefs:
                    key = getattr(real, "_prefs_key", None)
                    panels[key() if callable(key) else "panel_unknown"] = prefs
            if panels:
                self.services.prefs.save_panel_batch({QT_PREFS_PANEL: panels})
        except Exception:  # noqa: BLE001
            pass
        # 面板资源释放（如 PDF 编辑器关闭文档/等待缩略图线程）。
        # 只处理已构建的面板——访问 LazyPage 属性会触发真面板构造（秒级卡顿）。
        for page in self.pages.values():
            real = getattr(page, "_real", page)
            if real is None:
                continue
            cleanup = getattr(real, "cleanup", None)
            if callable(cleanup):
                try:
                    cleanup()
                except Exception:  # noqa: BLE001
                    pass

        # 窗口状态记忆（设置开启时）
        try:
            if self.services.get_pref("remember_window", True):
                self._save_window_state()
        except Exception:  # noqa: BLE001
            pass
        # 退出时清理转换临时文件（设置开启时，按分类勾选执行）
        try:
            if self.services.get_pref("cleanup_temp_on_exit", False):
                from utils.temp_cleanup import cleanup_temp_files
                cats = ["concat", "update"]  # 轻量残留默认清理
                if self.services.get_pref("cleanup_share_dirs", True):
                    cats.append("share")
                if self.services.get_pref("cleanup_m3u8_dirs", True):
                    cats.append("m3u8")
                cleanup_temp_files(cats)
        except Exception:  # noqa: BLE001
            pass

        # 偏好兜底落盘：后台合并写的脏数据在退出前同步刷出
        # （_save_window_state 等走 set_pref → 后台写，不 flush 会丢）
        try:
            self.services.prefs.flush()
        except Exception:  # noqa: BLE001
            pass

        super().closeEvent(e)

    def _ensure_tray(self):
        """确保系统托盘图标已创建并显示（关闭→托盘时使用）。"""
        self.services.set_pref("tray", True)
        self._setup_tray()


_SINGLE_INSTANCE_SHM = None   # 持有引用，防止锁被 GC 释放


def _try_acquire_single_instance():
    """单实例锁（QSharedMemory 跨进程互斥）。

    返回 True 表示本进程是首个实例；False 表示已有实例在运行，
    此时激活已有窗口并让本进程退出（避免任务管理器出现多个进程）。
    进程被强制结束可能残留锁：自动探测并清理一次，避免程序打不开。
    """
    global _SINGLE_INSTANCE_SHM
    from PySide6.QtCore import QSharedMemory

    def _acquire():
        shm = QSharedMemory("FormatMaster_SingleInstance_v1")
        if shm.create(1):
            return shm
        return None

    try:
        shm = _acquire()
        if shm is None:
            # 区分「有活动实例」与「残留锁（原进程崩溃）」
            probe = QSharedMemory("FormatMaster_SingleInstance_v1")
            if probe.attach():
                # 有活动实例：激活其窗口后退出本进程
                probe.detach()
                _activate_existing_window()
                return False
            # 残留锁：清理后重试一次
            probe.detach()
            shm = _acquire()
            if shm is not None:
                _SINGLE_INSTANCE_SHM = shm
                return True
            # 仍失败：可能刚被其它实例抢到，视为已有实例
            _activate_existing_window()
            return False
        _SINGLE_INSTANCE_SHM = shm
        return True
    except Exception:  # noqa: BLE001 - 锁失败不阻止启动（降级为多实例）
        return True


def _activate_existing_window():
    """找到已运行的格式大师主窗口并激活（还原最小化后置前）。"""
    try:
        import ctypes
        u32 = ctypes.windll.user32
        for title in ("格式大师", "FormatMaster"):
            hwnd = u32.FindWindowW(None, title)
            if hwnd:
                if u32.IsIconic(hwnd):
                    u32.ShowWindow(hwnd, 9)   # SW_RESTORE
                u32.SetForegroundWindow(hwnd)
                break
    except Exception:  # noqa: BLE001
        pass


def restart_application(window=None):
    """重启程序：释放单实例锁 → 启动新实例 → 退出当前实例。

    用于工具（FFmpeg/yt-dlp）更新完成后自动重启，让新版本生效——
    版本号、硬件加速检测、ffmpeg 路径缓存等都需重新初始化。
    window 传入时标记强制退出，跳过「关闭确认」对话框。
    """
    global _SINGLE_INSTANCE_SHM

    # 标记强制退出：跳过关闭确认对话框（否则重启会卡在「关闭确认」）
    if window is not None:
        try:
            window._force_quit = True
        except Exception:  # noqa: BLE001
            pass

    # 释放单实例锁：否则新实例检测到已有实例会激活旧窗口并退出
    try:
        if _SINGLE_INSTANCE_SHM is not None:
            _SINGLE_INSTANCE_SHM.detach()
            _SINGLE_INSTANCE_SHM = None
    except Exception:  # noqa: BLE001
        pass

    # 启动新实例（不带任何启动参数，恢复干净主界面）
    try:
        import subprocess
        from utils.config import get_app_dir, _is_frozen
        app_dir = get_app_dir()
        if _is_frozen():
            cmd = [sys.executable]
        else:
            cmd = [sys.executable, os.path.join(app_dir, "main_qt.py")]
        # CREATE_NO_WINDOW：静默拉起新实例，不闪现控制台黑框
        flags = 0x08000000 if os.name == "nt" else 0
        subprocess.Popen(cmd, cwd=app_dir, creationflags=flags)
    except Exception:  # noqa: BLE001 - 启动新实例失败仍退出旧实例
        pass

    # 退出当前实例
    QApplication.quit()


def _update_check_due(get_pref):
    """按设置「更新检查频率」判断本次启动是否应检查更新。"""
    try:
        freq = get_pref("update_check_freq", "always")
        if freq == "always":
            return True
        import datetime
        today = datetime.date.today().isoformat()
        last = get_pref("update_last_check", "") or ""
        if freq == "daily":
            return last != today
        if freq == "weekly":
            if not last:
                return True
            try:
                from datetime import date
                return (date.today() - date.fromisoformat(last)).days >= 7
            except ValueError:
                return True
    except Exception:  # noqa: BLE001
        return True
    return True


def _install_crash_logging():
    """安装全局异常兜底：未捕获异常/原生崩溃写入 %APPDATA%/FormatMaster/crash.log。

    用于定位"任务完成后闪退"等难以复现的问题——下次崩溃时
    crash.log 会记录完整 traceback（或 faulthandler 线程栈），可据此修复。
    """
    try:
        from utils.config import get_user_data_dir
        import time as _time
        crash_path = os.path.join(get_user_data_dir(), "crash.log")

        def _hook(exc_type, exc_val, exc_tb):
            import traceback
            try:
                with open(crash_path, "a", encoding="utf-8") as f:
                    f.write(f"\n[{_time.strftime('%Y-%m-%d %H:%M:%S')}] "
                            f"未捕获异常: {exc_type.__name__}: {exc_val}\n")
                    traceback.print_tb(exc_tb, file=f)
            except Exception:
                pass
            # 保持默认行为（打印 + 退出）
            sys.__excepthook__(exc_type, exc_val, exc_tb)

        sys.excepthook = _hook
        # 原生崩溃（段错误/C 扩展 abort）也记录线程栈
        import faulthandler
        with open(crash_path, "a", encoding="utf-8") as f:
            faulthandler.enable(file=f)
    except Exception:  # noqa: BLE001 - 日志兜底失败不影响启动
        pass


def run(convert_path=None):
    """应用入口：python main_qt.py

    convert_path: 右键菜单 --convert 传入的文件路径，启动后自动打开
    对应面板并添加文件（见 _auto_open_convert_file）。
    """
    _install_crash_logging()
    # 崩溃弹窗（未捕获异常 → 主线程弹出错误反馈对话框，链式保留 crash.log）
    try:
        from app.crash_report import install_crash_handler
        install_crash_handler()
    except Exception:  # noqa: BLE001
        pass
    # 语言偏好已在 main_qt.py 预加载（必须在 import gui_qt.app 之前），
    # 此处不再重复读取 user_prefs.json，避免冗余磁盘 I/O。
    app = QApplication(sys.argv)
    app.setApplicationName("FormatMaster")

    # ── 应用/窗口图标：任务栏显示（exe 的 --icon 只影响文件图标，
    # 运行时窗口图标需显式设置；开发与打包双路径由 get_resource_path 处理）──
    try:
        from PySide6.QtGui import QIcon
        from utils.config import get_resource_path
        _icon_path = get_resource_path(os.path.join("assets", "icon.ico"))
        if os.path.isfile(_icon_path):
            app.setWindowIcon(QIcon(_icon_path))
    except Exception:  # noqa: BLE001 - 图标失败不影响启动
        pass

    # ── 字体：使用系统默认字体（微软雅黑/Segoe UI）──
    # 不再加载/指定 MiSans：qfluentwidgets 保持库默认 fontFamilies
    # （['Segoe UI', 'Microsoft YaHei', 'PingFang SC']），全局字体由
    # MainWindow 按 FONT_BODY（Microsoft YaHei）设置，观感即系统默认。

    # ── 单实例锁：已有实例时激活其窗口并退出本进程 ──
    if not _try_acquire_single_instance():
        return

    # ── 预加载 PyMuPDF（消除 GC 竞态崩溃）────────────────
    # pymupdf 的模块级 C 扩展对象在 import 过程的密集分配会触发 Python GC，
    # 若此时后台线程正跑 subprocess（首页工具版本检查 yt-dlp --version /
    # 系统信息采集 PowerShell）会出现线程间访问冲突（access violation，
    # 实测稳定复现于 offscreen 快速切换 pdf_editor 页面）。
    # 在启动早期（尚无任何后台线程）同步完成 import，之后 prewarm/页面
    # 切换全部命中缓存，import 密集 GC 窗口不再与子进程线程并发。
    try:
        import pymupdf  # noqa: F401
    except Exception:  # noqa: BLE001 - 预加载失败不影响启动
        pass

    # ── 全局修复：ComboBox 弹窗强制向下 ────────
    ds.fix_combobox_popup_direction()

    # ── 启动画面（QSplashScreen）：主窗口构建期间显示品牌 Logo，
    #     窗口就绪后 finish() 平滑关闭，掩盖初始化等待。失败静默跳过。
    # 注：qfluentwidgets SplashScreen 的 IconWidget 与 PySide6 6.11 存在
    # overload 兼容问题，用 Qt 内置 QSplashScreen + 程序化启动图替代。
    #     设置页「常规 → 启动画面」可关闭（快速启动的机器可选跳过）。──
    splash = None
    try:
        from utils.config import USER_PREFS
        if USER_PREFS.get("qt_app", "show_splash", True):
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
            from PySide6.QtWidgets import QSplashScreen
            _pm = QPixmap(420, 240)
            _pm.fill(QColor("#2F6BFF"))
            _p = QPainter(_pm)
            _p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
            _icon_pm = app.windowIcon().pixmap(64, 64)
            _p.drawPixmap((420 - 64) // 2, 42, 64, 64, _icon_pm)
            _p.setPen(QColor("white"))
            _p.setFont(QFont("Microsoft YaHei", 19, QFont.Weight.Bold))
            _p.drawText(0, 128, 420, 44, Qt.AlignmentFlag.AlignHCenter,
                        tr("格式大师", "FormatMaster"))
            _p.setFont(QFont("Microsoft YaHei", 11))
            _p.setOpacity(0.85)
            _p.drawText(0, 172, 420, 30, Qt.AlignmentFlag.AlignHCenter,
                        tr("全能格式转换工具", "All-in-one format converter"))
            _p.end()
            splash = QSplashScreen(_pm)
            splash.show()
            splash.showMessage(tr("正在启动…", "Starting…"),
                               Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
                               QColor("white"))
            app.processEvents()
    except Exception:  # noqa: BLE001 - 启动画面失败不影响启动
        splash = None

    window = MainWindow()

    # ── 启动后全局优化 ───────────────────────
    ds.enable_smooth_scrolling(window)
    ds.install_scroll_speed_booster(app)

    # ── 后台预检测硬件加速（避免首次打开视频面板时同步卡顿 ~500ms）──
    try:
        from utils.hardware_accel import prewarm_hw_accel_async
        prewarm_hw_accel_async()
    except Exception:  # noqa: BLE001 - 预热失败不影响启动
        pass

    # ── 启动时后台检查更新（不阻塞）──
    # 由下方「程序自身自动更新」块统一处理（12 秒后检查 + 自动下载弹窗）

    window.show()
    # 主窗口就绪：平滑关闭启动画面（若创建成功）
    if splash is not None:
        try:
            splash.finish(window)
        except Exception:  # noqa: BLE001 - 关闭失败不影响
            pass

    # ── 分帧预热懒加载页面：消除首次点击侧边栏功能时的构建卡顿 ──
    # 延迟 600ms 启动：让首页先稳定显示、用户先看到内容，再在后台
    # 空闲分帧构建其余页面，避免 show 后立即抢占 UI 造成启动卡顿。
    from PySide6.QtCore import QTimer
    from gui_qt.components.sidebar import start_prewarm
    QTimer.singleShot(200, lambda: start_prewarm(window))

    # ── 工具（FFmpeg/yt-dlp）版本检测：后台自动检测，发现新版本弹确认框 ──
    # 延迟 8 秒：避开启动初期的页面预热/硬件检测；检测走后台线程不阻塞 UI。
    # 挂到 window._tool_checker，供工具状态卡片「检查更新」按钮手动触发。
    try:
        from gui_qt.components.tool_update_checker import (
            ToolUpdateChecker, show_tool_update_dialog,
            show_tool_unreachable_notice)
        from gui_qt.components import toast
        window._tool_checker = ToolUpdateChecker(window)
        window._tool_checker.found.connect(
            lambda ups: show_tool_update_dialog(window, ups))
        window._tool_checker.finished.connect(
            lambda ups: (show_tool_unreachable_notice(window, ups)
                         if ups else toast.show_info(window, tr("已是最新版本", "Already up to date"))))
        # 启动后立即（500ms）后台预热 yt-dlp 本地版本：yt-dlp.exe 是
        # PyInstaller 单文件，--version 首次要解压约 7 秒。提前预热后，
        # 8s 自动检测与用户手动点「检查更新」都命中缓存，秒出结果，
        # 不再让用户干等 7 秒。
        try:
            import threading as _th
            from core.tool_updater import current_ytdlp_version
            QTimer.singleShot(500, lambda: _th.Thread(
                target=current_ytdlp_version, daemon=True).start())
        except Exception:  # noqa: BLE001 - 预热失败不影响
            pass
        QTimer.singleShot(8000, lambda: window._tool_checker.check_async(notify=False))
    except Exception:  # noqa: BLE001 - 检测初始化失败不影响启动
        pass

    # ── 应用网络代理设置（urllib 体系自动读取环境变量，全局生效）──
    try:
        from utils.net_proxy import proxy_from_prefs
        proxy_from_prefs(window.services.get_pref)
    except Exception:  # noqa: BLE001 - 代理设置失败不影响启动
        pass

    # ── 应用日志级别与保留份数（设置优先，覆盖环境变量默认）──
    try:
        from app import logger
        logger.configure(
            level=window.services.get_pref("log_level", "debug"),
            backup_count=window.services.get_pref("log_backup", 1))
    except Exception:  # noqa: BLE001 - 日志配置失败不影响启动
        pass

    # ── 程序自身自动更新：启动后检查 GitHub Releases 新版本 ──
    # 延迟 12 秒避开启动高峰；尊重设置「启动时检查更新」开关（默认开）；
    # 发现新版 → prompt_app_update 弹确认框，确认后镜像下载更新包 →
    # 替换文件 → 自动重启。开发模式也会检查并提示（自动替换仅打包版可用）。
    try:
        from gui_qt.components.app_update_checker import (
            AppUpdateChecker, prompt_app_update)
        # 清理上次更新成功后的旧版备份残留（_fm_old，回滚式替换的安全网）
        try:
            import sys as _sys
            from core.app_updater import cleanup_backup
            if getattr(_sys, "frozen", False):
                cleanup_backup(os.path.dirname(_sys.executable))
        except Exception:  # noqa: BLE001 - 备份清理失败不影响启动
            pass
        if window.services.get_pref("check_update_on_start", True) \
                and _update_check_due(window.services.get_pref):
            # 记录本次检查日期（供 daily/weekly 频率判断）
            try:
                import datetime as _dt
                window.services.set_pref(
                    "update_last_check", _dt.date.today().isoformat())
            except Exception:  # noqa: BLE001
                pass
            window._app_update = AppUpdateChecker(window)
            window._app_update.found.connect(
                lambda v: prompt_app_update(window, v))
            QTimer.singleShot(12000, lambda: window._app_update.check_async())
    except Exception:  # noqa: BLE001 - 自更新初始化失败不影响启动
        pass

    # ── 右键菜单 --convert：窗口就绪后自动打开对应面板并添加文件 ──
    if convert_path and os.path.isfile(convert_path):
        from PySide6.QtCore import QTimer
        QTimer.singleShot(
            400, lambda: _auto_open_convert_file(window, convert_path))

    sys.exit(app.exec())


# 扩展名 → 面板 key（右键菜单自动路由）
_CONVERT_ROUTE = [
    ("video", {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
               ".m4v", ".mpg", ".mpeg", ".ts"}),
    ("audio", {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma"}),
    ("image", {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff",
               ".webp", ".ico", ".tga", ".avif"}),
    ("document", {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt",
                  ".pptx", ".txt"}),
]


def _auto_open_convert_file(window, path):
    """右键菜单打开：按扩展名路由到对应面板并添加文件。"""
    try:
        ext = os.path.splitext(path)[1].lower()
        for key, exts in _CONVERT_ROUTE:
            if ext in exts and key in window.pages:
                page = window.pages[key]
                window.switchTo(page)
                fc = getattr(page, "file_card", None)
                if fc is not None and hasattr(fc, "add_files"):
                    fc.add_files([path])
                return
    except Exception:  # noqa: BLE001 - 路由失败不影响应用启动
        pass


# （旧的 _check_update_on_startup 已移除：启动检查统一由 AppUpdateChecker 处理，
#   弹「立即更新」→ 镜像下载更新包 → 替换 → 自动重启，不再跳浏览器）
