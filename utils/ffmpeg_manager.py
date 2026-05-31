"""FFmpeg下载和管理"""
import os
import subprocess
import zipfile
import shutil
import urllib.request
import ssl
import threading
from utils.config import get_bin_dir, get_ffmpeg_path, get_ffprobe_path

# 优先使用国内可达的源，GitHub放最后
SOURCES = [
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
]


class FFmpegManager:
    def __init__(self, progress_callback=None):
        self.progress_callback = progress_callback
        self._downloading = False

    def is_available(self):
        return get_ffmpeg_path() is not None and get_ffprobe_path() is not None

    def download_async(self, callback=None):
        if self._downloading:
            return
        threading.Thread(target=self._download, args=(callback,), daemon=True).start()

    def _report(self, pct, msg):
        if self.progress_callback:
            self.progress_callback(pct, msg)

    def _download(self, callback=None):
        self._downloading = True

        # 1) 本地bin目录已有
        if self.is_available():
            self._report(100, "FFmpeg已就绪")
            if callback:
                callback(True, "FFmpeg已就绪")
            self._downloading = False
            return

        # 2) 检查系统PATH
        self._report(10, "检测系统FFmpeg...")
        sys_ffmpeg = shutil.which("ffmpeg")
        if sys_ffmpeg:
            self._report(100, "使用系统FFmpeg")
            if callback:
                callback(True, "使用系统FFmpeg")
            self._downloading = False
            return

        # 3) 下载
        bin_dir = get_bin_dir()
        zip_path = os.path.join(bin_dir, "ffmpeg_dl.zip")

        # 禁用SSL验证（部分网络环境证书问题）
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        downloaded = False
        last_error = ""

        for idx, url in enumerate(SOURCES):
            self._report(15 + idx * 5, f"尝试源 {idx+1}/{len(SOURCES)}...")
            try:
                # 直接用urlopen，它会自动跟随303/302重定向
                req = urllib.request.Request(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "*/*",
                })
                resp = urllib.request.urlopen(req, timeout=30, context=ctx)
                total = int(resp.headers.get('Content-Length', 0))
                dl = 0
                self._report(25, f"开始下载 ({total // 1024 // 1024}MB)...")

                with open(zip_path, 'wb') as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        dl += len(chunk)
                        if total > 0:
                            pct = 25 + int(dl * 55 / total)
                            self._report(pct, f"下载中 {dl // 1024 // 1024}/{total // 1024 // 1024}MB")

                downloaded = True
                break
            except Exception as e:
                last_error = str(e)
                self._report(15, f"源{idx+1}失败: {last_error[:60]}")
                continue

        if not downloaded:
            self._report(0, "下载失败，请手动安装FFmpeg")
            if callback:
                callback(False, f"下载失败: {last_error[:100]}")
            self._downloading = False
            return

        # 4) 解压
        self._report(85, "正在解压...")
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for name in zf.namelist():
                    basename = os.path.basename(name).lower()
                    if basename in ('ffmpeg.exe', 'ffprobe.exe'):
                        target = os.path.join(bin_dir, os.path.basename(name))
                        with zf.open(name) as src, open(target, 'wb') as dst:
                            shutil.copyfileobj(src, dst)

            # 清理zip
            try:
                os.remove(zip_path)
            except OSError:
                pass

        except Exception as e:
            self._report(0, f"解压失败: {e}")
            if callback:
                callback(False, f"解压失败: {e}")
            self._downloading = False
            return

        # 5) 验证
        if self.is_available():
            self._report(100, "FFmpeg安装完成")
            if callback:
                callback(True, "FFmpeg安装成功")
        else:
            self._report(0, "FFmpeg安装异常，文件可能损坏")
            if callback:
                callback(False, "安装异常")

        self._downloading = False
