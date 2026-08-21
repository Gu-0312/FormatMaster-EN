"""国内 GitHub 加速镜像统一管理（版本检查 / 下载共用）。

三处调用方（core/tool_updater.py、core/app_updater.py、
utils/ffmpeg_manager.py）原本各自维护一份镜像列表，改由此模块统一提供：
以后增删镜像只改这一处即可。

实测结论（2026-08-16，无代理环境直连 40+ 候选镜像）：
- gh-proxy.com：API + 下载双通（API ~1.3s / 下载 ~0.9s），但偶发超时
  （多次实测既有 1s 命中也有 6s 超时）→ 不稳定，必须配合并发抢答；
- ghproxy.net：API 403 快速失败（~0.7s，不阻塞），下载稳（~0.9s）；
- gh.ddlc.top：API 404（~0.8s），下载稳（~0.9s）。
- 以下镜像已实测失效或返回错误内容，勿加：
  ghfast.top / mirror.ghproxy.com / github.moeyy.xyz / ghproxy.cn（HTML 页）/
  ghps.cc / gh-proxy.net / gh.con.sh（abuse 暂停）/ ghproxy.cc / gh.llkk.cc /
  gh.endpot.cn / hub.gitmirror.com / gh.991231.xyz / github-proxy.xiaoguan.us /
  ghproxy.8ka.moe / gh.akio.top / ghproxy.184444.xyz / gh-proxy.20m4.net /
  gh.wibac.com / ghproxy.netlify.app / gh.api.99988866.xyz / ghproxy.one /
  ghproxy.buzz / gh.94422.xyz / gh.arrow-s.top / ghp.ci / gh.bylink.cn 等。

镜像 URL 拼接方式：`<镜像前缀><原始 GitHub URL>`
（如 https://gh-proxy.com/https://api.github.com/...）。
"""

# 版本检查用镜像：优先顺序即列表顺序，配合 parallel_first 并发抢答，
# 单个镜像失效（超时/403/404）快速跳过，不影响整体。
# 2026-08-21 按用户要求「全面添加」：并发抢答机制下（任一源成功即返回、
# 其余立即取消、不等待慢源），失效镜像只占一个并发槽、不拖慢整体、
# 不污染结果（解析失败/网络错误均返回 None）——故可多列候选，
# 实测最快的 gh-proxy.com 仍靠前优先命中。
API_MIRRORS = [
    "https://gh-proxy.com/",
    "https://ghproxy.net/",
    "https://gh.ddlc.top/",
    "https://ghfast.top/",
    "https://ghps.cc/",
    "https://ghproxy.cc/",
    "https://gh.llkk.cc/",
    "https://ghproxy.cn/",
    "https://github.moeyy.xyz/",
    "https://gh-proxy.ygxz.in/",
    "https://gh-proxy.20m4.net/",
    "https://gh.con.sh/",
    "https://ghproxy.netlify.app/",
    "https://gh.94422.xyz/",
]

# 下载用镜像：与 API 列表一致（下载路径实测三个都可达；扩展候选同机制
# ——掐流/限速源由调用方吞吐熔断弃源，错误内容由 zip 校验拒绝）。
DOWNLOAD_MIRRORS = API_MIRRORS


def parallel_first(urls, fetch, timeout=6):
    """并发请求多个 URL，返回第一个成功（非 None）结果。

    与串行「逐个试到超时」相比，并发抢答在首个源不可达时无需等待其
    超时——任一源成功即返回，其余线程立即取消不阻塞。全部失败返回 None。

    参数：
        urls    要尝试的 URL 列表
        fetch   callable(url) -> 成功返回值或 None（内部自带超时/异常兜底）
        timeout 每个 fetch 内部请求超时由调用方控制，此参数保留供扩展
    """
    import concurrent.futures

    ex = concurrent.futures.ThreadPoolExecutor(max_workers=len(urls))
    try:
        futs = [ex.submit(fetch, u) for u in urls]
        for fut in concurrent.futures.as_completed(futs):
            try:
                v = fut.result()
            except Exception:  # noqa: BLE001 - 单源异常视为失败
                continue
            if v:
                return v
        return None
    finally:
        # wait=False + cancel_futures：拿到结果立即返回，不等慢源
        ex.shutdown(wait=False, cancel_futures=True)
