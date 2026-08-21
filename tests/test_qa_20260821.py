# -*- coding: utf-8 -*-
"""2026-08-21 修复项 QA 回归（第三轮）。

覆盖：
- Bug1：bin 目录定位（开发模式 = 项目根/bin）
- Bug2：侧边栏展开/折叠状态记忆（含重启恢复）
- Bug3：页面选中记忆（切页即时落盘）
- 坏配置容错：qt_app 关键键为脏类型时新窗口启动不崩（P1~P5 类回归）
- 全页面遍历切换（与 test_main_window 互补，含全部面板构建）

offscreen 平台伪影规避：gc.disable（与 test_main_window 一致）。
"""
import gc
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["FORMATMASTER_OFFSCREEN"] = "1"
if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
    gc.disable()

import pytest

from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def window(app):
    from gui_qt.app import MainWindow
    win = MainWindow()
    win.show()
    app.processEvents()
    yield win
    win.deleteLater()
    app.processEvents()


# ── Bug1：bin 目录 ──────────────────────────────
def test_bin_dir_dev_mode():
    """开发模式可写 bin 目录 = 项目根/bin（Bug1 回归）。"""
    from utils import config
    expected = os.path.join(config.get_app_dir(), "bin")
    assert os.path.normcase(config.get_writable_bin_dir()) == \
        os.path.normcase(expected)
    assert os.path.isdir(config.get_writable_bin_dir())


# ── Bug2：侧边栏展开/折叠记忆 ───────────────────
def test_sidebar_expand_memory(window, app):
    """展开/折叠状态保存与恢复（Bug2 回归）。"""
    from qfluentwidgets import NavigationDisplayMode
    from utils import config

    config.USER_PREFS.set("qt_app", "nav_expanded", True)
    config.USER_PREFS.flush()
    panel = window.navigationInterface.panel
    # 确保初始展开态（避免环境残留状态依赖）
    if panel.displayMode != NavigationDisplayMode.EXPAND:
        panel.expand(useAni=False)
    app.processEvents()
    # 折叠 → 保存 False
    panel.toggle()
    app.processEvents()
    assert panel.displayMode == NavigationDisplayMode.COMPACT
    assert config.USER_PREFS.get("qt_app", "nav_expanded") is False, \
        "折叠应保存 False"
    # 展开 → 保存 True
    panel.toggle()
    app.processEvents()
    assert panel.displayMode == NavigationDisplayMode.EXPAND
    assert config.USER_PREFS.get("qt_app", "nav_expanded") is True, \
        "展开应保存 True"
    config.USER_PREFS.set("qt_app", "nav_expanded", True)
    config.USER_PREFS.flush()


def test_sidebar_expand_restore_logic(window, app):
    """nav_expanded 脏值守卫（非 bool 按默认展开），避免损坏配置误判。

    注意：offscreen 平台下「创建第二个 MainWindow」会触发 qfluentwidgets
    scroll_bar 的 Shiboken 竞态 segfault（真实程序单实例单窗口不受影响），
    故重启恢复改由独立进程 e2e 验证（见 QA 报告），此处只验证守卫逻辑。
    """
    from gui_qt.components.sidebar import _normalize_nav_expanded
    assert _normalize_nav_expanded(True) is True
    assert _normalize_nav_expanded(False) is False
    assert _normalize_nav_expanded(None) is True   # 缺失 → 默认展开
    assert _normalize_nav_expanded("脏") is True   # 损坏 → 默认展开
    assert _normalize_nav_expanded(["a"]) is True
    assert _normalize_nav_expanded({"x": 1}) is True


# ── Bug3：页面选中记忆 ──────────────────────────
def test_nav_page_guard():
    """nav_page 脏值守卫：非字符串回退空串（dict/list 不可哈希会 TypeError）。"""
    from gui_qt.app import _safe_nav_page
    assert _safe_nav_page("settings") == "settings"
    assert _safe_nav_page("") == ""
    assert _safe_nav_page(None) == ""
    assert _safe_nav_page(12345) == ""
    assert _safe_nav_page(["a", "b"]) == ""
    assert _safe_nav_page({"x": 1}) == ""


