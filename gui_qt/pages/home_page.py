"""home_page — 首页 Dashboard（按参考截图「首页截图.png」重做）。

布局（自下而上与截图一致）：
  通栏：欢迎语 + 副标题
  统计卡 ×4：今日转换文件 / 节省空间 / 成功率 / 累计运行（各带「较昨日」变化）
  快速功能行：8 个图标入口
  双栏主区：
    左栏（约 7/10）：最近任务表格 + 公告通知
    右栏（约 3/10）：系统信息 + 新手指南
"""
import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QVBoxLayout,
                               QWidget)
from qfluentwidgets import (FluentIcon, ScrollArea)

from gui_qt.components import design_system as ds
from gui_qt.components.stat_card_new import StatCard
from gui_qt.components.quick_function_row import QuickFunctionRow
from gui_qt.components.recent_tasks_table import RecentTasksTable
from gui_qt.components.changelog_card import ChangelogCard
from gui_qt.components.system_info_card import SystemInfoCard
from gui_qt.components.open_source_card import OpenSourceCard


class HomePage(QWidget):
    """首页 Dashboard（按参考截图设计）。"""

    def __init__(self, window, services, parent=None):
        super().__init__(parent)
        self.window = window
        self.services = services
        self.stats = services.get("stats")

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
            "专业、强大、易用的格式转换工具 —— 视频 / 音频 / 图片 / 文档一站式处理",
            self)
        v.addWidget(self.hero)

    def _greeting(self):
        hour = datetime.datetime.now().hour
        if hour < 6:
            return "你好，夜深了也别忘了保存工作"
        if hour < 12:
            return "你好，欢迎使用格式大师！"
        if hour < 14:
            return "你好，午间时光也要高效工作"
        if hour < 18:
            return "你好，下午好！欢迎使用格式大师"
        return "你好，晚上好！欢迎使用格式大师"

    # ── 2. 统计卡 ×4 ─────────────────────────────
    def _build_stats(self, v):
        grid_w = QWidget()
        grid_w.setStyleSheet("background: transparent;")
        grid = QGridLayout(grid_w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)

        self.stat_today = StatCard(
            "今日转换文件", "0 个", "较昨日 +0%",
            "#5B5BD6", FluentIcon.PLAY)
        self.stat_saved = StatCard(
            "节省空间", "--", "较昨日 +0%",
            "#2FC99A", FluentIcon.LIBRARY)
        self.stat_rate = StatCard(
            "成功率", "--", "较昨日 +0%",
            "#F0A63A", FluentIcon.ACCEPT)
        self.stat_uptime = StatCard(
            "累计运行", "0 秒", "较昨日 +0分钟",
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

        self.changelog = ChangelogCard()
        lv.addWidget(self.changelog)
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
        page = self.window.pages.get(key)
        if page:
            self.window.switchTo(page)

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
        today = datetime.date.today().isoformat()
        total = ok = fail = 0
        if self.stats:
            d = self.stats.get_range(today, today)
            for day_records in d.values():
                for rec in day_records:
                    total += 1
                    if rec.get("status") == "success":
                        ok += 1
                    else:
                        fail += 1
        self.stat_today.set_value(f"{total} 个")
        self.stat_saved.set_value("--")  # 需要磁盘节省统计，暂不展示
        self.stat_rate.set_value(
            f"{ok / total * 100:.1f} %" if total else "--")
        try:
            self.stat_uptime.set_value(self.services.uptime_str())
        except Exception:
            pass

    def _refresh_tasks(self):
        try:
            tasks = self.services.task_manager.all_tasks()[:6]
        except Exception:
            tasks = []
        self.recent_tasks.set_tasks(tasks)

    def showEvent(self, e):
        self._refresh_all()
        try:
            self.sysinfo.refresh()
        except Exception:
            pass
        super().showEvent(e)

    def save_prefs(self):
        pass
