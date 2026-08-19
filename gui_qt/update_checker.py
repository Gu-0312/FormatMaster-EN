"""update_checker — 检查 GitHub Releases 是否有新版本（关于页 / 启动检查共用）。

后台线程请求 GitHub API，语义化版本比较，发现新版本通过信号通知 UI；
支持解析安装包资产并自动下载（进度回调），下载完成后可一键运行安装。
所有网络失败/超时静默忽略，绝不阻塞启动。
"""
from gui_qt.i18n import tr
import json
import os
import re
import socket
import threading
import urllib.error
import urllib.request

from PySide6.QtCore import QObject, QThread, Signal
from gui_qt.components.safe_worker import SafeWorker
from utils.mirrors import API_MIRRORS, parallel_first

GITHUB_REPO = "Gu-0312/FormatMaster-EN"
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"

_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
_TIMEOUT = 8


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


def _parse_release(data):
    """从 release 数据提取 (version, html_url, asset_url)。"""
    version = (data.get("tag_name") or "").lstrip("vV")
    url = data.get("html_url") or RELEASES_URL
    asset_url = None
    try:
        assets = data.get("assets") or []
        # 优先 .exe 安装包，其次 .zip
        for ext in (".exe", ".zip"):
            for a in assets:
                if (a.get("name") or "").lower().endswith(ext):
                    asset_url = a.get("browser_download_url")
                    break
            if asset_url:
                break
    except Exception:
        pass
    return (version, url, asset_url) if version else None


def fetch_latest_release():
    """获取 GitHub 最新 release。成功返回 (version, html_url)，失败返回 None。"""
    r = fetch_latest_release_with_asset()
    return (r[0], r[1]) if r else None


def _fetch_github_release_json(url):
    """请求 GitHub releases/latest API，返回解析后的 JSON dict；失败返回 None。"""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "FormatMaster",
            "Accept": "application/vnd.github+json",
        })
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except Exception:  # noqa: BLE001 - 单源失败交给并发抢答补位
        return None


def fetch_latest_release_with_asset():
    """获取最新 release 及安装包资产。返回 (version, url, asset_url|None)。

    经国内镜像并发抢答（parallel_first）：GitHub API 直连在国内常超时，
    任一镜像可用即返回，避免启动检查/关于页更新检测长时间无反馈。
    """
    urls = [f"{m}{_API_URL}" for m in API_MIRRORS] + [_API_URL]
    data = parallel_first(urls, _fetch_github_release_json, timeout=_TIMEOUT)
    return _parse_release(data) if data else None


def download_asset(asset_url, dest_dir, progress_cb=None):
    """流式下载安装包到 dest_dir，返回文件路径；失败抛异常/返回 None。

    progress_cb(done_bytes, total_bytes)：主线程外调用，用于驱动进度条。
    """
    if not asset_url:
        return None
    try:
        socket.setdefaulttimeout(_TIMEOUT)
        req = urllib.request.Request(asset_url, headers={
            "User-Agent": "FormatMaster"})
        os.makedirs(dest_dir, exist_ok=True)
        fname = asset_url.split("/")[-1].split("?")[0] or "update"
        dest = os.path.join(dest_dir, fname)
        with urllib.request.urlopen(req, timeout=30) as resp, \
                open(dest, "wb") as f:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress_cb:
                    progress_cb(done, total)
        return dest
    except Exception:
        return None


class _DownloadThread(SafeWorker):
    """后台下载安装包（进度/完成/失败信号）。"""

    progress = Signal(int, int)   # done, total
    finished_ok = Signal(str)     # 下载文件路径
    failed = Signal()

    def __init__(self, asset_url, dest_dir, parent=None):
        super().__init__(parent)
        self._url = asset_url
        self._dest = dest_dir

    def work(self):
        path = download_asset(self._url, self._dest, self.progress.emit)
        if path:
            self.finished_ok.emit(path)
        else:
            self.failed.emit()



class UpdateChecker(QObject):
    """后台检查更新，发现新版本发出信号。"""

    # (new_version, download_url) 或 (None, "")
    checked = Signal(object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self.last_asset = None    # 最新版本安装包下载地址（可能为 None）

    def check_async(self):
        """后台线程检查（可重复调用，内部去重）。"""
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self):
        try:
            result = fetch_latest_release_with_asset()
            if result:
                self.last_asset = result[2]
                self.checked.emit(result[0], result[1])
            else:
                self.last_asset = None
                self.checked.emit(None, "")
        except Exception as exc:  # noqa: BLE001 - 更新检查失败不影响应用
            from app.logger import error as _error
            _error(f"更新检查线程异常: {exc}", exc)
            try:
                self.last_asset = None
                self.checked.emit(None, "")
            except Exception:  # noqa: BLE001
                pass
        finally:
            self._running = False


def show_update_dialog(parent, new_version, url, asset_url=None):
    """弹出新版本提示框：点击「前往下载」跳转 GitHub releases 页面下载。

    asset_url 保留仅为兼容旧调用方，不再使用（自动下载流程已移除）。
    """
    try:
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        from qfluentwidgets import MessageBox

        box = MessageBox(
            tr("发现新版本", "New version available"),
            tr("格式大师 v{} 已发布，是否前往 GitHub 查看并下载？",
               "FormatMaster v{} released — open GitHub to view and download?").format(new_version),
            parent)
        box.yesButton.setText(tr("前往下载", "Go to download"))
        box.cancelButton.setText(tr("暂不", "Not now"))
        if box.exec():
            QDesktopServices.openUrl(QUrl(url))
    except Exception:
        pass
