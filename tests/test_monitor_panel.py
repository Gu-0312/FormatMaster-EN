# -*- coding: utf-8 -*-
"""监视面板回归测试。

历史 bug（2026-08-17 全功能体检）：
1. 文件夹监视目录只在启动时快照到 self._dir，运行中改 ed_dir（浏览按钮）
   不生效，扫描的仍是旧目录 —— 与局域网接收目录同款「运行中配置不生效」。
2. 运行中切换目标类型，_seen 快照仍是旧类型扩展名集合，该类型下已存在的
   文件会被当成「新文件」批量误转。
3. _convert 提交异常会中断 _scan，导致 _seen = now 不执行 → 同一文件
   下次扫描重复提交（死循环风险）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _monitor_src():
    import inspect
    from gui_qt.panels import monitor_panel as mp
    return inspect.getsource(mp.MonitorPanelPage)


def test_scan_reads_dir_live():
    """锁 1：_scan 必须实时读 ed_dir（运行中改监视目录立即生效）。"""
    src = _monitor_src()
    assert "self.ed_dir.text()" in src, \
        "_scan 必须实时读 ed_dir，而非只用启动时快照 self._dir"


def test_kind_change_rebuilds_seen():
    """锁 2：_kind_changed 在监视运行中必须重建 _seen 快照。"""
    src = _monitor_src()
    assert "_seen = {f for f in self._list_files" in src, \
        "切换目标类型必须重建 _seen，防止已存在文件被批量误转"


def test_scan_convert_exception_safe():
    """锁 3：_scan 中 _convert 必须异常隔离，确保 _seen 始终更新。"""
    src = _monitor_src()
    assert "self._convert(f)" in src
    assert "except Exception" in src, "_convert 异常不应中断 _seen 更新"


def test_live_dir_change_scan():
    """行为测试：运行中改监视目录 → 下一次 _scan 立即扫描新目录。"""
    import tempfile
    from PySide6.QtWidgets import QApplication
    from gui_qt.services import QtServices
    from gui_qt.task_manager import TaskManager
    from gui_qt.components.theme_manager import ThemeManager
    from gui_qt.panels.monitor_panel import MonitorPanelPage

    app = QApplication.instance() or QApplication([])
    services = QtServices()
    services.task_manager = TaskManager(services)
    services.theme_mgr = ThemeManager(services)

    class _Window:
        pass

    dirA = tempfile.mkdtemp(prefix='fm_watch_a_')
    dirB = tempfile.mkdtemp(prefix='fm_watch_b_')
    open(os.path.join(dirA, 'a1.mp4'), 'w').write('x')
    open(os.path.join(dirB, 'b1.mp4'), 'w').write('x')

    panel = MonitorPanelPage(_Window(), services)
    app.processEvents()
    try:
        panel.ed_dir.setText(dirA)
        panel._toggle()                       # 开始监视 A（默认 video 类型）
        assert panel._running
        assert os.path.join(dirA, 'a1.mp4') in panel._seen

        # 运行中改监视目录为 B → _scan 实时读 ed_dir
        panel.ed_dir.setText(dirB)
        panel._seen = set()
        panel._convert = lambda f: None       # stub：不真实提交转换任务
        panel._scan()
        assert os.path.join(dirB, 'b1.mp4') in panel._seen, \
            "运行中改目录后 _scan 必须扫描新目录"
        assert os.path.join(dirA, 'a1.mp4') not in panel._seen, \
            "不应再扫描旧目录"
    finally:
        panel._toggle()                       # 停止监视
        panel.deleteLater()
        app.processEvents()
