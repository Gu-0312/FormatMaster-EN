"""sysinfo — 系统信息采集（首页「系统信息」面板数据源）。

纯函数采集：操作系统 / CPU / 内存 / 显卡 / 软件版本。
所有探测带 try/except 与超时兜底，任何一项失败都不影响整体。
不依赖三方库（显卡/内存探测用 ctypes 调 Win32 API，超时降级）。
"""
from gui_qt.i18n import tr
import ctypes
import os
import platform
import subprocess
import sys


def os_info():
    """操作系统信息。Python 的 platform.release() 对 Win11 返回 '10'，
    需要依据 build 号（>=22000 即 Win11）修正显示名。"""
    try:
        version = platform.version()
        build = ""
        release = platform.release()
        system = platform.system()
        if system == "Windows":
            for part in version.split():
                if part.replace(".", "").isdigit():
                    build = part
                    break
            if build:
                build = build.split(".")[-1]
            try:
                if build and int(build) >= 22000:
                    release = "11"
            except ValueError:
                pass
        return {
            "system": system,
            "release": release,
            "build": build,
            "arch": platform.machine(),
        }
    except Exception:
        return {"system": tr("未知", "Unknown"), "release": "", "build": "", "arch": ""}


_cpu_cache = None


def cpu_info():
    """CPU 名称（用户指定：只显示型号，不带核心数/频率）。

    从 Windows 注册表读取处理器名称（如 "13th Gen Intel(R) Core(TM) i7-13700H"）。
    会话内缓存结果，避免每次刷新首页都重复探测。
    """
    global _cpu_cache
    if _cpu_cache is not None:
        return _cpu_cache
    try:
        _cpu_cache = _cpu_name()
    except Exception:  # noqa: BLE001
        _cpu_cache = tr("未知 CPU", "Unknown CPU")
    return _cpu_cache


def _cpu_name():
    """CPU 名称。Windows 从注册表读取。"""
    try:
        if os.name == "nt":
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            winreg.CloseKey(key)
            return name.strip()
    except Exception:
        pass
    try:
        return platform.processor() or tr("未知 CPU", "Unknown CPU")
    except Exception:
        return tr("未知 CPU", "Unknown CPU")


def _cpu_details():
    """CPU 核心数 / 线程数 / 频率。用 PowerShell CIM 查询。"""
    try:
        out = _powershell(
            "Get-CimInstance Win32_Processor | Select-Object -First 1"
            " | Select-Object NumberOfCores, NumberOfLogicalProcessors,"
            " MaxClockSpeed | ConvertTo-Json")
        if out:
            import json
            data = json.loads(out)
            cores = data.get("NumberOfCores", "")
            threads = data.get("NumberOfLogicalProcessors", "")
            mhz = data.get("MaxClockSpeed", 0)
            ghz = f"{mhz / 1000:.1f} GHz" if mhz else ""
            return {"cores": str(cores), "threads": str(threads), "ghz": ghz}
    except Exception:
        pass
    return {}


def _powershell(cmd, timeout=6):
    """执行 PowerShell 命令，返回 stdout（去空白）。带超时与创建隐藏窗口。"""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if out.returncode == 0 and out.stdout:
            return out.stdout.decode("utf-8", errors="ignore").strip()
    except Exception:
        pass
    return None


_gpu_cache = None


