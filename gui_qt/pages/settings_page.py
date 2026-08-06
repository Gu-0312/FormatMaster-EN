"""settings_page — 设置中心（Fluent SettingsCard 分组）。

分组：常规 / 主题 / 转换 / 高级。全部持久化到 USER_PREFS 的
qt_app 面板键（与 tkinter 旧偏好隔离）。开机启动走 Windows 注册表 Run 键。
"""
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QVBoxLayout, QWidget
from qfluentwidgets import (ComboBox, ExpandLayout, FluentIcon,
                            PushSettingCard, ScrollArea, SettingCard,
                            SettingCardGroup, SwitchSettingCard)

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
            FluentIcon.POWER_BUTTON, "开机启动", "登录 Windows 后自动运行格式大师",
            parent=g)
        self.card_autostart.setValue(_autostart_enabled())
        self.card_autostart.checkedChanged.connect(self._on_autostart)
        g.addSettingCard(self.card_autostart)

        self.card_tray = SwitchSettingCard(
            FluentIcon.BACKGROUND_FILL, "系统托盘", "关闭时最小化到托盘而不是退出",
            parent=g)
        self.card_tray.setValue(bool(self.services.get_pref("tray", False)))
        self.card_tray.checkedChanged.connect(
            lambda on: self.services.set_pref("tray", bool(on)))
        g.addSettingCard(self.card_tray)

        self.card_outdir = PushSettingCard(
            self.services.get_pref("default_out_dir", "") or "未设置",
            FluentIcon.FOLDER, "默认输出目录",
            "自定义目录不存在时会自动创建", g)
        self.card_outdir.clicked.connect(self._pick_outdir)
        g.addSettingCard(self.card_outdir)

        from gui_qt import i18n
        self.card_lang = _ComboSettingCard(
            FluentIcon.LANGUAGE, "界面语言",
            "简体中文 / English，切换后重启应用生效",
            ["简体中文", "English"], g)
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
            self, "语言已切换，重启应用后生效"
            if lang == "en" else
            "Language switched, restart to apply")

    def _on_autostart(self, on):
        from gui_qt.components import toast
        if _set_autostart(bool(on)):
            toast.show_success(self, tr("开机启动", "Launch at startup") + ("已开启" if on else "已关闭"))
        else:
            toast.show_error(self, "设置开机启动失败（注册表写入被拒绝）")
            self.card_autostart.setValue(_autostart_enabled())

    def _pick_outdir(self):
        d = QFileDialog.getExistingDirectory(self, "选择默认输出目录")
        if d:
            self.services.set_pref("default_out_dir", d)
            self.card_outdir.setContent(d)

    # ── 主题 ─────────────────────────────────────
    def _build_theme(self):
        g = self._group("主题")
        self.card_theme = _ComboSettingCard(
            FluentIcon.BRIGHTNESS, "应用主题", "浅色 / 深色 / 跟随系统",
            MODES, g)
        cur = self.theme_mgr.current_mode()
        self.card_theme.comboBox.setCurrentText(
            cur if cur in MODES else MODE_AUTO)
        self.card_theme.comboBox.currentTextChanged.connect(
            self.theme_mgr.set_mode)
        g.addSettingCard(self.card_theme)

    # ── 转换 ─────────────────────────────────────
    def _build_convert(self):
        g = self._group("转换")

        self.card_fmt = _ComboSettingCard(
            FluentIcon.VIDEO, "默认视频格式", "新会话的默认目标格式",
            list(SUPPORTED_VIDEO), g)
        self.card_fmt.comboBox.setCurrentText(
            self.services.get_pref("default_fmt", "MP4"))
        self.card_fmt.comboBox.currentTextChanged.connect(
            lambda t: self.services.set_pref("default_fmt", t))
        g.addSettingCard(self.card_fmt)

        self.card_codec = _ComboSettingCard(
            FluentIcon.CODE, "默认编码器", "「默认」表示按容器自动选择",
            list(VIDEO_CODECS), g)
        self.card_codec.comboBox.setCurrentText(
            self.services.get_pref("default_codec", "默认"))
        self.card_codec.comboBox.currentTextChanged.connect(
            lambda t: self.services.set_pref("default_codec", t))
        g.addSettingCard(self.card_codec)

        self.card_gpu = SwitchSettingCard(
            FluentIcon.SPEED_HIGH, "GPU 加速", "默认启用硬件加速（失败自动降级 CPU）",
            parent=g)
        self.card_gpu.setValue(bool(self.services.get_pref("gpu_accel", True)))
        self.card_gpu.checkedChanged.connect(
            lambda on: self.services.set_pref("gpu_accel", bool(on)))
        g.addSettingCard(self.card_gpu)

        self.card_parallel = _ComboSettingCard(
            FluentIcon.SYNC, "并行转换", "同时执行的任务数（建议 1~4）",
            ["1", "2", "3", "4", "6", "8"], g)
        self.card_parallel.comboBox.setCurrentText(
            str(self.services.get_pref("parallel", 1)))
        self.card_parallel.comboBox.currentTextChanged.connect(
            self._on_parallel_changed)
        g.addSettingCard(self.card_parallel)

        self.card_retry = _ComboSettingCard(
            FluentIcon.RETURN, "失败重试", "转换失败后自动重试的次数",
            ["0", "1", "2", "3"], g)
        self.card_retry.comboBox.setCurrentText(
            str(self.services.get_pref("max_retries", 0)))
        self.card_retry.comboBox.currentTextChanged.connect(
            lambda t: self.services.set_pref("max_retries", int(t)))
        g.addSettingCard(self.card_retry)

        self.card_open_dir = SwitchSettingCard(
            FluentIcon.FOLDER, "转换后打开输出目录",
            "所有任务完成后自动打开输出文件夹",
            parent=g)
        self.card_open_dir.setValue(bool(self.services.get_pref("open_dir_on_done", False)))
        self.card_open_dir.checkedChanged.connect(
            lambda on: self.services.set_pref("open_dir_on_done", bool(on)))
        g.addSettingCard(self.card_open_dir)

        self.card_notify_sound = SwitchSettingCard(
            FluentIcon.PLAY, "完成提示音",
            "转换成功后播放系统提示音",
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
            "已安装" if _cm.installed() else "未安装", FluentIcon.MENU,
            "文件右键菜单",
            "右键任意文件 →「用格式大师转换」直接打开；点击切换安装状态", g)
        self.card_menu.clicked.connect(self._toggle_context_menu)
        g.addSettingCard(self.card_menu)

        ffmpeg_path = get_ffmpeg_path() or "未找到"
        self.card_ffmpeg = PushSettingCard(
            ffmpeg_path, FluentIcon.COMMAND_PROMPT, "FFmpeg 路径",
            "点击重新检测；缺失时自动下载", g)
        self.card_ffmpeg.clicked.connect(self._redetect_ffmpeg)
        g.addSettingCard(self.card_ffmpeg)

        self.card_debug = SwitchSettingCard(
            FluentIcon.DEVELOPER_TOOLS, "调试模式", "输出更详细的调试日志",
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
                toast.show_error(self, f"卸载失败：{err}")
                return
            self.card_menu.setContent("未安装")
            toast.show_info(self, "已卸载右键菜单")
        else:
            err = cm.install()
            if err:
                toast.show_error(self, f"安装失败：{err}")
                return
            self.card_menu.setContent("已安装")
            toast.show_success(self, "已安装右键菜单")

    def _redetect_ffmpeg(self):
        from gui_qt.components import toast
        if self.services.ffmpeg_ready():
            self.card_ffmpeg.setContent(get_ffmpeg_path() or "未找到")
            toast.show_success(self, "FFmpeg 已就绪")
            return
        toast.show_info(self, "FFmpeg 缺失，正在后台下载…")

        def _done(ok):
            # 下载线程回调：通过 QTimer 切回主线程刷新 UI
            from PySide6.QtCore import QTimer

            def _update():
                if ok:
                    self.card_ffmpeg.setContent(get_ffmpeg_path() or "未找到")
                    toast.show_success(self, "FFmpeg 下载完成")
                else:
                    toast.show_error(self, "FFmpeg 下载失败，请检查网络")
            QTimer.singleShot(0, _update)
        self.services.ffmpeg_mgr.download_async(callback=_done)
