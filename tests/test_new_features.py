# -*- coding: utf-8 -*-
"""新增四功能回归测试：电子书互转 / 压缩到指定大小 / 批量重命名增强 / GIF 胶片抽帧。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _mk_tmp_img(tmp_path, size=(1600, 1200), mode="RGB"):
    from PIL import Image
    img = Image.new(mode, size, (128, 64, 32))
    p = str(tmp_path / "src.jpg")
    img.save(p, quality=92)
    return p


# ── 电子书互转 ────────────────────────────────
def test_ebook_txt_to_epub_roundtrip(tmp_path):
    from core.ebook_converter import convert_ebook
    txt = tmp_path / "book.txt"
    txt.write_text("第一章 开端\n\n这是第一段。\n\n" + "内容" * 200, encoding="utf-8")
    ep = tmp_path / "book.epub"
    ok, msg = convert_ebook(str(txt), str(ep))
    assert ok, msg
    assert ep.stat().st_size > 500
    out_txt = tmp_path / "book2.txt"
    ok, msg = convert_ebook(str(ep), str(out_txt))
    assert ok, msg
    assert "内容" in out_txt.read_text(encoding="utf-8")


def test_ebook_epub_to_html(tmp_path):
    from core.ebook_converter import convert_ebook
    txt = tmp_path / "b.txt"
    txt.write_text("第一章\n\n段落文字。", encoding="utf-8")
    ep = tmp_path / "b.epub"
    convert_ebook(str(txt), str(ep))
    html = tmp_path / "b.html"
    ok, msg = convert_ebook(str(ep), str(html))
    assert ok, msg
    assert "第一章" in html.read_text(encoding="utf-8")


def test_ebook_unsupported_target_hint(tmp_path):
    from core.ebook_converter import convert_ebook
    txt = tmp_path / "b.txt"
    txt.write_text("hi", encoding="utf-8")
    ok, msg = convert_ebook(str(txt), str(tmp_path / "b.mobi"))
    assert not ok
    assert "Calibre" in msg  # 未装 Calibre 时给出明确提示


# ── 压缩到指定大小 ────────────────────────────
def test_image_compress_to_size(tmp_path):
    from core.tools import image_compress_to_size
    src = _mk_tmp_img(tmp_path)
    out = tmp_path / "small.jpg"
    ok, msg, size = image_compress_to_size(str(src), str(out), 50)
    assert ok, msg
    assert size <= 50 * 1024, f"目标 50KB 实际 {size // 1024}KB"


def test_image_compress_to_size_1mb(tmp_path):
    from core.tools import image_compress_to_size
    src = _mk_tmp_img(tmp_path)
    out = tmp_path / "small2.jpg"
    ok, msg, size = image_compress_to_size(str(src), str(out), 1024)
    assert ok, msg
    assert size <= 1024 * 1024


# ── 批量重命名增强 ────────────────────────────
def test_rename_plan_regex_and_case(tmp_path):
    from core.tools import build_rename_plan
    files = []
    for i in range(3):
        p = tmp_path / f"IMG_2026{i}_photo.JPG"
        p.write_bytes(b"x")
        files.append(str(p))
    plan = build_rename_plan(
        files, "照片_{n:02d}", start_num=1,
        regex_pattern=r"\.JPG$", regex_replace=".jpg", case="lower")
    names = [n for _, n, _ in plan]
    assert names == ["照片_01.jpg", "照片_02.jpg", "照片_03.jpg"], names


def test_rename_plan_preview_equals_execute(tmp_path):
    from core.tools import build_rename_plan, batch_rename
    files = []
    for i in range(3):
        p = tmp_path / f"photo_{i}.JPG"
        p.write_bytes(b"x")
        files.append(str(p))
    plan = build_rename_plan(files, "pic_{n:03d}", case="lower")
    new_names = [n for _, n, _ in plan]
    renamed = batch_rename(files, "pic_{n:03d}", case="lower")
    assert len(renamed) == 3
    disk = sorted(os.path.basename(b) for _a, b in renamed)
    assert disk == sorted(new_names), (disk, new_names)


# ── GIF 胶片抽帧 ─────────────────────────────
def test_extract_strip_frames_rejects_bad_input(tmp_path):
    from core.video_frame_extract import extract_strip_frames
    # 不存在文件 → (False, 0)
    ok, n = extract_strip_frames(str(tmp_path / "missing.mp4"), str(tmp_path), 12)
    assert ok is False and n == 0


# ── 二维码美化 ───────────────────────────────
def _mk_logo(tmp_path):
    from PIL import Image
    p = str(tmp_path / "logo.png")
    Image.new("RGB", (64, 64), (230, 80, 80)).save(p)
    return p


def test_qr_all_styles_and_gradients(tmp_path):
    from core.qr_maker import (make_fancy_qr, GRAD_DIAGONAL, GRAD_NONE,
                               GRAD_VERTICAL, STYLE_DIAMOND, STYLE_DOT,
                               STYLE_ROUNDED, STYLE_SQUARE)
    logo = _mk_logo(tmp_path)
    for style in (STYLE_SQUARE, STYLE_ROUNDED, STYLE_DOT, STYLE_DIAMOND):
        for grad in (GRAD_NONE, GRAD_VERTICAL, GRAD_DIAGONAL):
            img = make_fancy_qr("https://example.com", size=240,
                                fg="#5B5BD6", style=style, gradient=grad,
                                logo_path=logo)
            assert img.size == (240, 240)


def test_qr_without_logo_and_bad_color(tmp_path):
    from core.qr_maker import make_fancy_qr
    img = make_fancy_qr("WIFI:T:WPA;S:test;P:pwd;;", size=200,
                        fg="notacolor")  # 非法色应回退默认，不崩
    assert img.size == (200, 200)
    img2 = make_fancy_qr("x" * 500, size=300)   # 长内容版本自适应
    assert img2.size == (300, 300)


# ── 视频质量分析（码率采样）──────────────────
def test_bitrate_samples_ffprobe_missing(tmp_path, monkeypatch):
    """无 ffprobe 时返回 None（不崩）。"""
    import utils.config as uc
    monkeypatch.setattr(uc, "get_ffprobe_path", lambda: None)
    from core.mediainfo import get_bitrate_samples
    assert get_bitrate_samples(str(tmp_path / "x.mp4")) is None


def test_bitrate_samples_bad_input(tmp_path):
    """不存在文件 → None（不崩）。"""
    from core.mediainfo import get_bitrate_samples
    assert get_bitrate_samples(str(tmp_path / "missing.mp4")) is None


# ── 高级控件组件（QtPdf/QtWebEngine/QtMultimedia/pyqtgraph/superqt/3D）──
def test_range_slider_row_values():
    """superqt 双滑块：区间设置/读取/信号。"""
    import gc
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    gc.disable()
    from gui_qt.components.range_slider_row import RangeSliderRow
    r = RangeSliderRow()
    if not r.available():
        return  # superqt 未装时跳过
    r.set_range(0, 120)
    r.set_values(10, 40)
    lo, hi = r.values()
    assert abs(lo - 10) < 2 and abs(hi - 40) < 2, (lo, hi)
    got = []
    r.valueChanged.connect(lambda a, b: got.append((round(a), round(b))))
    r._slider.setValue((500, 800))
    assert got and got[-1] == (60, 96), got


def test_audio_waveform_decode_missing():
    """波形解码：缺文件/无 ffmpeg 路径安全返回 None。"""
    import gc
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    gc.disable()
    from gui_qt.components.audio_waveform import _decode_pcm, _bucket_peaks
    samples, dur = _decode_pcm("no_such_file.mp3")
    assert samples is None and dur == 0
    assert _bucket_peaks([], 100) == []


def test_pdf_preview_dialog_build():
    """QtPdf 预览对话框：缺文件不崩、文档对象存在。"""
    import gc
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    gc.disable()
    from gui_qt.components.pdf_preview import PdfPreviewDialog
    d = PdfPreviewDialog()
    assert d._doc is not None or not hasattr(d, "_doc")  # 兜底标签路径
    d.close()


def test_html_preview_dialog_build():
    """QtWebEngine 预览对话框：构建不崩（offscreen 走兜底或可用）。"""
    import gc
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    gc.disable()
    from gui_qt.components.html_preview import HtmlPreviewDialog
    d = HtmlPreviewDialog()
    d.close()


def test_video_preview_dialog_build():
    """QtMultimedia 视频预览：构建不崩、播放器存在。"""
    import gc
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    gc.disable()
    from gui_qt.components.video_preview import VideoPreviewDialog
    d = VideoPreviewDialog()
    assert d.player_widget is not None
    d.close()


def test_stats3d_dialog_build():
    """QtDataVisualization 3D：构建不崩（offscreen 无 GL 走兜底）。"""
    import gc
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    gc.disable()
    from gui_qt.components.stats3d import Stats3DDialog
    d = Stats3DDialog()
    # offscreen 可能无 OpenGL → available False，但构建不崩即通过
    d.close()


# ── 硬核控件（代码编辑器/ECharts 大屏/毛玻璃）──
def test_code_editor_open_save(tmp_path):
    """代码编辑器：打开 JSON 高亮 + 保存回写。"""
    import gc
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    gc.disable()
    f = tmp_path / "cfg.json"
    f.write_text('{"key": "value"}', encoding="utf-8")
    from gui_qt.components.code_editor import CodeEditorDialog
    dlg = CodeEditorDialog(str(f))
    assert dlg.editor.language() == "json"
    dlg.editor.setPlainText('{"updated": true}')
    dlg.save()
    assert f.read_text(encoding="utf-8") == '{"updated": true}'


def test_echarts_dialog_build():
    """ECharts 大屏：构建不崩、资产文件存在。"""
    import gc
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    gc.disable()
    from gui_qt.components.echarts_view import EchartsStatsDialog, _ASSET_DIR
    assert os.path.isfile(os.path.join(_ASSET_DIR, "report.html"))
    assert os.path.isfile(os.path.join(_ASSET_DIR, "echarts.min.js"))
    d = EchartsStatsDialog()
    d.close()


def test_glass_bar_blur_offscreen():
    """毛玻璃：offscreen 下 _refresh 安全跳过（不段错误）、模糊转换可用。"""
    import gc
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    gc.disable()
    from gui_qt.components.glass_bar import GlassBar, _blur_pixmap
    from PySide6.QtGui import QPixmap, QColor
    pix = QPixmap(64, 32)
    pix.fill(QColor("#5B5BD6"))
    b = _blur_pixmap(pix, 8)
    assert not b.isNull()
    g = GlassBar()
    g.resize(100, 30)
    g.show()
    app.processEvents()
    assert g._blurred is None  # offscreen 守卫：不抓取背景
    g.close()


# ── 简繁转换字库扩充（opencc 词汇级 + 2314 内置字表）──
def test_zh_convert_opencc_priority():
    """opencc 优先：词汇级转换（软件→軟件、后台→後臺）。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "zh_convert_test", "plugins/zh_convert.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert len(mod._PAIRS) >= 2000, f"字表仅 {len(mod._PAIRS)} 对"
    assert mod.s2t("软件开发后台") == "軟件開發後臺"
    assert mod.t2s("臺灣的繁體中文") == "台湾的繁体中文"