def gpu_info():
    """显卡名称（用户指定：只显示型号，不带显存/驱动）。

    多显卡时优先显示独立显卡（NVIDIA/AMD），排除 Microsoft 基本显示适配器。
    返回格式: "NVIDIA GeForce RTX 4060 Laptop GPU"
    会话内缓存结果（显卡信息运行期基本不变），避免重复 PowerShell 查询。

    说明：显存不再读取——Win32_VideoController.AdapterRAM 是 32 位，
    >4GB 显存（如 8GB 的 4060）会被截断显示成 4GB，误导用户。
    """
    global _gpu_cache
    if _gpu_cache is not None:
        return _gpu_cache
    result = tr("未知显卡", "Unknown GPU")
    try:
        out = _powershell(
            "Get-CimInstance Win32_VideoController"
            " | Select-Object Name | ConvertTo-Json")
        if out:
            import json
            data = json.loads(out)
            if not isinstance(data, list):
                data = [data]
            # 过滤掉无效/基本显示适配器
            gpus = []
            for item in data:
                name = (item.get("Name") or "").strip()
                if not name:
                    continue
                low = name.lower()
                if "microsoft" in low and "basic" in low:
                    continue
                gpus.append({"name": name})
            if gpus:
                # 优先独立显卡（NVIDIA / AMD / Intel Arc）
                discrete = [g for g in gpus if any(
                    kw in g["name"].lower()
                    for kw in ("nvidia", "amd", "radeon", "arc"))]
                gpu = discrete[0] if discrete else gpus[0]
                result = gpu["name"]
    except Exception:  # noqa: BLE001
        pass
    if result == tr("未知显卡", "Unknown GPU"):
        # 兜底：直接取第一个显卡名称
        name = _powershell(
            "Get-CimInstance Win32_VideoController | Select-Object -First 1"
            " -ExpandProperty Name")
        result = name or tr("未知显卡", "Unknown GPU")
    _gpu_cache = result
    return result


def mem_info():
    """内存信息：(总 GB, 可用 GB, 使用率%)。"""
    total_gb = available_gb = used_pct = None
    try:
        if os.name == "nt":
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                total_gb = stat.ullTotalPhys / (1024 ** 3)
                available_gb = stat.ullAvailPhys / (1024 ** 3)
                used_pct = stat.dwMemoryLoad
    except Exception:
        pass
    if total_gb is None:
        try:
            import psutil
            vm = psutil.virtual_memory()
            total_gb, available_gb = vm.total / 1e9, vm.available / 1e9
            used_pct = vm.percent
        except Exception:
            pass
    return total_gb, available_gb, used_pct


_mem_module_cache = None


def memory_modules_info():
    """内存条信息：型号 + 条数 + 总容量。

    用 Win32_PhysicalMemory 查询每根内存条的 PartNumber（如
    MTC4C10163S1SC48BA1）与 Capacity。返回
    {"module": "MTC4C10163S1SC48BA1", "count": 2, "total_gb": 16}；
    失败/无数据返回 None，绝不抛异常。
    """
    global _mem_module_cache
    if _mem_module_cache is not None:
        return _mem_module_cache
    result = None
    try:
        out = _powershell(
            "Get-CimInstance Win32_PhysicalMemory"
            " | Select-Object PartNumber, Capacity | ConvertTo-Json")
        if out:
            import json
            data = json.loads(out)
            if not isinstance(data, list):
                data = [data]
            count = len(data)
            total_gb = sum(d.get("Capacity") or 0 for d in data) / 2 ** 30
            module = next(
                ((d.get("PartNumber") or "").strip() for d in data
                 if (d.get("PartNumber") or "").strip()),
                "")
            if count > 0:
                result = {"module": module, "count": count,
                          "total_gb": total_gb}
    except Exception:  # noqa: BLE001
        result = None
    _mem_module_cache = result
    return result


_mobo_cache = None


def motherboard_info():
    """主板型号（Win32_BaseBoard.Product，如 FX507VV）。

    Product 为空或是通用占位名（"Base Board"/"System Product Name" 等）
    时回退 Manufacturer；仍无效返回空串。
    """
    global _mobo_cache
    if _mobo_cache is not None:
        return _mobo_cache
    result = ""
    try:
        out = _powershell(
            "Get-CimInstance Win32_BaseBoard | Select-Object -First 1"
            " Manufacturer, Product | ConvertTo-Json")
        if out:
            import json
            data = json.loads(out)
            if not isinstance(data, list):
                data = [data]
            item = data[0] if data else {}
            product = (item.get("Product") or "").strip()
            mfr = (item.get("Manufacturer") or "").strip()
            # 通用占位名过滤
            _generic = {"base board", "none", "system product name",
                        "to be filled by o.e.m.", "not applicable"}
            if product and product.lower() not in _generic:
                result = product
            elif mfr and mfr.lower() not in _generic:
                result = mfr
    except Exception:  # noqa: BLE001
        pass
    _mobo_cache = result
    return result


