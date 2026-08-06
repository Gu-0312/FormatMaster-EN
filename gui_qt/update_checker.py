"""update_checker — 检查 GitHub Releases 是否有新版本（关于页 / 启动检查共用）。

后台线程请求 GitHub API，语义化版本比较，发现新版本通过信号通知 UI。
所有网络失败/超时静默忽略，绝不阻塞启动。
"""
from gui_qt.i18n import tr
import json
import re
import socket
import threading
import urllib.error
import urllib.request

from PySide6.QtCore import QObject, Signal

GITHUB_REPO = "Gu-0312/FormatMaster-EN"
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"

_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
_TIMEOUT = 5


def version_gt(v1, v2):
    """语义化版本比较：v1 > v2 返回 True。忽略非数字后缀（beta 等）。"""
    try:
        def clean(v):
            return [int(x) for x in re.findall(r"\d+", str(v))]
        parts1 = clean(v1)
        parts2 = clean(v2)
        while len(parts1) < len(parts2):
            parts1.append(0)
        while len(parts2) < len(parts1):
            parts2.append(0)
        return parts1 > parts2
    except Exception:
        return False


def fetch_latest_release():
    """获取 GitHub 最新 release。成功返回 (version, html_url)，失败返回 None。"""
    try:
        socket.setdefaulttimeout(_TIMEOUT)
        req = urllib.request.Request(_API_URL, headers={
            "User-Agent": "FormatMaster",
            "Accept": "application/vnd.github+json",
        })
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        version = (data.get("tag_name") or "").lstrip("vV")
        url = data.get("html_url") or RELEASES_URL
        return (version, url) if version else None
    except Exception:
        return None


class UpdateChecker(QObject):
    """后台检查更新，发现新版本发出信号。"""

    # (new_version, download_url) 或 (None, "")
    checked = Signal(object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False

    def check_async(self):
        """后台线程检查（可重复调用，内部去重）。"""
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self):
        result = fetch_latest_release()
        self._running = False
        if result:
            self.checked.emit(result[0], result[1])
        else:
            self.checked.emit(None, "")


def show_update_dialog(parent, new_version, url):
    """弹出新版本提示框：点击「前往下载」跳转 releases 页。"""
    try:
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        from qfluentwidgets import MessageBox

        box = MessageBox(
            tr("发现新版本", "New version available"),
            tr("格式大师 v{} 已发布，是否前往 GitHub 查看并下载？", "FormatMaster v{} released — open GitHub to view and download?").format(new_version),
            parent)
        box.yesButton.setText(tr("前往下载", "Go to download"))
        box.cancelButton.setText(tr("暂不", "Not now"))
        if box.exec():
            QDesktopServices.openUrl(QUrl(url))
    except Exception:
        pass
