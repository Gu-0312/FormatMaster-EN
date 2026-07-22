"""yt-dlp下载和管理"""
import os
import subprocess
import urllib.request
import ssl
import threading
from utils.config import get_writable_bin_dir, get_ytdlp_path

YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"


class YTDLPManager:
    def __init__(self, progress_callback=None):
        self.progress_callback = progress_callback
        self._downloading = False

    def is_available(self):
        return get_ytdlp_path() is not None

    def get_version(self):
        path = get_ytdlp_path()
        if not path:
            return None
        try:
            result = subprocess.run(
                [path, "--version"],
                capture_output=True, text=True, timeout=10
            )
            return result.stdout.strip() or None
        except Exception:
            return None

    def download_async(self, callback=None):
        if self._downloading:
            return
        threading.Thread(target=self._download, args=(callback,), daemon=True).start()

    def _report(self, pct, msg):
        if self.progress_callback:
            self.progress_callback(pct, msg)

    def _download(self, callback=None):
        self._downloading = True

        if self.is_available():
            ver = self.get_version() or ""
            self._report(100, f"yt-dlp 已就绪 ({ver})" if ver else "yt-dlp 已就绪")
            if callback:
                callback(True, "已就绪")
            self._downloading = False
            return

        bin_dir = get_writable_bin_dir()
        exe_path = os.path.join(bin_dir, "yt-dlp.exe")
        tmp_path = exe_path + ".tmp"

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        self._report(10, "正在下载 yt-dlp...")
        try:
            req = urllib.request.Request(YTDLP_URL, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            })
            resp = urllib.request.urlopen(req, timeout=120, context=ctx)
            total = int(resp.headers.get('Content-Length', 0))
            dl = 0
            self._report(15, f"开始下载 ({total // 1024 // 1024}MB)..." if total else "开始下载...")

            with open(tmp_path, 'wb') as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    dl += len(chunk)
                    if total > 0:
                        pct = 15 + int(dl * 75 / total)
                        self._report(pct, f"下载中 {dl // 1024 // 1024}/{total // 1024 // 1024}MB")
            os.replace(tmp_path, exe_path)
        except Exception as e:
            self._report(0, f"下载失败: {e}")
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            if callback:
                callback(False, f"下载失败: {e}")
            self._downloading = False
            return

        if self.is_available():
            ver = self.get_version() or ""
            self._report(100, f"yt-dlp {ver} 安装完成" if ver else "yt-dlp 安装完成")
            if callback:
                callback(True, ver or "ok")
        else:
            self._report(0, "yt-dlp 安装异常")
            if callback:
                callback(False, "安装异常")

        self._downloading = False
