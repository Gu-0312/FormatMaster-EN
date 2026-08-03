"""M3U8/HLS 视频下载 — 全功能版"""
import os
import re
import glob
import shutil
import tempfile
import time
import json
import urllib.request


# ═══════════════════════════════════════
#  下载历史 & 收藏 管理
# ═══════════════════════════════════════
class M3U8Store:
    """管理下载历史和链接收藏"""

    def __init__(self):
        from utils.config import get_user_data_dir
        self._dir = get_user_data_dir()
        self._history_file = os.path.join(self._dir, "m3u8_history.json")
        self._fav_file = os.path.join(self._dir, "m3u8_favorites.json")
        self._history = self._load(self._history_file)
        self._favorites = self._load(self._fav_file)

    def _load(self, path):
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception: pass
        return []

    def _save(self, path, data):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception: pass

    # ── 下载历史 ──
    def add_history(self, url, name, output_path, size=0, duration=0):
        entry = {
            "url": url, "name": name, "output_path": output_path,
            "size": size, "duration": duration,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._history = [h for h in self._history if h.get("url") != url]
        self._history.insert(0, entry)
        self._history = self._history[:200]
        self._save(self._history_file, self._history)

    def get_history(self):
        return list(self._history)

    def clear_history(self):
        self._history = []
        self._save(self._history_file, [])

    def is_downloaded(self, url):
        return any(h.get("url") == url for h in self._history)

    # ── 链接收藏 ──
    def add_favorite(self, url, name="", note=""):
        entry = {"url": url, "name": name or url[:60], "note": note,
                 "time": time.strftime("%Y-%m-%d %H:%M:%S")}
        self._favorites = [f for f in self._favorites if f.get("url") != url]
        self._favorites.insert(0, entry)
        self._save(self._fav_file, self._favorites)

    def remove_favorite(self, url):
        self._favorites = [f for f in self._favorites if f.get("url") != url]
        self._save(self._fav_file, self._favorites)

    def update_favorite(self, url, name=None, note=None):
        for f in self._favorites:
            if f.get("url") == url:
                if name is not None: f["name"] = name
                if note is not None: f["note"] = note
                break
        self._save(self._fav_file, self._favorites)

    def get_favorites(self):
        return list(self._favorites)

    def clear_favorites(self):
        self._favorites = []
        self._save(self._fav_file, [])


# ═══════════════════════════════════════
#  M3U8 下载器
# ═══════════════════════════════════════
class M3U8Downloader:
    def __init__(self):
        self._cancel = False
        self._process = None
        self.store = M3U8Store()

    def cancel(self):
        self._cancel = True

    def _cleanup_ts_files(self, output_path):
        out_dir = os.path.dirname(output_path)
        base_name = os.path.splitext(os.path.basename(output_path))[0]
        for ext in ("*.ts", "*.segment", "*.part"):
            for f in glob.glob(os.path.join(out_dir, ext)):
                try: os.remove(f)
                except Exception: pass
        seg_dir = os.path.join(out_dir, base_name + "_segments")
        if os.path.isdir(seg_dir):
            try: shutil.rmtree(seg_dir, ignore_errors=True)
            except Exception: pass
        temp_dir = tempfile.gettempdir()
        for pattern in (f"{base_name}*.ts", f"{base_name}*.part", f"ffmpeg*.ts"):
            for f in glob.glob(os.path.join(temp_dir, pattern)):
                try: os.remove(f)
                except Exception: pass

    # ═══════════════════════════════════════
    #  m3u8 解析
    # ═══════════════════════════════════════
    def _parse_m3u8(self, url, headers=None, cookie=None, proxy=None):
        req_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        if headers: req_headers.update(headers)
        if cookie: req_headers["Cookie"] = cookie
        req = urllib.request.Request(url, headers=req_headers)
        handler = urllib.request.ProxyHandler({"https": proxy, "http": proxy}) if proxy else None
        opener = urllib.request.build_opener(handler) if handler else urllib.request.build_opener()
        with opener.open(req, timeout=15) as resp:
            content = resp.read().decode("utf-8", errors="replace")
        base_url = url.rsplit("/", 1)[0] + "/"
        segments = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"): continue
            segments.append(line if line.startswith("http") else base_url + line)
        if not segments:
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    sub_url = line if line.startswith("http") else base_url + line
                    return self._parse_m3u8(sub_url, headers, cookie, proxy)
        return segments

    def get_qualities(self, url, headers=None, cookie=None, proxy=None):
        try:
            req_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            if headers: req_headers.update(headers)
            if cookie: req_headers["Cookie"] = cookie
            req = urllib.request.Request(url, headers=req_headers)
            handler = urllib.request.ProxyHandler({"https": proxy, "http": proxy}) if proxy else None
            opener = urllib.request.build_opener(handler) if handler else urllib.request.build_opener()
            with opener.open(req, timeout=15) as resp:
                content = resp.read().decode("utf-8", errors="replace")
        except Exception: return []
        base_url = url.rsplit("/", 1)[0] + "/"
        qualities, pending = [], {}
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("#EXT-X-STREAM-INF:"):
                pending = {}
                for part in line[len("#EXT-X-STREAM-INF:"):].split(","):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        k, v = k.strip(), v.strip().strip('"')
                        if k == "BANDWIDTH": pending["bandwidth"] = int(v)
                        elif k == "RESOLUTION": pending["resolution"] = v
                        elif k == "NAME": pending["name"] = v
            elif line and not line.startswith("#") and pending:
                sub_url = line if line.startswith("http") else base_url + line
                pending["url"] = sub_url
                res, bw, name = pending.get("resolution", ""), pending.get("bandwidth", 0), pending.get("name", "")
                if name: label = name
                elif res:
                    h = res.split("x")[-1] if "x" in res else ""
                    label = {"2160":"4K","1440":"2K","1080":"1080p","720":"720p","480":"480p","360":"360p"}.get(h, res)
                elif bw: label = f"{bw//1000}kbps"
                else: label = f"流{len(qualities)+1}"
                bw_str = f"{bw/1000000:.1f}Mbps" if bw > 1000000 else (f"{bw//1000}kbps" if bw > 1000 else "")
                qualities.append({"resolution": res, "bandwidth": bw, "url": sub_url,
                                  "label": label, "bandwidth_str": bw_str,
                                  "display": f"{label}  ({bw_str})" if bw_str else label})
                pending = {}
        qualities.sort(key=lambda x: x.get("bandwidth", 0), reverse=True)
        return qualities

    def get_subtitles(self, url, headers=None, cookie=None, proxy=None):
        """解析m3u8获取字幕轨道列表"""
        try:
            req_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            if headers: req_headers.update(headers)
            if cookie: req_headers["Cookie"] = cookie
            req = urllib.request.Request(url, headers=req_headers)
            handler = urllib.request.ProxyHandler({"https": proxy, "http": proxy}) if proxy else None
            opener = urllib.request.build_opener(handler) if handler else urllib.request.build_opener()
            with opener.open(req, timeout=15) as resp:
                content = resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            print(f"[M3U8] get_subtitles fetch error: {e}")
            return []
        base_url = url.rsplit("/", 1)[0] + "/"
        subs = []
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("#EXT-X-MEDIA:") and "SUBTITLES" in line.upper():
                attrs = {}
                for part in line[len("#EXT-X-MEDIA:"):].split(","):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        k, v = k.strip(), v.strip().strip('"')
                        attrs[k] = v
                uri = attrs.get("URI", "")
                if uri:
                    sub_url = uri if uri.startswith("http") else base_url + uri
                    lang = attrs.get("LANGUAGE", "und")
                    name = attrs.get("NAME", lang)
                    subs.append({"url": sub_url, "lang": lang, "name": name,
                                 "display": f"{name} ({lang})"})
        if not subs:
            lines = content.strip().splitlines()[:20]
            print(f"[M3U8] No subtitles found. First 20 lines:")
            for l in lines:
                print(f"  {l}")
        return subs

    # ═══════════════════════════════════════
    #  断点续传
    # ═══════════════════════════════════════
    def _get_progress_file(self, output_path):
        return output_path + ".progress"

    def _load_progress(self, output_path):
        pf = self._get_progress_file(output_path)
        if os.path.exists(pf):
            try:
                with open(pf, "r") as f: return json.load(f)
            except Exception: pass
        return {"downloaded": [], "total_bytes": 0}

    def _save_progress(self, output_path, progress_data):
        try:
            with open(self._get_progress_file(output_path), "w") as f:
                json.dump(progress_data, f)
        except Exception: pass

    def _clear_progress(self, output_path):
        try: os.remove(self._get_progress_file(output_path))
        except Exception: pass

    # ═══════════════════════════════════════
    #  多线程下载
    # ═══════════════════════════════════════
    def _download_with_threads(self, url, output_path, progress_callback=None,
                               threads=16, cookie=None, headers=None,
                               proxy=None, speed_limit=0, resume=True):
        import concurrent.futures
        from urllib3.util.retry import Retry
        from urllib3.connectionpool import HTTPSConnectionPool, HTTPConnectionPool
        from urllib.parse import urlparse

        segments = self._parse_m3u8(url, headers, cookie, proxy)
        if not segments:
            if progress_callback: progress_callback(-1, "错误：未找到可下载分片")
            return False

        total = len(segments)
        done_set, total_bytes = set(), 0
        if resume:
            prog = self._load_progress(output_path)
            done_set = set(prog.get("downloaded", []))
            total_bytes = prog.get("total_bytes", 0)
            if done_set and progress_callback:
                progress_callback(0, f"共 {total} 分片，已下载 {len(done_set)} 个，继续...")

        if not done_set and progress_callback:
            progress_callback(0, f"共 {total} 个分片，开始下载...")

        parsed = urlparse(url)
        is_https = parsed.scheme == "https"
        host, port = parsed.hostname, parsed.port or (443 if is_https else 80)
        pool_cls = HTTPSConnectionPool if is_https else HTTPConnectionPool
        pool = pool_cls(host, port=port, maxsize=32, block=False,
                        retries=Retry(total=5, backoff_factor=0.3), timeout=30)

        temp_dir = tempfile.mkdtemp(suffix="_m3u8")
        os.makedirs(temp_dir, exist_ok=True)

        for idx in list(done_set):
            seg_file = os.path.join(temp_dir, f"seg_{idx:06d}.ts")
            if not os.path.exists(seg_file): done_set.discard(idx)

        downloaded = len(done_set)
        start_time = time.time()
        speed_limit_bytes = speed_limit * 1024 * 1024 if speed_limit > 0 else 0
        last_download_time = [time.time()]

        def download_one(args):
            idx, seg_url = args
            if self._cancel: return None
            if idx in done_set:
                seg_file = os.path.join(temp_dir, f"seg_{idx:06d}.ts")
                if os.path.exists(seg_file): return (idx, seg_file, 0)
            if speed_limit_bytes > 0:
                elapsed_wait = time.time() - last_download_time[0]
                min_interval = 1.0 / (speed_limit_bytes / 1048576 / threads) if speed_limit_bytes > 0 else 0
                if elapsed_wait < min_interval: time.sleep(min_interval - elapsed_wait)

            parsed_seg = urlparse(seg_url)
            path = parsed_seg.path + ("?" + parsed_seg.query if parsed_seg.query else "")
            req_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                           "Connection": "keep-alive", "Accept-Encoding": "identity"}
            if headers: req_headers.update(headers)
            if cookie: req_headers["Cookie"] = cookie

            for retry in range(5):
                try:
                    data = pool.urlopen("GET", path, headers=req_headers).data
                    seg_file = os.path.join(temp_dir, f"seg_{idx:06d}.ts")
                    with open(seg_file, "wb") as f: f.write(data)
                    last_download_time[0] = time.time()
                    return (idx, seg_file, len(data))
                except Exception:
                    if retry == 4: return None
                    time.sleep(0.1 * (retry + 1))
            return None

        max_workers = min(threads, total)
        results = [None] * total
        for idx in done_set:
            seg_file = os.path.join(temp_dir, f"seg_{idx:06d}.ts")
            if os.path.exists(seg_file): results[idx] = seg_file

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            todo = [(i, seg) for i, seg in enumerate(segments) if i not in done_set]
            futures = {executor.submit(download_one, a): a[0] for a in todo}
            for future in concurrent.futures.as_completed(futures):
                if self._cancel:
                    executor.shutdown(wait=False, cancel_futures=True)
                    self._save_progress(output_path, {"downloaded": [i for i, r in enumerate(results) if r], "total_bytes": total_bytes})
                    self._cleanup_temp(temp_dir); pool.close()
                    if progress_callback: progress_callback(-1, "已取消，进度已保存")
                    return False
                result = future.result()
                if result:
                    idx, seg_file, size = result
                    results[idx] = seg_file
                    total_bytes += size; downloaded += 1
                    if downloaded % 10 == 0:
                        self._save_progress(output_path, {"downloaded": [i for i, r in enumerate(results) if r], "total_bytes": total_bytes})
                    elapsed = time.time() - start_time
                    speed = total_bytes / elapsed if elapsed > 0 else 0
                    pct = int(downloaded * 100 / total)
                    speed_str = f"{speed/1024/1024:.1f}MB/s" if speed > 1024*1024 else (f"{speed/1024:.0f}KB/s" if speed > 1024 else f"{speed:.0f}B/s")
                    remaining = ""
                    if speed > 0 and downloaded < total:
                        eta = int((total - downloaded) * (elapsed / downloaded))
                        remaining = f"  剩余{eta}s" if eta < 60 else (f"  剩余{eta//60}m{eta%60}s" if eta < 3600 else f"  剩余{eta//3600}h{(eta%3600)//60}m")
                    speed_info = f"  限速{speed_limit}MB/s" if speed_limit > 0 else ""
                    if progress_callback:
                        progress_callback(pct, f"下载中 {pct}%  {speed_str}{remaining}{speed_info}  {total_bytes/1024/1024:.1f}MB  {int(elapsed)}s  {downloaded}/{total}")
        pool.close()

        if progress_callback: progress_callback(95, "正在合并分片...")
        try:
            with open(output_path, "wb") as out_f:
                for seg_file in results:
                    if seg_file and os.path.exists(seg_file):
                        with open(seg_file, "rb") as in_f: shutil.copyfileobj(in_f, out_f)
        except Exception as e:
            self._cleanup_temp(temp_dir)
            if progress_callback: progress_callback(-1, f"合并失败：{e}")
            return False

        self._cleanup_temp(temp_dir); self._clear_progress(output_path)
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            if progress_callback: progress_callback(-1, "错误：输出文件为空")
            return False
        elapsed = int(time.time() - start_time)
        size_mb = os.path.getsize(output_path) / 1024 / 1024
        if progress_callback:
            progress_callback(100, f"下载完成  {size_mb:.1f}MB  耗时{elapsed}s")
        return True

    def _cleanup_temp(self, temp_dir):
        try:
            if os.path.isdir(temp_dir): shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception: pass

    # ═══════════════════════════════════════
    #  字幕下载
    # ═══════════════════════════════════════
    def download_subtitle(self, sub_url, output_path, cookie=None, headers=None, proxy=None):
        """下载字幕文件，支持直接文件和m3u8字幕列表"""
        req_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        if headers: req_headers.update(headers)
        if cookie: req_headers["Cookie"] = cookie

        def fetch(url):
            req = urllib.request.Request(url, headers=req_headers)
            handler = urllib.request.ProxyHandler({"https": proxy, "http": proxy}) if proxy else None
            opener = urllib.request.build_opener(handler) if handler else urllib.request.build_opener()
            with opener.open(req, timeout=15) as resp:
                return resp.read()

        try:
            data = fetch(sub_url)
            content = data.decode("utf-8", errors="replace")
            if content.strip().startswith("#EXTM3U") or "#EXT-X-TARGETDURATION" in content:
                base = sub_url.rsplit("/", 1)[0] + "/"
                parts = []
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"): continue
                    seg_url = line if line.startswith("http") else base + line
                    try:
                        seg_data = fetch(seg_url)
                        parts.append(seg_data.decode("utf-8", errors="replace"))
                    except Exception: pass
                content = "\n".join(parts)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except Exception: return False

    # ═══════════════════════════════════════
    #  主下载入口
    # ═══════════════════════════════════════
    def download(self, url, output_path, progress_callback=None, threads=16,
                 cookie=None, headers=None, proxy=None, speed_limit=0,
                 resume=True, output_format="mp4"):
        self._cancel = False
        if not url or not url.strip():
            if progress_callback: progress_callback(-1, "错误：请输入M3U8链接")
            return False
        url = url.strip()
        if not url.lower().startswith(("http://", "https://")):
            if progress_callback: progress_callback(-1, "错误：请输入有效的HTTP/HTTPS链接")
            return False
        ext = f".{output_format}" if output_format else ".mp4"
        if not output_path.lower().endswith(ext):
            output_path = os.path.splitext(output_path)[0] + ext

        # 检查是否已下载过
        if self.store.is_downloaded(url):
            if progress_callback:
                progress_callback(100, f"该链接已下载过，正在重新下载...")

        # 检查文件是否已存在
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            if progress_callback:
                progress_callback(100, f"文件已存在，跳过下载: {os.path.basename(output_path)}")
            return True

        if not self._cancel and self._try_ytdlp(url, output_path, progress_callback, threads, cookie, proxy, speed_limit):
            self._record_history(url, output_path)
            return True
        if self._cancel:
            self._cleanup_ts_files(output_path)
            if progress_callback: progress_callback(-1, "已取消")
            return False
        if progress_callback: progress_callback(-1, "切换多线程直连...")
        if not self._cancel and self._download_with_threads(url, output_path, progress_callback,
                                                             threads, cookie, headers, proxy, speed_limit, resume):
            self._record_history(url, output_path)
            return True
        if self._cancel:
            self._cleanup_ts_files(output_path)
            if progress_callback: progress_callback(-1, "已取消")
            return False
        if progress_callback: progress_callback(-1, "切换ffmpeg...")
        result = self._try_ffmpeg(url, output_path, progress_callback, cookie, headers, proxy, output_format)
        if result: self._record_history(url, output_path)
        return result

    def _record_history(self, url, output_path):
        size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        name = os.path.splitext(os.path.basename(output_path))[0]
        self.store.add_history(url, name, output_path, size)

    def _try_ytdlp(self, url, output_path, progress_callback=None, threads=16,
                    cookie=None, proxy=None, speed_limit=0):
        try: from yt_dlp import YoutubeDL
        except Exception: return False
        out_dir = os.path.dirname(output_path)
        base_name = os.path.splitext(os.path.basename(output_path))[0]
        ext = os.path.splitext(output_path)[1] or ".mp4"
        output_template = os.path.join(out_dir, base_name + ".%(ext)s")
        start_time = time.time()

        def progress_hook(d):
            if self._cancel: raise Exception("已取消")
            if d["status"] == "downloading":
                pct = 0
                if "total_bytes" in d and d["total_bytes"]:
                    pct = int(d.get("downloaded_bytes", 0) * 100 / d["total_bytes"])
                elif "fragment_index" in d and "fragment_count" in d and d["fragment_count"]:
                    pct = int(d["fragment_index"] * 100 / d["fragment_count"])
                speed = d.get("speed", 0) or 0
                speed_str = f"{speed/1024/1024:.1f}MB/s" if speed > 1024*1024 else (f"{speed/1024:.0f}KB/s" if speed > 1024 else f"{speed:.0f}B/s")
                eta = d.get("eta", 0) or 0
                eta_str = f"  剩余{eta}s" if eta and eta < 60 else (f"  剩余{eta//60}m{eta%60}s" if eta and eta < 3600 else (f"  剩余{eta//3600}h{(eta%3600)//60}m" if eta else ""))
                frag = f"  分片{d['fragment_index']}/{d['fragment_count']}" if d.get("fragment_index") and d.get("fragment_count") else ""
                if progress_callback: progress_callback(pct, f"下载中 {pct}%  {speed_str}{eta_str}{frag}")
            elif d["status"] == "finished":
                if progress_callback: progress_callback(95, "正在合并...")

        ydl_opts = {"quiet": True, "no_warnings": True, "outtmpl": output_template,
                    "merge_output_format": ext.lstrip("."), "concurrent_fragment_downloads": threads,
                    "fragment_retries": 10, "retries": 10, "http_chunk_size": 2097152,
                    "progress_hooks": [progress_hook],
                    "socket_timeout": 30, "http_timeout": 30}
        if cookie: ydl_opts["http_headers"] = {"Cookie": cookie}
        if proxy: ydl_opts["proxy"] = proxy
        if speed_limit > 0: ydl_opts["ratelimit"] = speed_limit * 1024 * 1024

        try:
            with YoutubeDL(ydl_opts) as ydl: ydl.download([url])
            actual = output_path
            if not os.path.exists(actual):
                for f in glob.glob(os.path.join(out_dir, base_name + ".*")):
                    if f.endswith(ext): actual = f; break
            if actual != output_path and os.path.exists(actual):
                try: os.rename(actual, output_path)
                except Exception: pass
            self._cleanup_ts_files(output_path)
            elapsed = int(time.time() - start_time)
            if progress_callback: progress_callback(100, f"下载完成  耗时{elapsed}s")
            return True
        except Exception: return False

    def _try_ffmpeg(self, url, output_path, progress_callback=None,
                     cookie=None, headers=None, proxy=None, output_format="mp4"):
        import subprocess, select
        from utils.config import get_ffmpeg_path
        ffmpeg = get_ffmpeg_path()
        if not ffmpeg:
            if progress_callback: progress_callback(-1, "错误：FFmpeg未安装")
            return False
        cmd = [ffmpeg, "-y", "-headers", "User-Agent: Mozilla/5.0\r\n"]
        if cookie: cmd.extend(["-headers", f"Cookie: {cookie}\r\n"])
        if headers:
            for k, v in headers.items(): cmd.extend(["-headers", f"{k}: {v}\r\n"])
        if proxy: cmd.extend(["-http_proxy", proxy])
        cmd.extend(["-i", url, "-c", "copy", "-movflags", "+faststart", output_path])
        try:
            self._process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            time_pattern = re.compile(r"time=(\d+):(\d+):(\d+)\.(\d+)")
            error_output = []
            while True:
                if self._cancel:
                    self._process.terminate()
                    try: self._process.wait(timeout=3)
                    except Exception: self._process.kill()
                    self._cleanup_ts_files(output_path)
                    if progress_callback: progress_callback(-1, "已取消")
                    return False
                try: ready, _, _ = select.select([self._process.stderr], [], [], 0.5)
                except Exception: ready = [self._process.stderr]
                if not ready:
                    if self._process.poll() is not None: break
                    continue
                line = self._process.stderr.readline()
                if not line:
                    if self._process.poll() is not None: break
                    continue
                line_str = line.decode("utf-8", errors="replace")
                error_output.append(line_str)
                m = time_pattern.search(line_str)
                if m:
                    h, mi, s, ms = m.groups()
                    current = int(h)*3600 + int(mi)*60 + int(s) + int(ms)/100
                    if progress_callback: progress_callback(-1, f"ffmpeg下载中... {int(current)}s")
            if self._process.returncode == 0 and os.path.exists(output_path):
                self._cleanup_ts_files(output_path)
                if progress_callback: progress_callback(100, "下载完成")
                return True
            else:
                self._cleanup_ts_files(output_path)
                if progress_callback: progress_callback(-1, f"ffmpeg失败：{''.join(error_output[-5:])[:200]}")
                return False
        except Exception as e:
            self._cleanup_ts_files(output_path)
            if progress_callback: progress_callback(-1, f"错误：{e}")
            return False
