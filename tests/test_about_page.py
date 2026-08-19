"""冒烟测试：设置页关于分区三段式（Hero + 双栏 + 底部 GitHub 按钮）。"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="module")
def prefs_file():
    """隔离 user_prefs.json，避免污染真实偏好。"""
    fp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    fp.close()
    # 把全局 USER_PREFS_FILE 指向临时文件
    import utils.config as _cfg
    _orig = getattr(_cfg, "USER_PREFS_FILE", None)
    _cfg.USER_PREFS_FILE = fp.name
    yield fp.name
    _cfg.USER_PREFS_FILE = _orig


class TestAboutPage:
    def _mk_services(self):
        from gui_qt.components.theme_manager import ThemeManager
        from gui_qt.services import QtServices
        services = QtServices()
        services.theme_mgr = ThemeManager(services)
        return services

    def _mk_page(self, qapp, prefs_file):
        from gui_qt.pages.settings_page import SettingsPage
        services = self._mk_services()
        class _W:
            pass
        sp = SettingsPage(_W(), services)
        sp.show()
        qapp.processEvents()
        # 设置页分区懒构建：about 卡片默认不建，这里按导航路径触发构建，
        # 供本文件其余用例检查关于分区内容（hero + 双栏 + GitHub 按钮）
        try:
            sp._on_nav_changed(sp._section_order.index("about"))
            qapp.processEvents()
        except Exception:  # noqa: BLE001
            pass
        return sp

    def test_settings_page_builds(self, qapp, prefs_file):
        """设置页整体构建不应抛错。"""
        sp = self._mk_page(qapp, prefs_file)
        sections = list(sp._sections.keys())
        assert "about" in sections, f"about section missing in {sections}"

    def test_about_section_has_sections(self, qapp, prefs_file):
        """about 分区应有对应的 page widget（含 hero + 双栏 + 底部）。"""
        sp = self._mk_page(qapp, prefs_file)
        _item, scroll = sp._sections["about"]
        page_widget = scroll.widget()
        assert page_widget is not None
        # 至少包含一个 Hero 卡片
        from gui_qt.components.card import Card
        cards = page_widget.findChildren(Card, options=Qt.FindDirectChildrenOnly) \
            if False else page_widget.findChildren(Card)
        # 至少 4 张卡片（hero + 关于左 + 更新右 + footer）
        assert len(cards) >= 4, f"expected ≥4 cards, got {len(cards)}"

    def test_fm_logo_pixmap_renders(self, qapp, prefs_file):
        """FM 徽标自绘应返回非空 QPixmap。"""
        from PySide6.QtGui import QPixmap
        sp = self._mk_page(qapp, prefs_file)
        pm = sp._fm_logo_pixmap(80)
        assert isinstance(pm, QPixmap)
        assert not pm.isNull()
        assert pm.width() > 0 and pm.height() > 0

    def test_github_button_single(self, qapp, prefs_file):
        """底部页脚只应有一个 GitHub 按钮（按 tooltip 文本识别）。

        v4 起 footer 改用 `_colored_icon` 自绘的 QWidget（不再用 ToolButton），
        改为兼容：所有含「GitHub」tooltip 的 QWidget 都视为 GitHub 按钮。
        """
        from PySide6.QtWidgets import QWidget
        sp = self._mk_page(qapp, prefs_file)
        github_btns = [
            w for w in sp.findChildren(QWidget)
            if "GitHub" in (w.toolTip() or "")
        ]
        assert len(github_btns) == 1, (
            f"expected 1 GitHub button, got {len(github_btns)}")
        b = github_btns[0]
        assert b.width() == 36 and b.height() == 36

    def test_about_check_button_works(self, qapp, prefs_file):
        """检查更新按钮应在（_build_about 后被赋值给 self.btn_check）。"""
        sp = self._mk_page(qapp, prefs_file)
        assert hasattr(sp, "btn_check")
        assert sp.btn_check is not None
        assert sp.btn_check.isEnabled()

    def test_paint_event_no_nameerror(self, qapp, prefs_file):
        """强制触发自绘控件 paintEvent，不应抛 NameError（内嵌类漏 import Qt 类型）。

        回归：`_make_about_feature._IconPainter.paintEvent` 用了 `QColor`，但
        局部 `from PySide6.QtGui import QFont, QPainter, QImage` 漏了 `QColor`，
        内嵌类的方法找不到名字，paint 时报 `name 'QColor' is not defined`。

        Qt 在调用 Python override 失败时把异常吞掉、向 qtCategoryMessage
        输出 `Error calling Python override of XXX::paintEvent(): ...`，
        走 C++ stderr，不走 Python sys.stderr。需 `qInstallMessageHandler`
        拦截，再对每个内嵌自绘 widget 调 `render(p, QPoint)` 强制 paint。
        """
        from PySide6.QtGui import QPixmap, QPainter
        from PySide6.QtCore import Qt, QPoint, qInstallMessageHandler

        captured = []

        def _handler(msg_type, context, message):
            captured.append(str(message))

        qInstallMessageHandler(_handler)
        try:
            sp = self._mk_page(qapp, prefs_file)
            sp.pivot.setCurrentRow(list(sp._sections.keys()).index("about"))
            qapp.processEvents()
            _item, scroll = sp._sections["about"]
            page = scroll.widget()
            outer = page.layout().itemAt(0).widget()
            outer.setFixedWidth(950)
            qapp.processEvents()

            # 对每个内嵌自绘 widget 调 render() 强制 paint
            from PySide6.QtWidgets import QWidget
            for w in outer.findChildren(QWidget):
                cls = type(w).__name__
                if cls not in ("_IconPainter", "_Hero3D", "_Shield"):
                    continue
                pm = QPixmap(max(1, w.width()), max(1, w.height()))
                pm.fill(Qt.transparent)
                p = QPainter(pm)
                try:
                    w.render(p, QPoint(0, 0))
                finally:
                    p.end()
        finally:
            qInstallMessageHandler(None)

        joined = "\n".join(captured)
        assert "NameError" not in joined, (
            "paintEvent 抛 NameError：\n" + joined[:1500])

    def test_contact_email_present(self, qapp, prefs_file):
        """联系作者邮箱 gujh0312@outlook.com 应出现在 about 分区。"""
        from PySide6.QtWidgets import QLabel
        sp = self._mk_page(qapp, prefs_file)
        _item, scroll = sp._sections["about"]
        page = scroll.widget()
        outer = page.layout().itemAt(0).widget()
        # 收集所有 label 文本，找含 gujh0312@outlook.com 的那个
        all_text = "\n".join(
            lbl.text() for lbl in outer.findChildren(QLabel)
            if lbl.text()
        )
        assert "gujh0312@outlook.com" in all_text, (
            f"未找到联系作者邮箱，所有 label 文本：\n{all_text}")

    def test_right_column_three_cards(self, qapp, prefs_file):
        """右栏应堆叠 3 张卡（更新与支持 + 项目生态 + 隐私与安全）。"""
        from gui_qt.components.card import Card
        from PySide6.QtWidgets import QLabel
        sp = self._mk_page(qapp, prefs_file)
        _item, scroll = sp._sections["about"]
        page = scroll.widget()
        outer = page.layout().itemAt(0).widget()
        # 收集 outer 的顶层卡片（外层 QVBoxLayout hero + 两个 QHBoxLayout 子项）
        # 实际嵌套：outer = QVBoxLayout(hero, two_col, footer)
        # two_col = QHBoxLayout(left_card, right_w with 3 cards)
        # 直接 count Card 数量：1 hero + 1 left + 3 right + 1 footer = 6
        cards = outer.findChildren(Card)
        assert len(cards) >= 6, (
            f"右栏应有 3 张卡 + 其他应有 3 张（hero/left/footer）= 6+，"
            f"实际 {len(cards)}")
        # 检查 3 个标题
        titles = []
        for lbl in outer.findChildren(QLabel):
            t = lbl.text()
            if t in ("更新与支持", "项目生态", "隐私与安全",
                    "Updates & Support", "Ecosystem", "Privacy & Security"):
                titles.append(t)
        assert len(titles) >= 3, (
            f"右栏应包含「更新与支持」「项目生态」「隐私与安全」三个标题，"
            f"实际：{titles}")


from PySide6.QtCore import Qt  # noqa: E402