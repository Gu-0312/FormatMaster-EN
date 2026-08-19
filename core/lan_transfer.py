"""lan_transfer — 局域网文件传输与设备协作（标准库 http.server，无第三方依赖）。

- 发送：文件/文件夹（自动 zip）复制到临时共享目录 → HTTP 下载服务 + 二维码
- 接收：HTTP 上传服务，浏览器选择文件上传保存
- 密码保护：发送/接收服务可设访问密码（cookie 会话）
- 防火墙：启动服务时自动添加 Windows 防火墙入站放行规则（需管理员，
  失败返回 False 由面板提示手动放行）
- 传输回调：接收完成/下载记录回调（历史、通知、速度）

服务器在线程中运行，stop 时关闭。
"""

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def add_firewall_rule(port):
    """为 TCP 端口添加 Windows 防火墙入站放行规则（需管理员权限）。

    返回 True=已添加/已存在；False=失败（权限不足等，面板应提示手动放行）。
    """
    if os.name != "nt":
        return True
    try:
        r = subprocess.run(
            ["netsh", "advfirewall", "firewall", "add", "rule",
             f"name=FormatMaster LAN {port}", "dir=in", "action=allow",
             "protocol=TCP", f"localport={port}",
             f"program={sys.executable}"],
            capture_output=True, timeout=10, check=False,
            creationflags=_CREATE_NO_WINDOW)
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def remove_firewall_rule(port):
    """删除端口对应的防火墙规则（服务停止时调用，忽略失败）。"""
    if os.name != "nt":
        return
    try:
        subprocess.run(
            ["netsh", "advfirewall", "firewall", "delete", "rule",
             f"name=FormatMaster LAN {port}"],
            capture_output=True, timeout=10, check=False,
            creationflags=_CREATE_NO_WINDOW)
    except Exception:  # noqa: BLE001
        pass


