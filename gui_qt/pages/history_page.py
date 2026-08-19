"""history_page — 转换历史（Prism 设计系统）。

搜索 + 筛选 + 统计概览：顶部统计卡（总数/成功/失败/今日），
工具栏含搜索框、类型与结果筛选，表格展示记录。
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView,
                               QVBoxLayout, QWidget)
from qfluentwidgets import (CaptionLabel, ComboBox, FluentIcon, LineEdit,
                            PillPushButton, PushButton, ScrollArea, TableView)

from gui_qt.components import toast
from gui_qt.components import design_system as ds
from gui_qt.components.card import Card
from gui_qt.components.empty_state import EmptyState
from gui_qt.i18n import tr
from gui_qt.components.page_header import PageHeader

_COLS = ["时间", tr("类型", "Type"), "源文件", tr("输出文件", "Output file"), "结果"]
_RESULTS = [tr("全部", "All"), tr("成功", "Success"), tr("失败", "Failed")]

# 当前导航中仍存在的功能类型白名单：历史记录里已删除功能的旧类型
# （如 LUT 调色、语音转字幕）不再显示在筛选下拉中。新增功能在此登记。
_ACTIVE_TYPES = {
    # 转换中心
    tr("视频转换", "Video Convert"), tr("音频转换", "Audio Convert"),
    tr("图片转换", "Image Convert"), tr("文档转换", "Doc Convert"),
    tr("GIF 转换", "GIF Convert"), tr("场景化转换", "Scene Convert"),
    tr("图像裁剪", "Image Crop"), tr("视频转 GIF", "Video to GIF"),
    tr("场景化处理", "Scene Process"),
    # PDF
    tr("PDF 处理", "PDF Tools"), tr("PDF 编辑", "PDF Edit"),
    # 视频工具
    tr("封面裁剪", "Cover Crop"), tr("视频处理", "Video Tools"),
    tr("视频压缩", "Video Compress"), tr("视频抽帧", "Frame Extract"),
    tr("字幕提取", "Subtitle"), tr("视频反挤压", "Unwarp"),
    # 音频工具
    tr("音频处理", "Audio Tools"), tr("音频增强", "Audio Enhance"),
    tr("音频裁剪", "Audio Cut"),
    # 图片工具
    tr("图片压缩", "Image Compress"), tr("图片水印", "Image Watermark"),
    tr("证件照换底色", "ID Photo"), tr("图片拼接", "Image Merge"),
    # 识别工具
    tr("OCR 识别", "OCR"), tr("表格识别", "Table OCR"),
    # 实用工具
    tr("视频缩略图", "Video Thumbnails"), tr("哈希校验", "Hash Check"),
    tr("文件夹监视", "Folder Watch"), tr("文件安全", "File Security"),
    # 网络下载
    tr("视频下载", "Video Download"), tr("M3U8 下载", "M3U8 Download"),
}


class _StatChip(Card):
    """顶部统计小卡片：数值 + 标题。"""

    def __init__(self, title, accent, parent=None):
        super().__init__(parent, radius=12)
        self.setMinimumHeight(64)
        from PySide6.QtWidgets import QVBoxLayout
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 10, 16, 10)
        v.setSpacing(2)
        self.value_label = CaptionLabel("0", self)
        self.value_label.setStyleSheet(
            f"font-size: 20px; font-weight: 700; color: {accent};"
            "border: none; background: transparent;")
        v.addWidget(self.value_label)
        self.title_label = CaptionLabel(title, self)
        self.title_label.setStyleSheet(
            f"font-size: 11px;"
            "border: none; background: transparent;")
        v.addWidget(self.title_label)

    def set_value(self, v):
        self.value_label.setText(str(v))


class HistoryPage(ScrollArea):
    """转换历史页：搜索 + 筛选 + 统计。"""

    def __init__(self, window, services, parent=None):
        super().__init__(parent)
        self.setObjectName("history")
        self.main_window = window
        self.services = services
        self._all_records = []
        self.setWidgetResizable(True)
        self.setViewportMargins(0, 0, 0, 0)

        content = QWidget()
        v = QVBoxLayout(content)
        v.setContentsMargins(24, 20, 24, 24)
        v.setSpacing(14)
        self.setWidget(content)
        content.setAutoFillBackground(False)

        # ── 页面标题 ───────────────────────────────
        v.addWidget(PageHeader(
            tr("转换历史", "History"), tr("搜索、筛选并统计所有转换记录", "Search, filter and summarize all records"),
            icon=FluentIcon.HISTORY))

        # ── 统计概览 ───────────────────────────────
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self.stat_total = _StatChip(tr("累计转换", "Total conversions"), ds.accent())
        self.stat_ok = _StatChip(tr("成功", "Success"), ds.tokens()["success"])
        self.stat_fail = _StatChip(tr("失败", "Failed"), ds.tokens()["error"])
        self.stat_today = _StatChip(tr("今日转换", "Today"), ds.tokens()["warn"])
        for c in (self.stat_total, self.stat_ok, self.stat_fail,
                  self.stat_today):
            stats_row.addWidget(c, 1)
        v.addLayout(stats_row)

        # ── 图表区：近 14 天趋势 + 类型分布 ──────────
        from gui_qt.components.visual_widgets import TrendChart, TypeChart
        charts_row = QHBoxLayout()
        charts_row.setSpacing(12)
        self.chart_trend = TrendChart()
        self.chart_type = TypeChart()
        for c in (self.chart_trend, self.chart_type):
            c.setFixedHeight(160)
            charts_row.addWidget(c, 1)
        v.addLayout(charts_row)

        # ── 工具栏（搜索 + 筛选）──────────────────
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.search_edit = LineEdit(self)
        self.search_edit.setPlaceholderText(tr("搜索文件名 / 类型…", "Search name / type…"))
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._refresh)
        toolbar.addWidget(self.search_edit, 1)

        self.type_combo = ComboBox(self)
        self.type_combo.addItem(tr("全部类型", "All types"))
        self.type_combo.currentTextChanged.connect(self._refresh)
        toolbar.addWidget(self.type_combo)

        # 结果筛选 → PillPushButton 标签组（全部/成功/失败）
        self._result_val = tr("全部", "All")
        self.result_pills = []
        for label in _RESULTS:
            pill = PillPushButton(label, self)
            pill.setCheckable(True)
            pill.clicked.connect(
                lambda _=False, lab=label: self._on_result_pill(lab))
            toolbar.addWidget(pill)
            self.result_pills.append(pill)
        self.result_pills[0].setChecked(True)

        self.count_label = CaptionLabel("")
        self.count_label.setStyleSheet(
            f"font-size: 12px;")
        toolbar.addWidget(self.count_label)

        # 数据大屏（ECharts 交互图表，QtWebEngine 渲染）
        self.btn_dashboard = PushButton(FluentIcon.PIE_SINGLE,
                                        tr("数据大屏", "Dashboard"))
        self.btn_dashboard.setToolTip(
            tr("近 30 天转换趋势与类型分布（交互图表）",
               "30-day trend & type distribution (interactive)"))
        self.btn_dashboard.clicked.connect(self._open_dashboard)
        toolbar.addWidget(self.btn_dashboard)

        self.btn_clear = PushButton(FluentIcon.DELETE, tr("清空历史", "Clear history"))
        self.btn_clear.clicked.connect(self._clear)
        toolbar.addWidget(self.btn_clear)
        v.addLayout(toolbar)

        # ── 空态 ───────────────────────────────────
        self.empty_widget = QWidget()
        self.empty_widget.setLayout(EmptyState(
            icon=FluentIcon.HISTORY, title=tr("暂无转换记录", "No conversion records"),
            desc=tr("完成一次转换后，记录将在此显示", "Records will appear here after a conversion"),
            btn_text=tr("前往视频转换", "Go to Video Convert"),
            btn_clicked=lambda: self._goto("video")))
        v.addWidget(self.empty_widget, 1)

        # ── 表格（qfw TableView + 排序模型）────────
        self._model = QStandardItemModel(0, len(_COLS))
        self._model.setHorizontalHeaderLabels(_COLS)
        self.table = TableView(self)
        self.table.setModel(self._model)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.verticalHeader().setVisible(False)
        # 点击表头排序（QStandardItemModel 内置 sort）
        self.table.setSortingEnabled(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        v.addWidget(self.table, 1)

        self._load_types()
        self._refresh()

    def _on_result_pill(self, label):
        """Pill 互斥：只保留当前选中的高亮，并刷新。"""
        for pill in self.result_pills:
            pill.setChecked(pill.text() == label)
        self._result_val = label
        self._refresh()

    def _load_types(self):
        """从历史记录收集类型填充筛选下拉，仅保留当前仍存在的功能。"""
        seen = []
        for r in self.services.history.get_all():
            t = r.get("type", "")
            if t and t not in seen and t in _ACTIVE_TYPES:
                seen.append(t)
        self.type_combo.blockSignals(True)
        self.type_combo.clear()
        self.type_combo.addItem(tr("全部类型", "All types"))
        self.type_combo.addItems(seen)
        self.type_combo.blockSignals(False)

    def _filtered(self):
        """按搜索词 + 类型 + 结果筛选记录。"""
        kw = self.search_edit.text().strip().lower()
        type_f = self.type_combo.currentText()
        result_f = self._result_val
        out = []
        for r in self._all_records:
            if kw:
                src = str(r.get("source", "")).lower()
                typ = str(r.get("type", "")).lower()
                tgt = str(r.get("target", "")).lower()
                if kw not in src and kw not in typ and kw not in tgt:
                    continue
            if type_f != tr("全部类型", "All types") and r.get("type") != type_f:
                continue
            if result_f == tr("成功", "Success") and r.get("status") != "success":
                continue
            if result_f == tr("失败", "Failed") and r.get("status") == "success":
                continue
            out.append(r)
        return out

    def _refresh(self):
        records = self.services.history.get_all()
        self._all_records = records
        self._update_stats(records)
        filtered = self._filtered()

        # 排序状态下清空会丢失排序状态：先禁用排序再重建
        self.table.setSortingEnabled(False)
        self._model.removeRows(0, self._model.rowCount())
        for r in filtered:
            status = tr("成功", "Success") if r.get("status") == "success" else tr("失败", "Failed")
            out_name = os.path.basename(str(r.get("output_path", "")))
            tgt = out_name or r.get("target", "")
            values = [r.get("time", ""), r.get("type", ""),
                      r.get("source", ""), tgt, status]
            items = []
            for c, val in enumerate(values):
                item = QStandardItem(str(val))
                item.setEditable(False)
                if c == 4:
                    t = ds.tokens()
                    fg = t["success"] if status == tr("成功", "Success") else t["error"]
                    item.setForeground(QColor(fg))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                elif c == 0:
                    item.setForeground(QColor(ds.ink_sec()))
                items.append(item)
            self._model.appendRow(items)
        self.table.setSortingEnabled(True)

        shown = len(filtered)
        total = len(records)
        self.count_label.setText(
            tr("共 {} 条", "{} records").format(total) + (tr("（筛选 {}）", " (filtered {})").format(shown) if shown != total else ""))
        has = total > 0
        self.empty_widget.setVisible(not has)
        self.table.setVisible(has)

    def _update_stats(self, records):
        ok = sum(1 for r in records if r.get("status") == "success")
        fail = len(records) - ok
        today = __import__("datetime").date.today().isoformat()
        today_n = sum(1 for r in records
                      if str(r.get("time", ""))[:10] == today)
        self.stat_total.set_value(len(records))
        self.stat_ok.set_value(ok)
        self.stat_fail.set_value(fail)
        self.stat_today.set_value(today_n)
        self._update_charts(records)

    def _update_charts(self, records):
        """刷新趋势图（近 14 天）与类型分布图。"""
        import datetime as _dt
        from collections import Counter
        days, ok_c, fail_c = [], [], []
        today = _dt.date.today()
        ok_counter, fail_counter = Counter(), Counter()
        for r in records:
            ds_ = str(r.get("time", ""))[:10]
            if r.get("status") == "success":
                ok_counter[ds_] += 1
            else:
                fail_counter[ds_] += 1
        for i in range(13, -1, -1):
            d = (today - _dt.timedelta(days=i)).isoformat()
            days.append(d[5:])
            ok_c.append(ok_counter.get(d, 0))
            fail_c.append(fail_counter.get(d, 0))
        self.chart_trend.set_data(days, ok_c, fail_c)
        type_counter = Counter(str(r.get("type", "未知")) for r in records)
        self.chart_type.set_data(type_counter.most_common(7))

    def _open_dashboard(self):
        """ECharts 交互数据大屏：近 30 天趋势 + 类型分布。"""
        from collections import Counter
        import datetime as _dt
        records = self.services.history.get_all()
        if not records:
            from gui_qt.components import toast
            toast.show_info(self, tr("暂无转换记录", "No conversion records"))
            return
        today = _dt.date.today()
        ok_c, fail_c = Counter(), Counter()
        type_c = Counter(str(r.get("type", "未知")) for r in records)
        for r in records:
            d = str(r.get("time", ""))[:10]
            if r.get("status") == "success":
                ok_c[d] += 1
            else:
                fail_c[d] += 1
        days, ok_l, fail_l = [], [], []
        for i in range(29, -1, -1):
            d = (today - _dt.timedelta(days=i)).isoformat()
            days.append(d[5:])
            ok_l.append(ok_c.get(d, 0))
            fail_l.append(fail_c.get(d, 0))
        types, counts = [], []
        for t, c in type_c.most_common(7):
            types.append(t)
            counts.append(c)
        from gui_qt.components.echarts_view import EchartsStatsDialog
        dlg = EchartsStatsDialog(self.window())
        if not dlg.available():
            from gui_qt.components import toast
            toast.show_warning(self, tr("数据大屏不可用", "Dashboard unavailable"))
            dlg.deleteLater()
            return
        dlg.set_data(days, ok_l, fail_l, types, counts)
        dlg.exec()

    def _clear(self):
        if self._model.rowCount() == 0:
            return
        # 危险操作二次确认（qfw MessageBox：yesButton.clicked 在 accept 前同步触发）
        from qfluentwidgets import MessageBox
        box = MessageBox(
            tr("清空历史记录？", "Clear all history?"),
            tr("将删除全部转换记录，此操作不可撤销。",
               "This deletes all records and cannot be undone."),
            self)
        box.yesButton.setText(tr("清空", "Clear"))
        box.cancelButton.setText(tr("取消", "Cancel"))
        box.yesButton.clicked.connect(self._do_clear)
        box.exec()

    def _do_clear(self):
        self.services.history.clear()
        self._load_types()
        self._refresh()
        toast.show_success(self, tr("历史记录已清空", "History cleared"))

    def _goto(self, nav_key):
        pages = getattr(self.main_window, "pages", {})
        page = pages.get(nav_key)
        if page is not None:
            self.main_window.switchTo(page)

    def showEvent(self, e):
        self._load_types()
        self._refresh()
        super().showEvent(e)
