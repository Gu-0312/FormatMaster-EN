# -*- coding: utf-8 -*-
"""偏好记忆功能回归测试（2026-08-17 新增）。

背景：用户要求「设置里默认输出目录增加记忆模式，所有功能/设置/属性面板
都加记忆」——重进面板不用重新浏览目录。

实现：
1. BaseQtPanel 统一兜底：save_prefs 自动补存 out_dir_combo/out_dir_path，
   __init__ 统一回填（有真实 out_row 的面板全部生效，零改动）。
2. 6 个此前完全没有 collect_prefs/apply_prefs 的面板补齐业务配置记忆：
   file_security / phantom / scene / table_ocr / batch_rename / monitor。
3. hash_panel 的 out_row 是 _NoOutRow 占位类（无 mode/path），
   兜底必须 duck-typing 跳过，不能崩。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _qt_env(monkeypatch, tmp_path):
    """offscreen Qt + prefs 备份（测试内 set_pref 会真实落盘 user_prefs.json）。"""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["FORMATMASTER_OFFSCREEN"] = "1"
    import gc
    gc.disable()
    from utils.config import USER_PREFS
    from gui_qt.services import QT_PREFS_PANEL
    # 备份整个 qt_app/panel_* 命名空间
    panels = USER_PREFS.prefs.get(QT_PREFS_PANEL, {})
    backup = dict(panels)

    def _restore():
        panels.clear()
        panels.update(backup)
        USER_PREFS._save()

    return _restore


def _mk_services():
    from PySide6.QtWidgets import QApplication
    from gui_qt.services import QtServices
    from gui_qt.task_manager import TaskManager
    from gui_qt.components.theme_manager import ThemeManager
    app = QApplication.instance() or QApplication([])
    services = QtServices()
    services.task_manager = TaskManager(services)
    services.theme_mgr = ThemeManager(services)
    return app, services


class _Window:
    pass


def test_panel_without_collect_now_memorizes(monkeypatch):
    """6 个此前无 collect_prefs 的面板：collect 非空 + 保存 + 重建回填。"""
    import tempfile
    import importlib
    _restore = _qt_env(monkeypatch, None)
    try:
        app, services = _mk_services()
        cases = [("file_security", "FileSecurityPanelPage"),
                 ("phantom", "PhantomPanelPage"),
                 ("scene", "ScenePanelPage"),
                 ("table_ocr", "TableOcrPanelPage"),
                 ("batch_rename", "BatchRenamePanelPage"),
                 ("monitor", "MonitorPanelPage")]
        for pkey, cls in cases:
            PC = getattr(importlib.import_module(f"gui_qt.panels.{pkey}_panel"), cls)
            p1 = PC(_Window(), services)
            app.processEvents()
            prefs = p1.collect_prefs()
            assert prefs, f"{pkey}: collect_prefs 为空（配置未记忆）"
            # 有真实 out_row 的面板：save 自动补 out_dir
            if hasattr(p1, "out_row") and hasattr(p1.out_row, "mode"):
                d = tempfile.mkdtemp(prefix="fm_mem_")
                p1.out_row.set_state(p1.out_row.MODE_CUSTOM, d)
            p1.save_prefs()
            p1.deleteLater()
            app.processEvents()
            p2 = PC(_Window(), services)
            app.processEvents()
            if hasattr(p2, "out_row") and hasattr(p2.out_row, "mode") \
                    and p2.out_row.mode() == p2.out_row.MODE_CUSTOM:
                assert p2.out_row.path() == d, f"{pkey}: 重建未回填输出目录"
            p2.deleteLater()
            app.processEvents()
    finally:
        _restore()


def test_base_fallback_auto_memorizes_out_dir(monkeypatch):
    """有 collect_prefs 但未含 out_dir 的面板（如 audio_enhance）也自动记忆。"""
    import tempfile
    _restore = _qt_env(monkeypatch, None)
    try:
        app, services = _mk_services()
        from gui_qt.panels.audio_enhance_panel import AudioEnhancePanelPage
        from gui_qt.services import QT_PREFS_PANEL
        from utils.config import USER_PREFS
        d = tempfile.mkdtemp(prefix="fm_od_")
        p1 = AudioEnhancePanelPage(_Window(), services)
        app.processEvents()
        p1.out_row.set_state(p1.out_row.MODE_CUSTOM, d)
        p1.save_prefs()
        stored = USER_PREFS.get(QT_PREFS_PANEL, "panel_audio_enhance", {})
        assert stored.get("out_dir_combo") == p1.out_row.MODE_CUSTOM, \
            "save_prefs 必须自动补存 out_dir"
        assert stored.get("out_dir_path") == d
        p1.deleteLater()
        app.processEvents()
        p2 = AudioEnhancePanelPage(_Window(), services)
        app.processEvents()
        assert p2.out_row.path() == d, "重进面板必须自动恢复上次目录"
        p2.deleteLater()
        app.processEvents()
    finally:
        _restore()


def test_hash_placeholder_out_row_safe(monkeypatch):
    """hash_panel 的 out_row 是 _NoOutRow 占位类：save_prefs 必须安全跳过。"""
    _restore = _qt_env(monkeypatch, None)
    try:
        app, services = _mk_services()
        from gui_qt.panels.hash_panel import HashPanelPage
        p = HashPanelPage(_Window(), services)
        app.processEvents()
        p.save_prefs()   # 不应抛 AttributeError
        p.deleteLater()
        app.processEvents()
    finally:
        _restore()
