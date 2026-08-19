"""core/app_updater.py 纯逻辑测试：资产匹配 / URL 构建 / 更新器脚本（无网络）。"""

import os
import zipfile

import pytest

from core import app_updater
from core.app_updater import (
    UpdateCancelled, asset_download_url, build_download_urls,
    cleanup_backup, download_update, find_portable_asset, prepare_update,
)


class TestFindPortableAsset:
    def test_portable_keyword(self):
        names = ["格式大师_v1.3.8_免安装.zip", "说明.txt", "安装包.exe"]
        assert find_portable_asset(names) == "格式大师_v1.3.8_免安装.zip"

    def test_portable_english(self):
        names = ["FormatMaster_v1.3.8_Portable.zip"]
        assert find_portable_asset(names) == "FormatMaster_v1.3.8_Portable.zip"

    def test_version_preferred(self):
        # 多个免安装包时优先当前版本号
        names = ["格式大师_v1.3.7_免安装.zip", "格式大师_v1.3.8_免安装.zip"]
        assert find_portable_asset(names) == "格式大师_v1.3.7_免安装.zip"

    def test_single_zip_fallback(self):
        # 只有单个 zip 时兜底使用（宽松）
        assert find_portable_asset(["仅有的包.zip"]) == "仅有的包.zip"

    def test_no_match(self):
        # 多个 zip 但无免安装关键词 → None（避免误下安装包）
        assert find_portable_asset(["a.zip", "b.zip"]) is None
        assert find_portable_asset(["说明.txt"]) is None
        assert find_portable_asset([]) is None


class TestUrls:
    def test_asset_download_url(self):
        url = asset_download_url("格式大师_v1.3.8_免安装.zip", "1.3.8")
        assert "download/v1.3.8/" in url
        assert "格式大师_v1.3.8_免安装.zip" in url

    def test_build_download_urls(self):
        raw = asset_download_url("x.zip", "1.3.8")
        urls = build_download_urls(raw)
        # 镜像在前（国内可达优先），原始兜底最后
        assert urls[0].startswith(app_updater.GITHUB_MIRRORS[0])
        assert urls[-1] == raw
        assert len(urls) == len(app_updater.GITHUB_MIRRORS) + 1


class TestPrepareUpdate:
    def _make_zip(self, path, exe_name):
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr(exe_name, "fake-exe")
            zf.writestr("_internal/data.txt", "x")

    def test_flat_zip(self, tmp_path):
        # zip 根即程序目录（exe 在根部）
        app_dir = tmp_path / "格式大师"
        app_dir.mkdir()
        (app_dir / "格式大师.exe").write_bytes(b"old")
        zip_path = tmp_path / "upd.zip"
        self._make_zip(str(zip_path), "格式大师.exe")

        bat = prepare_update(str(zip_path), str(app_dir), "格式大师.exe")
        assert os.path.isfile(bat)
        # 新版本已解压到 _fm_new
        new_dir = tmp_path / "_fm_new"
        assert (new_dir / "格式大师.exe").is_file()
        assert (new_dir / "_internal" / "data.txt").is_file()
        # bat 内容（GBK 解码）包含替换逻辑
        with open(bat, "rb") as f:
            content = f.read().decode("gbk", errors="ignore")
        assert "rmdir" in content and "move" in content
        assert "格式大师.exe" in content

    def test_bat_rollback_safe(self, tmp_path):
        # 回滚式更新脚本：备份 _fm_old + :restore 恢复分支
        app_dir = tmp_path / "格式大师"
        app_dir.mkdir()
        (app_dir / "格式大师.exe").write_bytes(b"old")
        zip_path = tmp_path / "upd.zip"
        self._make_zip(str(zip_path), "格式大师.exe")
        bat = prepare_update(str(zip_path), str(app_dir), "格式大师.exe")
        with open(bat, "rb") as f:
            content = f.read().decode("gbk", errors="ignore")
        assert "_fm_old" in content, "应备份旧目录到 _fm_old"
        assert "ren \"%PD%%OLD%\" \"%BAK%\"" in content, "旧目录应改名而非直接删除"
        assert ":restore" in content, "应有回滚分支"
        assert 'ren "%PD%%BAK%" "%OLD%"' in content, "回滚应恢复旧版"
        assert "timeout /t 8" in content, "应有新版存活确认窗口"

    def test_nested_zip(self, tmp_path):
        # zip 内含一层「格式大师/」目录
        app_dir = tmp_path / "格式大师"
        app_dir.mkdir()
        (app_dir / "格式大师.exe").write_bytes(b"old")
        zip_path = tmp_path / "upd.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("格式大师/格式大师.exe", "fake")
        bat = prepare_update(str(zip_path), str(app_dir), "格式大师.exe")
        assert (tmp_path / "_fm_new" / "格式大师.exe").is_file()
        assert os.path.isfile(bat)

    def test_invalid_zip(self, tmp_path):
        # 解压后没有主 exe → 报错并清理
        app_dir = tmp_path / "格式大师"
        app_dir.mkdir()
        (app_dir / "格式大师.exe").write_bytes(b"old")
        zip_path = tmp_path / "upd.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("README.txt", "no exe here")
        with pytest.raises(RuntimeError):
            prepare_update(str(zip_path), str(app_dir), "格式大师.exe")
        assert not (tmp_path / "_fm_new").exists()


