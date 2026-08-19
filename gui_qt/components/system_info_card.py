"""system_info_card — 首页「系统信息」面板。

键值行（用户指定格式与顺序）：
处理器（纯名称）/ 显卡（纯名称）/ 内存（型号 xN·总容量）/ 主板（型号）/
存储（物理盘 型号(实际容量GB)，分号连接）/ 操作系统（Windows 11）。
数据来自 gui_qt.components.sysinfo，PowerShell 探测放后台线程避免阻塞 UI。
"""
from PySide6.QtCore import Qt, QThread, Signal
from gui_qt.components.safe_worker import SafeWorker
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QVBoxLayout, QWidget)
from qfluentwidgets import CaptionLabel, FluentIcon, IconWidget

from gui_qt.i18n import tr
from gui_qt.components import design_system as ds
from gui_qt.components import sysinfo
from gui_qt.components.card import Card


class _InfoThread(SafeWorker):
    """后台采集全部系统信息（OS/CPU/内存/显卡/版本）。

    CPU/显卡探测会启动 PowerShell CIM 查询（1~3 秒），必须在后台线程
    执行，否则切换首页时 UI 线程被阻塞造成卡顿。采集结果缓存于
    sysinfo 模块，后续刷新秒回。
    """

    done = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

    def work(self):
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
            f"font-size: 12px;"
            "border: none; background: transparent;")
        self.key_label.setFixedWidth(72)
        lay.addWidget(self.key_label)

        self.value_label = CaptionLabel(value, self)
        self.value_label.setStyleSheet(
            f"font-size: 12px; font-weight: 600;"
            "border: none; background: transparent;")
        self.value_label.setWordWrap(True)
        lay.addWidget(self.value_label, 1)

    def set_value(self, v):
        self.value_label.setText(str(v))
        self._reflow_height()

    def _reflow_height(self):
        """按 label 当前实际宽度重算换行所需最小高度，避免被布局压缩导致内容被裁。

        Qt 布局在算 QLabel 高度时，widthHint 可能不等于 label 实际 width
        （尤其含 \n 的多行文本或窄列宽），导致 heightForWidth 估算偏小，
        分配的行高不足以显示全部内容——此处手动按当前 width 算并设最小高度。
        """
        w = max(self.value_label.width(), 1)
        h = self.value_label.heightForWidth(w)
        if h > 0:
            self.value_label.setMinimumHeight(h)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # 列宽变化后（如窗口缩放）重算高度
        self._reflow_height()


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
            f"font-size: 15px; font-weight: 700;"
            "border: none; background: transparent;")
        header.addWidget(title)
        header.addStretch(1)
        v.addLayout(header)

        # 行顺序与内容格式按用户指定：
        # 处理器 / 显卡 / 内存 / 主板 / 存储 / 操作系统
        self.row_cpu = _InfoRow(tr("处理器", "CPU"), tr("读取中…", "Loading…"))
        self.row_gpu = _InfoRow(tr("显卡", "GPU"), tr("读取中…", "Loading…"))
        self.row_mem = _InfoRow(tr("内存", "Memory"), tr("读取中…", "Loading…"))
        self.row_mobo = _InfoRow(tr("主板", "Motherboard"), tr("读取中…", "Loading…"))
        self.row_disk = _InfoRow(tr("存储", "Storage"), tr("读取中…", "Loading…"))
        self.row_os = _InfoRow(tr("操作系统", "OS"), tr("读取中…", "Loading…"))
        for row in (self.row_cpu, self.row_gpu, self.row_mem,
                    self.row_mobo, self.row_disk, self.row_os):
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
        """主线程：用采集结果填充各行（格式按用户指定）。"""
        # 1. 处理器：纯名称，如 "13th Gen Intel(R) Core(TM) i7-13700H"
        self.row_cpu.set_value(d.get("cpu") or tr("读取中…", "Loading…"))

        # 2. 显卡：纯名称，如 "NVIDIA GeForce RTX 4060 Laptop GPU"
        self.row_gpu.set_value(d.get("gpu") or tr("未知显卡", "Unknown GPU"))

        # 3. 内存：型号 x条数·总容量，如 "MTC4C10163S1SC48BA1 x2·总容量: 16GB"
        module_info = d.get("mem_module") or {}
        if module_info.get("total_gb"):
            total_gb = module_info.get("total_gb", 0)
            count = module_info.get("count") or 0
            module = module_info.get("module") or ""
            segs = []
            if module:
                segs.append(module)
            if count:
                segs.append(f"x{count}")
            base = " ".join(segs)
            total_str = tr("总容量: {:.0f}GB", "Total: {:.0f}GB").format(total_gb)
            self.row_mem.set_value(f"{base}·{total_str}" if base else total_str)
        else:
            total = d.get("mem_total")
            self.row_mem.set_value(
                tr("{:.0f} GB", "{:.0f} GB").format(total)
                if total is not None else tr("未知", "Unknown"))

        # 4. 主板：型号，如 "FX507VV"
        self.row_mobo.set_value(d.get("motherboard") or tr("未知", "Unknown"))

        # 5. 存储：物理盘 "型号(实际容量GB)"，多盘用分号连接，
        #    如 "NVMe WD PC SN740 SDDPNQD-512G-1002(477GB); NVMe HYV512X4 (GR)(477GB)"
        phys = d.get("phys_disks") or []
        disks = d.get("disks") or []
        disk_text = None
        if phys:
            from utils.format_helpers import format_physical_disk
            segs = [
                format_physical_disk(p.get("interface", ""),
                                     p.get("model", ""),
                                     p.get("size_gb"))
                for p in phys if p.get("model")
            ]
            if segs:
                disk_text = "; ".join(segs)
        if disk_text is None and disks:
            # 降级：逻辑分区（物理硬盘查询失败时）
            from utils.format_helpers import format_capacity_gb
            segs = []
            for disk in disks:
                drive = disk.get("drive", "")
                total = disk.get("total_gb")
                free = disk.get("free_gb")
                if total is None:
                    continue
                segs.append(
                    tr("{} {}（剩 {}）", "{} {} ({} free)").format(
                        drive, format_capacity_gb(total),
                        format_capacity_gb(free)))
            if segs:
                disk_text = "；".join(segs)
                self.row_disk.value_label.setWordWrap(True)
        if disk_text is None:
            dtotal = d.get("disk_total")
            dfree = d.get("disk_free")
            if dtotal is not None:
                from utils.format_helpers import format_capacity_gb
                disk_text = tr("共 {}（剩 {}）", "{} total ({} free)").format(
                    format_capacity_gb(dtotal), format_capacity_gb(dfree))
                self.row_disk.value_label.setWordWrap(True)
        self.row_disk.set_value(disk_text or tr("未知", "Unknown"))

        # 6. 操作系统：简洁版，如 "Windows 11"
        os_info = d.get("os") or {}
        if os_info.get("system"):
            self.row_os.set_value(
                f"{os_info['system']} {os_info.get('release', '')}".strip())
        else:
            self.row_os.set_value(tr("未知", "Unknown"))
