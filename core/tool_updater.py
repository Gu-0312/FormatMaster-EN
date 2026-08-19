"""tool_updater — 外部工具（FFmpeg / yt-dlp）版本检测与更新。

纯逻辑、无 UI 依赖，供首页「工具状态」卡与启动后台检测共用。

版本来源：
- FFmpeg 最新版本：https://www.gyan.dev/ffmpeg/builds/release-version（纯文本版本号）
- yt-dlp 最新版本：GitHub API releases/latest 的 tag_name
- 当前版本：`ffmpeg -version` 首行 / `yt-dlp --version`

版本比较：语义化数字序列（FFmpeg "8.1.1" vs "9.0.1"；yt-dlp "2026.07.04"）。
所有网络/子进程失败一律静默返回 None，绝不阻塞调用方。
"""
import json
import os
import re
import subprocess
import urllib.request

from utils.config import get_ffmpeg_path, get_writable_bin_dir
from utils.mirrors import API_MIRRORS, DOWNLOAD_MIRRORS, parallel_first

GYAN_VERSION_URL = "https://www.gyan.dev/ffmpeg/builds/release-version"
# BtbN FFmpeg-Builds 最新 release（GitHub API，published_at 日期可比较，
# 可用 gh-proxy 镜像加速——gyan.dev 国内实测 HTTP 000 不可达）
FFMPEG_BTBN_API = ("https://api.github.com/repos/BtbN/FFmpeg-Builds/"
                   "releases/latest")
YTDLP_API_URL = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
YTDLP_EXE = "yt-dlp.exe" if os.name == "nt" else "yt-dlp"

# 国内镜像统一由 utils/mirrors.py 提供（API_MIRRORS 检查 / DOWNLOAD_MIRRORS
# 下载），多源并发抢答（parallel_first）+ 快速失败，任一源可达即出结果。
GITHUB_MIRRORS = API_MIRRORS  # 兼容旧引用

# 检查超时（秒）：国内网络 gyan.dev / GitHub API 常超时，超时过长会让
# 「检查更新」按钮点击后长时间无反馈（实测最坏 ~23s）。收紧为 5s，
# 配合「镜像并发抢答」，单次手动检查最快 1~2s 出结果。
_TIMEOUT = 5


def _parse_version(v):
    """提取版本字符串中的数字序列（用于比较）。"""
    return [int(x) for x in re.findall(r"\d+", str(v))]


# BtbN master 构建的版本号格式：N-126133-gead4378652-20260814（git describe）
# 捕获组 1 = 末尾构建日期（20260814）
_GIT_DESCRIBE_RE = re.compile(r"^N-\d+-g[0-9a-fA-F]+-(\d{8})$")


def _is_git_describe(v):
    """判断版本号是否为 git 描述格式（BtbN master 构建）。"""
    return bool(_GIT_DESCRIBE_RE.match(str(v).strip()))


def display_version(v):
    """版本号美化显示。

    - git 描述格式（BtbN master 构建 N-126133-gead4378652-20260814）
      → 提取构建日期显示为 2026.08.14；
    - release 版本（9.0.1-essentials_build / n8.1.2-20260723）→ 剥离开头的
      厂商前缀（npmmirror 的 n、通用 v）与结尾的构建日期，只取 X.Y.Z
      （如 n8.1.2-20260723 → 8.1.2），避免状态卡显示脏版本号。
    """
    v = str(v).strip()
    gm = _GIT_DESCRIBE_RE.match(v)
    if gm:
        d = gm.group(1)
        return f"{d[:4]}.{d[4:6]}.{d[6:8]}"
    # release 版：剥离开头的厂商前缀（n / v）与结尾构建日期，取 X.Y.Z。
    # 例：n8.1.2-20260723 → 8.1.2；9.0.1-essentials_build → 9.0.1。
    head = re.match(r"[nv]?(\d+(?:\.\d+)*)", v)
    return head.group(1) if head else v


def version_gt(a, b):
    """语义化版本比较：a > b 返回 True。忽略非数字后缀。

    特殊处理：b 为 git 描述版本（如 N-126133-...-20260814，BtbN master
    构建）时，与 release 版本号（如 9.0.1）语义不可比；且国内网络下载源
    本身即 master 构建，提示「有 release 更新」只会引导用户反复下载仍
    得到 master（死循环）。故视为「已是最新」返回 False。
    """
    if _is_git_describe(b):
        return False
    try:
        pa, pb = _parse_version(a), _parse_version(b)
        while len(pa) < len(pb):
            pa.append(0)
        while len(pb) < len(pa):
            pb.append(0)
        return pa > pb
    except Exception:  # noqa: BLE001
        return False


