"""system_info_card — 首页「系统信息」面板（按参考截图设计）。

两列键值行：操作系统 / CPU / 内存 / 显卡 / 软件版本。
数据来自 gui_qt.components.sysinfo，显卡探测放后台线程避免阻塞 UI。
"""
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QVBoxLayout, QWidget)
from qfluentwidgets import CaptionLabel, FluentIcon, IconWidget

from gui_qt.i18n import tr
from gui_qt.components import design_system as ds
from gui_qt.components import sysinfo
from gui_qt.components.card import Card


class _InfoThread(QThread):
    """后台采集全部系统信息（OS/CPU/内存/显卡/版本）。

    CPU/显卡探测会启动 PowerShell CIM 查询（1~3 秒），必须在后台线程
    执行，否则切换首页时 UI 线程被阻塞造成卡顿。采集结果缓存于
    sysinfo 模块，后续刷新秒回。
    """

    done = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        try:
            data = sysinfo.collect()
        except Exception:
            data = {}
        self.done.emit(data)


class _InfoRow(QWidget):
    """单行键值对：左侧灰字 label，右侧白字 value。"""

    def __init__(self, key, value="", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        self.key_label = CaptionLabel(key, self)
        self.key_label.setStyleSheet(
            f"font-size: 12px; color: {ds.ink_sec()};"
            "border: none; background: transparent;")
        self.key_label.setFixedWidth(72)
        lay.addWidget(self.key_label)

        self.value_label = CaptionLabel(value, self)
        self.value_label.setStyleSheet(
            f"font-size: 12px; color: {ds.ink()}; font-weight: 600;"
            "border: none; background: transparent;")
        self.value_label.setWordWrap(True)
        lay.addWidget(self.value_label, 1)

    def set_value(self, v):
        self.value_label.setText(str(v))


class SystemInfoCard(Card):
    """系统信息面板。"""

    def __init__(self, parent=None):
        super().__init__(parent, radius=12)

        v = QVBoxLayout(self)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(8)

        header = QHBoxLayout()
        icon = IconWidget(FluentIcon.INFO, self)
        icon.setFixedSize(18, 18)
        header.addWidget(icon)
        title = QLabel(tr("系统信息", "System info"))
        title.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {ds.ink()};"
            "border: none; background: transparent;")
        header.addWidget(title)
        header.addStretch(1)
        v.addLayout(header)

        self.row_os = _InfoRow(tr("操作系统", "OS"), tr("读取中…", "Loading…"))
        self.row_cpu = _InfoRow("CPU", tr("读取中…", "Loading…"))
        self.row_mem = _InfoRow(tr("内存", "Memory"), tr("读取中…", "Loading…"))
        self.row_gpu = _InfoRow(tr("显卡", "GPU"), tr("读取中…", "Loading…"))
        self.row_ver = _InfoRow(tr("软件版本", "Version"), tr("读取中…", "Loading…"))
        for row in (self.row_os, self.row_cpu, self.row_mem,
                    self.row_gpu, self.row_ver):
            v.addWidget(row)
        v.addStretch(1)

    def refresh(self):
        """后台采集系统信息，完成后一次性更新全部行（不阻塞 UI）。"""
        if getattr(self, "_thread", None) is not None and self._thread.isRunning():
            return  # 上一次采集仍在进行，避免重复启动
        self._thread = _InfoThread(self)
        self._thread.done.connect(self._apply)
        self._thread.start()

    def _apply(self, d):
        """主线程：用采集结果填充各行。"""
        os_info = d.get("os") or {}
        if os_info.get("system") == "Windows":
            build = f" (Build {os_info['build']})" if os_info.get("build") else ""
            self.row_os.set_value(
                f"{os_info['system']} {os_info['release']}{build}"
                + tr(" · {}位", " · {}bit").format(os_info['arch']))
        else:
            self.row_os.set_value(os_info.get("system") or tr("未知", "Unknown"))
        self.row_cpu.set_value(d.get("cpu") or tr("读取中…", "Loading…"))
        if d.get("version"):
            self.row_ver.set_value(d["version"])
        total = d.get("mem_total")
        avail = d.get("mem_avail")
        used_pct = d.get("mem_used_pct")
        if total is not None:
            used = total - (avail or 0)
            pct_str = tr("（使用 {}%）", " ({}% used)").format(used_pct) if used_pct is not None else ""
            self.row_mem.set_value(
                tr("{:.0f} GB（已用 {:.1f} GB{}）", "{:.0f} GB ({:.1f} GB used {})").format(total, used, pct_str))
        else:
            self.row_mem.set_value(tr("未知", "Unknown"))
        self.row_gpu.set_value(d.get("gpu") or tr("未知显卡", "Unknown GPU"))
