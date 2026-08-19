"""core/tool_updater.py 纯逻辑测试：版本比较与版本解析（无网络/子进程依赖）。"""

from core.tool_updater import _parse_version, version_gt
from core import tool_updater as tu


class TestParseVersion:
    def test_plain(self):
        assert _parse_version("8.1.1") == [8, 1, 1]

    def test_with_suffix(self):
        # 提取数字序列，忽略字母/连字符
        assert _parse_version("9.0.1-full_build") == [9, 0, 1]

    def test_ytdlp_date(self):
        assert _parse_version("2026.07.04") == [2026, 7, 4]

    def test_single_number(self):
        assert _parse_version("7") == [7]


class TestVersionGt:
    def test_major_greater(self):
        assert version_gt("9.0.1", "8.1.1")
        assert not version_gt("8.1.1", "9.0.1")

    def test_minor_greater(self):
        assert version_gt("8.2.0", "8.1.1")
        assert not version_gt("8.1.1", "8.2.0")

    def test_patch_greater(self):
        assert version_gt("8.1.2", "8.1.1")

    def test_equal(self):
        assert not version_gt("8.1.1", "8.1.1")

    def test_date_versions(self):
        assert version_gt("2026.08.01", "2026.07.04")
        assert not version_gt("2026.07.04", "2026.07.04")

    def test_different_length(self):
        # 1.9 vs 1.10：按数字序列逐位比较，10 > 9
        assert version_gt("1.10", "1.9")
        assert not version_gt("1.9", "1.10")

    def test_non_numeric_input(self):
        # 非数字输入不抛异常，返回 False
        assert not version_gt(None, "1.0")
        assert not version_gt("abc", "1.0")

    def test_git_describe_current(self):
        # 当前是 BtbN master 构建（git 描述）：与 release 版本号语义不可比，
        # 且国内下载源本身即 master 构建，提示更新只会死循环 →
        # 视为「已是最新」（不触发更新提示）
        assert not version_gt("9.0.1", "N-126133-gead4378652-20260814")
        assert not version_gt("9.0.1", "N-1-gabcd1234-20260814")

    def test_is_git_describe(self):
        from core.tool_updater import _is_git_describe
        assert _is_git_describe("N-126133-gead4378652-20260814")
        assert _is_git_describe("N-1-gabcd1234-20260814")
        assert not _is_git_describe("9.0.1")
        assert not _is_git_describe("9.0.1-essentials_build")


class TestCheckButtonFeedback:
    """「检查更新」按钮点击后立即反馈：禁用→检查中→完成后恢复。"""

    def test_button_disabled_then_restored(self):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ["FORMATMASTER_OFFSCREEN"] = "1"
        from PySide6.QtCore import QObject, Signal
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        from gui_qt.components.tool_status_card import ToolStatusCard

        class _FakeChecker(QObject):
            finished = Signal(list)
            found = Signal(list)

            def __init__(self):
                super().__init__()
                self._running = False

            def is_running(self):
                return self._running

            def check_async(self, notify=False):
                self.finished.emit([])  # 模拟检查完成（无更新）

        class _Win(QObject):
            def __init__(self):
                super().__init__()
                self._tool_checker = _FakeChecker()

        win = _Win()
        card = ToolStatusCard()
        card.window = lambda: win
        card._check_update()
        app.processEvents()
        # 完成后按钮恢复可用且文案还原
        assert card.btn_check.isEnabled()
        assert card.btn_check.text() == "检查更新"
        card.deleteLater()
        app.processEvents()


# ── 国内镜像加速（2026-08-16 第 3 轮优化）──

