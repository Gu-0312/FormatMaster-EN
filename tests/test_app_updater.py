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
        # 排除 Source 后没剩余 zip → None（实际 release 全部是 source 归档）
        assert find_portable_asset(["Source code (zip)"]) is None
        # 没 zip → None
        assert find_portable_asset(["说明.txt"]) is None
        assert find_portable_asset([]) is None

    def test_source_excluded(self):
        # source code 自动归档被排除，剩余 zip 兜底选首个（用户主安装包）
        assert find_portable_asset(
            ["FormatMasterv1.4.1.zip", "Source code (zip)"]) \
            == "FormatMasterv1.4.1.zip"


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

    def test_nested_zip_dirname_mismatch(self, tmp_path):
        # 用户安装目录名与 zip 内层目录名不一致（如改名安装目录），
        # 仍应正确提升内层目录并解出主 exe（Bug A 回归，2026-08-21）
        app_dir = tmp_path / "MyFormat"      # 用户改名的安装目录
        app_dir.mkdir()
        (app_dir / "格式大师.exe").write_bytes(b"old")
        zip_path = tmp_path / "upd.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("格式大师/格式大师.exe", "fake")
            zf.writestr("格式大师/_internal/data.txt", "x")
        bat = prepare_update(str(zip_path), str(app_dir), "格式大师.exe")
        new_dir = tmp_path / "_fm_new"
        assert (new_dir / "格式大师.exe").is_file(), "目录名不同也应提升出主 exe"
        assert (new_dir / "_internal" / "data.txt").is_file()
        assert os.path.isfile(bat)

    def test_exe_name_mismatch_fallback(self, tmp_path):
        # 打包 --name 与当前程序 exe 名不一致（最常见：1.4.0 用旧名打、
        # 1.4.1 改了 name），zip 内 exe 找不到精确名 → 兜底选任意 .exe
        # 并重命名为 app_exe_name（Bug C 回归，2026-08-21）
        app_dir = tmp_path / "格式大师"
        app_dir.mkdir()
        (app_dir / "FormatMaster.exe").write_bytes(b"old")  # 当前 exe 是这个名
        zip_path = tmp_path / "upd.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("格式大师.exe", "fake-new")  # zip 内是中文名
            zf.writestr("_internal/data.txt", "x")
        bat = prepare_update(str(zip_path), str(app_dir), "FormatMaster.exe")
        new_dir = tmp_path / "_fm_new"
        # 自动重命名为期望名（保证 bat 的 EXE 变量命中）
        assert (new_dir / "FormatMaster.exe").is_file(), \
            "兜底匹配应将 zip 内 exe 重命名为 app_exe_name"
        assert (new_dir / "_internal" / "data.txt").is_file()
        # bat 应使用期望名（不是 zip 内的中文名）
        with open(bat, "rb") as f:
            content = f.read().decode("gbk", errors="ignore")
        assert "EXE=FormatMaster.exe" in content

    def test_no_exe_at_all(self, tmp_path):
        # zip 内完全没有 .exe（异常包）：应暴露目录树到日志 + 清晰报错
        app_dir = tmp_path / "格式大师"
        app_dir.mkdir()
        (app_dir / "格式大师.exe").write_bytes(b"old")
        zip_path = tmp_path / "upd.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("README.txt", "no exe here")
        with pytest.raises(RuntimeError) as ei:
            prepare_update(str(zip_path), str(app_dir), "格式大师.exe")
        assert "未找到主程序" in str(ei.value)
        assert "格式大师.exe" in str(ei.value)  # 报错含期望名
        assert not (tmp_path / "_fm_new").exists()

    def test_invalid_zip(self, tmp_path):
        # 同 test_no_exe_at_all（无 .exe 异常包），保留作为兼容断言入口
        self.test_no_exe_at_all(tmp_path)
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

    def test_stall_source_circuit_break(self, monkeypatch):
        # 掐流源（连接存活但吞吐低于阈值）应在窗口期后主动弃源，
        # 而不是被 urlopen timeout 卡死（Bug B 回归，2026-08-21）。
        # 注入小窗口/小阈值（0.2s/512B）让测试秒级完成，逻辑与产品一致。
        monkeypatch.setattr(app_updater, "STALL_WINDOW_SEC", 0.2)
        monkeypatch.setattr(app_updater, "STALL_MIN_BYTES", 512)

        class StallResp:
            headers = {"Content-Length": "10485760"}  # 10MB

            def read(self, n):
                import time as _t
                _t.sleep(0.01)
                return b"x" * 16  # 每 10ms 16B → 0.2s 窗口 320B < 512B 阈值

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        monkeypatch.setattr(
            app_updater.urllib.request, "urlopen",
            lambda req, timeout=30, context=None: StallResp())
        # 不断流但低速 → 应在窗口内熔断报错（永不"成功"）
        with pytest.raises(RuntimeError) as ei:
            download_update(["https://m1/slow.zip"])
        assert "吞吐过低" in str(ei.value)

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

    def test_removes_new_residue(self, tmp_path):
        """启动时同时清理未完成更新的 _fm_new 解压残留（占磁盘大）。"""
        app_dir = tmp_path / "格式大师"
        app_dir.mkdir()
        new_dir = tmp_path / "_fm_new"
        new_dir.mkdir()
        (new_dir / "格式大师.exe").write_bytes(b"x")
        (new_dir / "_internal").mkdir()
        cleanup_backup(str(app_dir))
        assert not new_dir.exists(), "应清理未完成更新的 _fm_new 残留"

    def test_no_backup_noop(self, tmp_path):
        app_dir = tmp_path / "格式大师"
        app_dir.mkdir()
        cleanup_backup(str(app_dir))  # 不抛异常
        assert not (tmp_path / "_fm_old").exists()
        assert not (tmp_path / "_fm_new").exists()
