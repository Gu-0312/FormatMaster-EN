"""主窗口级集成测试：MainWindow 构建、全导航注册、页面切换、主题切换。

offscreen 模式下验证窗口级集成（真实窗口交互需人工/真实环境）。

注：offscreen 平台下 Python 3.11 的 GC 回收 Shiboken 包装对象会触发
access violation（真实 windows 平台不触发，已实测）。测试环境禁用
自动 GC（gc.disable）规避该测试平台伪影；真实应用运行不受影响。
"""
import gc
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["FORMATMASTER_OFFSCREEN"] = "1"

# offscreen 平台伪影规避：详见模块 docstring
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


def test_main_window_builds(window):
    """主窗口可构建，全部 41 个导航入口注册。"""
    from gui_qt import nav_registry as nr
    total = sum(1 for _ in nr.all_items())
    assert len(window.pages) == total, \
        f"注册页面 {len(window.pages)} != 导航条目 {total}"
    assert window.windowTitle() == "格式大师"


def test_all_pages_switchable(window, app):
    """逐个切换全部页面：无异常、当前页正确。"""
    from gui_qt import nav_registry as nr
    failures = []
    for item in nr.all_items():
        key = item["key"]
        try:
            window.switchTo(window.pages[key])
            app.processEvents()
            assert window.stackedWidget.currentWidget() is window.pages[key]
        except Exception as e:  # noqa: BLE001
            failures.append(f"[{key}] {type(e).__name__}: {e}")
    if failures:
        print("\n".join(failures))
    assert not failures, f"{len(failures)} 个页面切换失败"
    # 切回首页
    window.switchTo(window.pages["home"])
    app.processEvents()


def test_theme_toggle(window, app):
    """主题切换（亮→暗→亮）无异常。"""
    from gui_qt.components import theme_manager as tm
    mgr = window.theme_mgr
    for mode in (tm.MODE_DARK, tm.MODE_LIGHT, tm.MODE_DARK):
        mgr.set_mode(mode)
        app.processEvents()
    mgr.set_mode(tm.MODE_LIGHT)
    app.processEvents()


def test_task_manager_flow(window, app):
    """任务管理器：注册→进度→完成 状态流转。"""
    tm = window.task_manager
    state = {}

    def _on_state(tid, s):
        state[tid] = s

    tm.sig_state.connect(_on_state)
    tid = tm.add_task(
        name="集成测试任务", task_type="generic",
        file_path="nonexist.mp4", output_path="nonexist.mp4",
        params={}, runner=lambda task, progress_cb: True,
        need_ffmpeg=False)
    assert tid is not None
    app.processEvents()
    assert state.get(tid) in ("waiting", "running", "done", "success"), \
        f"任务状态异常: {state.get(tid)}"
    tm.cancel_task(tid)
    app.processEvents()


def test_task_failure_writes_log(window, app):
    """转换失败/成功/取消必须写入 debug.log（设置页「运行日志」可见）。"""
    import time
    from app.logger import configure, get_log_path
    configure(level="debug")
    log_path = get_log_path()
    # 记录本次测试前日志行数，只断言新增内容（不破坏用户既有日志）
    baseline = 0
    try:
        with open(log_path, encoding="utf-8") as f:
            baseline = sum(1 for _ in f)
    except OSError:
        pass

    mgr = window.task_manager

    def _bad_runner(task, progress_cb):
        raise RuntimeError("编码器初始化失败")

    def _wait_terminal(tid, want):
        for _ in range(30):
            app.processEvents()
            t = mgr.get_task(tid)
            if t and t.state == want:
                return True
            time.sleep(0.1)
        return False

    # 失败任务（generic runner 抛异常）
    t_fail = mgr.add_task(
        name="日志失败测试.mp4", task_type="generic",
        file_path="", output_path="", params={},
        runner=_bad_runner, need_ffmpeg=False)
    # 成功任务
    t_ok = mgr.add_task(
        name="日志成功测试.mp4", task_type="generic",
        file_path="", output_path="", params={},
        runner=lambda t, cb: True, need_ffmpeg=False)
    # 取消任务
    t_cancel = mgr.add_task(
        name="日志取消测试.mp4", task_type="generic",
        file_path="", output_path="", params={},
        runner=lambda t, cb: True, need_ffmpeg=False)
    mgr.cancel_task(t_cancel)

    assert _wait_terminal(t_fail, "failed")
    assert _wait_terminal(t_ok, "success")
    assert _wait_terminal(t_cancel, "cancelled")
    time.sleep(0.3)

    with open(log_path, encoding="utf-8") as f:
        lines = f.readlines()
    new = "".join(lines[baseline:])
    assert "日志失败测试.mp4 失败" in new, "失败未写日志"
    assert "失败:" in new, "失败原因未写日志"
    assert "日志成功测试.mp4 完成" in new, "成功未写日志"
    assert "日志取消测试.mp4 已取消" in new, "取消未写日志"
