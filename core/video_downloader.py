"""视频下载"""
import os
import time
import subprocess
import json


SUPPORTED_PLATFORMS = (
    "YouTube · B站(bilibili) · 微博(weibo) · Instagram · Twitter/X · "
    "Facebook · 快手(kuaishou) · 小红书 · 知乎 · 网易云音乐 · 腾讯视频 · 优酷 · 爱奇艺"
)

# known short-domain redirect patterns that need special handling
_SHORT_DOMAINS = {
    "v.douyin.com": "douyin",
    "douyin.com": "douyin",
    "www.douyin.com": "douyin",
    "b23.tv": "bilibili",
}


def _find_ytdlp_exe():
    """查找 yt-dlp.exe 便携版"""
    from utils.config import get_bin_dir
    for name in ("yt-dlp.exe", "yt-dlp"):
        path = os.path.join(get_bin_dir(), name)
        if os.path.exists(path):
            return path
    import shutil
    return shutil.which("yt-dlp")


class VideoDownloader:
    def __init__(self):
        self._cancel = False
        self._process = None
        self._last_error = ""

    def cancel(self):
        self._cancel = True
        if self._process:
            try:
                self._process.terminate()
            except Exception:
                pass

    def _make_ydl_opts(self, **extra):
        opts = {
            "quiet": True,
            "no_warnings": True,
            "no_check_certificates": True,
            "ignoreerrors": True,
            "source_address": "0.0.0.0",
        }
        opts.update(extra)
        return opts

    def _detect_site(self, url):
        for domain, site in _SHORT_DOMAINS.items():
            if domain in url:
                return site
        return None

    def get_formats(self, url):
        """获取格式信息，返回 (formats, title, thumbnail, playlist)"""
        # 优先尝试 Python 模块
        try:
            return self._get_formats_module(url)
        except ImportError:
            pass
        # 降级到命令行
        return self._get_formats_cli(url)

    def _get_formats_module(self, url):
        from yt_dlp import YoutubeDL
        try:
            ydl_opts = self._make_ydl_opts()
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info is None:
                    raise RuntimeError("无法解析该链接，请检查URL是否正确")
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
                if not formats:
                    raise RuntimeError("未找到可下载的格式，该视频可能受DRM保护或需要登录")
                title = info.get("title", "") or info.get("fulltitle", "") or "untitled"
                # 从同一次 extract_info 结果中提取播放列表信息，避免重复请求
                playlist = None
                entries = info.get("entries")
                if entries and len(entries) > 1:
                    items = []
                    for e in entries:
                        if e:
                            items.append({
                                "url": e.get("url") or e.get("webpage_url", ""),
                                "title": e.get("title", ""),
                                "duration": e.get("duration", 0),
                            })
                    playlist = {"title": info.get("title", ""), "count": len(items), "items": items}
                return formats, title, info.get("thumbnail", ""), playlist
        except RuntimeError:
            raise
        except Exception as e:
            err_str = str(e)
            # douyin/tiktok 需要 cookies
            if "cookies" in err_str.lower() and ("douyin" in err_str.lower() or "tiktok" in err_str.lower()):
                # 尝试从浏览器自动获取 cookies
                for browser in ("chrome", "edge", "firefox", "opera"):
                    try:
                        ydl_opts = self._make_ydl_opts(cookies_from_browser=browser)
                        with YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(url, download=False)
                            if info and info.get("formats"):
                                formats = []
                                for f in info["formats"]:
                                    if f.get("ext") in ("mhtml", "json"):
                                        continue
                                    formats.append({
                                        "format_id": f.get("format_id", ""),
                                        "ext": f.get("ext", ""),
                                        "resolution": f.get("resolution", "") or f.get("format_note", ""),
                                        "filesize": f.get("filesize", 0) or f.get("filesize_approx", 0),
                                        "vcodec": f.get("vcodec", "none"),
                                        "acodec": f.get("acodec", "none"),
                                    })
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

    def _get_formats_cli(self, url):
        """使用 yt-dlp.exe 命令行解析格式"""
        exe = _find_ytdlp_exe()
        if not exe:
            raise RuntimeError("未找到 yt-dlp，请安装: pip install yt-dlp")
        cmd = [exe, "--dump-json", "--no-download", "--no-warnings", url]
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding='utf-8', errors='ignore', timeout=30,
                                creationflags=0x08000000)
        if result.returncode != 0 and not result.stdout.strip():
            raise RuntimeError(f"解析失败: {result.stderr[:200]}")
        info = json.loads(result.stdout)
        formats = []
        for f in info.get("formats", []):
            ext = f.get("ext", "")
            if ext in ("mhtml", "json"):
                continue
            formats.append({
                "format_id": f.get("format_id", ""),
                "ext": ext,
                "resolution": f.get("resolution", "") or f.get("format_note", ""),
                "filesize": f.get("filesize", 0) or f.get("filesize_approx", 0),
                "vcodec": f.get("vcodec", "none"),
                "acodec": f.get("acodec", "none"),
            })
        if not formats:
            raise RuntimeError("未找到可下载的格式")
        title = info.get("title", "") or "untitled"
        # 从同一次解析结果中提取播放列表信息
        playlist = None
        entries = info.get("entries")
        if entries and len(entries) > 1:
            items = []
            for e in entries:
                if e:
                    items.append({
                        "url": e.get("url") or e.get("webpage_url", ""),
                        "title": e.get("title", ""),
                        "duration": e.get("duration", 0),
                    })
            playlist = {"title": info.get("title", ""), "count": len(items), "items": items}
        return formats, title, info.get("thumbnail", ""), playlist

    def download(self, url, output_path, format_id=None, progress_callback=None,
                 cookie=None, headers=None, proxy=None, speed_limit=0,
                 audio_only=False, audio_format="mp3", subtitles=False,
                 output_template=None):
        self._cancel = False
        self._last_error = ""
        from utils.config import get_ffmpeg_path
        ffmpeg = get_ffmpeg_path()
        if output_template:
            tmpl = output_template
        else:
            tmpl = os.path.splitext(output_path)[0] + ".%(ext)s"
        ydl_opts = self._make_ydl_opts(
            outtmpl=tmpl,
            progress_hooks=[],
        )
        if ffmpeg:
            ydl_opts["ffmpeg_location"] = ffmpeg
        if cookie:
            ydl_opts["cookiefile"] = cookie
        if proxy:
            ydl_opts["proxy"] = proxy
        if headers:
            ydl_opts["http_headers"] = headers
        if speed_limit > 0:
            ydl_opts["throttledratelimit"] = speed_limit * 1024 * 1024
        if audio_only:
            ydl_opts["format"] = "bestaudio/best"
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": audio_format,
            }]
        elif format_id:
            ydl_opts["format"] = format_id
        else:
            ydl_opts["format"] = "bestvideo+bestaudio/best"
        if subtitles:
            ydl_opts["writesubtitles"] = True
            ydl_opts["writeautomaticsub"] = True
            ydl_opts["subtitleslangs"] = ["all"]
            ydl_opts["embedsubs"] = False

        start = time.time()

        def progress_hook(d):
            if self._cancel:
                raise Exception("已取消")
            if d["status"] == "downloading":
                pct = 0
                if "total_bytes" in d and d["total_bytes"]:
                    pct = int(d.get("downloaded_bytes", 0) * 100 / d["total_bytes"])
                elif "total_bytes_estimate" in d and d["total_bytes_estimate"]:
                    pct = int(d.get("downloaded_bytes", 0) * 100 / d["total_bytes_estimate"])
                speed = d.get("speed", 0) or 0
                speed_str = f"{speed/1024/1024:.1f}MB/s" if speed > 1024*1024 else f"{speed/1024:.0f}KB/s" if speed else ""
                eta = d.get("eta", 0) or 0
                if progress_callback:
                    progress_callback(pct, f"下载中 {pct}%  {speed_str}  剩余{eta}s")
            elif d["status"] == "finished":
                if progress_callback:
                    progress_callback(95, "正在合并...")

        ydl_opts["progress_hooks"] = [progress_hook]
        # 优先尝试 Python 模块
        try:
            from yt_dlp import YoutubeDL
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            elapsed = time.time() - start
            if progress_callback:
                progress_callback(100, f"下载完成  耗时{int(elapsed)}s")
            return True
        except ImportError:
            pass
        # 降级到命令行
        return self._download_cli(url, output_path, format_id, progress_callback,
                                  cookie, proxy, audio_only, audio_format)

    def _download_cli(self, url, output_path, format_id=None, progress_callback=None,
                      cookie=None, proxy=None, audio_only=False, audio_format="mp3"):
        """使用 yt-dlp.exe 命令行下载"""
        exe = _find_ytdlp_exe()
        if not exe:
            if progress_callback:
                progress_callback(-1, "未找到 yt-dlp")
            return False
        from utils.config import get_ffmpeg_path
        ffmpeg = get_ffmpeg_path()
        cmd = [exe, "-o", output_path, "--no-check-certificates"]
        if ffmpeg:
            cmd.extend(["--ffmpeg-location", os.path.dirname(ffmpeg)])
        if cookie:
            cmd.extend(["--cookies", cookie])
        if proxy:
            cmd.extend(["--proxy", proxy])
        if audio_only:
            cmd.extend(["-x", "--audio-format", audio_format])
        elif format_id:
            cmd.extend(["-f", format_id])
        cmd.append(url)

        try:
            self._process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='ignore',
                creationflags=0x08000000)
            for line in self._process.stdout:
                if self._cancel:
                    self._process.terminate()
                    if progress_callback:
                        progress_callback(-1, "已取消")
                    return False
                # 解析进度
                if "%" in line:
                    try:
                        pct_str = line.split("%")[0].split()[-1]
                        pct = int(float(pct_str))
                        if progress_callback:
                            progress_callback(pct, f"下载中 {pct}%")
                    except Exception:
                        pass
            self._process.wait()
            if self._process.returncode == 0:
                if progress_callback:
                    progress_callback(100, "下载完成")
                return True
            else:
                if progress_callback:
                    progress_callback(-1, "下载失败")
                return False
        except Exception as e:
            if progress_callback:
                progress_callback(-1, f"下载失败: {str(e)[:60]}")
            return False

    def _resolve_douyin_short_url(self, url):
        """尝试解析抖音短链接 (v.douyin.com) 为重定向后的长链接"""
        import urllib.request
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            })
            resp = urllib.request.urlopen(req, timeout=10)
            return resp.geturl()
        except Exception:
            return url

    def get_playlist_info(self, url):
        from yt_dlp import YoutubeDL
        ydl_opts = self._make_ydl_opts(extract_flat=True, force_generic_extractor=False)
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if info is None:
            return None
        entries = info.get("entries", [])
        if entries:
            items = []
            for e in entries:
                if e:
                    items.append({
                        "url": e.get("url") or e.get("webpage_url", ""),
                        "title": e.get("title", ""),
                        "duration": e.get("duration", 0),
                    })
            return {"title": info.get("title", ""), "count": len(items), "items": items}
        return None

    @staticmethod
    def update_ytdlp(progress_cb=None):
        import subprocess, sys
        if progress_cb: progress_cb("正在更新 yt-dlp...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if progress_cb: progress_cb("yt-dlp 已更新到最新版")
            return True
        except Exception as e:
            if progress_cb: progress_cb(f"更新失败：{e}")
            return False