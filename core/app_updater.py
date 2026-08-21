"""app_updater — 程序自身自动更新（免安装版，纯逻辑无 UI 依赖）。

流程：
1. fetch_latest_tag()：GitHub Releases latest 的 tag（直连失败走国内镜像 ghproxy.net/gh-proxy.com）
2. find_portable_asset()：在 release assets 中找免安装版 zip（名称含「免安装」/portable）
3. build_download_urls()：资产下载 URL → [国内镜像..., 原始]，逐个尝试
4. download_update()：下载 zip 到临时目录（带进度回调）
5. prepare_update()：解压到程序目录同级「格式大师_new」+ 生成 update.bat（GBK 编码，
   中文 Windows cmd 默认代码页可正确解析中文路径/进程名）
6. 主程序退出后由 update.bat 完成：等主进程退出 → 删旧目录 → 移动新目录 → 启动新版本 → 自删

仓库配置见下方常量；发布免安装版时把 zip 上传到 GitHub Releases 即可。
"""
import json
import os
import shutil
import ssl
import tempfile
import urllib.request
import zipfile

from core.tool_updater import version_gt
from utils.mirrors import DOWNLOAD_MIRRORS, parallel_first

# ── GitHub 发布仓库（按需修改）──
APP_OWNER = "Gu-0312"
APP_REPO = "FormatMaster-EN"

# 免安装版资产匹配关键词（名称含任一即视为免安装包）
PORTABLE_KEYWORDS = ("免安装", "portable", "Portable", "PORTABLE")

# 国内加速镜像统一由 utils/mirrors.py 提供（多源并发抢答 + 快速失败）。
GITHUB_MIRRORS = DOWNLOAD_MIRRORS

_API = "https://api.github.com"
# 版本检查超时（秒）：直连 + 国内镜像并发抢答，任一源成功即返回；
# 原串行 4×8s=32s 已改为并发，单源超时不再拖慢整体。
_TIMEOUT = 8

_UA = "FormatMaster-Updater/1.0"


class UpdateCancelled(Exception):
    """用户取消了更新（should_stop 回调返回 True）。

    与普通下载失败区分：取消不尝试下一个源、不算错误，调用方应静默收尾。
    """


