"""tool_check — 工具/依赖状态检查（首页「工具状态」卡，纯逻辑可测）。"""

import os

from utils.config import get_ffmpeg_path, get_ffprobe_path, get_resource_path

# 打包后 get_resource_path 指向 _MEIPASS/bin（对应 build.py --add-data bin;bin）；
# 开发环境即项目根 bin/。
_BIN_DIR = get_resource_path("bin")


def check_tools():
    """同步检查各项工具状态。

    返回 [(名称, 是否正常, 详情)]：
    - FFmpeg / FFprobe：按 utils.config 查找链（用户 bin → 项目 bin → PATH）
    - yt-dlp：项目 bin/yt-dlp.exe
    - OCR 引擎：rapidocr_onnxruntime 可导入
    - 插件中心：插件扫描数量
    """
    items = []
    ff = get_ffmpeg_path()
    items.append(("FFmpeg", bool(ff),
                  os.path.basename(ff) if ff else "未安装"))
    fp = get_ffprobe_path()
    items.append(("FFprobe", bool(fp),
                  os.path.basename(fp) if fp else "未安装"))
    dl = os.path.isfile(os.path.join(_BIN_DIR, "yt-dlp.exe"))
    items.append(("yt-dlp", dl, "已就绪" if dl else "未安装"))
    try:
        import rapidocr_onnxruntime  # noqa: F401
        ocr_ok = True
    except ImportError:
        ocr_ok = False
    items.append(("OCR 引擎", ocr_ok,
                  "已就绪" if ocr_ok else "未安装"))
    try:
        from core.plugin_loader import scan_plugins
        n = len(scan_plugins())
        items.append(("插件中心", True, f"{n} 个插件已加载"))
    except Exception:  # noqa: BLE001
        items.append(("插件中心", False, "加载失败"))
    return items


def _version_first_line(exe, pattern):
    """运行 exe -version，用 pattern 从首行提取版本号；失败返回 None。"""
    import re
    import subprocess
    try:
        r = subprocess.run([exe, "-version"], capture_output=True, timeout=8,
                           text=True, encoding="utf-8", errors="ignore",
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        first = (r.stdout or "").splitlines()
        if not first:
            return None
        m = re.search(pattern, first[0], re.IGNORECASE)
        if not m:
            return None
        raw = m.group(1).strip()
        # 统一交给 core.tool_updater.display_version 美化（剥离厂商前缀 / 构建
        # 日期、git 描述→日期），避免状态卡显示 n8.1.2-20260723 这类脏版本号。
        from core.tool_updater import display_version
        return display_version(raw)
    except Exception:  # noqa: BLE001
        return None


def ffmpeg_version():
    """FFmpeg 版本号（如 "8.1.1"）；后台线程调用，失败返回 None。"""
    ff = get_ffmpeg_path()
    if not ff:
        return None
    return _version_first_line(ff, r"ffmpeg version (\S+)")


def ffprobe_version():
    """FFprobe 版本号（如 "8.1.1"）；后台线程调用，失败返回 None。"""
    fp = get_ffprobe_path()
    if not fp:
        return None
    return _version_first_line(fp, r"ffprobe version (\S+)")


def ytdlp_version():
    """yt-dlp 版本号（如 "2026.07.04"）。

    注意：yt-dlp.exe 是 PyInstaller 单文件，`--version` 每次启动解压约 7 秒，
    只应在后台线程调用（复用 core.tool_updater 的实现）。
    """
    from core.tool_updater import current_ytdlp_version
    return current_ytdlp_version()


def ocr_version():
    """OCR 引擎（rapidocr-onnxruntime）版本号（如 "1.4.4"）；失败返回 None。"""
    try:
        import importlib.metadata as _md
        return _md.version("rapidocr-onnxruntime")
    except Exception:  # noqa: BLE001
        return None
