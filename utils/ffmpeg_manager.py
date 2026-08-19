"""FFmpeg下载和管理"""
import os
import re
import json
import subprocess
import zipfile
import shutil
import time
import urllib.request
import ssl
import threading
from utils.config import get_bin_dir, get_ffmpeg_path, get_ffprobe_path

# BtbN 的 GitHub release 直链（Windows 64 位 GPL 完整版）
_BTBN_URL = ("https://github.com/BtbN/FFmpeg-Builds/releases/download/"
             "latest/ffmpeg-master-latest-win64-gpl.zip")

# GitHub 加速代理（国内可达，加速 BtbN 下载）。免费代理可能限速/失效，
# 故多备几个，逐个尝试，失败自动回退下一个源。列表统一由
# utils/mirrors.py 提供（实测 2026-08：gh-proxy.com 双通最稳但偶发超时，
# ghproxy.net / gh.ddlc.top 下载稳；其余 40+ 候选已失效勿加）。
from utils.mirrors import DOWNLOAD_MIRRORS
_GITHUB_PROXIES = DOWNLOAD_MIRRORS

# 下载请求 UA（部分 GitHub 代理会拒绝默认 urllib UA）
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# 下载源优先级：国内加速代理 BtbN（实测可达、可下载）优先 → gyan.dev
# release（干净版本号如 9.0.1，但国内网络常不可达）→ GitHub 原始兜底。
# 注意：BtbN 是 master 构建，版本号是 git 描述（N-xxx-gxxx-日期），
# 下载后由 core/tool_updater.display_version 美化显示为日期。
SOURCES = []
for _p in _GITHUB_PROXIES:
    SOURCES.append(_p + _BTBN_URL)
SOURCES.append("https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip")
SOURCES.append(_BTBN_URL)

# 国内直连镜像（淘宝 npmmirror 同步的 ffmpeg-builds，KarinJS 构建）：
# 版本号与 FFmpeg 官方一一对应（如 v8.1.2），国内直连高速，非 GitHub、
# 非 gyan.dev。资产为 .tar.xz（ffmpeg-<ver>-win32-x64-gpl.tar.xz），
# 运行时解析最新版本目录 + tar.xz 解压（见 _resolve_npmmirror_ffmpeg_url /
# _extract_ffmpeg）。作为「以防万一」的兜底源：GitHub 代理全失效时仍有路。
_NPMMIRROR_BASE = "https://registry.npmmirror.com/-/binary/ffmpeg-builds"
_NPMMIRROR_VER_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)/$")