def _run_version_raw(exe, args, pattern):
    """运行 exe 获取版本首行，用 pattern 提取『原始』版本 token（不美化）。

    返回如 "N-126133-gead4378652-20260814"（BtbN master）或
    "9.0.1-essentials_build"（gyan）/ "8.1.2"（npmmirror）。失败返回 None。
    供 current_ffmpeg_version / current_ffmpeg_version_raw 复用。
    """
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        r = subprocess.run(
            [exe] + args, capture_output=True, timeout=15,
            text=True, encoding="utf-8", errors="ignore",
            creationflags=flags)
        first = (r.stdout or "").splitlines()
        if not first:
            return None
        m = re.search(pattern, first[0], re.IGNORECASE)
        return m.group(1).strip() if m else None
    except Exception:  # noqa: BLE001
        return None


def current_ffmpeg_version_raw():
    """当前 FFmpeg 原始版本 token（如 "N-...-20260814" / "9.0.1-..."）。

    用于判断构建版本体系（BtbN 构建日期 vs release X.Y.Z），供 check_updates
    选择正确比对基准，避免日期版与版本号版错配误报更新。
    """
    ff = get_ffmpeg_path()
    if not ff:
        return None
    return _run_version_raw(ff, ["-version"], r"ffmpeg version (\S+)")


def current_ffmpeg_version():
    """当前 FFmpeg 版本号（如 "8.1.1" / "2026.08.14" 美化显示）；失败返回 None。"""
    raw = current_ffmpeg_version_raw()
    return display_version(raw) if raw else None


def _ytdlp_exe_path():
    """定位 yt-dlp 可执行文件：用户可写 bin → 内置 bin（打包资源）。"""
    p = os.path.join(get_writable_bin_dir(), YTDLP_EXE)
    if os.path.isfile(p):
        return p
    # 内置 bin：打包后经 get_resource_path 指向 _MEIPASS/bin（build.py
    # --add-data bin;bin），开发环境即项目根 bin/
    try:
        from utils.config import get_resource_path
        proj = get_resource_path(os.path.join("bin", YTDLP_EXE))
        return proj if os.path.isfile(proj) else None
    except Exception:  # noqa: BLE001
        return None


# yt-dlp 版本缓存：yt-dlp.exe 是 PyInstaller 单文件，`--version` 每次启动
# 解压约 7 秒，版本在程序运行期间不变（除非更新），故缓存首次结果，
# 后续检测直接用缓存（download_ytdlp 更新成功后清缓存）。
_ytdlp_version_cache = None


def current_ytdlp_version():
    """当前 yt-dlp 版本号（如 "2026.07.04"）；失败返回 None。

    注意：yt-dlp.exe 是 PyInstaller 单文件，每次启动需解压运行时，
    `--version` 实测约 7 秒（远超一般 CLI）。首次结果缓存，避免重复耗时。
    """
    global _ytdlp_version_cache
    if _ytdlp_version_cache is not None:
        return _ytdlp_version_cache
    exe = _ytdlp_exe_path()
    if not exe:
        return None
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        r = subprocess.run(
            [exe, "--version"], capture_output=True, timeout=20,
            text=True, encoding="utf-8", errors="ignore",
            creationflags=flags)
        line = (r.stdout or "").strip().splitlines()
        ver = line[0].strip() if line else None
        if ver:
            _ytdlp_version_cache = ver
        return ver
    except Exception:  # noqa: BLE001
        return None


