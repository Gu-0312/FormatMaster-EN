# -*- coding: utf-8 -*-
"""migrate_legacy_bin_files：历史 %APPDATA% 工具副本去重迁移。

背景：旧版把更新后的 ffmpeg/ffprobe/yt-dlp 下载到 %APPDATA%/FormatMaster/bin，
与安装目录随包 bin 双份占用；本测试覆盖迁移/去重/跳过/回退各分支。
"""
import os
import sys
import tempfile as _tf
import time

import pytest

from utils import config


@pytest.fixture
def frozen_env(tmp_path, monkeypatch):
    """模拟 PyInstaller onedir 打包环境。

    - sys.frozen=True；sys.executable=<模拟安装目录>/格式大师.exe；
      sys._MEIPASS=<模拟安装目录>/_internal（PyInstaller 6.x onedir 标准结构）
    - APPDATA=<临时根>；USER_PREFS 替换为内存 stub（不碰真实偏好文件）
    返回 (appdata_bin, install_bin) 两个目录。
    """
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    install_bin = tmp_path / "_internal" / "bin"
    install_bin.mkdir(parents=True)
    monkeypatch.setattr(sys, "executable",
                        str(tmp_path / "格式大师.exe"), raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(install_bin.parent),
                        raising=False)

    appdata_bin = tmp_path / "appdata" / config.APP_NAME / "bin"
    appdata_bin.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    class _Stub:
        def __init__(self):
            self.store = {}

        def get(self, panel, key, default=None):
            return self.store.get((panel, key), default)

        def set(self, panel, key, value):
            self.store[(panel, key)] = value

    monkeypatch.setattr(config, "USER_PREFS", _Stub())
    # 重置可写 bin 目录缓存（模块级全局，跨测试会污染）
    config._WRITABLE_BIN_DIR_CACHE = None
    yield appdata_bin, install_bin
    config._WRITABLE_BIN_DIR_CACHE = None


def _make_file(path, mtime_offset=0):
    path.write_text("x", encoding="utf-8")
    t = time.time() + mtime_offset
    os.utime(path, (t, t))
    return path


def test_dev_mode_skips(tmp_path, monkeypatch):
    """开发模式（未 frozen）不执行迁移。"""
    monkeypatch.delattr(sys, "frozen", raising=False)
    legacy = tmp_path / "appdata" / config.APP_NAME / "bin"
    legacy.mkdir(parents=True)
    _make_file(legacy / "ffmpeg.exe")
    config.migrate_legacy_bin_files()
    assert (legacy / "ffmpeg.exe").exists(), "开发模式不应动 %APPDATA%"


def test_migrate_when_missing_in_app_bin(frozen_env):
    """安装目录无该文件 → move 迁移过去，%APPDATA% 清空。"""
    appdata_bin, install_bin = frozen_env
    # 顺带验证 onedir 下可写 bin 目录即安装目录 _internal/bin
    assert os.path.normcase(config.get_writable_bin_dir()) == \
        os.path.normcase(str(install_bin))
    src = _make_file(appdata_bin / "yt-dlp.exe")
    config.migrate_legacy_bin_files()
    assert not src.exists(), "%APPDATA% 副本应被移除"
    assert (install_bin / "yt-dlp.exe").exists(), "应迁移到安装目录 bin"
    assert not appdata_bin.exists(), "%APPDATA% bin 目录应被清空删除"


def test_overwrite_when_appdata_newer(frozen_env):
    """两边都有且 %APPDATA% 副本更新 → 覆盖安装目录旧版并删副本。"""
    appdata_bin, install_bin = frozen_env
    _make_file(install_bin / "ffmpeg.exe", mtime_offset=-5000)
    _make_file(appdata_bin / "ffmpeg.exe", mtime_offset=0)
    config.migrate_legacy_bin_files()
    dst = install_bin / "ffmpeg.exe"
    assert dst.exists()
    # copy2 保留 src 的 mtime（≈now）：确认安装目录文件被新副本覆盖
    assert os.path.getmtime(dst) > time.time() - 60, \
        "安装目录文件应被 %APPDATA% 新版本覆盖"
    assert not (appdata_bin / "ffmpeg.exe").exists(), "副本应删除"


def test_keep_app_bin_when_newer(frozen_env):
    """两边都有且安装目录版本更新 → 只删 %APPDATA% 副本，不覆盖。"""
    appdata_bin, install_bin = frozen_env
    _make_file(appdata_bin / "ffmpeg.exe", mtime_offset=-5000)
    _make_file(install_bin / "ffmpeg.exe", mtime_offset=0)
    config.migrate_legacy_bin_files()
    assert not (appdata_bin / "ffmpeg.exe").exists(), "%APPDATA% 副本应删除"
    assert (install_bin / "ffmpeg.exe").exists()


def test_mark_skips_second_run(frozen_env):
    """迁移完成后写标记，第二次调用跳过（零开销）。"""
    appdata_bin, install_bin = frozen_env
    _make_file(appdata_bin / "ffmpeg.exe")
    config.migrate_legacy_bin_files()
    assert config.USER_PREFS.get("qt_app", config._LEGACY_BIN_MARK,
                                 False) is True, "应写入迁移完成标记"
    # 标记存在 → 第二次调用跳过，新副本原样保留
    appdata_bin.mkdir(parents=True, exist_ok=True)
    again = _make_file(appdata_bin / "ffprobe.exe")
    config.migrate_legacy_bin_files()
    assert again.exists(), "已迁移过，第二次应跳过"


def test_unavailable_app_bin_keeps_legacy(frozen_env, monkeypatch):
    """安装目录 bin 不可用（onedir 判定失败）→ 保留 %APPDATA% 副本不动。"""
    appdata_bin, install_bin = frozen_env
    src = _make_file(appdata_bin / "ffmpeg.exe")
    monkeypatch.setattr(sys, "_MEIPASS", str(install_bin.parent) + "_nope")
    config._WRITABLE_BIN_DIR_CACHE = None  # 环境变化须重置缓存
    config.migrate_legacy_bin_files()
    assert src.exists(), "无法定位安装目录时保留原副本"


def test_writable_bin_dir_cached(frozen_env, monkeypatch):
    """可写 bin 目录结果缓存：第二次调用不再做文件系统探测。"""
    install_bin = frozen_env[1]
    calls = []
    orig_makedirs = config.os.makedirs

    def counting(*a, **k):
        calls.append(a)
        return orig_makedirs(*a, **k)

    monkeypatch.setattr(config.os, "makedirs", counting)
    first = config.get_writable_bin_dir()
    second = config.get_writable_bin_dir()
    assert os.path.normcase(first) == os.path.normcase(str(install_bin))
    assert first == second
    assert len(calls) == 1, "第二次调用应命中缓存，不再 makedirs/探针"


def test_migrate_same_dir_skips(frozen_env, monkeypatch):
    """目标 bin == %APPDATA%（onefile/只读回退）→ 直接跳过不处理。"""
    appdata_bin, install_bin = frozen_env
    src = _make_file(appdata_bin / "ffmpeg.exe")
    # 让 get_writable_bin_dir 回退到 %APPDATA%：安装目录路径不可写/不存在
    monkeypatch.setattr(sys, "_MEIPASS", str(install_bin.parent) + "_nope")
    config._WRITABLE_BIN_DIR_CACHE = None
    config.migrate_legacy_bin_files()
    assert src.exists(), "目标==%APPDATA% 时应跳过，副本原样保留"
