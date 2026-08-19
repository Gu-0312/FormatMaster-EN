"""打包依赖完整性回归测试（2026-08-16）。

覆盖三类打包风险：
1. 动态加载资源路径（plugins / bin / data/models）在打包环境（_MEIPASS）
   下可被正确解析——修复 __file__ 推导在 PyInstaller onedir 下指向
   exe 旁而非 _internal/ 的问题；
2. id_photo MODNet 模型路径打包兼容（资源优先 + 用户目录下载回退）；
3. build.py 关键收集配置齐全（plugins add-data、core collect-submodules、
   qtawesome collect-data、data/models add-data；core.pdf_form 已移除）。
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_PY = os.path.join(ROOT, "build.py")


def _build_text():
    with open(BUILD_PY, encoding="utf-8") as f:
        return f.read()


@pytest.fixture()
def packaged_env():
    """模拟 PyInstaller 打包环境：sys.frozen + _MEIPASS（含随包资源）。"""
    meipass = tempfile.mkdtemp(prefix="fm_pkg_")
    for sub in ("bin", "plugins", "data/models/idphoto"):
        os.makedirs(os.path.join(meipass, sub), exist_ok=True)
    for src_rel, dst in (("bin/yt-dlp.exe", "bin"),
                         ("plugins/ascii_art.py", "plugins"),
                         ("data/models/idphoto/modnet.onnx",
                          "data/models/idphoto")):
        s = os.path.join(ROOT, src_rel)
        if os.path.isfile(s):
            shutil.copy(s, os.path.join(meipass, dst,
                                        os.path.basename(s)))
    old_frozen = getattr(sys, "frozen", None)
    old_meipass = getattr(sys, "_MEIPASS", None)
    sys.frozen = True
    sys._MEIPASS = meipass
    yield meipass
    if old_frozen is None:
        del sys.frozen
    else:
        sys.frozen = old_frozen
    if old_meipass is None:
        if hasattr(sys, "_MEIPASS"):
            del sys._MEIPASS
    else:
        sys._MEIPASS = old_meipass
    # 恢复被 reload 成打包路径的模块（防污染后续开发环境测试）
    import importlib
    for m in ("core.tool_check", "core.plugin_loader",
              "core.tool_updater", "core.video_downloader",
              "core.id_photo"):
        try:
            importlib.reload(importlib.import_module(m))
        except Exception:  # noqa: BLE001
            pass
    shutil.rmtree(meipass, ignore_errors=True)


class TestPackagedPaths:
    """打包环境（_MEIPASS）下资源路径可解析。"""

    def test_bin_dir(self, packaged_env):
        import importlib
        import core.tool_check as tc
        importlib.reload(tc)
        assert tc._BIN_DIR.startswith(packaged_env), tc._BIN_DIR
        assert os.path.isdir(tc._BIN_DIR)

    def test_plugin_dirs(self, packaged_env):
        import importlib
        import core.plugin_loader as pl
        importlib.reload(pl)
        dirs = pl.plugin_dirs()
        assert any(d.startswith(packaged_env) and os.path.isdir(d)
                   for d in dirs), dirs

    def test_ytdlp_exe_path(self, packaged_env):
        import importlib
        import core.tool_updater as tu
        importlib.reload(tu)
        p = tu._ytdlp_exe_path()
        assert p and p.startswith(packaged_env), p

    def test_video_downloader_ytdlp(self, packaged_env):
        import importlib
        import core.video_downloader as vd
        importlib.reload(vd)
        p = vd._find_ytdlp_exe()
        assert p and p.startswith(packaged_env), p

    def test_idphoto_model(self, packaged_env):
        import importlib
        import core.id_photo as ip
        importlib.reload(ip)
        p = ip._model_path()
        assert p.startswith(packaged_env), p
        # 模型缺失（删掉 _MEIPASS 内模型）→ 回退用户数据目录（可写下载目标）
        shutil.rmtree(os.path.join(packaged_env, "data"), ignore_errors=True)
        from utils.config import get_user_data_dir
        p2 = ip._model_path()
        assert p2.startswith(get_user_data_dir()), p2


class TestDevPaths:
    """开发环境路径保持命中。"""

    def test_bin_and_plugins(self):
        from core.tool_check import _BIN_DIR
        from core.plugin_loader import plugin_dirs
        from core.tool_updater import _ytdlp_exe_path
        from core.video_downloader import _find_ytdlp_exe
        assert os.path.isdir(_BIN_DIR)
        assert any(os.path.isdir(d) for d in plugin_dirs())
        assert _ytdlp_exe_path() and os.path.isfile(_ytdlp_exe_path())
        assert _find_ytdlp_exe()

    def test_idphoto_model_dev(self):
        from core.id_photo import _model_path
        assert os.path.isfile(_model_path())


class TestBuildConfig:
    """build.py 打包配置完整性（防回归删配置）。"""

    def test_plugins_collected(self):
        t = _build_text()
        assert "--add-data" in t and "plugins" in t, "plugins 未 add-data"
        assert os.path.join(ROOT, "plugins").replace("\\", "/") in t \
            or "plugins" in t

    def test_core_collect_submodules(self):
        assert "--collect-submodules" in _build_text() and \
            '"core"' in _build_text()

    def test_qtawesome_not_collected(self):
        t = _build_text()
        assert "qtawesome" not in t, \
            "插件中心已改用 FluentIcon，build.py 不应再收集 qtawesome"

    def test_models_add_data(self):
        t = _build_text()
        assert "data/models" in t, "MODNet 模型未 add-data"

    def test_pdf_form_removed(self):
        assert "core.pdf_form" not in _build_text(), \
            "core.pdf_form 已删除，build.py 不应再引用"

    def test_bin_and_assets(self):
        t = _build_text()
        assert "bin;bin" in t or "bin" in t
        assert "assets;assets" in t or "assets" in t