def _http_get_text(url, timeout=_TIMEOUT):
    """GET 请求返回响应文本；失败返回 None。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FormatMaster"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return None


def fetch_latest_ffmpeg_both(raw=None):
    """返回 (btbn_date, gyan_ver) 双版本基准（按已安装版本体系只查需要的源）：

    - raw 为 BtbN git 描述（master 构建）→ 只查 BtbN 构建日期，省去 gyan 请求；
    - raw 为 release（gyan / npmmirror）→ 只查 gyan release 版本号，省去 BtbN 请求；
    - raw 为 None（兼容旧调用）→ 两者都查。

    任一网络失败为 None。供 check_updates 选择正确比对基准，避免日期版与
    版本号版错配误报更新。
    """
    if raw is not None and _is_git_describe(raw):
        btbn = parallel_first(
            [f"{m}{FFMPEG_BTBN_API}" for m in API_MIRRORS],
            _fetch_btbn_latest_from_url, timeout=4)
        return btbn, None
    if raw is not None:
        gyan = (_http_get_text(GYAN_VERSION_URL, timeout=4) or "").strip() or None
        return None, gyan
    # raw 未知：两者都查（兼容旧调用 fetch_latest_ffmpeg_version）
    btbn = parallel_first(
        [f"{m}{FFMPEG_BTBN_API}" for m in API_MIRRORS],
        _fetch_btbn_latest_from_url, timeout=4)
    gyan = (_http_get_text(GYAN_VERSION_URL, timeout=4) or "").strip() or None
    return btbn, gyan


def fetch_latest_ffmpeg_version():
    """最新 FFmpeg 版本号（单一值，兼容旧调用）。优先 BtbN 日期（命中即返回，
    不查 gyan），失败才 gyan.dev 兜底。"""
    btbn = parallel_first(
        [f"{m}{FFMPEG_BTBN_API}" for m in API_MIRRORS],
        _fetch_btbn_latest_from_url, timeout=4)
    if btbn:
        return btbn
    return (_http_get_text(GYAN_VERSION_URL, timeout=4) or "").strip() or None


def _fetch_btbn_latest_from_url(url):
    """解析 BtbN release API 响应，返回发布日期版本号（"2026.08.16"）。

    BtbN 的 tag 恒为 "latest" 不可比较，published_at 才是每次构建的真实
    时间；解析失败返回 None。
    """
    text = _http_get_text(url, timeout=4)
    if not text:
        return None
    try:
        data = json.loads(text)
        pub = (data.get("published_at") or "").strip()
        if not pub:
            return None
        # "2026-08-16T02:33:07Z" → "2026.08.16"
        return pub[:10].replace("-", ".")
    except Exception:  # noqa: BLE001
        return None


def _fetch_btbn_latest_mirror(mirror):
    """兼容旧调用：传镜像前缀（如 "https://gh-proxy.com/"）拼完整 URL。"""
    return _fetch_btbn_latest_from_url(f"{mirror}{FFMPEG_BTBN_API}")


def fetch_latest_ytdlp_version():
    """yt-dlp 最新 release 版本号（tag 去 v 前缀）；失败返回 None。

    镜像并发抢答 + GitHub 直连兜底。
    """
    def _from_url(url):
        text = _http_get_text(url)
        if not text:
            return None
        try:
            data = json.loads(text)
            tag = (data.get("tag_name") or "").lstrip("vV").strip()
            return tag or None
        except Exception:  # noqa: BLE001
            return None

    urls = [f"{m}{YTDLP_API_URL}" for m in API_MIRRORS] + [YTDLP_API_URL]
    return parallel_first(urls, _from_url)


# 工具更新检查结果缓存：FFmpeg/yt-dlp 更新频率低（周/月级），启动自动
# 检测后 5 分钟内重复点击「检查更新」直接返回缓存结果（0 耗时），不必
# 重复联网。手动检查想要最新结果可等 TTL 过期或重启程序。
_CHECK_CACHE_TTL = 300  # 秒
_check_cache = {"ts": 0.0, "result": None}


def check_updates(use_cache=True):
    """检测需要更新的工具。

    返回 [{"tool": "ffmpeg"|"yt-dlp", "current": str, "latest": str}, ...]；
    无新版本或任一检测失败（静默）时返回空列表。绝不抛异常。

    FFmpeg 受限提示：当官方有更高版本但当前网络实际下不到时，返回带
    "hint": True 的条目（含 official_latest），供 UI 显示「更新受限」
    信息而非「立即更新」按钮（auto 检测应静默，仅手动检查才提示）。

    use_cache=True（默认）：TTL 内命中缓存直接返回，重复点击秒回；
    use_cache=False：强制重新检测（下载前确认最新版等场景）。

    FFmpeg 与 yt-dlp 并行检测：二者都含子进程 + 网络请求（首次最坏约
    7s——yt-dlp.exe --version 解压），并行后总耗时约 max(4, 7) ≈ 7s；
    yt-dlp 本地版本与 check_updates 结果均有缓存，二次检测 0 耗时。
    """
    import threading
    import time

    now = time.time()
    if use_cache and _check_cache["result"] is not None \
            and now - _check_cache["ts"] < _CHECK_CACHE_TTL:
        return list(_check_cache["result"])

    results = {}

    def _check_ffmpeg():
        try:
            cur = current_ffmpeg_version()
            raw = current_ffmpeg_version_raw()
            if not cur or not raw:
                return
            # 统一基准：用 best_ffmpeg_source 取与『实际可下载版本』一致的最新版
            # （按已安装构建的版本体系选源），确保「广告的版本」==「下载安装的版本」，
            # 杜绝「更新完重进仍提示更新」死循环。
            from utils import ffmpeg_manager as fm
            target = fm.best_ffmpeg_source(raw)
            if target and version_gt(target[1], cur):
                results["ffmpeg"] = {
                    "tool": "ffmpeg",
                    "current": cur,
                    "latest": target[2],
                }
                return
            # 可达源无更新 → 查「官方最新」（忽略二进制可达性）：若官方确实更高，
            # 记 hint 条目供 UI 提示「官方有更新但当前网络下不到」，避免误报「已最新」。
            if not _is_git_describe(raw):
                official = fm.official_latest_ffmpeg()
                if official and version_gt(official[0], cur):
                    results["ffmpeg"] = {
                        "tool": "ffmpeg",
                        "current": cur,
                        "latest": target[2] if target else cur,
                        "official_latest": official[1],
                        "hint": True,
                    }
        except Exception:  # noqa: BLE001
            pass

    def _check_ytdlp():
        try:
            cur = current_ytdlp_version()
            latest = fetch_latest_ytdlp_version()
            if cur and latest and version_gt(latest, cur):
                results["yt-dlp"] = {
                    "tool": "yt-dlp",
                    "current": display_version(cur),
                    "latest": display_version(latest),
                }
        except Exception:  # noqa: BLE001
            pass

    t1 = threading.Thread(target=_check_ffmpeg, daemon=True)
    t2 = threading.Thread(target=_check_ytdlp, daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    out = [results[k] for k in ("ffmpeg", "yt-dlp") if k in results]
    _check_cache["ts"] = now
    _check_cache["result"] = list(out)
    return out


def download_ytdlp(progress_cb=None):
    """下载最新 yt-dlp.exe 到可写 bin 目录，返回 (ok, msg)。

    流程：获取最新 tag → 经国内镜像下载到 .tmp → 替换旧 exe（若旧文件
    被占用则报错）。progress_cb(done_bytes, total_bytes)：供进度条驱动，
    主线程外调用。注意：此函数含网络下载（可能几十秒），必须由调用方
    在后台线程执行。
    """
    tag = fetch_latest_ytdlp_version()
    if not tag:
        return (False, "获取 yt-dlp 最新版本失败，请检查网络")
    raw = f"https://github.com/yt-dlp/yt-dlp/releases/download/{tag}/{YTDLP_EXE}"
    # 镜像优先（国内可达），原始直连兜底
    urls = [f"{m}{raw}" for m in DOWNLOAD_MIRRORS] + [raw]
    dest_dir = get_writable_bin_dir()
    dest = os.path.join(dest_dir, YTDLP_EXE)
    tmp = dest + ".tmp"
    last_err = ""
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "FormatMaster"})
            with urllib.request.urlopen(req, timeout=60) as resp, \
                    open(tmp, "wb") as f:
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
            break  # 下载成功，跳出源循环
        except Exception as e:  # noqa: BLE001
            last_err = f"{e}"
            try:
                if os.path.isfile(tmp):
                    os.remove(tmp)
            except OSError:  # noqa: BLE001
                pass
    else:
        return (False, f"yt-dlp 下载失败：{last_err}")
    # 替换旧版本（旧文件可能正被下载任务占用，删除失败时给出明确提示）
    try:
        if os.path.isfile(dest):
            os.remove(dest)
    except OSError as e:
        try:
            os.remove(tmp)
        except OSError:  # noqa: BLE001
            pass
        return (False, f"无法替换旧版本（可能正被使用）：{e}")
    os.replace(tmp, dest)
    # 更新成功后清版本缓存，下次检测重新读取新版本号
    global _ytdlp_version_cache
    _ytdlp_version_cache = None
    return (True, tag)
