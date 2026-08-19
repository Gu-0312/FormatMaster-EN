"""FFmpeg 并行抢答下载的回归测试（不触碰真实网络）。

验证点（对应「卡在 0% / 极慢」修复）：
- 某个源死掉/超时 → 不阻塞，最快可用的源胜出并完成下载；
- 全部源失败 → 返回 None 并留下结构化错误；
- 单源限速掐流（连续无新字节超过阈值）→ 被自动弃源。
"""
import io
import os
import json
import tarfile
import zipfile

import pytest

import utils.ffmpeg_manager as fm


def _make_zip_bytes():
    """构造一个含 ffmpeg.exe/ffprobe.exe 的合法 zip（用于模拟完整下载）。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("ffmpeg.exe", b"MZ fake ffmpeg binary")
        zf.writestr("ffprobe.exe", b"MZ fake ffprobe binary")
    return buf.getvalue()


def _make_tar_xz_bytes():
    """构造一个含 bin/ffmpeg.exe、bin/ffprobe.exe 的合法 tar.xz（npmmirror 源）。"""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:xz") as tf:
        for name in ("ffmpeg-8.1.2-win32-x64-gpl/bin/ffmpeg.exe",
                     "ffmpeg-8.1.2-win32-x64-gpl/bin/ffprobe.exe"):
            data = b"MZ fake ffmpeg binary"
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


ZIP_BYTES = _make_zip_bytes()
TXZ_BYTES = _make_tar_xz_bytes()
CLOCK = {"t": 0.0}


class FakeResp:
    """模拟 urllib 响应：read() 每次吐一个 chunk，并可推进可控时钟。"""

    def __init__(self, chunks, advance=0.0, raise_on_read=None):
        self._chunks = list(chunks)
        self._advance = advance
        self._raise = raise_on_read
        self.status = 200
        self.headers = {"Content-Length": str(sum(len(c) for c in self._chunks))}

    def read(self, n):
        if self._advance:
            CLOCK["t"] += self._advance
        if self._raise is not None:
            raise self._raise
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


@pytest.fixture
def tmp_zip(tmp_path):
    return str(tmp_path / "ffmpeg_dl.zip")


def test_race_picks_fast_source_when_one_stalls(tmp_zip, monkeypatch):
    """源0 读时抛超时（模拟限速/掐流死连接），源1 正常完成 → 源1 胜出。"""
    import urllib.error

    def fake_urlopen(req, timeout=None, context=None):
        # 生产代码传入的是 Request 对象（非裸 URL 字符串）
        url = getattr(req, "full_url", req)
        if url.startswith("http://slow/"):
            return FakeResp([], raise_on_read=urllib.error.URLError("timed out"))
        return FakeResp([ZIP_BYTES], advance=0.0)

    monkeypatch.setattr(fm.urllib.request, "urlopen", fake_urlopen)
    mgr = fm.FFmpegManager()
    mgr.last_errors = []

    out = mgr._race_download(
        ["http://slow/ffmpeg.zip", "http://fast/ffmpeg.zip"], tmp_zip, None)

    assert out is not None, "应有一个源下载成功"
    assert zipfile.is_zipfile(out), "胜出文件应是合法 zip"
    # 慢源的错误应被记录，但整体仍成功
    assert any(e["phase"] == "download" and "slow" in e["url"] for e in mgr.last_errors)
    # 临时文件应被清理
    leftovers = [p for p in os.listdir(os.path.dirname(tmp_zip))
                 if p.endswith(".src0") or p.endswith(".src1")]
    assert not leftovers


def test_race_all_fail_returns_none(tmp_zip, monkeypatch):
    """全部源失败 → 返回 None 并留下结构化错误。"""
    import urllib.error

    def fake_urlopen(req, timeout=None, context=None):
        return FakeResp([], raise_on_read=urllib.error.URLError("conn reset"))

    monkeypatch.setattr(fm.urllib.request, "urlopen", fake_urlopen)
    mgr = fm.FFmpegManager()
    mgr.last_errors = []

    out = mgr._race_download(
        ["http://a/ffmpeg.zip", "http://b/ffmpeg.zip"], tmp_zip, None)

    assert out is None
    assert len(mgr.last_errors) >= 2


def test_race_abandons_throttled_source(tmp_zip, monkeypatch):
    """单源持续掐流（每次 read 推进 16s 虚拟时钟）→ 触发限速熔断返回 None。"""
    import urllib.error

    def fake_urlopen(req, timeout=None, context=None):
        # 持续掐流：每次 read 推进 16s 虚拟时钟且仍返回字节（不 EOF），
        # 第 3 次迭代 now-last 超过 STALL_SECS → 触发限速熔断
        return FakeResp([b"x" * 10] * 100000, advance=16.0)

    monkeypatch.setattr(fm.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(fm.time, "monotonic", lambda: CLOCK["t"])
    mgr = fm.FFmpegManager()
    mgr.last_errors = []

    out = mgr._race_download(["http://drip/ffmpeg.zip"], tmp_zip, None)

    assert out is None
    assert any("限速" in e["msg"] or "无响应" in e["msg"]
               for e in mgr.last_errors), "应检测到限速并弃源"


def test_race_accepts_tar_xz_source(tmp_zip, monkeypatch):
    """npmmirror 的 tar.xz 源应被识别为合法压缩包并胜出。"""
    def fake_urlopen(req, timeout=None, context=None):
        return FakeResp([TXZ_BYTES], advance=0.0)

    monkeypatch.setattr(fm.urllib.request, "urlopen", fake_urlopen)
    mgr = fm.FFmpegManager()
    mgr.last_errors = []
    out = mgr._race_download(["http://npm/ff.txz"], tmp_zip, None)
    assert out is not None, "tar.xz 源应下载成功"
    # 解压到临时目录验证能提取出 exe（zip/tar.xz 自适应）
    dest = tmp_zip + ".bin"
    os.makedirs(dest, exist_ok=True)
    fm._extract_ffmpeg(out, dest)
    assert os.path.isfile(os.path.join(dest, "ffmpeg.exe"))
    assert os.path.isfile(os.path.join(dest, "ffprobe.exe"))


def test_extract_tar_xz(tmp_path):
    """_extract_ffmpeg 能处理 tar.xz（按 basename 提取 exe）。"""
    src = tmp_path / "ff.txz"
    src.write_bytes(TXZ_BYTES)
    dest = tmp_path / "bin"
    dest.mkdir()
    fm._extract_ffmpeg(str(src), str(dest))
    assert (dest / "ffmpeg.exe").is_file()
    assert (dest / "ffprobe.exe").is_file()


def test_resolve_npmmirror_url(monkeypatch):
    """解析 npmmirror 目录列表 → 取最高版本 → 拼出 win32-x64-gpl tar.xz 直链。"""
    listing = json.dumps([
        {"name": "v8.1/", "type": "dir"},
        {"name": "v8.1.2/", "type": "dir"},
        {"name": "v7.1.5/", "type": "dir"},
        {"name": "v8.0.3/", "type": "dir"},
    ])

    class _R:
        status = 200

        def __init__(self, body):
            self._b = body.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            return self._b

    def fake_urlopen(req, timeout=None, context=None):
        return _R(listing)

    monkeypatch.setattr(fm.urllib.request, "urlopen", fake_urlopen)
    url = fm._resolve_npmmirror_ffmpeg_url()
    assert url == ("https://registry.npmmirror.com/-/binary/ffmpeg-builds/"
                   "v8.1.2/ffmpeg-8.1.2-win32-x64-gpl.tar.xz")


def test_resolve_npmmirror_failure_returns_none(monkeypatch):
    """npmmirror 列表解析失败应静默返回 None（交给其他源），不抛异常。"""
    import urllib.error

    def fake_urlopen(req, timeout=None, context=None):
        raise urllib.error.URLError("conn reset")

    monkeypatch.setattr(fm.urllib.request, "urlopen", fake_urlopen)
    assert fm._resolve_npmmirror_ffmpeg_url() is None


# ── best_ffmpeg_source 二进制可达性探测（修 gyan 文本可达但 zip 不可达的静默死循环） ──

def _patch_source(monkeypatch, gyan_text, gyan_reachable, npm_url, npm_reachable):
    """best_ffmpeg_source 的可控 mock：各源版本+HEAD 可达性独立模拟。"""
    import core.tool_updater as tu
    monkeypatch.setattr(tu, "_http_get_text", lambda *a, **kw: gyan_text)
    def head(url, timeout=3):
        if "gyan.dev" in url: return gyan_reachable
        return npm_reachable
    monkeypatch.setattr(fm, "_head_ok", head)
    monkeypatch.setattr(fm, "_resolve_npmmirror_ffmpeg_url",
                        lambda: npm_url)


def test_best_source_gyan_zip_blocked_excludes_gyan(monkeypatch):
    """gyan 版本文本 9.0.1 但 zip HEAD 失败（国内被掐）→ 排除 gyan，广告 npmmirror 8.1.2。"""
    _patch_source(monkeypatch,
        gyan_text="9.0.1", gyan_reachable=False,
        npm_url="https://registry.npmmirror.com/-/binary/ffmpeg-builds/ffmpeg-8.1.2-win32-x64-gpl.tar.xz",
        npm_reachable=True)
    target = fm.best_ffmpeg_source("ffmpeg version 8.1.2-essentials_build")
    assert target is not None
    urls, ver, disp, scheme = target
    assert ver == "8.1.2"
    assert "gyan.dev" not in str(urls)


def test_best_source_both_reachable_gyan_wins(monkeypatch):
    _patch_source(monkeypatch,
        gyan_text="9.0.1", gyan_reachable=True,
        npm_url="https://registry.npmmirror.com/-/binary/ffmpeg-builds/ffmpeg-8.1.2-win32-x64-gpl.tar.xz",
        npm_reachable=True)
    target = fm.best_ffmpeg_source("ffmpeg version 8.1.2-essentials_build")
    assert target[1] == "9.0.1"
    assert "gyan.dev" in str(target[0])


def test_best_source_all_blocked_returns_none(monkeypatch):
    """所有二进制都不可达 → 不广告任何版本（让 check 显示「最新」）。"""
    _patch_source(monkeypatch,
        gyan_text="9.0.1", gyan_reachable=False,
        npm_url="https://registry.npmmirror.com/-/binary/ffmpeg-builds/ffmpeg-8.1.2-win32-x64-gpl.tar.xz",
        npm_reachable=False)
    target = fm.best_ffmpeg_source("ffmpeg version 8.1.2-essentials_build")
    assert target is None


def test_best_source_gyan_text_unreachable_excludes(monkeypatch):
    """gyan 版本文本也不可达 → 不进 gyan 候选。"""
    _patch_source(monkeypatch,
        gyan_text=None, gyan_reachable=True,
        npm_url="https://registry.npmmirror.com/-/binary/ffmpeg-builds/ffmpeg-8.1.2-win32-x64-gpl.tar.xz",
        npm_reachable=True)
    target = fm.best_ffmpeg_source("ffmpeg version 8.1.2-essentials_build")
    assert target[1] == "8.1.2"


# ── official_latest_ffmpeg：官方最新（忽略二进制可达性，只看版本信息端点） ──

def test_official_latest_returns_upstream(monkeypatch):
    import core.tool_updater as tu
    monkeypatch.setattr(tu, "_http_get_text", lambda *a, **kw: "9.0.1")
    monkeypatch.setattr(
        fm, "_resolve_npmmirror_ffmpeg_url",
        lambda: "https://registry.npmmirror.com/-/binary/ffmpeg-builds/ffmpeg-8.1.2-win32-x64-gpl.tar.xz")
    assert fm.official_latest_ffmpeg() == ("9.0.1", "9.0.1")


def test_official_latest_gyan_down_uses_npm(monkeypatch):
    import core.tool_updater as tu
    monkeypatch.setattr(tu, "_http_get_text", lambda *a, **kw: None)
    monkeypatch.setattr(
        fm, "_resolve_npmmirror_ffmpeg_url",
        lambda: "https://registry.npmmirror.com/-/binary/ffmpeg-builds/ffmpeg-8.1.2-win32-x64-gpl.tar.xz")
    assert fm.official_latest_ffmpeg()[0] == "8.1.2"


def test_official_latest_all_down_none(monkeypatch):
    import core.tool_updater as tu
    monkeypatch.setattr(tu, "_http_get_text", lambda *a, **kw: None)
    monkeypatch.setattr(fm, "_resolve_npmmirror_ffmpeg_url", lambda: None)
    assert fm.official_latest_ffmpeg() is None
