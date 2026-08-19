"""tool_update_checker — 外部工具（FFmpeg / yt-dlp）版本检测与更新协调。

- ToolUpdateChecker：后台线程检测工具新版本，发现后发出 found 信号；
- show_tool_update_dialog：弹确认框，确认后逐个下载替换；
- _update_tools：弹「下载进度」模态对话框实时显示进度，FFmpeg 复用
  FFmpegManager（force 强制替换），yt-dlp 走 core.tool_updater.download_ytdlp
  （下载 GitHub release 单文件 exe）。

下载均在后台线程执行，进度与结果通过 Qt Signal 队列调度回主线程更新
进度条 UI（本项目约定：后台线程回主线程一律用 Signal，禁止
QTimer.singleShot —— 后者在 daemon 线程无事件循环、回调永不触发）。
"""
import threading

from PySide6.QtCore import QObject, Signal

from core import tool_updater
from gui_qt.i18n import tr

_TOOL_NAMES = {"ffmpeg": "FFmpeg", "yt-dlp": "yt-dlp"}


class ToolUpdateChecker(QObject):
    """后台检测工具更新，发现新版本发出 found 信号。"""

    found = Signal(list)      # 发现更新（非空列表）
    finished = Signal(list)   # 检测完成（手动触发且无更新时发出，用于「已是最新」反馈）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._notify = False

    def is_running(self):
        """是否正在检测中。"""
        return self._running

    def check_async(self, notify=False):
        """后台线程检查（可重复调用，内部去重）。

        notify=True：检测完成但无更新时也发 finished 信号（供手动检查反馈）。
        若已有检测进行中：手动触发（notify=True）会更新 notify 标志，让
        当前检测完成后也给出「已是最新」反馈，避免点击「检查更新」无响应。
        """
        if self._running:
            if notify:
                self._notify = True
            return
        self._running = True
        self._notify = notify
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self):
        try:
            updates = tool_updater.check_updates()
            # 拆分「真更新」（可下载）与「受限提示」（官方更高但网络下不到）：
            # 真更新 → found 弹「立即更新」；受限提示只在手动检查时经 finished 展示，
            # 自动检测（notify=False）保持静默，不打扰用户。
            real = [u for u in updates if not u.get("hint")]
            hints = [u for u in updates if u.get("hint")]
            if real:
                self.found.emit(real)
            elif self._notify and hints:
                self.finished.emit(hints)
            elif self._notify:
                self.finished.emit([])
        except Exception:  # noqa: BLE001 - 检测失败静默
            if self._notify:
                self.finished.emit([])
        finally:
            self._running = False


def _update_tools(parent, updates):
    """逐个下载替换工具：弹出带进度条的模态对话框实时显示进度。

    下载在后台线程执行；进度/结果经对话框内部 Signal 队列回主线程。
    对话框 exec() 阻塞当前调用（模态），下载完成自动关闭或失败后用户手动关闭。
    有任一工具更新成功时，提示重启程序以让新版本生效。
    """
    any_ok = False
    for u in updates:
        tool = u["tool"]
        name = _TOOL_NAMES.get(tool, tool)

        if tool == "ffmpeg":
            ok = _update_ffmpeg(parent, name)
        elif tool == "yt-dlp":
            ok = _update_ytdlp(parent, name)
        else:
            ok = False
        any_ok = any_ok or ok

    if any_ok:
        _prompt_restart(parent)


def _update_ffmpeg(parent, name):
    """FFmpeg 更新：进度回调 (pct, msg) 直接对应进度条。返回是否更新成功。"""
    from gui_qt.components.download_progress_dialog import DownloadProgressDialog

    dlg = DownloadProgressDialog(name, parent)
    # 先启动后台下载，再进入模态事件循环（exec 内部有事件循环，能处理
    # 后台线程队列到主线程的进度信号）
    parent.services.ffmpeg_mgr.download_async(
        callback=dlg.finish, force=True, progress_cb=dlg.update)
    dlg.exec()
    return bool(dlg.ok and not dlg.cancelled)