def get_lan_ip():
    """获取本机局域网 IP；失败返回 '127.0.0.1'。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:  # noqa: BLE001
        return "127.0.0.1"


def get_lan_ips():
    """返回本机所有可用 IPv4（非环回、非链路本地），默认路由出口排最前。

    多网卡场景（WiFi + USB 共享 + 虚拟网卡 + Tailscale 等）下，
    手机可达的 IP 未必是默认出口，需要列出全部供用户选择。
    """
    ips = []
    try:
        host = socket.gethostname()
        for info in socket.getaddrinfo(host, None, socket.AF_INET):
            ip = info[4][0]
            if (ip not in ips and not ip.startswith("127.")
                    and not ip.startswith("169.254.")):
                ips.append(ip)
    except Exception:  # noqa: BLE001
        pass
    default = get_lan_ip()
    if default and default not in ips:
        ips.insert(0, default)
    if default in ips and ips[0] != default:
        ips.remove(default)
        ips.insert(0, default)
    return ips


def _start_idle_watch(handler_cls, timeout, on_idle):
    """空闲超时监视：timeout 秒无任何请求则回调 on_idle。timeout<=0 禁用。

    返回控制 dict（stop 置 True 停止监视），供服务 stop 时清理。
    """
    if not timeout or not callable(on_idle):
        return None
    flag = {"stop": False}

    def loop():
        while not flag["stop"]:
            time.sleep(5)
            try:
                if time.time() - handler_cls.last_visit > timeout:
                    on_idle()
                    return
            except Exception:  # noqa: BLE001
                return

    threading.Thread(target=loop, daemon=True).start()
    return flag


def _unique_path(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while os.path.exists(f"{base}_{i}{ext}"):
        i += 1
    return f"{base}_{i}{ext}"


# ── 分类数据（sender 和 receiver 共用）─────────

_CLASSIFY_GROUPS = {
    "图片": {
        # 常规位图/矢量
        "jpg", "jpeg", "jpe", "jfif", "png", "apng", "gif", "webp",
        "bmp", "ico", "svg", "avif", "heic", "heif", "tif", "tiff",
        "wbmp", "jxl", "bpg",
        # 相机 RAW
        "raw", "cr2", "cr3", "nef", "nrf", "arw", "srf", "srw",
        "orf", "rw2", "pef", "dng", "raf", "x3f", "kdc", "erf",
        "mrw", "mef", "mos", "iiq", "3fr",
        # 设计/特效/贴图
        "psd", "psb", "ai", "eps", "dds", "exr", "hdr", "tga",
        "pcx", "xcf",
    },
    "视频": {
        "mp4", "m4v", "mkv", "avi", "mov", "wmv", "flv", "f4v",
        "webm", "mpg", "mpeg", "mpe", "vob", "mts", "m2ts", "ts",
        "m2v", "ogv", "ogm", "3gp", "3g2", "asf", "asx", "rm",
        "rmvb", "divx", "xvid", "dv", "mxf", "m2p", "mod", "tod",
        "trp", "m1v", "nsv", "wtv",
    },
    "音频": {
        "mp3", "mp2", "mp1", "wav", "flac", "aac", "m4a", "m4b",
        "ogg", "oga", "opus", "wma", "ape", "mid", "midi", "amr",
        "wv", "tta", "mpc", "dsf", "dff", "aif", "aiff", "au",
        "caf", "spx", "ra",
        # 播放列表
        "m3u", "m3u8", "pls",
    },
    "文档": {
        # Office
        "doc", "docx", "docm", "dot", "dotx", "dotm",
        "xls", "xlsx", "xlsm", "xlsb", "xlt", "xltx", "xltm",
        "ppt", "pptx", "pptm", "pot", "potx", "potm", "xps",
        "csv", "tsv",
        # WPS 办公
        "wps", "et", "dps", "wpt",
        # PDF / 电子书
        "pdf", "epub", "mobi", "azw", "azw3", "fb2", "chm",
        "djvu", "oxps",
        # 文本 / 代码 / 数据
        "txt", "md", "rtf", "log", "ini", "conf", "cfg", "json",
        "xml", "yaml", "yml", "html", "htm", "css", "js",
        "jsx", "tsx", "vue", "py", "c", "cpp", "h", "hpp", "java",
        "go", "rs", "rb", "php", "sh", "bat", "cmd", "ps1", "vbs",
        "lua", "sql", "sqlite", "db", "mdb", "accdb", "ics", "vcf",
        "tex",
        # 苹果 iWork
        "pages", "numbers", "key",
    },
    "压缩包": {
        # 主流压缩格式
        "zip", "zipx", "rar", "7z", "tar", "gz", "bz2", "xz",
        "tgz", "tbz2", "txz", "zst", "lz", "lzma", "br",
        # 压缩/归档分卷与老格式
        "cab", "ace", "arc", "alz", "z", "lzh", "lha", "cpio",
        "iso", "uue",
        # 安装包 / 程序包（本质为归档）
        "msi", "wim", "swm", "jar", "war", "apk", "ipa", "deb",
        "rpm", "ar",
        # 扩展包 / 文档包 / 漫画包
        "xpi", "crx", "whl", "egg", "cbz", "cbr",
    },
}


_MEDIA_EXTS = _CLASSIFY_GROUPS["图片"] | _CLASSIFY_GROUPS["视频"]

_PREVIEW_EXTS = {
    # 图片
    "jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "heic", "heif",
    # 视频
    "mp4", "webm", "ogg",
    # PDF
    "pdf",
    # Office文档（需要转换）
    "doc", "docx", "xls", "xlsx", "ppt", "pptx",
}


# ── 门面函数 ────────────────────────────────────


def start_send_server(paths, port=8000, ip=None, progress_cb=None,
                      on_downloaded=None, on_all_done=None,
                      idle_timeout=0, on_idle=None):
    """把 paths（文件或文件夹）复制/打包到共享目录并启动下载服务。

    paths 含文件夹时自动打包 zip。返回 (url, server, share_dir)。
    on_all_done：全部文件下载完成时回调（触发一次）。
    idle_timeout：空闲秒数，超过则回调 on_idle（0=禁用）。
    """
    # 惰性导入：lan_sender 顶层依赖本模块（_CLASSIFY_GROUPS 等共享定义），
    # 若在此顶层 import lan_sender 会形成循环导入（按不同顺序 import 时
    # ImportError）。函数内导入在调用时才解析，规避循环。
    from core.lan_sender import _SendServer, make_zip
    share_dir = tempfile.mkdtemp(prefix="fm_share_")
    files = []
    try:
        for p in paths:
            if os.path.isdir(p):
                z = make_zip([p], share_dir,
                             os.path.basename(p.rstrip("\\/")),
                             progress_cb=progress_cb)
                files.append(z)
            elif os.path.isfile(p):
                dst = os.path.join(share_dir, os.path.basename(p))
                if os.path.abspath(dst).lower() != os.path.abspath(p).lower():
                    shutil.copy2(p, dst)
                files.append(dst)
        if not files:
            shutil.rmtree(share_dir, ignore_errors=True)
            return None, None, None
        if progress_cb:
            progress_cb(90, f"共享 {len(files)} 个文件/压缩包…")
        server = _SendServer(share_dir, port, on_downloaded=on_downloaded,
                             on_all_done=on_all_done,
                             idle_timeout=idle_timeout, on_idle=on_idle).start()
        if ip:
            server.url = lambda _ip=None, _u=server.url, _ip0=ip: _u(_ip0)
    except Exception:  # noqa: BLE001
        shutil.rmtree(share_dir, ignore_errors=True)
        return None, None, None
    if progress_cb:
        progress_cb(100, "服务已启动")
    return server.url(), server, share_dir


def start_recv_server(save_dir, port=8001, ip=None, on_received=None,
                      conflict="rename", classify=False,
                      on_progress=None, idle_timeout=0, on_idle=None):
    """启动接收服务（端口被占自动 +1）。

    classify: 按扩展名分类子目录。on_progress: (done, total) 实时进度。
    idle_timeout: 空闲秒数超时回调 on_idle（0=禁用）。
    返回 (url, server)；失败返回 (None, None)。
    """
    # 惰性导入（同 start_send_server：避免 lan_receiver ↔ lan_transfer 循环）
    from core.lan_receiver import _RecvServer
    os.makedirs(save_dir, exist_ok=True)
    try:
        server = _RecvServer(save_dir, port, on_received, conflict,
                             classify, on_progress, idle_timeout,
                             on_idle).start()
    except OSError:
        return None, None
    if ip:
        server.url = lambda _ip=None, _u=server.url, _ip0=ip: _u(_ip0)
    return server.url(), server
