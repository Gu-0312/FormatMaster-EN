"""home_page — 首页 Dashboard（按参考截图「首页截图.png」重做）。

布局（自下而上与截图一致）：
  通栏：欢迎语 + 副标题
  统计卡 ×4：今日转换文件 / 节省空间 / 成功率 / 累计运行（各带「较昨日」变化）
  快速功能行：8 个图标入口
  双栏主区：
    左栏（约 7/10）：最近任务表格 + 公告通知
    右栏（约 3/10）：系统信息 + 新手指南
"""
from gui_qt.i18n import tr
import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QVBoxLayout,
                               QWidget)
from qfluentwidgets import (FluentIcon, ScrollArea)

from gui_qt.components import design_system as ds
from gui_qt.components.stat_card_new import StatCard
from gui_qt.components.quick_function_row import QuickFunctionRow
from gui_qt.components.recent_tasks_table import RecentTasksTable
from gui_qt.components.tool_status_card import ToolStatusCard
from gui_qt.components.system_info_card import SystemInfoCard
from gui_qt.components.open_source_card import OpenSourceCard


def _fmt_bytes(n):
    """字节数 → 可读文本（B / KB / MB / GB）。"""
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{n / 1024 ** 3:.1f} GB"


class HomePage(QWidget):
    """首页 Dashboard（按参考截图设计）。"""

    def __init__(self, window, services, parent=None):
        super().__init__(parent)
        self.main_window = window
        self.services = services
        self.stats = services.stats

        self.scroll = ScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.inner = QWidget()
        v = QVBoxLayout(self.inner)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(16)

        self._build_welcome(v)
        self._build_stats(v)
        self._build_quick_functions(v)
        self._build_main_split(v)
        v.addStretch(1)

        self.scroll.setWidget(self.inner)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll)

        self._refresh_all()

    # ── 1. 欢迎区（Hero 渐变横幅） ───────────────
    def _build_welcome(self, v):
        from gui_qt.components.design_system import HeroBanner
        self.hero = HeroBanner(
            self._greeting(),
            tr("专业、强大、易用的格式转换工具 —— 视频 / 音频 / 图片 / 文档一站式处理", "Professional format converter — Video / Audio / Image / Document"),
            self)
        v.addWidget(self.hero)

    def _greeting(self):
        hour = datetime.datetime.now().hour
        if hour < 6:
            return tr("你好，夜深了也别忘了保存工作",
                      "Hi, late night — remember to save your work")
        if hour < 12:
            return tr("你好，欢迎使用格式大师！",
                      "Hi, welcome to FormatMaster!")
        if hour < 14:
            return tr("你好，午间时光也要高效工作",
                      "Hi, productive afternoon ahead")
        if hour < 18:
            return tr("你好，下午好！欢迎使用格式大师",
                      "Good afternoon, welcome to FormatMaster")
        return tr("你好，晚上好！欢迎使用格式大师",
                  "Good evening, welcome to FormatMaster")

    # ── 2. 统计卡 ×4 ─────────────────────────────
    def _build_stats(self, v):
        grid_w = QWidget()
        grid_w.setStyleSheet("background: transparent;")
        grid = QGridLayout(grid_w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)

        self.stat_today = StatCard(
            tr("今日转换文件", "Files converted today"), tr("0 个", "0 items"), tr("较昨日 +0%", "vs yesterday +0%"),
            "#5B5BD6", FluentIcon.PLAY)
        self.stat_saved = StatCard(
            tr("节省空间", "Space saved"), "--", tr("较昨日 +0%", "vs yesterday +0%"),
            "#2FC99A", FluentIcon.LIBRARY)
        self.stat_rate = StatCard(
            tr("成功率", "Success rate"), "--", tr("较昨日 +0%", "vs yesterday +0%"),
            "#F0A63A", FluentIcon.ACCEPT)
        self.stat_uptime = StatCard(
            tr("累计运行", "Total uptime"), tr("0 秒", "0 sec"), tr("较昨日 +0分钟", "vs yesterday +0 min"),
            "#EC4899", FluentIcon.STOP_WATCH)

        for i, c in enumerate([self.stat_today, self.stat_saved,
                               self.stat_rate, self.stat_uptime]):
            grid.addWidget(c, 0, i)
            grid.setColumnStretch(i, 1)
        v.addWidget(grid_w)

    # ── 3. 快速功能行 ────────────────────────────
    def _build_quick_functions(self, v):
        self.quick_fns = QuickFunctionRow()
        self.quick_fns.connect_nav(self._nav_to)
        v.addWidget(self.quick_fns)

    # ── 4. 双栏主区 ──────────────────────────────
    def _build_main_split(self, v):
        split = QWidget()
        split.setStyleSheet("background: transparent;")
        h = QHBoxLayout(split)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(16)

        # 左栏：最近任务 + 更新日志
        left = QWidget()
        left.setStyleSheet("background: transparent;")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(16)

        self.recent_tasks = RecentTasksTable()
        self.recent_tasks.btn_history.clicked.connect(
            lambda: self._nav_to("history"))
        self.recent_tasks.btn_clear.clicked.connect(self._clear_tasks)
        lv.addWidget(self.recent_tasks, 1)
        self._wire_task_badge()

        self.tool_status = ToolStatusCard()
        lv.addWidget(self.tool_status)
        h.addWidget(left, 7)

        # 右栏：系统信息 + 开源项目
        right = QWidget()
        right.setStyleSheet("background: transparent;")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(16)

        self.sysinfo = SystemInfoCard()
        rv.addWidget(self.sysinfo)

        self.open_source = OpenSourceCard()
        rv.addWidget(self.open_source)
        rv.addStretch(1)
        h.addWidget(right, 3)

        v.addWidget(split)

    def _nav_to(self, key):
        page = self.main_window.pages.get(key)
        if page:
            self.main_window.switchTo(page)

    # ── 首页「最近任务」进行中数徽章（InfoBadge）──
    def _wire_task_badge(self):
        """连接 TaskManager 状态信号 → 实时刷新徽章。"""
        try:
            mgr = self.services.task_manager
            mgr.sig_state.connect(self._refresh_active_badge)
            self._refresh_active_badge()
        except Exception:  # noqa: BLE001 - 徽章接线失败不影响首页
            pass

    def _refresh_active_badge(self, *args):
        """进行中任务数（等待/运行/暂停），0 时隐藏徽章。"""
        try:
            n = 0
            for task in self.services.task_manager.all_tasks():
                if task.state in ("waiting", "running", "paused"):
                    n += 1
            self.recent_tasks.badge_active.setText(str(n))
            self.recent_tasks.badge_active.setVisible(n > 0)
        except Exception:  # noqa: BLE001 - 徽章刷新失败不影响首页
            pass

    def _clear_tasks(self):
        try:
            for task in list(self.services.task_manager.all_tasks()):
                if task.state in ("success", "failed", "cancelled"):
                    del self.services.task_manager._tasks[task.task_id]
            self._refresh_tasks()
        except Exception:
            pass

    # ── 数据刷新 ─────────────────────────────────
    def _refresh_all(self):
        self._refresh_stats()
        self._refresh_tasks()

    def _refresh_stats(self):
        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)

        def _day_count(day):
            """返回 (总数, 成功数)。"""
            total = ok = 0
            if self.stats:
                d = self.stats.get_range(day, day)
                for recs in d.values():
                    for rec in recs:
                        total += 1
                        if rec.get("status") == "success":
                            ok += 1
            return total, ok

        t_total, t_ok = _day_count(today.isoformat())
        y_total, y_ok = _day_count(yesterday.isoformat())

        # 今日转换文件（较昨日：昨日为 0 用绝对值，否则用百分比）
        self.stat_today.set_value(tr("{} 个", "{} items").format(t_total))
        if y_total <= 0:
            if t_total > 0:
                self.stat_today.set_delta(
                    tr("较昨日 +{} 个", "vs yesterday +{} items").format(t_total))
            else:
                self.stat_today.set_delta(tr("与昨日持平", "same as yesterday"))
        else:
            pct = (t_total - y_total) / y_total * 100
            self.stat_today.set_delta(
                tr("较昨日 {:+.0f}%", "vs yesterday {:+.0f}%").format(pct))

        # 节省空间（历史记录 saved_bytes 累计，源文件 - 输出文件）
        total_saved = 0
        today_saved = 0
        yesterday_saved = 0
        try:
            for r in self.services.history.get_all():
                saved = int(r.get("saved_bytes", 0) or 0)
                total_saved += saved
                day = str(r.get("time", ""))[:10]
                if day == today.isoformat():
                    today_saved += saved
                elif day == yesterday.isoformat():
                    yesterday_saved += saved
        except Exception:
            pass
        self.stat_saved.set_value(_fmt_bytes(total_saved))
        if total_saved <= 0:
            self.stat_saved.set_delta("--")
        elif today_saved > 0:
            self.stat_saved.set_delta(
                tr("今日 +{}", "today +{}").format(_fmt_bytes(today_saved)))
        else:
            self.stat_saved.set_delta(
                tr("较昨日 {}", "vs yesterday {}").format(
                    _fmt_bytes(max(0, today_saved - yesterday_saved))))

        # 成功率（较昨日：百分点差）
        t_rate = t_ok / t_total * 100 if t_total else None
        y_rate = y_ok / y_total * 100 if y_total else None
        self.stat_rate.set_value(
            f"{t_rate:.1f} %" if t_rate is not None else "--")
        if t_rate is None or y_rate is None:
            self.stat_rate.set_delta("--")
        else:
            diff = t_rate - y_rate
            self.stat_rate.set_delta(
                tr("较昨日 {:+.1f} 个百分点", "vs yesterday {:+.1f} pt").format(diff))

        # 累计运行（本次会话时长）
        try:
            self.stat_uptime.set_value(self.services.uptime_str())
        except Exception:
            pass
        self.stat_uptime.set_delta(tr("本次运行", "this session"))

    def _refresh_tasks(self):
        try:
            tasks = self.services.task_manager.all_tasks()[:6]
        except Exception:
            tasks = []
        self.recent_tasks.set_tasks(tasks)

    def showEvent(self, e):
        self._refresh_all()
        # 系统信息采集（PowerShell 子进程 1~3 秒）首次延迟到预热窗口之后：
        # 启动早期 prewarm 会在主线程 import pymupdf（pdf_editor 页），其 GC
        # 回收 C 扩展对象与后台 subprocess 读取线程并发时曾触发 access violation
        # （PyMuPDF GC 竞态）。错开 4 秒后，pymupdf 已完成加载与缓存，风险消除。
        if not getattr(self, "_sysinfo_refreshed", False):
            self._sysinfo_refreshed = True
            try:
                from PySide6.QtCore import QTimer
                QTimer.singleShot(4000, self._refresh_sysinfo)
            except Exception:  # noqa: BLE001 - 延迟启动失败立即采集
                self._refresh_sysinfo()
        else:
            try:
                self.sysinfo.refresh()  # 缓存秒回，不重新跑子进程
            except Exception:  # noqa: BLE001
                pass
        # 切回首页时刷新工具状态（FFmpeg/yt-dlp/OCR/插件数量等），
        # 使插件增删、工具状态变化后无需手动点「刷新」即可看到最新。
        # scan_plugins 模块加载后有缓存（常态 ~11ms），不会造成卡顿。
        try:
            self.tool_status.refresh()
        except Exception:  # noqa: BLE001
            pass
        super().showEvent(e)

    def _refresh_sysinfo(self):
        try:
            self.sysinfo.refresh()
        except Exception:  # noqa: BLE001 - 采集失败不影响首页
            pass

    def save_prefs(self):
        pass