def _update_ytdlp(parent, name):
    """yt-dlp 更新：download_ytdlp 的进度回调是字节数，需换算成百分比。

    返回是否更新成功。
    """
    from gui_qt.components.download_progress_dialog import DownloadProgressDialog

    dlg = DownloadProgressDialog(name, parent)

    def _run():
        def _prog(done, total):
            if total > 0:
                pct = int(done * 100 / total)
                msg = tr("下载中 {:.1f} / {:.1f} MB",
                         "Downloading {:.1f} / {:.1f} MB").format(
                    done / 1048576, total / 1048576)
            else:
                # 服务器未返回 Content-Length：无法算百分比，只显示已下载量
                pct = 0
                msg = tr("已下载 {:.1f} MB", "Downloaded {:.1f} MB").format(
                    done / 1048576)
            dlg.update(pct, msg)

        ok, msg = tool_updater.download_ytdlp(progress_cb=_prog)
        dlg.finish(ok, msg)

    threading.Thread(target=_run, daemon=True).start()
    dlg.exec()
    return bool(dlg.ok and not dlg.cancelled)


def _prompt_restart(parent):
    """更新成功：弹提示框询问是否立即重启（重启后新版本生效）。"""
    try:
        from qfluentwidgets import MessageBox

        box = MessageBox(
            tr("更新完成", "Update complete"),
            tr("工具更新完成，需要重启程序才能生效。\n\n是否立即重启？",
               "Tools updated. A restart is required for changes to take "
               "effect.\n\nRestart now?"),
            parent)
        box.yesButton.setText(tr("立即重启", "Restart now"))
        box.cancelButton.setText(tr("稍后", "Later"))
        if box.exec():
            from gui_qt.app import restart_application
            restart_application(parent)
    except Exception:  # noqa: BLE001 - 重启提示失败不影响运行
        pass


def show_tool_unreachable_notice(parent, entries):
    """官方有更新但当前网络无法下载：信息提示（无「立即更新」按钮）。"""
    try:
        from qfluentwidgets import MessageBox

        lines = []
        for u in entries:
            name = _TOOL_NAMES.get(u["tool"], u["tool"])
            off = u.get("official_latest") or "?"
            reach = u.get("latest") or u.get("current") or "—"
            lines.append(tr(
                "{name}：官方最新 {off}，但当前网络无法下载"
                "（本机可达最新 {reach} 已安装）。",
                "{name}: official {off} is not downloadable from this network "
                "(reachable latest {reach} already installed).").format(
                name=name, off=off, reach=reach))
        lines.append(tr(
            "💡 开启代理（梯子）后重新检查，可更新到官方最新版。",
            "💡 Enable a proxy/VPN and re-check to update to the "
            "official latest."))
        box = MessageBox(tr("更新受限", "Update restricted"),
                         "\n".join(lines), parent)
        box.yesButton.setText(tr("知道了", "Got it"))
        box.cancelButton.hide()
        box.exec()
    except Exception:  # noqa: BLE001 - 提示失败不影响运行
        pass


def show_tool_update_dialog(parent, updates):
    """发现新版本：弹确认框，确认后逐个下载替换。"""
    try:
        from qfluentwidgets import MessageBox

        lines = []
        for u in updates:
            name = _TOOL_NAMES.get(u["tool"], u["tool"])
            lines.append(f"{name}：{u['current']} → {u['latest']}")
        detail = "\n".join(lines)

        box = MessageBox(
            tr("发现工具新版本", "Tool update available"),
            tr("检测到以下工具可更新：\n\n{}\n\n"
               "⚠️ 更新需从 GitHub 下载，请先开启代理（梯子），"
               "否则可能下载失败。\n\n是否立即更新？",
               "Updates available:\n\n{}\n\n"
               "⚠️ Downloads come from GitHub. Enable a proxy/VPN "
               "first, or the download may fail.\n\nUpdate now?").format(detail),
            parent)
        box.yesButton.setText(tr("立即更新", "Update now"))
        box.cancelButton.setText(tr("暂不", "Not now"))
        if box.exec():
            _update_tools(parent, updates)
    except Exception:  # noqa: BLE001 - 弹窗失败不影响运行
        pass