class TestDownloadCancellation:
    def test_should_stop_cancels(self, monkeypatch):
        # 下载中 should_stop 返回 True → 抛 UpdateCancelled，且不再试下一个源
        class FakeResp:
            headers = {"Content-Length": "100000"}

            def read(self, n):
                return b"x" * n  # 永远有数据（配合 should_stop 立即中断）

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        called = []

        def fake_urlopen(req, timeout=None, context=None):
            called.append(req.full_url)
            return FakeResp()

        monkeypatch.setattr(app_updater.urllib.request, "urlopen", fake_urlopen)
        urls = ["https://m1/x.zip", "https://m2/x.zip", "https://raw/x.zip"]
        with pytest.raises(UpdateCancelled):
            download_update(urls, should_stop=lambda: True)
        assert len(called) == 1, "取消后不应继续尝试下一个源"

    def test_stop_false_downloads_ok(self, monkeypatch, tmp_path):
        # should_stop 恒 False：正常下载并校验 zip
        import io
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("a.txt", "x")
        zip_bytes = buf.getvalue()

        class FakeResp:
            headers = {"Content-Length": str(len(zip_bytes))}

            def __init__(self):
                self._sent = False

            def read(self, n):
                if not self._sent:
                    self._sent = True
                    return zip_bytes
                return b""

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_urlopen(req, timeout=None, context=None):
            return FakeResp()

        monkeypatch.setattr(app_updater.urllib.request, "urlopen", fake_urlopen)
        p = download_update(["https://m1/x.zip"], should_stop=lambda: False)
        try:
            assert os.path.isfile(p)
            with zipfile.ZipFile(p) as zf:
                assert zf.read("a.txt") == b"x"
        finally:
            if os.path.isfile(p):
                os.remove(p)


class TestCleanupBackup:
    def test_removes_backup(self, tmp_path):
        app_dir = tmp_path / "格式大师"
        app_dir.mkdir()
        bak = tmp_path / "_fm_old"
        bak.mkdir()
        (bak / "old.exe").write_bytes(b"x")
        cleanup_backup(str(app_dir))
        assert not bak.exists(), "启动后应清理旧版备份残留"

    def test_no_backup_noop(self, tmp_path):
        app_dir = tmp_path / "格式大师"
        app_dir.mkdir()
        cleanup_backup(str(app_dir))  # 不抛异常
        assert not (tmp_path / "_fm_old").exists()
