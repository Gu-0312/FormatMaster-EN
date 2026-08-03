"""自动下载工具：yt-dlp"""
import os
import subprocess
import shutil
import urllib.request
import ssl
import zipfile
import threading
from utils.config import get_bin_dir

# ── SSL 上下文 ──
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


class ToolDownloader:
    def __init__(self):
        self._downloading = False

    # ═══════════════════════════════════════════
    #  yt-dlp
    # ═══════════════════════════════════════════
    def ytdlp_path(self):
        """查找 yt-dlp 可执行文件"""
        bin_dir = get_bin_dir()
        for name in ("yt-dlp.exe", "yt-dlp"):
            path = os.path.join(bin_dir, name)
            if os.path.exists(path):
                return path
        return shutil.which("yt-dlp")

    def ytdlp_available(self):
        return self.ytdlp_path() is not None

    def download_ytdlp_async(self, callback=None):
        if self._downloading:
            return
        threading.Thread(target=self._download_ytdlp, args=(callback,), daemon=True).start()

    def _download_ytdlp(self, callback=None):
        self._downloading = True
        bin_dir = get_bin_dir()
        exe_path = os.path.join(bin_dir, "yt-dlp.exe")

        try:
            # 下载 yt-dlp.exe
            url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
            req = urllib.request.Request(url, headers=_HEADERS)
            resp = urllib.request.urlopen(req, timeout=60, context=_CTX)

            total = int(resp.headers.get('Content-Length', 0))
            dl = 0
            with open(exe_path, 'wb') as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    dl += len(chunk)

            if os.path.exists(exe_path) and os.path.getsize(exe_path) > 100000:
                if callback:
                    callback(True, "yt-dlp 安装成功")
            else:
                if callback:
                    callback(False, "yt-dlp 下载异常")
        except Exception as e:
            # 下载失败后尝试清理不完整的文件
            try:
                if os.path.exists(exe_path) and os.path.getsize(exe_path) < 100000:
                    os.remove(exe_path)
            except OSError:
                pass
            if callback:
                callback(False, f"yt-dlp 下载失败: {str(e)[:60]}")

        self._downloading = False


# 全局实例
tool_downloader = ToolDownloader()
