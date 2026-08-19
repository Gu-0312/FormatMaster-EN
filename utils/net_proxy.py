"""utils/net_proxy — 网络代理设置（统一应用到全局）。

策略：设置 HTTP_PROXY / HTTPS_PROXY / ALL_PROXY 环境变量——
`urllib.request`（自动更新 / 工具更新 / FFmpeg 下载）默认读取环境变量代理，
设置后即全局生效，无需改动各下载模块。

调用时机：应用启动时（run() 里读 prefs 应用一次）。yt-dlp 视频下载
另在 download_panel 读取同款 pref 追加 --proxy 参数。
"""
import os


def apply_proxy(mode="off", host="", port=0):
    """按设置应用/清除环境变量代理。幂等，绝不抛异常。

    mode: "off" 关闭 / "manual" 手动代理。
    host/port: manual 模式下的代理地址。
    """
    try:
        if mode == "manual" and host and int(port) > 0:
            proxy = f"http://{host}:{int(port)}"
            os.environ["HTTP_PROXY"] = proxy
            os.environ["HTTPS_PROXY"] = proxy
            os.environ["ALL_PROXY"] = proxy
            # urllib 在 Windows 下读注册表 IE 代理，环境变量优先；清 no_proxy 兜底
            os.environ.pop("NO_PROXY", None)
            return True
        # 关闭：清除全部代理环境变量（恢复 urllib 默认行为）
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                    "http_proxy", "https_proxy", "all_proxy"):
            os.environ.pop(key, None)
        return False
    except Exception:  # noqa: BLE001 - 代理设置失败不影响启动
        return False


def proxy_from_prefs(get_pref):
    """从 prefs 读取代理设置并应用；返回是否已启用代理。"""
    mode = get_pref("proxy_mode", "off")
    host = get_pref("proxy_host", "")
    port = get_pref("proxy_port", 0)
    return apply_proxy(mode, host, port)


def proxy_args_for_ytdlp(get_pref):
    """返回 yt-dlp 的 --proxy 参数列表（未启用代理时为空列表）。"""
    if get_pref("proxy_mode", "off") != "manual":
        return []
    host = get_pref("proxy_host", "")
    port = get_pref("proxy_port", 0)
    try:
        if host and int(port) > 0:
            return ["--proxy", f"http://{host}:{int(port)}"]
    except (TypeError, ValueError):
        pass
    return []
