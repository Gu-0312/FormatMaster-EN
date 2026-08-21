"""pytest 公共配置"""
import sys
import os

import pytest

# 项目根加入 sys.path，测试中直接 from utils.xxx import ...
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def _reset_writable_bin_cache():
    """每个测试前后重置 utils.config._WRITABLE_BIN_DIR_CACHE。

    该缓存是模块级全局（运行期进程内只探测一次）。测试用 monkeypatch
    模拟打包环境（frozen/_MEIPASS/APPDATA）时会改变目录解析结果，若
    上一测试已填充缓存，后续测试（如 test_packaging_paths 的打包环境
    断言）会命中过期路径导致失败。autouse 前后都清一次最稳妥。
    """
    from utils import config
    config._WRITABLE_BIN_DIR_CACHE = None
    yield
    config._WRITABLE_BIN_DIR_CACHE = None


@pytest.fixture(scope="session", autouse=True)
def _isolate_user_prefs():
    """测试隔离：备份/恢复 user_prefs.json，防止测试污染开发数据。

    背景（2026-08-19 QA）：此前多个测试直接经 USER_PREFS.set() 写入
    data/user_prefs.json（如 out_dir_path='测试'），导致程序英文模式下
    面板输入框恢复出中文残留。此 fixture 在会话开始备份、结束恢复，
    测试期间写盘的内容一律丢弃。
    """
    import json
    import shutil
    from utils.config import USER_PREFS, get_user_prefs_path

    path = get_user_prefs_path()
    bak = path + ".pytest_bak"
    # 清理上次崩溃会话遗留的孤儿备份（segfault 中断时 teardown 不执行，
    # 旧 .pytest_bak 残留且内容过期；本次会话会重新备份）
    if os.path.exists(bak):
        try:
            os.remove(bak)
        except OSError:
            pass
    had = os.path.exists(path)
    if had:
        shutil.copy2(path, bak)
    else:
        USER_PREFS.prefs = {}

    yield

    # 结束：清掉后台写盘信号，避免恢复后又被写回测试值
    try:
        if getattr(USER_PREFS, "_dirty", None) is not None:
            USER_PREFS._dirty.clear()
    except Exception:  # noqa: BLE001 - 清理失败不影响
        pass
    if had and os.path.exists(bak):
        with open(bak, encoding="utf-8") as f:
            USER_PREFS.prefs = json.load(f)
        if os.path.exists(path):
            os.remove(path)
        shutil.move(bak, path)
    else:
        USER_PREFS.prefs = {}
        if os.path.exists(path):
            os.remove(path)
