"""tool_status_card — 首页「工具状态」卡片。

展示 FFmpeg / FFprobe / yt-dlp / OCR 引擎 / 插件中心 的安装状态，
带「刷新」按钮与异步 FFmpeg 版本检测（不卡界面）。
"""
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QVBoxLayout)
from qfluentwidgets import (CaptionLabel, FluentIcon, IconWidget, PushButton)

from gui_qt.components import design_system as ds
from gui_qt.components.card import Card
from gui_qt.i18n import tr
from core import tool_check


class ToolStatusCard(Card):
    """工具状态：每项一行（名称 + 状态色点 + 详情）。"""

    # 版本获取完成信号（后台线程 → 主线程，跨线程队列调度）
    _version_ready = Signal(int, str)  # (行索引, 版本号)
    # 工具状态检查完成信号（check_tools 含 rapidocr_onnxruntime import
    # ~200ms 与插件扫描，必须后台执行避免首页构建/刷新卡顿）
    _check_ready = Signal(int, list)  # (刷新序号, 状态列表)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._version_ready.connect(self._on_version_ready)
        self._check_ready.connect(self._on_check_ready)
        self._refresh_seq = 0  # 刷新序号：丢弃过期后台结果，防连点重复
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)

        # 标题
        header = QHBoxLayout()
        header.setSpacing(8)
        self._icon = IconWidget(FluentIcon.CHECKBOX, self)
        self._icon.setFixedSize(16, 16)
        self._icon.setStyleSheet(f";")
        header.addWidget(self._icon)
        self._title = QLabel(tr("工具状态", "Tool Status"))
        self._title.setStyleSheet(
            f"font-size: 15px; font-weight: 700;"
            "border: none; background: transparent;")
        header.addWidget(self._title)
        header.addStretch(1)
        btn = PushButton(tr("刷新", "Refresh"))
        btn.clicked.connect(self.refresh)
        header.addWidget(btn)
        self.btn_check = PushButton(tr("检查更新", "Check updates"))
        self.btn_check.clicked.connect(self._check_update)
        header.addWidget(self.btn_check)
        v.addLayout(header)

        # 状态列表
        self.items_layout = QVBoxLayout()
        self.items_layout.setSpacing(6)
        v.addLayout(self.items_layout)
        v.addStretch(1)

        # 主题切换时重刷颜色（QSS 创建时写死，深色模式下不会自动变浅）
        try:
            from qfluentwidgets import qconfig
            qconfig.themeChanged.connect(self._apply_theme)
        except Exception:  # noqa: BLE001
            pass
        self.refresh()

    def refresh(self):
        # 清空旧行（_add_row 用 addLayout 添加的是 QHBoxLayout，
        # item.widget() 对 layout item 返回 None，必须递归删除其中的
        # widget，否则重复 refresh 时旧文字残留 → 显示两遍）
        self._clear_items()
        # 工具状态检查挪到后台线程：check_tools() 会 import
        # rapidocr_onnxruntime（首次加载 ONNX dll 约 200ms）并扫描插件，
        # 若在主线程同步执行会让首页构建/点击「刷新」卡顿数百 ms。
        # 完成后经 Signal 切回主线程填充行；序号丢弃过期结果防连点重复。
        self._refresh_seq += 1
        seq = self._refresh_seq
        threading.Thread(
            target=self._check_worker, args=(seq,), daemon=True).start()

    def _check_worker(self, seq):
        """后台线程：执行工具状态检查，结果经信号回主线程。"""
        try:
            items = tool_check.check_tools()
        except Exception:  # noqa: BLE001 - 检查失败时显示空列表
            items = []
        self._check_ready.emit(seq, items)

    def _on_check_ready(self, seq, items):
        """主线程：填充工具状态行；行就绪后再异步获取各工具版本。"""
        if seq != self._refresh_seq:
            return  # 过期结果（期间用户又点了刷新）直接丢弃
        for name, ok, detail in items:
            self._add_row(name, ok, detail)
        self._fetch_versions()

    def _check_update(self):
        """手动触发工具更新检测：发现新版本弹确认框，无更新提示「已是最新」。

        ToolUpdateChecker 由 app.run() 挂到主窗口 window._tool_checker，
        found 信号弹确认框、finished 信号提示已是最新（都在主线程）。
        点击后立即禁用按钮显示「检查中…」，检查完成（found/finished）
        恢复按钮——否则国内网络下最长 ~10s 内按钮无任何反馈。
        """
        from gui_qt.components import toast
        checker = getattr(self.window(), "_tool_checker", None)
        if checker is None:
            return
        if checker.is_running():
            toast.show_info(self, tr("正在检查中，请稍候", "Checking in progress..."))
            return
        # 立即反馈：禁用按钮 + 文案变化，完成后恢复
        self.btn_check.setEnabled(False)
        self.btn_check.setText(tr("检查中…", "Checking…"))

        def _done(*_args):
            self.btn_check.setEnabled(True)
            self.btn_check.setText(tr("检查更新", "Check updates"))
            try:
                checker.finished.disconnect(_done)
                checker.found.disconnect(_done)
            except Exception:  # noqa: BLE001 - 重复断开忽略
                pass

        checker.finished.connect(_done)
        checker.found.connect(_done)
        checker.check_async(notify=True)

    def _clear_items(self):
        """递归清空状态列表中的所有 item（widget 与嵌套 layout）。"""
        while self.items_layout.count():
            self._clear_item(self.items_layout.takeAt(0))

    def _clear_item(self, item):
        """递归删除单个 QLayoutItem：widget 直接 deleteLater，layout 递归。"""
        if item is None:
            return
        w = item.widget()
        if w is not None:
            w.deleteLater()
            return
        lay = item.layout()
        if lay is not None:
            while lay.count():
                self._clear_item(lay.takeAt(0))
            lay.deleteLater()

    def _add_row(self, name, ok, detail):
        row = QHBoxLayout()
        row.setSpacing(8)
        color = ds.tokens()["success"] if ok else ds.tokens()["error"]
        dot = QLabel("●")
        dot.setStyleSheet(
            f"color: {color};"
            "font-size: 11px; border: none; background: transparent;")
        row.addWidget(dot)
        name_label = QLabel(name)
        name_label.setStyleSheet(
            f"font-size: 13px;"
            "border: none; background: transparent;")
        row.addWidget(name_label)
        row.addStretch(1)
        detail_label = QLabel(detail)
        detail_label._ok = ok   # 记住状态，供主题切换时重算颜色
        detail_label.setStyleSheet(
            f"font-size: 12px; color: {color}; font-weight: 600;"
            "border: none; background: transparent;")
        row.addWidget(detail_label)
        self.items_layout.addLayout(row)

    def _apply_theme(self, *args):
        """主题切换后重刷标题与每行颜色（深色模式下文字保持可读）。

        *args：qfluentwidgets 的 themeChanged 信号会带 Theme 参数，兼容之。
        """
        try:
            self._icon.setStyleSheet(f";")
            self._title.setStyleSheet(
                f"font-size: 15px; font-weight: 700;"
                "border: none; background: transparent;")
            for i in range(self.items_layout.count()):
                item = self.items_layout.itemAt(i)
                lay = item.layout() if item is not None else None
                if lay is None or lay.count() < 4:
                    continue
                ok = getattr(lay.itemAt(3).widget(), "_ok", True)
                color = ds.tokens()["success"] if ok else ds.tokens()["error"]
                lay.itemAt(0).widget().setStyleSheet(
                    f"color: {color};"
                    "font-size: 11px; border: none; background: transparent;")
                lay.itemAt(1).widget().setStyleSheet(
                    f"font-size: 13px;"
                    "border: none; background: transparent;")
                lay.itemAt(3).widget().setStyleSheet(
                    f"font-size: 12px; color: {color}; font-weight: 600;"
                    "border: none; background: transparent;")
        except Exception:  # noqa: BLE001
            pass

    def _fetch_versions(self):
        """后台线程异步获取各工具版本，成功后更新对应行详情。

        行索引与 check_tools() 返回顺序一致：0=FFmpeg / 1=FFprobe /
        2=yt-dlp / 3=OCR；第 4 行「插件中心」显示数量、无版本号。
        """
        tasks = [
            (0, tool_check.ffmpeg_version),
            (1, tool_check.ffprobe_version),
            (2, tool_check.ytdlp_version),
            (3, tool_check.ocr_version),
        ]
        for idx, fn in tasks:
            threading.Thread(
                target=self._fetch_version_worker, args=(idx, fn),
                daemon=True).start()

    def _fetch_version_worker(self, idx, fn):
        """单个工具版本获取（后台线程）：成功后经信号切回主线程更新。"""
        try:
            ver = fn()
        except Exception:  # noqa: BLE001 - 版本获取失败保持原状态文字
            ver = None
        if not ver:
            return
        # Signal.emit 跨线程安全：Qt 自动队列调度到主线程执行槽
        self._version_ready.emit(idx, ver)

    def _on_version_ready(self, idx, ver):
        """主线程：更新对应行的详情为版本号。"""
        try:
            if 0 <= idx < self.items_layout.count():
                row = self.items_layout.itemAt(idx)
                if row is not None and row.layout() is not None:
                    detail = row.layout().itemAt(3).widget()
                    detail.setText(ver)
        except Exception:  # noqa: BLE001
            pass