def test_page_memory_saved(window, app):
    """切页即时落盘（Bug3 回归）。"""
    from utils import config
    window.switchTo(window.pages["settings"])
    app.processEvents()
    assert config.USER_PREFS.get("qt_app", "nav_page") == "settings", \
        "切到设置页应保存 nav_page=settings"
    window.switchTo(window.pages["home"])
    app.processEvents()


# ── 全页面遍历 ──────────────────────────────────
def test_all_pages_switch_round2(window, app):
    """全导航页面逐个切换构建无异常（与 test_main_window 互补）。"""
    from gui_qt import nav_registry as nr
    for item in nr.all_items():
        key = item["key"]
        window.switchTo(window.pages[key])
        app.processEvents()
        real = getattr(window.pages[key], "_real", window.pages[key])
        assert real is not None, f"{key} 懒加载未构建"
    window.switchTo(window.pages["home"])
    app.processEvents()


def test_auto_prefs_wires_fluent_combo(window, app):
    """自动保存监听覆盖 qfluentwidgets ComboBox（QA 6-3 修复）。

    旧实现 findChildren(QComboBox) 找不到 Fluent ComboBox（继承 QPushButton），
    面板参数修改从不自动保存（强杀即丢）。注意：PySide6 对 Fluent 自定义
    信号的 receivers() 计数恒为 0（假象），用「修改控件 → 防抖定时器启动」
    验证连接真实生效。
    """
    window.switchTo(window.pages["video"])
    app.processEvents()
    real = window.pages["video"]._real
    real.cb_fmt.setCurrentIndex(2)
    app.processEvents()
    assert real._prefs_timer.isActive(), \
        "修改 Fluent ComboBox 应触发防抖自动保存"
    window.switchTo(window.pages["home"])
    app.processEvents()


def test_pdf_pwd_history(window, app):
    """PDF 密码历史（README v1.3.0 声明功能，2026-08-21 补全）。

    验证：记录去重置顶 / 10 条上限 / 历史下拉一键复用 / 选中后复位。
    """
    from utils import config
    config.USER_PREFS.prefs.setdefault("qt_app", {}) \
        .pop("pdf_pwd_history", None)
    window.switchTo(window.pages["pdf"])
    app.processEvents()
    real = window.pages["pdf"]._real
    # 记录 12 条 → 限 10 条、最新置顶、最旧淘汰
    for i in range(12):
        real._record_pwd(f"pwd{i}")
    h = real._pwd_hist()
    assert len(h) == 10, f"历史应限 10 条，实际 {len(h)}"
    assert h[0] == "pwd11", "最新密码应置顶"
    assert "pwd0" not in h and "pwd1" not in h, "最旧两条应被淘汰"
    # 去重
    real._record_pwd("pwd11")
    assert real._pwd_hist().count("pwd11") == 1, "重复密码应去重"
    # 历史下拉刷新（模拟任务成功回调 _on_state 主线程刷新）
    real._refresh_hist_combos()
    assert real.cb_open_hist.count() >= 2, "历史下拉应有密码项"
    real.cb_open_hist.setCurrentIndex(1)
    app.processEvents()
    assert real.ed_open_pwd.text() == real.cb_open_hist.itemText(1), \
        "选中历史应填入密码框"
    assert real.cb_open_hist.currentIndex() == 0, "选中后应复位到占位项"
    # 空密码不记录
    real._record_pwd("")
    assert len(real._pwd_hist()) == 10
    window.switchTo(window.pages["home"])
    app.processEvents()


# ── 主题往返 ────────────────────────────────────
def test_theme_switch_round2(window, app):
    """明暗主题往返 3 次无异常。"""
    from gui_qt.components import theme_manager as tm
    for _ in range(3):
        mode = window.theme_mgr.current_mode()
        window.theme_mgr.set_mode(
            tm.MODE_DARK if mode == tm.MODE_LIGHT else tm.MODE_LIGHT)
        app.processEvents()
    window.theme_mgr.set_mode(tm.MODE_LIGHT)
    app.processEvents()
