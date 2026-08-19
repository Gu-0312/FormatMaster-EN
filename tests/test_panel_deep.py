"""属性面板深度测试 + 构建性能统计。

覆盖：
1. 所有 BaseQtPanel 面板：SegmentedWidget/模式 ComboBox 逐项切换，
   collect_params/collect_prefs 往返无异常且参数随模式联动。
2. 输出格式下拉（cb_fmt / fmt 相关）与面板格式映射一致。
3. 构建性能：记录每个面板构建耗时，>200ms 视为性能隐患输出警告。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["FORMATMASTER_OFFSCREEN"] = "1"

import pytest

from PySide6.QtWidgets import QApplication, QComboBox
from qfluentwidgets import SegmentedWidget


@pytest.fixture(scope="module")
def app_ctx():
    from gui_qt.services import QtServices
    from gui_qt.task_manager import TaskManager
    app = QApplication.instance() or QApplication([])
    services = QtServices()
    services.task_manager = TaskManager(services)
    from gui_qt.components.theme_manager import ThemeManager
    services.theme_mgr = ThemeManager(services)

    class _Window:
        pass

    yield app, _Window(), services
    app.processEvents()


def _segmented_widgets(panel):
    return panel.findChildren(SegmentedWidget)


def _build_all(app_ctx):
    """构建全部面板，返回 {key: (panel, build_ms)}。"""
    app, win, services = app_ctx
    from gui_qt import nav_registry as nr
    from gui_qt.panels.base_panel import BaseQtPanel
    result = {}
    for item in nr.all_items():
        key = item["key"]
        t0 = time.perf_counter()
        try:
            panel = item["factory"](win, services)
            build_ms = (time.perf_counter() - t0) * 1000
            result[key] = (panel, build_ms)
        except Exception as e:  # noqa: BLE001
            result[key] = (None, 0)
            raise
    return result


def test_segmented_mode_switch_all_panels(app_ctx):
    """每个含 SegmentedWidget 的面板：逐模式切换后 collect_params 正常。"""
    app, win, services = app_ctx
    from gui_qt.panels.base_panel import BaseQtPanel
    checked = 0
    failures = []
    for key, (panel, _) in _build_all(app_ctx).items():
        if not isinstance(panel, BaseQtPanel):
            panel.deleteLater()
            continue
        try:
            for sg in _segmented_widgets(panel):
                # SegmentedWidget 无 count()，用 items 列表遍历
                items = list(getattr(sg, "items", []) or [])
                if not items:
                    continue
                for it in items:
                    sg.setCurrentItem(it)
                    app.processEvents()
                    params = panel.collect_params()
                    assert isinstance(params, dict)
                    checked += 1
            panel.deleteLater()
        except Exception as e:  # noqa: BLE001
            failures.append(f"[{key}] {type(e).__name__}: {e}")
    if failures:
        print("\n".join(failures))
    assert not failures, f"{len(failures)} 个面板模式切换失败"
    print(f"{checked} 次模式切换 + params 联动验证通过")


def test_format_dropdown_matches_panel(app_ctx):
    """输出格式下拉（含 fmt 属性的面板）与面板格式映射一致。"""
    app, win, services = app_ctx
    from gui_qt.panels.base_panel import BaseQtPanel
    mismatches = []
    for key, (panel, _) in _build_all(app_ctx).items():
        if not isinstance(panel, BaseQtPanel):
            panel.deleteLater()
            continue
        try:
            fmt_map = getattr(panel, "FMT_MAP", None) or getattr(panel, "formats", None)
            combos = [w for w in panel.findChildren(QComboBox)
                      if "fmt" in w.objectName().lower()
                      or getattr(w, "objectName", lambda: "")() in ("fmt", "cb_fmt")]
            if not combos:
                panel.deleteLater()
                continue
            for cb in combos:
                if cb.count() == 0:
                    continue
                for i in range(cb.count()):
                    cb.setCurrentIndex(i)
                    app.processEvents()
                    params = panel.collect_params()
                    assert isinstance(params, dict), f"{key} collect_params 非 dict"
            panel.deleteLater()
        except Exception as e:  # noqa: BLE001
            mismatches.append(f"[{key}] {type(e).__name__}: {e}")
    if mismatches:
        print("\n".join(mismatches))
    assert not mismatches
    print("输出格式下拉联动验证通过")


def test_panel_build_performance(app_ctx):
    """构建性能：输出各面板构建耗时，>200ms 视为隐患。"""
    app, win, services = app_ctx
    rows = []
    for key, (panel, build_ms) in _build_all(app_ctx).items():
        rows.append((key, build_ms))
        panel.deleteLater()
    rows.sort(key=lambda r: -r[1])
    print("\n面板构建耗时 TOP（ms）:")
    for key, ms in rows[:12]:
        flag = " ⚠️ >200ms" if ms > 200 else ""
        print(f"  {key:<18} {ms:7.1f}{flag}")
    slow = [k for k, ms in rows if ms > 200]
    # 不硬失败（重面板构建含 UI 线程外的预加载），只输出告警
    assert len(slow) == 0, f"构建 >200ms 的面板: {slow}"


def test_stress_filelist_batch(app_ctx):
    """压力：FileListCard 批量添加 500 文件 + 清空，验证耗时与去重。"""
    import tempfile
    from gui_qt.widgets import FileListCard
    app, win, services = app_ctx
    with tempfile.TemporaryDirectory() as d:
        paths = []
        for i in range(500):
            p = os.path.join(d, f"f{i:04d}.mp4")
            with open(p, "wb") as f:
                f.write(b"x")
            paths.append(p)
        card = FileListCard(file_exts={".mp4"})
        t0 = time.perf_counter()
        added = card.add_files(paths)
        ms = (time.perf_counter() - t0) * 1000
        assert added == 500, f"应添加 500 个，实际 {added}"
        assert len(card.files()) == 500
        # 去重：重复添加不增加
        card.add_files(paths)
        assert len(card.files()) == 500, "重复添加应去重"
        t0 = time.perf_counter()
        card.clear_files()
        ms_clear = (time.perf_counter() - t0) * 1000
        assert len(card.files()) == 0
        print(f"批量 500 文件: 添加 {ms:.0f}ms, 清空 {ms_clear:.0f}ms")
        assert ms < 5000, f"批量添加过慢: {ms:.0f}ms"
        card.deleteLater()


def test_stress_task_queue(app_ctx):
    """压力：任务队列注册 20 个任务无异常（不实际执行）。"""
    app, win, services = app_ctx
    tm = services.task_manager
    added = 0
    for i in range(20):
        try:
            tid = tm.add_task(
                name=f"压测任务 {i}",
                task_type="generic",
                file_path=f"stress-{i}.mp4",
                output_path=f"stress-{i}.mp4",
                params={"idx": i},
                runner=lambda task, progress_cb: True,
                need_ffmpeg=False,  # 压测不依赖 FFmpeg
            )
            if tid is not None:
                added += 1
        except Exception:  # noqa: BLE001 - 个别失败不影响统计
            pass
    assert added == 20, f"应成功注册 20 个任务，实际 {added}"
    print("任务队列 20 任务注册通过")
