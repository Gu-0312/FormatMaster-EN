"""settings_page — 设置中心（Fluent SettingsCard 分组）。

分组：常规 / 主题 / 转换 / 高级。全部持久化到 USER_PREFS 的
qt_app 面板键（与 tkinter 旧偏好隔离）。开机启动走 Windows 注册表 Run 键。
"""
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QVBoxLayout, QWidget
from qfluentwidgets import (ComboBox, ExpandLayout, FluentIcon,
                            PrimaryPushButton, PushSettingCard, ScrollArea,
                            SettingCard, SettingCardGroup, SwitchSettingCard)

from gui_qt.i18n import tr
from gui_qt.components.page_header import PageHeader
from gui_qt.components.theme_manager import (MODE_AUTO, MODE_DARK,
                                             MODE_LIGHT, MODES)
from gui_qt.components import design_system as ds
from utils.config import get_ffmpeg_path, SUPPORTED_VIDEO, VIDEO_CODECS


class _ComboSettingCard(SettingCard):
    """带下拉框的设置卡（偏好存 USER_PREFS，不依赖 qconfig）。"""

    def __init__(self, icon, title, content, texts, parent=None):
        super().__init__(icon, title, content, parent)
        self.comboBox = ComboBox(self)
        self.comboBox.addItems(texts)
        self.comboBox.setFixedWidth(170)
        self.hBoxLayout.addWidget(self.comboBox, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

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


class SettingsPage(ScrollArea):
    """设置中心页。"""

    def __init__(self, window, services, parent=None):
        super().__init__(parent)
        self.setObjectName("settings")
        self.window = window
        self.services = services
        self.theme_mgr = services.theme_mgr
        self.setWidgetResizable(True)
        self.setViewportMargins(0, 0, 0, 0)

        self.scroll_widget = QWidget()
        self.expand_layout = ExpandLayout(self.scroll_widget)
        self.expand_layout.setContentsMargins(24, 20, 24, 0)
        self.expand_layout.setSpacing(12)
        self.setWidget(self.scroll_widget)
        self.scroll_widget.setAutoFillBackground(False)

        # ── 页面标题 ───────────────────────────────
        self._build_header()

        self._build_general()
        self._build_theme()
        self._build_convert()
        self._build_advanced()

    def _group(self, title):
        # 必须以 scroll_widget 为父容器，否则分组不会显示
        g = SettingCardGroup(title, self.scroll_widget)
        self.expand_layout.addWidget(g)
        return g

    def _build_header(self):
        """页面标题区域。"""
        self.expand_layout.addWidget(PageHeader(
            tr("设置中心", "Settings"), tr("自定义应用行为、主题、编码与高级选项", "Customize behavior, theme, codecs and advanced options"),
            icon=FluentIcon.SETTING))

    # ── 常规 ─────────────────────────────────────
    def _build_general(self):
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

        # 默认输出目录：显式"浏览…"按钮选择目录，路径显示在卡片内容区
        self.card_outdir = SettingCard(
            FluentIcon.FOLDER, tr("默认输出目录", "Default output folder"),
            tr("自定义目录不存在时会自动创建", "Auto-created if the folder does not exist"), g)
        _d = self.services.get_pref("default_out_dir", "")
        self.card_outdir.setContent(_d or tr("未设置", "Not set"))
        self.btn_browse_outdir = PrimaryPushButton(
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
        setup = getattr(self.window, "_setup_tray", None)
        if callable(setup):
            try:
                setup()
            except Exception:  # noqa: BLE001
                pass

    def _pick_outdir(self):
        d = QFileDialog.getExistingDirectory(self, tr("选择默认输出目录", "Pick default output folder"))
        if d:
            self.services.set_pref("default_out_dir", d)
            self.card_outdir.setContent(d)

    # ── 主题 ─────────────────────────────────────
    def _build_theme(self):
        g = self._group(tr("主题", "Theme"))
        self.card_theme = _ComboSettingCard(
            FluentIcon.BRIGHTNESS, tr("应用主题", "Apply theme"), tr("浅色 / 深色 / 跟随系统", "Light / Dark / System"),
            MODES, g)
        cur = self.theme_mgr.current_mode()
        self.card_theme.comboBox.setCurrentText(
            cur if cur in MODES else MODE_AUTO)
        self.card_theme.comboBox.currentTextChanged.connect(
            self.theme_mgr.set_mode)
        g.addSettingCard(self.card_theme)

    # ── 转换 ─────────────────────────────────────
    def _build_convert(self):
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

    def _on_parallel_changed(self, text):
        n = int(text)
        self.services.set_pref("parallel", n)
        # 运行时调整 TaskManager 并行度
        tm = getattr(self.services, "task_manager", None)
        if tm is not None:
            tm.set_parallel(n)

    # ── 高级 ─────────────────────────────────────
    def _build_advanced(self):
        g = self._group(tr("高级", "Advanced"))

        from gui_qt import context_menu as _cm
        self.card_menu = PushSettingCard(
            tr("已安装", "Installed") if _cm.installed() else tr("未安装", "Not installed"), FluentIcon.MENU,
            tr("文件右键菜单", "Context menu"),
            tr("右键任意文件 →「用格式大师转换」直接打开；点击切换安装状态", "Right-click any file → \"Convert with FormatMaster\"; click to toggle install"), g)
        self.card_menu.clicked.connect(self._toggle_context_menu)
        g.addSettingCard(self.card_menu)

        ffmpeg_path = get_ffmpeg_path() or tr("未找到", "Not found")
        self.card_ffmpeg = PushSettingCard(
            ffmpeg_path, FluentIcon.COMMAND_PROMPT, tr("FFmpeg 路径", "FFmpeg path"),
            tr("点击重新检测；缺失时自动下载", "Click to re-detect; auto-downloads if missing"), g)
        self.card_ffmpeg.clicked.connect(self._redetect_ffmpeg)
        g.addSettingCard(self.card_ffmpeg)

        self.card_debug = SwitchSettingCard(
            FluentIcon.DEVELOPER_TOOLS, tr("调试模式", "Debug mode"), tr("输出更详细的调试日志", "Output more detailed debug logs"),
            parent=g)
        self.card_debug.setValue(bool(self.services.get_pref("debug", False)))
        self.card_debug.checkedChanged.connect(
            lambda on: self.services.set_pref("debug", bool(on)))
        g.addSettingCard(self.card_debug)

    def _toggle_context_menu(self):
        from gui_qt import context_menu as cm
        from gui_qt.components import toast
        if cm.installed():
            err = cm.uninstall()
            if err:
                toast.show_error(self, tr("卸载失败：{}", "Uninstall failed: {}").format(err))
                return
            self.card_menu.setContent(tr("未安装", "Not installed"))
            toast.show_info(self, tr("已卸载右键菜单", "Context menu uninstalled"))
        else:
            err = cm.install()
            if err:
                toast.show_error(self, tr("安装失败：{}", "Install failed: {}").format(err))
                return
            self.card_menu.setContent(tr("已安装", "Installed"))
            toast.show_success(self, tr("已安装右键菜单", "Context menu installed"))

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