class TestMirrorFallback:
    """版本检查「镜像优先 + 多源快速失败」：镜像可达不再碰国外源。"""

    def test_ffmpeg_mirror_first(self, monkeypatch):
        """FFmpeg：镜像并发抢答，gh-proxy 命中即返回（不碰 gyan.dev）。"""
        from core import tool_updater as tu
        calls = []

        def fake(url, timeout=None):
            calls.append(url)
            if "gh-proxy.com" in url:
                return '{"published_at": "2026-08-16T02:33:07Z"}'
            return None

        monkeypatch.setattr(tu, "_http_get_text", fake)
        v = tu.fetch_latest_ffmpeg_version()
        assert v == "2026.08.16"
        # 并发抢答：可能同时请求多个镜像，但绝不碰 gyan.dev 兜底
        assert any("gh-proxy.com" in u for u in calls)
        assert not any("gyan.dev" in u for u in calls)

    def test_ffmpeg_mirror_all_fail_gyan_fallback(self, monkeypatch):
        """FFmpeg：镜像全失败 → gyan.dev 兜底。"""
        from core import tool_updater as tu
        calls = []

        def fake(url, timeout=None):
            calls.append(url)
            if "gyan.dev" in url:
                return "9.0.1"
            return None

        monkeypatch.setattr(tu, "_http_get_text", fake)
        v = tu.fetch_latest_ffmpeg_version()
        assert v == "9.0.1"
        assert any("gyan.dev" in u for u in calls)

    def test_ytdlp_mirror_first(self, monkeypatch):
        """yt-dlp：镜像命中返回 tag（去 v 前缀）。"""
        from core import tool_updater as tu
        calls = []

        def fake(url, timeout=None):
            calls.append(url)
            if "ghproxy.net" in url:
                return '{"tag_name": "v2026.08.15"}'
            return None

        monkeypatch.setattr(tu, "_http_get_text", fake)
        # gh-proxy.com 第一个镜像失败 → ghproxy.net 命中
        v = tu.fetch_latest_ytdlp_version()
        assert v == "2026.08.15"
        assert calls[0].startswith("https://gh-proxy.com/")
        assert any("ghproxy.net" in u for u in calls)

    def test_btbn_published_at_date(self):
        """BtbN tag 恒为 latest → 用 published_at 日期作版本（可比较）。"""
        from core import tool_updater as tu
        v = tu._fetch_btbn_latest_mirror.__wrapped__ if hasattr(
            tu._fetch_btbn_latest_mirror, "__wrapped__") else None
        # 直接测内部解析逻辑（mock _http_get_text）
        import json
        original = tu._http_get_text
        try:
            tu._http_get_text = lambda url, timeout=None: json.dumps(
                {"tag_name": "latest", "published_at": "2026-08-16T02:33:07Z"})
            got = tu._fetch_btbn_latest_mirror("https://gh-proxy.com/")
            assert got == "2026.08.16", got
        finally:
            tu._http_get_text = original

    def test_git_describe_local_version_extract(self):
        """本地 BtbN master 版本（git describe）提取原始 token，美化后为日期段。"""
        from core import tool_updater as tu
        cur = tu._run_version_raw(
            "echo", ["ffmpeg version N-126133-gead4378652-20260814"],
            r"ffmpeg version (\S+)")
        assert cur == "N-126133-gead4378652-20260814", cur
        assert tu.display_version(cur) == "2026.08.14"
        # 比较闭环：master 新 build 提示更新；release 本地也提示（master 恒新）
        assert tu.version_gt("2026.08.16", "2026.08.14") is True
        assert tu.version_gt("2026.08.16", "9.0.1") is True
        assert tu.version_gt("2026.08.14", "2026.08.16") is False

    def test_download_ytdlp_mirror_first(self, monkeypatch, tmp_path):
        """yt-dlp 下载：镜像优先（原始直连兜底）。"""
        from core import tool_updater as tu
        seen = []

        class _FakeResp:
            headers = {"Content-Length": "0"}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, n):
                return b""

        def fake_urlopen(req, timeout=None):
            seen.append(req.full_url)
            return _FakeResp()

        monkeypatch.setattr(tu, "fetch_latest_ytdlp_version", lambda: "2026.08.15")
        monkeypatch.setattr(tu.urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setattr(tu, "get_writable_bin_dir",
                            lambda: str(tmp_path))
        ok, msg = tu.download_ytdlp()
        assert ok, msg
        assert seen and seen[0].startswith("https://gh-proxy.com/"), seen


class TestAppUpdaterParallel:
    """程序自身更新：直连 + 镜像并发抢答（原串行最坏 32s）。"""

    def test_first_ok_returns_fastest(self, monkeypatch):
        from core import app_updater as au
        import time

        def slow(url):
            time.sleep(2)
            return None

        def fast(url):
            return '{"tag_name": "v1.3.8"}'

        # 两个源并发：快的 0.1s 返回，慢的 2s 超时——总耗时应 < 1.5s
        def fake_get(url):
            return fast(url) if "gh-proxy.com" in url else slow(url)

        monkeypatch.setattr(au, "_http_get", fake_get)
        t0 = time.perf_counter()
        tag = au.fetch_latest_tag()
        el = time.perf_counter() - t0
        assert tag == "1.3.8", tag
        assert el < 1.5, f"并发抢答应 ~0.1s，实际 {el:.2f}s（串行会等慢源 2s）"

    def test_fetch_latest_tag_all_fail(self, monkeypatch):
        from core import app_updater as au
        monkeypatch.setattr(au, "_http_get", lambda url: None)
        try:
            au._tag_cache["ts"] = 0.0
            au._tag_cache["tag"] = None
            assert au.fetch_latest_tag() is None
        finally:
            au._tag_cache["ts"] = 0.0
            au._tag_cache["tag"] = None


class TestParallelMirrors:
    """镜像并发抢答：首个源慢/挂时其余源立即补位，不串行等待。"""

    def test_ffmpeg_fast_second_mirror_wins(self, monkeypatch):
        """gh-proxy.com 慢（2s）时 ghproxy.net 快速命中 → 总耗时接近快的。"""
        from core import tool_updater as tu
        import time

        def fake(url, timeout=None):
            if "gh-proxy.com" in url:
                time.sleep(2)          # 慢源：串行会卡 2s
                return '{"published_at": "2026-08-16T02:33:07Z"}'
            if "ghproxy.net" in url:
                time.sleep(0.1)        # 快源
                return '{"published_at": "2026-08-16T02:33:07Z"}'
            return None

        monkeypatch.setattr(tu, "_http_get_text", fake)
        t0 = time.perf_counter()
        v = tu.fetch_latest_ffmpeg_version()
        el = time.perf_counter() - t0
        assert v == "2026.08.16"
        # 并发抢答：即使第一个镜像最慢 2s，其他镜像 0.1s 命中 → 总耗时 < 1s
        assert el < 1.0, f"并发抢答应 ~0.1s，实际 {el:.2f}s（疑似串行等待慢源）"

    def test_shared_mirror_source(self):
        """三处镜像统一由 utils/mirrors.py 提供（单点维护）。"""
        from utils import mirrors
        from core import tool_updater as tu
        from core import app_updater as au
        from utils import ffmpeg_manager as fm
        assert tu.API_MIRRORS is mirrors.API_MIRRORS
        assert tu.DOWNLOAD_MIRRORS is mirrors.DOWNLOAD_MIRRORS
        assert au.GITHUB_MIRRORS is mirrors.DOWNLOAD_MIRRORS
        assert fm._GITHUB_PROXIES is mirrors.DOWNLOAD_MIRRORS
        # 列表非空且是同一份
        assert len(mirrors.API_MIRRORS) >= 3


class TestCheckCache:
    """更新检查结果缓存：重复点击秒回，TTL 过期才重新联网。"""

    def test_check_updates_second_call_cached(self, monkeypatch):
        """首次联网检测 → 二次命中缓存（0 网络请求、毫秒级返回）。"""
        from core import tool_updater as tu
        from utils import ffmpeg_manager as fm
        import time
        net = {"n": 0}

        def fake_target(r):
            net["n"] += 1
            time.sleep(0.1)
            return ("urls", "9.0.1", "9.0.1", "release")

        monkeypatch.setattr(tu, "current_ffmpeg_version", lambda: "8.1.1")
        monkeypatch.setattr(tu, "current_ffmpeg_version_raw",
                            lambda: "8.1.1-essentials_build")
        monkeypatch.setattr(fm, "best_ffmpeg_source", fake_target)
        monkeypatch.setattr(tu, "current_ytdlp_version", lambda: "2026.07.01")
        monkeypatch.setattr(tu, "fetch_latest_ytdlp_version", lambda: "2026.07.04")
        try:
            tu._check_cache["ts"] = 0.0
            tu._check_cache["result"] = None  # 清残留缓存，确保首次真查
            r1 = tu.check_updates()
            t0 = time.perf_counter()
            r2 = tu.check_updates()
            el = time.perf_counter() - t0
            assert len(r1) == 2 and len(r2) == 2
            assert net["n"] == 1, f"二次应命中缓存不联网，实际联网 {net['n']} 次"
            assert el < 0.05, f"二次应秒回，实际 {el * 1000:.0f}ms"
        finally:
            tu._check_cache["ts"] = 0.0
            tu._check_cache["result"] = None

    def test_check_updates_ttl_expired_requery(self, monkeypatch):
        """TTL 过期后再次检查重新联网。"""
        from core import tool_updater as tu
        from utils import ffmpeg_manager as fm
        net = {"n": 0}
        monkeypatch.setattr(tu, "current_ffmpeg_version", lambda: "8.1.1")
        monkeypatch.setattr(tu, "current_ffmpeg_version_raw",
                            lambda: "8.1.1-essentials_build")
        monkeypatch.setattr(fm, "best_ffmpeg_source",
                            lambda r: (net.__setitem__("n", net["n"] + 1)
                                       or ("urls", "9.0.1", "9.0.1", "release")))
        monkeypatch.setattr(tu, "current_ytdlp_version", lambda: "2026.07.01")
        monkeypatch.setattr(tu, "fetch_latest_ytdlp_version",
                            lambda: (net.__setitem__("n", net["n"] + 1) or "2026.07.04"))
        try:
            tu._check_cache["ts"] = 0.0  # 模拟 TTL 过期
            tu.check_updates()
            assert net["n"] == 2, f"TTL 过期应重新联网，实际 {net['n']}"
        finally:
            tu._check_cache["ts"] = 0.0
            tu._check_cache["result"] = None

    def test_fetch_latest_tag_second_call_cached(self, monkeypatch):
        """程序版本检查：二次命中缓存不联网。"""
        from core import app_updater as au
        net = {"n": 0}
        monkeypatch.setattr(
            au, "_first_ok",
            lambda urls, parse: (net.__setitem__("n", net["n"] + 1) or "1.3.8"))
        try:
            au._tag_cache["ts"] = 0.0
            au._tag_cache["tag"] = None  # 清残留缓存，确保首次真查
            tag1 = au.fetch_latest_tag()
            tag2 = au.fetch_latest_tag()
            assert tag1 == tag2 == "1.3.8"
            assert net["n"] == 1, f"二次应命中缓存，实际联网 {net['n']}"
        finally:
            au._tag_cache["ts"] = 0.0
            au._tag_cache["tag"] = None


class TestSchemeAwareComparison:
    """FFmpeg 更新比对：检查与下载共用 best_ffmpeg_source 基准，杜绝误报死循环。

    旧逻辑用 BtbN 构建日期（2026.08.16）与 gyan/npmmirror 的 release 版本号
    （9.0.1）直接比大小 → 恒为真 → 每次误报「有更新」，且下载 race 抢到的总是
    npmmirror 8.1.2 / BtbN master（永远 ≠ 9.0.1）→ 更新完重进仍提示更新。
    """

    def _patch(self, monkeypatch, cur, raw, target, yt_cur, yt_last):
        from core import tool_updater as tu
        from utils import ffmpeg_manager as fm
        monkeypatch.setattr(tu, "current_ffmpeg_version", lambda: cur)
        monkeypatch.setattr(tu, "current_ffmpeg_version_raw", lambda: raw)
        monkeypatch.setattr(fm, "best_ffmpeg_source", lambda r: target)
        # 默认无官方受限提示（否则 target==cur 时 _check_ffmpeg 会真的联网）
        monkeypatch.setattr(fm, "official_latest_ffmpeg", lambda: None)
        monkeypatch.setattr(tu, "current_ytdlp_version", lambda: yt_cur)
        monkeypatch.setattr(tu, "fetch_latest_ytdlp_version", lambda: yt_last)
        tu._check_cache["ts"] = 0.0
        tu._check_cache["result"] = None

    def test_release_vs_release_no_false_update(self, monkeypatch):
        """已装 gyan/npmmirror release 版时，best 源即同版本 → 不误报更新。"""
        self._patch(monkeypatch, "9.0.1", "9.0.1-essentials_build",
                    ("urls", "9.0.1", "9.0.1", "release"),
                    "2026.07.04", "2026.07.04")
        r = tu.check_updates()
        tools = {u["tool"]: u for u in r}
        assert "ffmpeg" not in tools, f"release 版不应误报更新: {tools}"

    def test_git_describe_vs_date_detects_real_update(self, monkeypatch):
        """已装 BtbN master（日期 2026.08.14），best 源为 2026.08.16 → 正确报更新。"""
        self._patch(monkeypatch, "2026.08.14", "N-126133-gead4378652-20260814",
                    ("urls", "2026.08.16", "2026.08.16", "git"),
                    "2026.07.04", "2026.07.04")
        r = tu.check_updates()
        tools = {u["tool"]: u for u in r}
        assert tools.get("ffmpeg", {}).get("latest") == "2026.08.16"

    def test_release_update_when_newer_exists(self, monkeypatch):
        """已装较旧 release 版，且 gyan 确有更新版本时，正确报更新。"""
        self._patch(monkeypatch, "8.1.2", "8.1.2",
                    ("urls", "9.0.1", "9.0.1", "release"),
                    "2026.07.04", "2026.07.04")
        r = tu.check_updates()
        tools = {u["tool"]: u for u in r}
        assert tools.get("ffmpeg", {}).get("latest") == "9.0.1"

    def test_vendor_prefixed_no_loop(self, monkeypatch):
        """关键回归：已装 npmmirror n8.1.2-20260723，best 源=同版本 npmmirror
        8.1.2（gyan 不可达）→ 不应误报更新（即用户遇到的死循环场景）。"""
        self._patch(monkeypatch, "8.1.2", "n8.1.2-20260723",
                    ("urls", "8.1.2", "8.1.2", "release"),
                    "2026.07.04", "2026.07.04")
        r = tu.check_updates()
        tools = {u["tool"]: u for u in r}
        assert "ffmpeg" not in tools, f"同版本不应误报更新: {tools}"

    def test_official_newer_but_unreachable_yields_hint(self, monkeypatch):
        """可达源=已装 8.1.2（无更新）但官方 9.0.1 更高 → 受限提示条目
        （不再假装「已最新」）。"""
        from core import tool_updater as tu
        from utils import ffmpeg_manager as fm
        monkeypatch.setattr(tu, "current_ffmpeg_version", lambda: "8.1.2")
        monkeypatch.setattr(tu, "current_ffmpeg_version_raw",
                            lambda: "n8.1.2-20260723")
        monkeypatch.setattr(fm, "best_ffmpeg_source",
                            lambda r: ("urls", "8.1.2", "8.1.2", "release"))
        monkeypatch.setattr(fm, "official_latest_ffmpeg",
                            lambda: ("9.0.1", "9.0.1"))
        monkeypatch.setattr(tu, "current_ytdlp_version", lambda: "2026.07.04")
        monkeypatch.setattr(tu, "fetch_latest_ytdlp_version",
                            lambda: "2026.07.04")
        tu._check_cache["ts"] = 0.0
        tu._check_cache["result"] = None
        r = tu.check_updates()
        ff = {u["tool"]: u for u in r}.get("ffmpeg")
        assert ff is not None and ff.get("hint") is True
        assert ff["official_latest"] == "9.0.1"
        assert ff["latest"] == "8.1.2"

    def test_official_equal_no_hint(self, monkeypatch):
        """官方最新==可达最新==已装 → 无任何 ffmpeg 条目（真正的最新）。"""
        from core import tool_updater as tu
        from utils import ffmpeg_manager as fm
        monkeypatch.setattr(tu, "current_ffmpeg_version", lambda: "9.0.1")
        monkeypatch.setattr(tu, "current_ffmpeg_version_raw",
                            lambda: "9.0.1-essentials_build")
        monkeypatch.setattr(fm, "best_ffmpeg_source",
                            lambda r: ("urls", "9.0.1", "9.0.1", "release"))
        monkeypatch.setattr(fm, "official_latest_ffmpeg",
                            lambda: ("9.0.1", "9.0.1"))
        monkeypatch.setattr(tu, "current_ytdlp_version", lambda: "2026.07.04")
        monkeypatch.setattr(tu, "fetch_latest_ytdlp_version",
                            lambda: "2026.07.04")
        tu._check_cache["ts"] = 0.0
        tu._check_cache["result"] = None
        r = tu.check_updates()
        assert "ffmpeg" not in {u["tool"] for u in r}

    def test_git_scheme_skips_official(self, monkeypatch):
        """已装 BtbN master（git 体系）时不做 release 官方比对（版本体系不可比）。"""
        from core import tool_updater as tu
        from utils import ffmpeg_manager as fm
        called = {"n": 0}
        monkeypatch.setattr(tu, "current_ffmpeg_version", lambda: "2026.08.16")
        monkeypatch.setattr(tu, "current_ffmpeg_version_raw",
                            lambda: "N-126133-gead4378652-20260816")
        monkeypatch.setattr(fm, "best_ffmpeg_source",
                            lambda r: ("urls", "2026.08.16", "2026.08.16", "git"))
        monkeypatch.setattr(
            fm, "official_latest_ffmpeg",
            lambda: (called.__setitem__("n", called["n"] + 1)
                     or ("9.0.1", "9.0.1")))
        monkeypatch.setattr(tu, "current_ytdlp_version", lambda: "2026.07.04")
        monkeypatch.setattr(tu, "fetch_latest_ytdlp_version",
                            lambda: "2026.07.04")
        tu._check_cache["ts"] = 0.0
        tu._check_cache["result"] = None
        r = tu.check_updates()
        assert "ffmpeg" not in {u["tool"] for u in r}
        assert called["n"] == 0, "git 体系不应调用 release 官方比对"
