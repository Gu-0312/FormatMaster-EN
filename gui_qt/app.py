"""app — PySide6 应用引导与主窗口（Prism 设计系统）。

MainWindow：FluentWindow + Mica 云母背景（Win11，Win10 自动降级）
+ 侧边导航（nav_registry 全量注册）+ 亮/暗/跟随系统主题。
启动时应用 Prism 设计系统全局样式。
"""
from gui_qt.i18n import tr
import os
import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
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
        self._init_size()  # 按当前屏幕可用区域自适应初始尺寸
        self.setObjectName("FluentWindow")
        self._center_on_screen()

        # ── 全局字体 ──────────────────────────────
        # 用 setPointSizeF 指定逻辑点数，Qt 在高 DPI 下自动换算物理像素，
        # 保证 1080p / 2K / 4K 等不同缩放下文字大小一致且锐利。
        font = QFont("Microsoft YaHei UI")
        font.setPointSizeF(9.5)
        QApplication.instance().setFont(font)

        # ── 服务容器 ─────────────────────────────
        self.services = QtServices()
        self.theme_mgr = ThemeManager(self.services)
        self.services.theme_mgr = self.theme_mgr

        # ── 语言（必须在导航构建前设置，导航文案随语言渲染）──
        from gui_qt import i18n
        i18n.set_language(self.services.get_pref("language", "zh"))

        # ── Prism 窗口注册（必须在 apply_saved 之前，
        #     确保 QSS 作用域为窗口级而非全局 app）──
        ds.set_app_window(self)
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

    def _init_size(self):
        """初始窗口尺寸自适应屏幕。

        以 1080p（1920×1080）下的 1280×820 为基准，按当前屏幕
        可用区域等比放大；屏幕更小时按比例收缩，保证不超过
        可用区域。2K / 4K 等大屏自动获得更大的初始窗口。
        """
        try:
            screen = QApplication.primaryScreen()
            if screen is None:
                self.resize(1280, 820)
                return
            sg = screen.availableGeometry()
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

    def switchTo(self, interface):
        """切换页面时清理当前窗口的 InfoBar 提示。"""
        from gui_qt.components import toast
        toast.close_all()
        super().switchTo(interface)

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
        """所有任务完成后的钩子：提示音 + 自动打开输出目录。"""
        import os
        # 提示音
        if self.services.get_pref("notify_sound", True):
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_OK)
            except Exception:
                pass
        # 自动打开输出目录（取最后一个成功的输出目录）
        if self.services.get_pref("open_dir_on_done", False):
            mgr = self.task_manager
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
        if not _is_win11():
            return
        try:
            self.windowEffect.setMicaEffect(self.winId(),
                                            isDarkMode=isDarkTheme())
        except Exception:  # noqa: BLE001 - 特效失败不应阻断启动
            pass

    def closeEvent(self, e):
        # 面板偏好收尾保存（视频面板等）
        for page in self.pages.values():
            save = getattr(page, "save_prefs", None)
            if callable(save):
                try:
                    save()
                except Exception:  # noqa: BLE001
                    pass
        # 面板资源释放（如 PDF 编辑器关闭文档/等待缩略图线程）
        for page in self.pages.values():
            cleanup = getattr(page, "cleanup", None)
            if callable(cleanup):
                try:
                    cleanup()
                except Exception:  # noqa: BLE001
                    pass
        super().closeEvent(e)


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
    # 提前加载语言偏好（main_qt.py 已做，此处兜底保证 run() 直接调用也生效——
    # config 等模块的模块级 tr() 需要正确语言）
    try:
        import json as _json
        from gui_qt.i18n import set_language
        from utils.config import get_user_data_dir
        _p = os.path.join(get_user_data_dir(), "user_prefs.json")
        _lang = "zh"
        if os.path.isfile(_p):
            with open(_p, encoding="utf-8") as _f:
                _lang = _json.load(_f).get("language", "zh")
        set_language(_lang)
    except Exception:  # noqa: BLE001
        pass
    app = QApplication(sys.argv)
    app.setApplicationName("FormatMaster")

    # ── 全局修复：ComboBox 弹窗强制向下 ────────
    ds.fix_combobox_popup_direction()

    window = MainWindow()

    # ── 启动后全局优化 ───────────────────────
    ds.enable_smooth_scrolling(window)
    ds.install_scroll_speed_booster(app)

    # ── 启动时后台检查更新（不阻塞；有新版则弹提示）──
    _check_update_on_startup(window)

    window.show()

    # ── 强制展开侧边导航栏（COMPACT→EXPAND，显示文字）──
    window.navigationInterface.panel._isMenuButtonVisible = False
    window.navigationInterface.panel.expand(False)

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


def _check_update_on_startup(window):
    """启动后延迟 3 秒后台检查更新，发现新版本弹窗提示。

    网络失败/超时静默忽略，绝不阻塞启动。
    """
    from PySide6.QtCore import QTimer
    from gui_qt.update_checker import (UpdateChecker, show_update_dialog,
                                       version_gt)
    from utils.config import APP_VERSION

    def _start():
        checker = UpdateChecker(window)

        def _done(version, url):
            if version and version_gt(version, APP_VERSION):
                show_update_dialog(window, version, url)

        checker.checked.connect(_done)
        checker.check_async()

    # 延迟到主窗口显示后，避免启动时弹窗干扰
    QTimer.singleShot(3000, _start)
