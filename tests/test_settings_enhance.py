"""设置页增强 6 项功能回归测试（2026-08-16）。

1. 一键恢复默认设置（UserPrefs.clear）
2. 界面缩放比例（ui_scale → QSS 字号缩放）
3. 转换冲突处理策略（make_output_path auto_rename/overwrite）
4. 清理选项细化（cleanup_temp_files 分类）
5. 启动画面开关（show_splash 偏好 + 设置页控件）
6. FFmpeg 全局附加参数（_extra_ffmpeg_args 解析）

注意：所有 USER_PREFS 读写必须 try/finally 恢复，避免污染真实配置。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["FORMATMASTER_OFFSCREEN"] = "1"

import gc

gc.disable()

import pytest

from PySide6.QtWidgets import QApplication

from utils.config import USER_PREFS

_SAVED = {
    "conflict_policy": None,
    "ui_scale": None,
    "ffmpeg_extra_args": None,
}


@pytest.fixture(autouse=True)
def _backup_prefs():
    """备份并恢复受影响偏好（防测试污染真实配置）。"""
    for k in _SAVED:
        _SAVED[k] = USER_PREFS.get("qt_app", k, None)
    yield
    for k, v in _SAVED.items():
        if v is None:
            # 恢复为默认：直接删除该键（用 set 回默认值等价）
            USER_PREFS.set("qt_app", k, {
                "conflict_policy": "auto_rename",
                "ui_scale": 1.0,
                "ffmpeg_extra_args": "",
            }[k])
        else:
            USER_PREFS.set("qt_app", k, v)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class TestResetDefaults:
    def test_userprefs_clear(self):
        USER_PREFS.set("qt_app", "test_key", "v1")
        USER_PREFS.clear()
        assert USER_PREFS.get("qt_app", "test_key", None) is None
        assert USER_PREFS.get("qt_app", "conflict_policy", "auto_rename") \
            == "auto_rename"


class TestUiScale:
    def test_qss_scale_apply_and_restore(self):
        from gui_qt.components import design_system as ds
        USER_PREFS.set("qt_app", "ui_scale", 1.25)
        qss_big = ds.generate_qss()
        assert "font-size: 15px" in qss_big, "12px×1.25=15px 应出现"
        USER_PREFS.set("qt_app", "ui_scale", 1.0)
        qss_norm = ds.generate_qss()
        assert "font-size: 12px" in qss_norm
        assert "font-size: 15px" not in qss_norm

    def test_scale_clamped(self):
        from gui_qt.components.design_system import ui_scale
        USER_PREFS.set("qt_app", "ui_scale", 5.0)
        assert ui_scale() == 1.5
        USER_PREFS.set("qt_app", "ui_scale", 0.1)
        assert ui_scale() == 0.85


class TestConflictPolicy:
    def test_auto_rename(self):
        from gui_qt.task_manager import make_output_path
        d = tempfile.mkdtemp()
        src = os.path.join(d, "src")
        out = os.path.join(d, "out")
        os.makedirs(src), os.makedirs(out)
        f = os.path.join(src, "a.mp4")
        open(f, "w").write("x")
        open(os.path.join(out, "a.mp4"), "w").write("x")
        open(os.path.join(out, "a_1.mp4"), "w").write("x")
        USER_PREFS.set("qt_app", "conflict_policy", "auto_rename")
        p = make_output_path(f, out, ".mp4")
        assert os.path.basename(p) == "a_2.mp4", p

    def test_overwrite(self):
        from gui_qt.task_manager import make_output_path
        d = tempfile.mkdtemp()
        src = os.path.join(d, "src")
        out = os.path.join(d, "out")
        os.makedirs(src), os.makedirs(out)
        f = os.path.join(src, "a.mp4")
        open(f, "w").write("x")
        open(os.path.join(out, "a.mp4"), "w").write("x")
        USER_PREFS.set("qt_app", "conflict_policy", "overwrite")
        p = make_output_path(f, out, ".mp4")
        assert os.path.basename(p) == "a.mp4", p

    def test_same_path_never_overwrite_source(self):
        """源目同路径时即使 overwrite 也重命名（防覆盖源文件）。"""
        from gui_qt.task_manager import make_output_path
        d = tempfile.mkdtemp()
        f = os.path.join(d, "a.mp4")
        open(f, "w").write("x")
        USER_PREFS.set("qt_app", "conflict_policy", "overwrite")
        p = make_output_path(f, d, ".mp4")
        assert os.path.basename(p) == "a_1.mp4", p

    def test_fixed_suffix_panels_use_make_output_path(self):
        """固定后缀输出面板（图片压缩/音频处理/缩略图墙）的 _make_task 必须
        统一走 make_output_path，应用冲突策略 + 源目同路径保护。

        历史 bug：这些面板直接 os.path.join 拼接（如 *_compressed.ext），
        输出已存在时无条件覆盖，与用户设置的冲突策略不一致。
        """
        import inspect
        from gui_qt.panels import (audio_trim_panel, compress_img_panel,
                                   video_frame_panel)
        for mod, method in ((audio_trim_panel, "_make_task"),
                            (compress_img_panel, "_make_task"),
                            (video_frame_panel, "_make_task")):
            cls = [c for c in mod.__dict__.values()
                   if isinstance(c, type) and method in c.__dict__
                   and c.__module__ == mod.__name__][0]
            src = inspect.getsource(getattr(cls, method))
            assert "make_output_path" in src, \
                f"{mod.__name__}.{method} 必须走 make_output_path（冲突策略）"


class TestCleanupCategories:
    def test_category_filter(self):
        from utils.temp_cleanup import cleanup_temp_files
        tmp = tempfile.gettempdir()
        p1 = os.path.join(tmp, "formatmaster_concat_cf.txt")
        p2 = os.path.join(tmp, "fm_share_empty_cf")
        open(p1, "w").write("x")
        os.makedirs(p2, exist_ok=True)
        try:
            cleanup_temp_files(["share"])   # 只清 share：concat 应保留
            assert os.path.isfile(p1)
            cleanup_temp_files(["concat"])
            assert not os.path.isfile(p1)
        finally:
            if os.path.isfile(p1):
                os.remove(p1)
            if os.path.isdir(p2) and not os.listdir(p2):
                os.rmdir(p2)


class TestFfmpegExtraArgs:
    def test_parse(self):
        from core.ffmpeg_progress import _extra_ffmpeg_args
        USER_PREFS.set("qt_app", "ffmpeg_extra_args", "-threads 4 -preset fast")
        assert _extra_ffmpeg_args() == ["-threads", "4", "-preset", "fast"]
        USER_PREFS.set("qt_app", "ffmpeg_extra_args", "")
        assert _extra_ffmpeg_args() == []


class TestSettingsControls:
    """设置页 6 项新控件存在性（懒构建触发）。"""

    def test_new_controls(self, app):
        from gui_qt.services import QtServices
        from gui_qt.task_manager import TaskManager
        from gui_qt.components.theme_manager import ThemeManager
        services = QtServices()
        services.task_manager = TaskManager(services)
        services.theme_mgr = ThemeManager(services)

        class _Win:
            pass

        from gui_qt.pages.settings_page import SettingsPage
        sp = SettingsPage(_Win(), services)
        try:
            sp._build_general()
            sp._build_appearance()
            sp._build_convert()
            sp._build_advanced()
            app.processEvents()
            for name in ("card_splash", "card_reset_defaults",
                         "btn_reset_defaults", "card_ui_scale",
                         "card_conflict", "card_clean_share",
                         "card_clean_m3u8", "ed_ffmpeg_args"):
                assert hasattr(sp, name), f"{name} 缺失"
            # 默认值
            assert sp.card_splash.isChecked() is True  # show_splash 默认开
            assert sp.card_conflict.comboBox.currentIndex() == 0
        finally:
            sp.deleteLater()
            app.processEvents()
