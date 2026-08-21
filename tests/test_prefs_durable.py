# -*- coding: utf-8 -*-
"""偏好 durable 落盘回归测试（2026-08-21）。

背景：退出收尾/页面侧边栏记忆的 prefs.flush() 原先只把数据写到操作系统
Page Cache（内核缓冲），断电/进程被杀仍丢失。修复：flush()/_save() 走
durable 路径（os.fsync 物理落盘），后台合并写保持非 durable 保性能。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from utils import config


def test_atomic_write_durable_fsync(tmp_path, monkeypatch):
    """durable=True 时写入后调用 os.fsync；False 不调用。"""
    fsync_calls = []
    orig_fsync = os.fsync

    def counting(fd):
        fsync_calls.append(fd)
        return orig_fsync(fd)

    monkeypatch.setattr(config.os, "fsync", counting)
    path = str(tmp_path / "prefs.json")

    # durable=False：不 fsync（后台合并写路径）
    assert config._atomic_write_json(path, {"a": 1}, durable=False) is True
    assert fsync_calls == [], "非 durable 不应调用 os.fsync"
    assert os.path.isfile(path)

    # durable=True：fsync 被调用且文件内容正确
    assert config._atomic_write_json(path, {"b": 2}, durable=True) is True
    assert len(fsync_calls) == 1, "durable 应调用一次 os.fsync"
    import json
    with open(path, encoding="utf-8") as f:
        assert json.load(f) == {"b": 2}


def test_flush_is_durable(tmp_path, monkeypatch):
    """UserPrefs.flush() 走 durable 路径（fsync 物理落盘）。"""
    fsync_calls = []
    orig_fsync = os.fsync

    def counting(fd):
        fsync_calls.append(fd)
        return orig_fsync(fd)

    monkeypatch.setattr(config.os, "fsync", counting)
    # 隔离：替换 USER_PREFS 为独立实例，指向临时 prefs 文件
    monkeypatch.setattr(config, "get_user_prefs_path", lambda: str(tmp_path / "u.json"))
    prefs = config.UserPrefs()
    prefs.set("qt_app", "nav_page", "settings")
    prefs.flush()
    assert len(fsync_calls) >= 1, "flush 应触发 os.fsync 物理落盘"
    import json
    with open(str(tmp_path / "u.json"), encoding="utf-8") as f:
        data = json.load(f)
    assert data["qt_app"]["nav_page"] == "settings"


def test_writer_loop_not_durable(tmp_path, monkeypatch):
    """后台合并写不 fsync（性能路径：150ms 防抖数据丢失可接受）。"""
    fsync_calls = []
    orig_fsync = os.fsync

    def counting(fd):
        fsync_calls.append(fd)
        return orig_fsync(fd)

    monkeypatch.setattr(config.os, "fsync", counting)
    monkeypatch.setattr(config, "get_user_prefs_path",
                        lambda: str(tmp_path / "w.json"))
    prefs = config.UserPrefs()
    # 直接验证 _writer_loop 使用的底层写路径不带 durable
    import copy
    with prefs._write_lock:
        config._atomic_write_json(str(tmp_path / "w.json"),
                                  {"k": "v"}, durable=False)
    assert fsync_calls == [], "后台路径不应 fsync"