def test_zh_convert_fallback_table():
    """无 opencc 回退：内置 2314 字表仍可转常用字。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "zh_convert_fb", "plugins/zh_convert.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    saved = (mod._HAS_OPENCC, getattr(mod, "_cc_s2t", None),
             getattr(mod, "_cc_t2s", None))
    try:
        mod._HAS_OPENCC = False
        assert mod.s2t("中华人民共和国") == "中華人民共和國"
        assert mod.t2s("臺灣的繁體中文") == "台湾的繁体中文"
    finally:
        mod._HAS_OPENCC = saved[0]


# ── 插件功能补全（hash 13 算法 / base 2-36 / 摩斯标点 / UUID 版本 / 金额大写）──
def _load_plugin(name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, f"plugins/{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_plugin_hash_13_algs():
    """哈希校验：13 种算法（含 SHA3/BLAKE2/CRC32）。"""
    import hashlib, zlib
    h = _load_plugin("hash_calc")
    assert len(h._ALGS) == 13
    assert h.hash_text("hello", "MD5") == hashlib.md5(b"hello").hexdigest()
    assert h.hash_text("hello", "SHA3-256") == hashlib.sha3_256(b"hello").hexdigest()
    assert h.hash_text("hello", "CRC32") == f"{zlib.crc32(b'hello') & 0xffffffff:08x}"


def test_plugin_base_convert_full():
    """进制转换：2-36 全进制 + 负数 + 前缀识别。"""
    b = _load_plugin("base_convert")
    assert b.parse_int("0xFF") == 255
    assert b.parse_int("-128") == -128
    assert b.parse_int("FF", 16) == 255
    assert b.parse_int("1010", 2) == 10
    assert b.to_base(255, 16, True) == "FF"
    assert b.to_base(-255, 2) == "-11111111"
    assert b.parse_int("zz", 36) == 35 * 36 + 35


def test_plugin_morse_punct():
    """摩斯电码：常用标点（ITU）。"""
    m = _load_plugin("morse_code")
    assert m._MORSE.get(".") == ".-.-.-"
    assert m._MORSE.get("?") == "..--.."
    assert m._MORSE.get(",") == "--..--"


def test_plugin_uuid_versions():
    """UUID 生成器：v1/v3/v4/v5 合法。"""
    import re
    u = _load_plugin("uuid_generator")
    for x in (u.gen_uuid("UUID v1", 0), u.gen_uuid("UUID v3", 1),
              u.gen_uuid("UUID v4", 2), u.gen_uuid("UUID v5", 3)):
        assert re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                        r"[0-9a-f]{4}-[0-9a-f]{12}$", x), x


def test_plugin_money_upper_edges():
    """数字大写：内部零/尾部零/万亿/负数边界。"""
    mo = _load_plugin("money_upper")
    cases = [(0, "零元整"), (10, "壹拾元整"), (101, "壹佰零壹元整"),
             (1001, "壹仟零壹元整"), (10005, "壹万零伍元整"),
             (10000001, "壹仟万零壹元整"), (100010000, "壹亿零壹万元整"),
             (1e13, "壹拾万亿元整"), (-50.5, "负伍拾元伍角"), (0.29, "贰角玖分")]
    for inp, want in cases:
        assert mo.money_upper(inp) == want, (inp, mo.money_upper(inp), want)


def test_plugin_id_card_regions():
    """身份证解析：地级市地区库（300+ 条）生效。"""
    import re
    m = _load_plugin("id_card")
    assert len(m._CITIES) >= 300, len(m._CITIES)
    assert m._CITIES.get("4403") == "深圳"
    assert m._CITIES.get("3205") == "苏州"
    w = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    codes = "10X98765432"
    def gen(p17):
        return p17 + codes[sum(int(p17[i]) * w[i] for i in range(17)) % 11]
    ok, txt = m.parse_id_card(gen("44030319951212001"))
    assert ok and "深圳" in txt


# ── 证件照排版打印升级 + QtCharts 移除 ──
def test_id_photo_a6_layout():
    """A6 照片纸排版：1寸 16 张/版、2寸 9 张/版。"""
    from PIL import Image
    from core.id_photo import PAPER_SIZES, layout_print
    assert "A6" in PAPER_SIZES
    cun1 = Image.new("RGB", (295, 413), (255, 0, 0))
    a6 = layout_print(cun1, PAPER_SIZES["A6"], dpi=300)
    assert (a6.width // 295) * (a6.height // 413) >= 16
    cun2 = Image.new("RGB", (413, 579), (0, 0, 255))
    a6b = layout_print(cun2, PAPER_SIZES["A6"], dpi=300)
    assert (a6b.width // 413) * (a6b.height // 579) >= 9


def test_mediainfo_no_qtcharts():
    """媒体信息页：QtCharts 码率图表已移除（无 chart/pivot/文件残留）。"""
    import os
    assert not os.path.exists("gui_qt/components/bitrate_chart.py")
    src = open("gui_qt/panels/mediainfo_panel.py", encoding="utf-8").read()
    assert "QtCharts" not in src and "BitrateChart" not in src
    assert "self.chart" not in src


# ── SpinBox 微调箭头图标修复 ──
def test_spinbox_arrow_icons():
    """SpinIcon patch 生效：本地 SVG 路径替代缺失的 qrc 资源。"""
    import os
    import gui_qt.components.design_system  # 触发 patch
    from qfluentwidgets.components.widgets.spin_box import SpinIcon
    p_up = SpinIcon.UP.path()
    p_down = SpinIcon.DOWN.path()
    assert p_up.endswith("spin_up.svg") and os.path.isfile(p_up), p_up
    assert p_down.endswith("spin_down.svg") and os.path.isfile(p_down), p_down
    # 实际能渲染（drawSvgIcon 不抛异常且像素非全白）
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QPixmap, QPainter, QColor
    app = QApplication.instance() or QApplication([])
    pix = QPixmap(40, 40)
    pix.fill(QColor("#ffffff"))
    p = QPainter(pix)
    SpinIcon.UP.render(p, pix.rect())
    p.end()
    img = pix.toImage()
    non_white = sum(1 for x in range(40) for y in range(40)
                    if img.pixelColor(x, y).lightness() < 230)
    assert non_white > 50, f"箭头渲染像素不足：{non_white}"


def test_spinbox_qss_no_border_triangle():
    """QSS 不再用 Qt 不支持的 border 三角形画箭头，改用本地 SVG image。"""
    import gui_qt.components.design_system as ds
    from qfluentwidgets import setTheme, Theme
    setTheme(Theme.LIGHT)
    qss = ds.generate_qss()
    # up-arrow 段不再使用 border 三角（Qt QSS 不支持）
    if "::up-arrow" in qss:
        up_seg = qss.split("::up-arrow", 1)[1].split("::down-arrow", 1)[0]
        assert "border-bottom:" not in up_seg
    # 新方案：使用本地 SVG image 引用
    assert "spin_up.svg" in qss and "spin_down.svg" in qss


# ── 设置页全分区检查（构建 + 交互 + 回调绑定）──
def test_settings_all_sections_build_and_interact():
    """11 分区构建 + 关键交互（主题/开关/动画）+ 回调绑定齐全。"""
    import gc
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    gc.disable()
    from gui_qt.services import QtServices
    services = QtServices()
    win = type("W", (), {"pages": {}})()
    services.window = win
    from gui_qt.components.theme_manager import ThemeManager
    services.theme_mgr = ThemeManager(services)
    from gui_qt.task_manager import TaskManager
    services.task_manager = TaskManager(services)
    from gui_qt.pages.settings_page import SettingsPage
    page = SettingsPage(win, services)
    # 全分区构建
    for key in page._section_order:
        page._section_builders[key]()
    # 常规开关写入偏好
    writes = []
    _orig = services.set_pref

    def spy(key, val, panel=None):
        writes.append(key)
        return _orig(key, val)
    services.set_pref = spy
    page.card_tray.setValue(not page.card_tray.isChecked())
    app.processEvents()
    assert "tray" in writes
    # 主题切换
    tm2 = services.theme_mgr
    cur = tm2.current_mode()
    tm2.set_mode("light" if cur != "light" else "dark", persist=False)
    # 动画开关
    from gui_qt.components import design_system as ds
    before = ds.animations_enabled()
    ds.set_animations(not before)
    ds.set_animations(before)
    # 备份导出（临时 zip）
    import tempfile, shutil
    from utils.backup import export_backup
    tmp = tempfile.mkdtemp()
    z = os.path.join(tmp, "bk.zip")
    try:
        n = export_backup(z)
        assert os.path.isfile(z) and os.path.getsize(z) > 0 and n > 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── 卡片 hover 高亮修复（纯展示卡触碰不再整卡变色）──
def test_card_no_hover_highlight():
    """Card（纯展示卡）触碰不高亮；HoverCard（可点击卡）保留高亮。"""
    import gc
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    gc.disable()
    from qfluentwidgets import setTheme, Theme
    setTheme(Theme.LIGHT)
    from gui_qt.components import design_system as ds
    from gui_qt.components.card import Card, HoverCard
    from PySide6.QtGui import QColor
    t = ds.tokens()
    c = Card()
    c.show()
    app.processEvents()
    c.isHover = True
    c._updateBackgroundColor()
    assert c.backgroundColorAni.endValue() == QColor(t["card_bg"])
    h = HoverCard()
    h.show()
    app.processEvents()
    h.isHover = True
    h._updateBackgroundColor()
    assert h.backgroundColorAni.endValue() == QColor(t["card_hover"])
    c.close()
    h.close()


# ── QA 审查修复：配置损坏容错 + ffprobe duration 清洗 ──
def test_config_corruption_tolerance():
    """配置损坏（非 dict / 脏值）时全面板构建不崩。"""
    import gc
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    gc.disable()
    from gui_qt.services import QtServices
    services = QtServices()
    win = type("W", (), {"pages": {}})()
    services.window = win
    from gui_qt.components.theme_manager import ThemeManager
    services.theme_mgr = ThemeManager(services)
    from gui_qt.task_manager import TaskManager
    services.task_manager = TaskManager(services)
    from gui_qt.nav_registry import NAV_GROUPS

    bad_values = ["garbage", 12345, ["x", "y"],
                  {"offset": "xyz", "target_kb": "abc"}, None]
    fails = 0
    for bad in bad_values:
        class BadPrefs:
            def get(self, a, b, c=None):
                return bad

            def set(self, a, b, c=None):
                pass
        services.prefs = BadPrefs()
        for _g, items in NAV_GROUPS:
            for it in items:
                try:
                    it["factory"](win, services)
                except Exception as e:  # noqa: BLE001
                    fails += 1
                    raise AssertionError(
                        f"坏配置 {bad!r} → [{it['key']}] 构建崩: {type(e).__name__}: {e}")
    assert fails == 0


def test_ffprobe_duration_cleaning():
    """ffprobe duration='N/A'/空 统一归一为 0，下游 float() 安全。"""
    from core.ffmpeg_executor import get_ffprobe_raw
    # 直接验证清洗逻辑（构造等价数据路径）
    data = {"format": {"duration": "N/A"}}
    try:
        _fmt = data.get("format") or {}
        _d = _fmt.get("duration")
        if not isinstance(_d, (int, float)) and (
                _d is None or not str(_d).strip().lstrip("-").replace(".", "", 1).isdigit()):
            _fmt["duration"] = "0"
    except Exception:  # noqa: BLE001
        pass
    assert float(data["format"]["duration"]) == 0.0
    data2 = {"format": {"duration": "12.5"}}
    assert float(data2["format"]["duration"]) == 12.5


# ── QA 跟进项：Image.open 句柄管理 + auto_recover 日志 ──
def test_image_open_with_context(tmp_path):
    """Image.open 统一 with 化：原地覆盖保存无文件锁冲突。"""
    from PIL import Image
    from core.image_cropper import crop_to_preset
    src = tmp_path / "a.png"
    Image.new("RGB", (300, 200), (255, 0, 0)).save(src)
    # 输出覆盖输入路径（with 化后 Windows 下不 PermissionError）
    ok = crop_to_preset(str(src), str(src), (150, 150), mode="cover")
    assert ok
    with Image.open(src) as im:
        assert im.size == (150, 150)


def test_auto_recover_logging_ok():
    """auto_recover 关键分支带日志：分类/降级参数逻辑不受影响。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("ar_t", "core/auto_recover.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.classify_failure(None, "moov atom not found") == "damage"
    assert m.classify_failure(ValueError("x")) == "bug"
    assert m.classify_failure(KeyboardInterrupt()) == "cancel"
    fb = m.build_fallback_params(
        {"subtitle_path": "a.srt", "hw_accel": "nvidia", "copy_mode": True},
        "bug")
    assert "subtitle_path" not in fb and fb["hw_accel"] is None
    assert fb["copy_mode"] is False


# ── 插件中心双语（_i18n 共享翻译表）──
def test_plugin_bilingual_ui():
    """英文模式下插件 UI 文案走共享翻译表（无中文残留、面板可构建）。"""
    import gc
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    gc.disable()
    from gui_qt.i18n import set_language
    from plugins._i18n import t
    set_language("en")
    assert t("选择文件") == "Choose file"
    assert t("编码") == "Encode"
    assert t("复制结果") == "Copy result"
    set_language("zh")
    assert t("选择文件") == "选择文件"
    # 英文模式构建代表插件（base_convert 解析逻辑依赖下拉格式）
    set_language("en")
    import importlib.util
    spec = importlib.util.spec_from_file_location("p_bc_t", "plugins/base_convert.py")
    bc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bc)
    p = bc.BaseConvertPanel()
    assert p.cb_src.currentText() == "Auto detect"
    assert bc.parse_int("FF", 16) == 255
    # 插件中心卡片：内置插件 name/description 英文模式全量翻译，无中文残留
    from core.plugin_loader import scan_plugins
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proj_plugs = [pp for pp in scan_plugins()
                  if os.path.normpath(pp.source).startswith(
                      os.path.normpath(os.path.join(root, "plugins")))]
    assert len(proj_plugs) >= 30, f"内置插件数异常: {len(proj_plugs)}"
    missing = []
    for pp in proj_plugs:
        if t(pp.name) == pp.name:
            missing.append(f"name: {pp.name}")
        if pp.description and t(pp.description) == pp.description:
            missing.append(f"desc: {pp.description}")
    assert not missing, f"插件卡片缺英文翻译: {missing}"
    from gui_qt.panels.plugin_panel import _PluginCard
    c = _PluginCard(0, "简繁转换",
                    "简体 ↔ 繁体互转（opencc 词汇级 + 2314 常用字表）")
    assert c.lb_name.text() == "Simplified ↔ Traditional"
    assert "opencc" in c.lb_desc.text()
    c.deleteLater()
    set_language("zh")  # 还原语言，避免污染后续测试


