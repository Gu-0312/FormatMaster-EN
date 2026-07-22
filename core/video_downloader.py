"""视频下载（通过 yt-dlp.exe 子进程）"""
import os
import re
import json
import subprocess
import time
import urllib.request
import sys

if os.name == "nt":
    _STARTUP = subprocess.STARTUPINFO()
    _STARTUP.dwFlags |= subprocess.STARTF_USESHOWWINDOW
else:
    _STARTUP = None


SUPPORTED_PLATFORMS = (
    "YouTube · B站(bilibili) · 微博(weibo) · Instagram · Twitter/X · "
    "Facebook · 快手(kuaishou) · 小红书 · 知乎 · 网易云音乐 · 腾讯视频 · 优酷 · 爱奇艺"
)

_SHORT_DOMAINS = {
    "v.douyin.com": "douyin",
    "douyin.com": "douyin",
    "www.douyin.com": "douyin",
    "b23.tv": "bilibili",
}


def _get_ytdlp():
    from utils.config import get_ytdlp_path
    path = get_ytdlp_path()
    if not path:
        raise RuntimeError("yt-dlp 未安装，请先在侧边栏点击 yt-dlp 下载")
    return path


class VideoDownloader:
    def __init__(self):
        self._cancel = False
        self._process = None

    def cancel(self):
        self._cancel = True
        if self._process:
            try:
                self._process.terminate()
            except Exception:
                pass

    def _detect_site(self, url):
        for domain, site in _SHORT_DOMAINS.items():
            if domain in url:
                return site
        return None

    def _parse_formats(self, info):
        formats = []
        for f in info.get("formats", []):
            fmt_id = f.get("format_id", "")
            ext = f.get("ext", "")
            resolution = f.get("resolution", "") or f.get("format_note", "")
            filesize = f.get("filesize", 0) or f.get("filesize_approx", 0)
            vcodec = f.get("vcodec", "none")
            acodec = f.get("acodec", "none")
            if ext in ("mhtml", "json"):
                continue
            formats.append({
                "format_id": fmt_id,
                "ext": ext,
                "resolution": resolution,
                "filesize": filesize,
                "vcodec": vcodec,
                "acodec": acodec,
            })
        return formats

    def _run_json(self, url, *extra_args):
        ytdlp = _get_ytdlp()
        cmd = [ytdlp, "-J", "--no-warnings", "--ignore-errors",
               "--no-check-certificate"] + list(extra_args) + [url]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip() or "解析失败"
            raise RuntimeError(err)
        return json.loads(result.stdout)

    def get_formats(self, url):
        try:
            info = self._run_json(url)
            formats = self._parse_formats(info)
            if not formats:
                raise RuntimeError("未找到可下载的格式，该视频可能受DRM保护或需要登录")
            title = info.get("title", "") or info.get("fulltitle", "") or "untitled"
            return formats, title, info.get("thumbnail", "")
        except RuntimeError:
            raise
        except subprocess.TimeoutExpired:
            raise RuntimeError("解析超时，请检查网络或URL是否正确")
        except Exception as e:
            err_str = str(e)
            if "cookies" in err_str.lower() and ("douyin" in err_str.lower() or "tiktok" in err_str.lower()):
                for browser in ("chrome", "edge", "firefox", "opera"):
                    try:
                        info = self._run_json(url, "--cookies-from-browser", browser)
                        formats = self._parse_formats(info)
                        if formats:
                            title = info.get("title", "") or "untitled"
                            return formats, title, info.get("thumbnail", "")
                    except Exception:
                        continue
                raise RuntimeError(
                    "抖音/ TikTok 受平台限制无法直接下载。\n"
                    "抖音网页版强制要求登录态，且 cookies 有效期很短。\n"
                    "建议使用 YouTube / B站等其它平台。"
                )
            raise RuntimeError(f"解析失败：{err_str}")

    def _resolve_douyin_short_url(self, url):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            })
            resp = urllib.request.urlopen(req, timeout=10)
            return resp.geturl()
        except Exception:
            return url

    def download(self, url, output_path, format_id=None, progress_callback=None):
        self._cancel = False
        self._last_error = ""
        ytdlp = _get_ytdlp()
        from utils.config import get_ffmpeg_path
        ffmpeg = get_ffmpeg_path()
        output_template = os.path.splitext(output_path)[0] + ".%(ext)s"

        cmd = [
            ytdlp, "--no-warnings", "--ignore-errors",
            "--no-check-certificate", "--newline",
        ]
        if ffmpeg:
            cmd += ["--ffmpeg-location", ffmpeg]
        if format_id:
            cmd += ["-f", format_id]
        else:
            cmd += ["-f", "bestvideo+bestaudio/best"]
        cmd += ["-o", output_template, url]

        start = time.time()
        self._process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, startupinfo=_STARTUP
        )

        last_pct = 0
        try:
            for line in self._process.stderr:
                if self._cancel:
                    self._process.terminate()
                    if progress_callback:
                        progress_callback(-1, "已取消")
                    return False

                line = line.strip()
                if not line:
                    continue

                m = re.search(r'\[download\]\s+([\d.]+)%', line)
                if m:
                    pct = int(float(m.group(1)))
                    if pct > last_pct:
                        last_pct = pct
                    speed_m = re.search(r'at\s+([\d.]+[KMG]?i?B/s)', line)
                    eta_m = re.search(r'ETA\s+([\d:]+)', line)
                    parts = [f"下载中 {pct}%"]
                    if speed_m:
                        parts.append(speed_m.group(1))
                    if eta_m:
                        parts.append(f"剩余{eta_m.group(1)}")
                    if progress_callback:
                        progress_callback(pct, "  ".join(parts))
                elif '[download] 100%' in line or '已合并' in line:
                    if progress_callback:
                        progress_callback(95, "正在合并...")

            self._process.wait()
        except Exception:
            self._process.wait()

        if self._cancel:
            return False

        if self._process.returncode != 0:
            # 尝试 cookies 重试
            for browser in ("chrome", "edge", "firefox", "opera"):
                if self._cancel:
                    return False
                try:
                    retry_cmd = cmd[:]
                    retry_cmd.insert(3, "--cookies-from-browser")
                    retry_cmd.insert(4, browser)
                    proc = subprocess.Popen(
                        retry_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        text=True, bufsize=1, startupinfo=_STARTUP
                    )
                    for line in proc.stderr:
                        if self._cancel:
                            proc.terminate()
                            return False
                    proc.wait()
                    if proc.returncode == 0:
                        elapsed = time.time() - start
                        if progress_callback:
                            progress_callback(100, f"下载完成  耗时{int(elapsed)}s")
                        return True
                except Exception:
                    continue
            if progress_callback:
                progress_callback(-1, "下载失败，请检查链接或网络")
            return False

        elapsed = time.time() - start
        if progress_callback:
            progress_callback(100, f"下载完成  耗时{int(elapsed)}s")
        return True
