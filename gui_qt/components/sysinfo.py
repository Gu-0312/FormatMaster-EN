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
    """CPU 详细信息：名称 + 核心数 + 频率。

    优先从 Windows 注册表读名称，从 PowerShell CIM 读核心数和频率。
    会话内缓存结果：PowerShell 冷启动 + CIM 查询耗时 1~3 秒，
    避免每次刷新首页都重复探测（见 _cpu_details）。
    """
    global _cpu_cache
    if _cpu_cache is not None:
        return _cpu_cache
    try:
        name = _cpu_name()
        details = _cpu_details()
        parts = [name]
        if details:
            cores = details.get("cores", "")
            threads = details.get("threads", "")
            ghz = details.get("ghz", "")
            if cores and threads and cores != threads:
                parts.append(tr("{}核{}线程", "{} cores / {} threads").format(cores, threads))
            elif cores:
                parts.append(tr("{}核", "{} cores").format(cores))
            if ghz:
                parts.append(ghz)
        _cpu_cache = " · ".join(parts)
    except Exception:
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
    """显卡详细信息：名称 + 显存 + 驱动版本。

    多显卡时优先显示独立显卡（NVIDIA/AMD），排除 Microsoft 基本显示适配器。
    返回格式: "NVIDIA GeForce RTX 4070 Ti · 12GB · 驱动 546.33"
    会话内缓存结果（显卡信息运行期基本不变），避免重复 PowerShell 查询。
    """
    global _gpu_cache
    if _gpu_cache is not None:
        return _gpu_cache
    result = tr("未知显卡", "Unknown GPU")
    try:
        out = _powershell(
            "Get-CimInstance Win32_VideoController"
            " | Select-Object Name, AdapterRAM, DriverVersion"
            " | ConvertTo-Json")
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
                vram_bytes = item.get("AdapterRAM", 0) or 0
                driver = (item.get("DriverVersion") or "").strip()
                gpus.append({
                    "name": name,
                    "vram_gb": vram_bytes / (1024 ** 3) if vram_bytes > 0 else 0,
                    "driver": driver,
                })
            if gpus:
                # 优先独立显卡（NVIDIA / AMD / Intel Arc）
                discrete = [g for g in gpus if any(
                    kw in g["name"].lower()
                    for kw in ("nvidia", "amd", "radeon", "arc"))]
                gpu = discrete[0] if discrete else gpus[0]
                parts = [gpu["name"]]
                if gpu["vram_gb"] > 0:
                    parts.append(f"{gpu['vram_gb']:.0f}GB")
                if gpu["driver"]:
                    parts.append(tr("驱动 {}", "Driver {}").format(gpu['driver']))
                result = " · ".join(parts)
    except Exception:
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


def app_version():
    """软件版本。"""
    try:
        from utils.config import APP_VERSION
        return APP_VERSION
    except Exception:
        try:
            return platform.python_version()
        except Exception:
            return "1.3.1"


def collect():
    """一次性采集全部系统信息。"""
    total_gb, avail_gb, used_pct = mem_info()
    return {
        "os": os_info(),
        "cpu": cpu_info(),
        "gpu": gpu_info(),
        "mem_total": total_gb,
        "mem_avail": avail_gb,
        "mem_used_pct": used_pct,
        "version": app_version(),
    }