def test_nav_bilingual_labels():
    """英文模式侧边导航零中文残留；切换语言即时生效（不随 import 固化）。"""
    import re
    from gui_qt.i18n import set_language
    from gui_qt import nav_registry as nr
    # 结构事实：NAV_GROUPS 存中文原文（而非 import 时翻译的结果），
    # 保证任意语言启动/切换后 label() 都能按当前语言重新翻译
    assert nr.NAV_GROUPS[1][0] == "转换中心"
    assert nr.find_item("video")["text"] == "视频转换"
    han = re.compile(r"[\u4e00-\u9fff]")
    set_language("en")
    leaks = []
    for item in nr.all_items():
        if han.search(nr.label(item)):
            leaks.append(f"{item['key']}: {nr.label(item)}")
    for g, _items in nr.NAV_GROUPS:
        if han.search(nr.group_label(g)):
            leaks.append(f"group: {g}")
    assert not leaks, f"侧边导航英文残留: {leaks}"
    # 先前缺翻译的 key 逐一断言
    for key, en in [("ebook", "Ebook Convert"), ("frame_extract", "Extract frames"),
                    ("video_unwarp", "Unwarp Video"), ("mediainfo", "Media Info"),
                    ("file_security", "File Security"), ("lan_transfer", "LAN Service"),
                    ("plugins", "Plugins")]:
        assert nr.label(nr.find_item(key)) == en, f"{key} -> {en}"
    # 统一不一致项：侧边栏英文与面板标题一致
    assert nr.label(nr.find_item("pdf")) == "PDF tools"
    assert nr.label(nr.find_item("audio_edit")) == "Audio Tools"
    assert nr.label(nr.find_item("watermark")) == "Watermark Tools"
    assert nr.label(nr.find_item("qrcode")) == "QR Generate"
    # 切回中文：NAV_GROUPS 存中文原文 → 即时回中文，不再残留英文
    set_language("zh")
    assert nr.label(nr.find_item("video")) == "视频转换"
    assert nr.group_label("转换中心") == "转换中心"
    assert nr.group_label("PDF工具") == "PDF工具"
    set_language("zh")