def _resolve_npmmirror_ffmpeg_url():
    """解析 npmmirror 最新 ffmpeg-builds 的 Windows x64 GPL tar.xz 直链。

    返回完整 URL 或 None（网络失败/解析失败）。下载开始时调用，失败不
    影响其余 GitHub 代理源——仅作为额外源参与 _race_download 抢答。
    """
    try:
        req = urllib.request.Request(
            _NPMMIRROR_BASE + "/",
            headers={"User-Agent": _UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        best, best_key = None, None
        for entry in data or []:
            m = _NPMMIRROR_VER_RE.match(entry.get("name", ""))
            if not m:
                continue
            key = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if best_key is None or key > best_key:
                best_key, best = key, entry["name"].rstrip("/")
        if not best:
            return None
        ver = best[1:]  # "v8.1.2" → "8.1.2"
        return (f"{_NPMMIRROR_BASE}/{best}/"
                f"ffmpeg-{ver}-win32-x64-gpl.tar.xz")
    except Exception:  # noqa: BLE001 - 解析失败静默，交给其他源
        return None


def best_ffmpeg_source(installed_raw):
    """统一『检查更新』与『下载』的版本基准，杜绝更新死循环。

    返回 (urls, version, display, scheme)：
    - urls: 该源可下载 URL 列表（含代理 / 直连兜底），供 _race_download 使用；
    - version: 规范版本号（与 installed 同体系，用于比对）；
    - display: 美化显示版本；
    - scheme: "git"（BtbN master 构建日期）或 "release"（gyan / npmmirror）。

    选择逻辑（按已安装构建的版本体系选择，确保『广告的版本』==『实际下载
    安装的版本』，更新一次即稳定，不再循环）：
    - 已装 BtbN master（git 描述 N-...-日期）→ 取 BtbN master 最新构建日期；
    - 已装 release 版（gyan / npmmirror，含 n 前缀）→ 在 gyan 与 npmmirror 中
      取 semver 最大者（二者均为 ffmpeg 官方 release 构建，版本可比）。

    全部源不可达 / 无法解析返回 None（调用方退回全源竞速兜底）。
    """
    import concurrent.futures as _cf
    from core import tool_updater as tu

    if installed_raw and tu._is_git_describe(installed_raw):
        btbn = tu.parallel_first(
            [f"{m}{tu.FFMPEG_BTBN_API}" for m in _GITHUB_PROXIES],
            tu._fetch_btbn_latest_from_url, timeout=4)
        if btbn:
            urls = [f"{p}{_BTBN_URL}" for p in _GITHUB_PROXIES]
            return (urls, btbn, tu.display_version(btbn) or btbn, "git")
        return None

    # release 体系：gyan 与 npmmirror 并发取 semver 最大者
    # 关键：必须对**二进制下载 URL**做 HEAD 探测 —— 国内 gyan 版本文本常可达但
    # zip 不可达，若仅凭文本就广告 9.0.1，下载会静默失败、已装版本不被覆盖、
    # 下次 check 又说「最新」形成死锁。HEAD 不通直接排除该源。
    def _gyan():
        g = (tu._http_get_text(tu.GYAN_VERSION_URL, timeout=4) or "").strip() or None
        if not g:
            return ("gyan", None)
        url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        if not _head_ok(url, timeout=3):
            return ("gyan", None)
        return ("gyan", g)

    def _npm():
        u = _resolve_npmmirror_ffmpeg_url()
        if not u:
            return ("npm", None)
        if not _head_ok(u, timeout=3):
            return ("npm", None)
        m = re.search(r"ffmpeg-(\d+\.\d+\.\d+)-win32", u)
        return ("npm", (m.group(1), u) if m else None)

    cands = []  # (semver_tuple, version, urls)
    with _cf.ThreadPoolExecutor(max_workers=2) as ex:
        for fut in _cf.as_completed([ex.submit(_gyan), ex.submit(_npm)]):
            kind, val = fut.result()
            if kind == "gyan" and val:
                cands.append((tu._parse_version(val), val,
                              ["https://www.gyan.dev/ffmpeg/builds/"
                               "ffmpeg-release-essentials.zip"]))
            elif kind == "npm" and val:
                ver, url = val
                cands.append((tu._parse_version(ver), ver, [url]))
    if not cands:
        return None
    cands.sort(key=lambda c: c[0], reverse=True)
    best = cands[0]
    disp = tu.display_version(best[1]) or best[1]
    return (best[2], best[1], disp, "release")


def _head_ok(url, timeout=3):
    """轻量探测下载 URL 是否真正可达：HEAD 返回 2xx/3xx 即视为可达。

    用于 best_ffmpeg_source 排除「版本文本可达但二进制被掐」的源，
    避免广告 9.0.1 后下载静默失败形成的更新死循环。
    """
    try:
        req = urllib.request.Request(url, method="HEAD")
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return 200 <= r.status < 400
    except Exception:  # noqa: BLE001
        return False


def official_latest_ffmpeg():
    """上游「官方最新」版本（忽略二进制可达性，只看版本信息端点）。

    best_ffmpeg_source 回答「当前网络能不能下到、下到什么」；本函数回答
    「上游官方到底有没有更新」。二者分离，供 UI 在网络受限时提示
    「官方最新 X 但下载不了，本机可达最新 Y 已装」。

    返回 (version, display)；gyan/npmmirror 的版本信息都拿不到时返回 None。
    """
    import concurrent.futures as _cf
    from core import tool_updater as tu

    def _gyan():
        g = (tu._http_get_text(tu.GYAN_VERSION_URL, timeout=4) or "").strip() or None
        return ("gyan", g)

    def _npm():
        u = _resolve_npmmirror_ffmpeg_url()
        if not u:
            return ("npm", None)
        m = re.search(r"ffmpeg-(\d+\.\d+\.\d+)-win32", u)
        return ("npm", m.group(1) if m else None)

    cands = []
    with _cf.ThreadPoolExecutor(max_workers=2) as ex:
        for fut in _cf.as_completed([ex.submit(_gyan), ex.submit(_npm)]):
            kind, val = fut.result()
            if val:
                cands.append((tu._parse_version(val), val))
    if not cands:
        return None
    cands.sort(key=lambda c: c[0], reverse=True)
    best = cands[0][1]
    return (best, tu.display_version(best) or best)


def _is_valid_archive(path):
    """判断下载文件是否为有效 zip 或 tar.xz（防代理返回错误页被当压缩包）。"""
    import tarfile

    try:
        if zipfile.is_zipfile(path):
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        with tarfile.open(path, "r:*") as tf:
            return next(iter(tf), None) is not None
    except Exception:  # noqa: BLE001 - 非 tar（如 HTML 错误页）即无效
        return False


def _extract_ffmpeg(archive_path, bin_dir):
    """从 zip 或 tar.xz 中提取 ffmpeg.exe / ffprobe.exe 到 bin_dir。

    两种压缩包的共同结构：顶层 bin/ 子目录下含 ffmpeg.exe、ffprobe.exe。
    按 basename 匹配（忽略路径与压缩格式差异），与原逻辑一致。
    """
    import tarfile

    targets = {"ffmpeg.exe", "ffprobe.exe"}
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path, "r") as zf:
            for name in zf.namelist():
                if os.path.basename(name).lower() in targets:
                    with zf.open(name) as src, open(
                            os.path.join(bin_dir, os.path.basename(name)), "wb") as dst:
                        shutil.copyfileobj(src, dst)
        return
    # tar.xz（npmmirror / KarinJS 构建）：ffmpeg-<ver>-win32-x64-gpl/bin/ffmpeg.exe
    with tarfile.open(archive_path, "r:*") as tf:
        for m in tf.getmembers():
            if m.isfile() and os.path.basename(m.name).lower() in targets:
                src = tf.extractfile(m)
                if src is None:
                    continue
                with src, open(
                        os.path.join(bin_dir, os.path.basename(m.name)), "wb") as dst:
                    shutil.copyfileobj(src, dst)


class FFmpegManager:
    def __init__(self, progress_callback=None):
        self.progress_callback = progress_callback
        self._downloading = False
        # 本次下载的临时进度回调（download_async 传入，优先于实例级回调）
        self._active_progress_cb = None
        # 结构化错误详情：每个失败源/阶段一条记录，供 UI 展示完整信息
        # 格式: [{"phase": "download"|"extract"|"verify", "url": str,
        #         "type": str, "msg": str}]
        self.last_errors = []

    def is_available(self):
        return get_ffmpeg_path() is not None and get_ffprobe_path() is not None

    def download_async(self, callback=None, force=False, progress_cb=None):
        """后台下载 FFmpeg。

        force=True：即使本地已就绪也强制下载替换（用于「更新到新版本」）。
        progress_cb(pct, msg)：下载过程中的进度回调（后台线程调用），
        pct 为 0-100 整数、msg 为阶段描述。供弹窗进度条驱动。
        """
        if self._downloading:
            # 已在下载中：回调通知调用方，不再静默忽略（避免调用方无限等待）
            if callback:
                callback(True, "正在下载中...")
            return
        threading.Thread(
            target=self._download, args=(callback, force, progress_cb),
            daemon=True).start()

    def _report(self, pct, msg):
        # 优先用本次下载传入的临时进度回调，其次用实例级回调
        cb = getattr(self, "_active_progress_cb", None) or self.progress_callback
        if cb:
            try:
                cb(pct, msg)
            except Exception:  # noqa: BLE001 - 进度回调异常不影响下载
                pass

    def _record_error(self, phase, msg, url="", exc=None):
        """记录一条结构化错误，不截断，保留异常类型供诊断。"""
        self.last_errors.append({
            "phase": phase,
            "url": url,
            "type": type(exc).__name__ if exc is not None else "",
            "msg": str(msg),
        })

    def _download(self, callback=None, force=False, progress_cb=None):
        self._downloading = True
        self._active_progress_cb = progress_cb
        self.last_errors = []  # 每次下载前清空，重试时不会累积旧错误
        try:
            self._download_impl(callback, force)
        finally:
            self._downloading = False
            self._active_progress_cb = None

    def _download_impl(self, callback, force):
        # 1) 本地bin目录已有（force 时跳过，直接下载替换）
        if not force and self.is_available():
            self._report(100, "FFmpeg已就绪")
            if callback:
                callback(True, "FFmpeg已就绪")
            return

        # 2) 检查系统PATH（force 时跳过：需要替换本地版本）
        if not force:
            self._report(10, "检测系统FFmpeg...")
            sys_ffmpeg = shutil.which("ffmpeg")
            if sys_ffmpeg:
                self._report(100, "使用系统FFmpeg")
                if callback:
                    callback(True, "使用系统FFmpeg")
                return

        # 3) 下载：统一『检查更新』与『下载』的版本基准——下载与广告的最新版
        # 一致，避免「更新完仍是旧版 → 又提示更新」的死循环。优先下载
        # best_ffmpeg_source 选定的源；全部不可达时退回全源竞速兜底。
        bin_dir = get_bin_dir()
        zip_path = os.path.join(bin_dir, "ffmpeg_dl.zip")

        # 禁用SSL验证（部分网络环境证书问题）
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        from core import tool_updater as tu
        target = best_ffmpeg_source(tu.current_ffmpeg_version_raw())
        if target is not None:
            sources = list(target[0])
            self._report(14, f"目标版本 ffmpeg {target[2]}")
        else:
            # 全部源不可达 / 无法判定：退回全源竞速（尽力而为）
            sources = list(SOURCES)
            npm = _resolve_npmmirror_ffmpeg_url()
            if npm:
                sources.append(npm)
                self._report(14, "已加入国内镜像源")
        zip_path = self._race_download(sources, zip_path, ctx)
        if not zip_path:
            # 全部源失败：再检查系统 PATH 作为兜底
            sys_ffmpeg_fallback = shutil.which("ffmpeg")
            if sys_ffmpeg_fallback:
                self._report(100, "下载失败但检测到系统FFmpeg")
                if callback:
                    callback(True, "使用系统FFmpeg（下载失败）")
                return
            err_lines = "; ".join(
                f"[{e['url'][:46]}] {e['msg'][:56]}" for e in self.last_errors[-5:]
            ) or "未知错误"
            msg = (f"全部源下载失败：{err_lines[:160]}"
                   "（如网络受限，可开启代理/梯子后重试）")
            self._report(0, msg)
            if callback:
                callback(False, msg)
            return

        # 4) 解压（zip / tar.xz 自适应）
        self._report(85, "正在解压...")
        try:
            _extract_ffmpeg(zip_path, bin_dir)

            # 清理压缩包
            try:
                os.remove(zip_path)
            except OSError:
                pass

        except Exception as e:
            self._record_error("extract", str(e), exc=e)
            self._report(0, f"解压失败: {e}")
            if callback:
                callback(False, f"解压失败: {e}")
            return

        # 5) 验证
        if self.is_available():
            from utils.config import invalidate_ffmpeg_path_cache
            invalidate_ffmpeg_path_cache()
            self._report(100, "FFmpeg安装完成")
            if callback:
                callback(True, "FFmpeg安装成功")
        else:
            self._record_error("verify", "解压后仍检测不到 ffmpeg.exe/ffprobe.exe")
            self._report(0, "FFmpeg安装异常，文件可能损坏")
            if callback:
                callback(False, "安装异常")

    def _race_download(self, sources, zip_path, ctx):
        """多镜像并行抢答下载：最快完成且 zip 完整者胜出，其余源立即中止。

        返回移动好的最终 zip_path（已校验），或 None（全部失败）。

        解决的问题：
        - 旧串行逻辑用 urlopen(timeout=10)，该超时只对「单次 read」生效；
          一旦某代理接通后限速掐流（每次 read 都挤一点字节），连接永不死、
          进度卡 0%，用户只能干等最慢/最烂的源。
        - 现改为所有源并发下载到各自临时文件，首个成功者置 stop 事件，
          落败源在下次读循环检查 stop 后立即退出，绝不浪费带宽/时间。
        - 额外双熔断：单源总时长硬上限 + 连续 N 秒无新字节即判限速弃源，
          任何单源劣化都不会再拖垮整体。
        """
        import concurrent.futures

        n = len(sources)
        if n == 0:
            return None

        stop = threading.Event()
        lock = threading.Lock()
        winner = [None]            # (idx, tmp_path)
        tmp_paths = []
        READ_TIMEOUT = 10          # 单次 read 超时（防单字节死等）
        STALL_WINDOW = 12          # 吞吐检测窗口（秒）
        STALL_MIN_BYTES = 64 * 1024  # 窗口内低于此字节数（≈5KB/s）→ 判限速/掐流弃源
        SOURCE_HARD = 120          # 单源总时长硬上限（兜底，正常 <60s）

        def worker(idx, url):
            if stop.is_set():
                return None
            tmp = f"{zip_path}.src{idx}"
            with lock:
                tmp_paths.append(tmp)
            self._report(15 + idx * 3, f"连接源 {idx+1}/{n}...")
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": _UA,
                    "Accept": "*/*",
                })
                resp = urllib.request.urlopen(req, timeout=READ_TIMEOUT, context=ctx)
                if getattr(resp, "status", 200) != 200:
                    raise RuntimeError(f"HTTP {resp.status}")
                total = int(resp.headers.get('Content-Length', 0) or 0)
                dl = 0
                start = time.monotonic()
                last_check = start       # 吞吐检测锚点（时间）
                dl_at_check = 0          # 吞吐检测锚点（字节）
                with open(tmp, 'wb') as f:
                    while not stop.is_set():
                        if time.monotonic() - start > SOURCE_HARD:
                            raise TimeoutError("单源总时长超时")
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        dl += len(chunk)
                        # 基于「窗口内实际吞吐」判定限速/掐流：仅看两次采样间隔
                        # 收到的字节量，而非「距上次收字节的时长」——后者在匀速慢
                        # 速源下恒为 0、永远不触发，正是「卡在 0%」的根因。
                        now = time.monotonic()
                        if now - last_check >= STALL_WINDOW:
                            if dl - dl_at_check < STALL_MIN_BYTES:
                                raise TimeoutError("源限速/无响应，切换下一个")
                            last_check = now
                            dl_at_check = dl
                        if total > 0:
                            self._report(
                                -1,
                                f"源{idx+1} 下载中 {dl // 1024 // 1024}/"
                                f"{total // 1024 // 1024}MB ({dl * 100 // total}%)")
                        else:
                            # 代理流式转发未返回 Content-Length：进度不确定，
                            # 显示忙碌条 + 已下载量，避免停在「0%」误以为卡死
                            self._report(-1, f"源{idx+1} 已下载 {dl // 1024 // 1024}MB")

                if stop.is_set():
                    return None
                if not _is_valid_archive(tmp):
                    raise ValueError("下载文件非有效压缩包（可能被代理替换为错误页）")
                with lock:
                    if winner[0] is None:
                        winner[0] = (idx, tmp)
                stop.set()  # 通知其余源立即中止
                return tmp
            except Exception as e:
                self._record_error("download", str(e)[:120], url=url, exc=e)
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                return None

        ex = concurrent.futures.ThreadPoolExecutor(max_workers=min(n, 4))
        result = None
        try:
            futs = {ex.submit(worker, i, u): i for i, u in enumerate(sources)}
            for fut in concurrent.futures.as_completed(futs):
                if winner[0] is not None:
                    break
                try:
                    fut.result()
                except Exception:  # noqa: BLE001 - 单源异常已记录，忽略
                    pass
            # 胜出文件移动到正式路径（必须在 finally 清理前完成，避免被误删）
            if winner[0] is not None:
                try:
                    if os.path.exists(zip_path):
                        os.remove(zip_path)
                except OSError:
                    pass
                try:
                    shutil.move(winner[0][1], zip_path)
                except Exception as e:  # noqa: BLE001
                    self._record_error("move", str(e), exc=e)
                    with lock:
                        winner[0] = None
                if winner[0] is not None:
                    self._report(80, "下载完成，准备解压")
                    result = zip_path
        finally:
            stop.set()
            ex.shutdown(wait=False, cancel_futures=True)
            for p in tmp_paths:
                if winner[0] is not None and p == winner[0][1]:
                    continue  # 已移动为 zip_path，跳过
                try:
                    os.remove(p)
                except OSError:
                    pass
        return result