def _http_get(url):
    """GET 返回文本；失败返回 None。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        return None


def _first_ok(urls, parse):
    """并发请求多个 URL，返回第一个能成功解析的结果。

    直连 + 镜像并发抢答（见 utils.mirrors.parallel_first）：任一源成功
    即返回，其余线程立即取消（不等待慢源）。全部失败返回 None。
    """
    def _try(url):
        text = _http_get(url)
        if not text:
            return None
        try:
            return parse(text)
        except Exception:  # noqa: BLE001
            return None

    return parallel_first(urls, _try, timeout=_TIMEOUT)


# 程序版本检查结果缓存：发布不频繁，启动自动检查后 10 分钟内重复点击
# 「检查更新」直接返回缓存（0 耗时）。手动检查想拿最新可等 TTL 或重启。
_TAG_CACHE_TTL = 600  # 秒
_tag_cache = {"ts": 0.0, "tag": None}


def fetch_latest_tag(use_cache=True):
    """GitHub Releases latest 的版本号（tag 去 v 前缀，如 "1.3.8"）。

    直连 + 国内镜像并发抢答（gh-proxy.com 国内实测最快，~1s 出结果）；
    全部失败返回 None。use_cache=True 时 TTL 内命中缓存秒回。
    """
    import time

    now = time.time()
    if use_cache and _tag_cache["tag"] is not None \
            and now - _tag_cache["ts"] < _TAG_CACHE_TTL:
        return _tag_cache["tag"]

    url = f"{_API}/repos/{APP_OWNER}/{APP_REPO}/releases/latest"
    urls = [url] + [f"{m}{url}" for m in GITHUB_MIRRORS]

    def _parse(text):
        data = json.loads(text)
        tag = (data.get("tag_name") or "").lstrip("vV").strip()
        return tag or None

    tag = _first_ok(urls, _parse)
    if tag:
        _tag_cache["ts"] = now
        _tag_cache["tag"] = tag
    return tag


def fetch_asset_names(tag):
    """返回 release 的资产文件名列表（用于找免安装 zip）；失败返回 []。"""
    url = f"{_API}/repos/{APP_OWNER}/{APP_REPO}/releases/tags/v{tag}"
    urls = [url] + [f"{m}{url}" for m in GITHUB_MIRRORS]

    def _parse(text):
        data = json.loads(text)
        assets = data.get("assets") or []
        return [a.get("name", "") for a in assets]

    return _first_ok(urls, _parse) or []


def find_portable_asset(asset_names):
    """在资产名中找免安装 zip（名称含关键词且以 .zip 结尾）。

    优先匹配含版本号(当前 APP_VERSION)的；否则取第一个匹配的。
    返回资产名或 None。

    排除 GitHub UI 创建 Release 时自动生成的 Source code 归档
    （asset.name='Source code (zip)' 不以 .zip 结尾时不会进入 zips，
    但以 .zip 结尾时需按名排除，避免它干扰"唯一 zip"宽松兜底）。
    """
    from utils.config import APP_VERSION
    zips = [n for n in asset_names
            if n.lower().endswith(".zip")
            and "source" not in n.lower()]   # 排除 Source code 自动归档
    portable = [n for n in zips if any(k in n for k in PORTABLE_KEYWORDS)]
    if portable:
        # 优先当前版本号
        for n in portable:
            if APP_VERSION in n:
                return n
        return portable[0]
    # 宽松兜底：剩余 zip 中的第一个（用户上传的主安装包）
    return zips[0] if zips else None


def asset_download_url(asset_name, tag):
    """资产原始直链。"""
    return (f"https://github.com/{APP_OWNER}/{APP_REPO}/releases/"
            f"download/v{tag}/{asset_name}")


def release_page_url():
    """GitHub Releases 页面（供自动更新失败时引导手动下载）。"""
    return f"https://github.com/{APP_OWNER}/{APP_REPO}/releases"


def build_download_urls(asset_url):
    """[镜像1, 镜像2, ..., 原始]——镜像优先（国内可达），原始兜底。"""
    return [f"{m}{asset_url}" for m in GITHUB_MIRRORS] + [asset_url]


def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def download_update(urls, progress_cb=None, should_stop=None):
    """从 urls 逐个尝试下载 zip，返回本地 zip 路径；全部失败抛异常。

    progress_cb(done_bytes, total_bytes)：主线程外调用（与 download_ytdlp 同签名）。
    should_stop()：可选回调，返回 True 时立即中止下载（抛 UpdateCancelled，
    不尝试下一个源）。用于用户点「取消」后真正停止，而不是继续下完。
    """
    ctx = _ssl_ctx()
    tmp = os.path.join(tempfile.gettempdir(),
                       f"formatmaster_update_{os.getpid()}.zip")
    last_err = ""
    for idx, url in enumerate(urls):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": _UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=30, context=ctx) as resp, \
                    open(tmp, "wb") as f:
                total = int(resp.headers.get("Content-Length") or 0)
                done = 0
                while True:
                    if should_stop is not None and should_stop():
                        raise UpdateCancelled("用户取消更新")
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if progress_cb:
                        progress_cb(done, total)
            # 校验 zip 完整性
            with zipfile.ZipFile(tmp) as zf:
                if zf.testzip() is not None:
                    raise ValueError("zip 校验失败")
            return tmp
        except UpdateCancelled:
            # 用户取消：立即中止，不尝试下一个源
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
        except Exception as e:  # noqa: BLE001
            last_err = f"源{idx+1}失败: {e}"
            try:
                os.remove(tmp)
            except OSError:
                pass
            continue
    raise RuntimeError(f"更新包下载失败。{last_err}")


def prepare_update(zip_path, app_dir, app_exe_name):
    """解压新版本到 app_dir 同级「格式大师_new」，并生成 update.bat。

    参数：
        zip_path   下载好的更新包
        app_dir    当前程序目录（PyInstaller 免安装版目录，含 exe+_internal）
        app_exe_name 主程序 exe 名（如 "格式大师.exe"）
    返回 update.bat 路径。
    """
    parent = os.path.dirname(app_dir)
    new_dir = os.path.join(parent, "_fm_new")
    if os.path.exists(new_dir):
        shutil.rmtree(new_dir, ignore_errors=True)
    os.makedirs(new_dir, exist_ok=True)

    # 解压：zip 根可能是程序目录本身，或含一层「格式大师/」目录
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(new_dir)
    inner = os.path.join(new_dir, os.path.basename(app_dir))
    if os.path.isdir(inner):
        # 内层目录提升到 new_dir 根（避免更新器 move 后双重嵌套）
        for item in os.listdir(inner):
            shutil.move(os.path.join(inner, item), os.path.join(new_dir, item))
        shutil.rmtree(inner, ignore_errors=True)
    # 解压结果必须含主 exe，否则视为无效
    if not os.path.isfile(os.path.join(new_dir, app_exe_name)):
        shutil.rmtree(new_dir, ignore_errors=True)
        raise RuntimeError("更新包内容无效（未找到主程序）")

    bat_path = os.path.join(parent, "_fm_update.bat")
    _write_updater_bat(bat_path, parent, os.path.basename(app_dir), app_exe_name)
    return bat_path


def _write_updater_bat(bat_path, parent, dir_name, app_exe_name):
    """写 update.bat（GBK 编码，中文 Windows cmd 默认代码页可正确解析）。

    %~dp0 = bat 所在目录（即程序目录的父目录）；用相对引用避免硬编码绝对路径。

    回滚式替换（防「删旧失败/移新失败/新版起不来」导致程序丢失）：
      1. 旧目录改名备份 _fm_old（改名失败即中止，旧版原样可用）；
      2. 新目录 _fm_new 移入正式位置；
      3. 启动新版，等待 8 秒后检测进程存活：
         - 存活 → 删除备份，自删本脚本；
         - 未存活（新版起不来）→ 删除失败的新目录，把 _fm_old 改回，启动旧版。
    """
    # 所有目录/文件名均基于 bat 自身目录（%~dp0），内容里的中文目录名用 GBK 编码存储
    bat = (
        "@echo off\r\n"
        "rem FormatMaster updater (rollback-safe)\r\n"
        "setlocal\r\n"
        "set \"PD=%~dp0\"\r\n"
        "set \"OLD=" + dir_name + "\"\r\n"
        "set \"NEW=_fm_new\"\r\n"
        "set \"BAK=_fm_old\"\r\n"
        "set \"EXE=" + app_exe_name + "\"\r\n"
        ":wait\r\n"
        'tasklist /FI "IMAGENAME eq %EXE%" 2>nul | find /i "%EXE%" >nul\r\n'
        "if not errorlevel 1 (\r\n"
        "  timeout /t 1 /nobreak >nul\r\n"
        "  goto wait\r\n"
        ")\r\n"
        "rem 1) 旧目录改名备份（失败即中止，旧版原样可用）\r\n"
        'if exist "%PD%%BAK%" rmdir /s /q "%PD%%BAK%"\r\n'
        'if exist "%PD%%OLD%" ren "%PD%%OLD%" "%BAK%"\r\n'
        "if errorlevel 1 goto restore\r\n"
        "rem 2) 新目录移入正式位置\r\n"
        'if exist "%PD%%NEW%" (\r\n'
        '  move /y "%PD%%NEW%" "%PD%%OLD%" >nul\r\n'
        "  if errorlevel 1 goto restore\r\n"
        ")\r\n"
        "rem 3) 启动新版并确认存活（8 秒窗口）\r\n"
        'start "" "%PD%%OLD%\\%EXE%"\r\n'
        "timeout /t 8 /nobreak >nul\r\n"
        'tasklist /FI "IMAGENAME eq %EXE%" 2>nul | find /i "%EXE%" >nul\r\n'
        "if errorlevel 1 goto restore\r\n"
        "rem 启动成功：清理备份并自删\r\n"
        'if exist "%PD%%BAK%" rmdir /s /q "%PD%%BAK%"\r\n'
        'del /f /q "%~f0"\r\n'
        "exit\r\n"
        ":restore\r\n"
        "rem 新版启动失败：恢复旧版\r\n"
        'if exist "%PD%%OLD%" rmdir /s /q "%PD%%OLD%"\r\n'
        'if exist "%PD%%BAK%" ren "%PD%%BAK%" "%OLD%"\r\n'
        'start "" "%PD%%OLD%\\%EXE%"\r\n'
        'del /f /q "%~f0"\r\n'
        "exit\r\n"
    )
    with open(bat_path, "w", encoding="gbk", newline="") as f:
        f.write(bat)


def cleanup_backup(app_dir):
    """启动时清理上次更新的遗留目录（幂等、静默、绝不抛异常）。

    - _fm_old：旧版备份目录（更新成功后的残留，update.bat 未能删除时）；
    - _fm_new：更新包解压目录（下载/解压后未完成替换的残留，update.bat
      从未运行或中途失败时遗留，占磁盘较大）。
    新版已正常启动并运行到这一步，说明更新流程已结束，残留目录均无价值。
    """
    try:
        parent = os.path.dirname(app_dir)
        for name in ("_fm_old", "_fm_new"):
            p = os.path.join(parent, name)
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
    except Exception:  # noqa: BLE001
        pass