def app_version():
    """软件版本。"""
    try:
        from utils.config import APP_VERSION
        return APP_VERSION
    except Exception:
        try:
            return platform.python_version()
        except Exception:
            return "1.3.7"


def collect():
    """一次性采集全部系统信息。"""
    total_gb, avail_gb, used_pct = mem_info()
    disk_total, disk_free = disk_info()
    return {
        "os": os_info(),
        "cpu": cpu_info(),
        "gpu": gpu_info(),
        "mem_total": total_gb,
        "mem_avail": avail_gb,
        "mem_used_pct": used_pct,
        "mem_module": memory_modules_info(),
        "motherboard": motherboard_info(),
        "disk_total": disk_total,
        "disk_free": disk_free,
        "disks": disks_info(),
        "phys_disks": physical_disks_info(),
        "version": app_version(),
    }


def disk_info():
    """安装盘空间（GB, GB）。失败返回 (None, None)。"""
    try:
        import shutil
        usage = shutil.disk_usage(os.path.abspath("."))
        return usage.total / 2 ** 30, usage.free / 2 ** 30
    except Exception:  # noqa: BLE001
        return None, None


def disks_info():
    """所有固定硬盘分区空间（按盘符排序）。

    返回 [{"drive": "C:", "total_gb": x, "free_gb": y}, ...]。
    只统计固定硬盘（DRIVE_FIXED，如 C:/D: 本地盘），排除 U 盘、光驱、
    网络映射盘等；用 GetDriveTypeW 判定，失败时兜底全部显示。
    任何异常静默跳过，绝不抛异常（首页采集用）。
    """
    disks = []
    try:
        import shutil
        import string
        DRIVE_FIXED = 3
        get_drive_type = None
        if os.name == "nt":
            try:
                get_drive_type = ctypes.windll.kernel32.GetDriveTypeW
            except Exception:  # noqa: BLE001
                get_drive_type = None
        for letter in string.ascii_uppercase:
            root = f"{letter}:\\"
            try:
                if not os.path.exists(root):
                    continue
                if get_drive_type is not None:
                    try:
                        # 只保留固定硬盘（跳过可移动/光驱/网络盘）
                        if get_drive_type(root) != DRIVE_FIXED:
                            continue
                    except Exception:  # noqa: BLE001
                        pass
                usage = shutil.disk_usage(root)
                disks.append({
                    "drive": f"{letter}:",
                    "total_gb": usage.total / 2 ** 30,
                    "free_gb": usage.free / 2 ** 30,
                })
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass
    return disks


_phys_disk_cache = None


def physical_disks_info():
    """物理硬盘列表（型号 + 实际容量）。

    用 Win32_DiskDrive 查询：Model（型号，NVMe 盘自带 "NVMe" 前缀）、
    Size（总字节）。容量换算成**二进制 GiB**（除以 2^30）——用户指定显示
    实际容量（如 476.9 → 477GB，与厂商标称 512GB 区分）。返回
    [{"interface": "", "model": "HYV512X4 (GR)", "size_gb": 477}, ...]。
    会话内缓存（物理硬盘运行期不变）；失败返回空列表，绝不抛异常。
    """
    global _phys_disk_cache
    if _phys_disk_cache is not None:
        return _phys_disk_cache
    disks = []
    try:
        out = _powershell(
            "Get-CimInstance Win32_DiskDrive"
            " | Select-Object InterfaceType, Model,"
            " @{N='SizeGB';E={[math]::Round($_.Size / 1GB, 1)}}"
            " | ConvertTo-Json")
        if out:
            import json
            data = json.loads(out)
            if not isinstance(data, list):
                data = [data]
            for item in data:
                model = (item.get("Model") or "").strip()
                if not model:
                    continue
                interface = (item.get("InterfaceType") or "").strip()
                # Windows 对 NVMe 盘的 InterfaceType 常报告为 SCSI（不准），
                # 而 Model 已带 "NVMe" 前缀；interface 仅作展示补充
                disks.append({
                    "interface": interface if interface and interface.lower() != "scsi" else "",
                    "model": model,
                    "size_gb": float(item.get("SizeGB") or 0),
                })
    except Exception:  # noqa: BLE001
        pass
    _phys_disk_cache = disks
    return disks
