"""通用格式辅助函数

从 main.py 提取的纯函数模块。
"""
import re


def extract_urls(text):
    """从文本中提取所有 http(s) URL"""
    return list(set(re.findall(r"https?://[^\s\u4e00-\u9fff\u3000-\u303f\uff00-\uffef<>\"']+", text)))


def format_size(size):
    """格式化文件大小为人类可读字符串"""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    else:
        return f"{size / (1024 * 1024 * 1024):.1f} GB"


def format_capacity_gb(gb):
    """格式化容量（GB 数值）为人类可读字符串：>=1024GB 显示 TB，否则 GB。

    例：format_capacity_gb(512) → "512 GB"；format_capacity_gb(2048) → "2.0 TB"。
    """
    try:
        gb = float(gb)
        if gb >= 1024:
            return f"{gb / 1024:.1f} TB"
        return f"{gb:.0f} GB"
    except Exception:  # noqa: BLE001
        return "Unknown"


def format_physical_disk(interface, model, size_gb):
    """物理硬盘显示标签（型号 + 实际容量）。

    例：format_physical_disk("", "NVMe WD PC SN740 SDDPNQD-512G-1002", 477)
        → "NVMe WD PC SN740 SDDPNQD-512G-1002(477GB)"
    型号以右括号结尾时容量括号前加空格保持可读：
        → "NVMe HYV512X4 (GR) (477GB)"
    interface/model 任一为空时省略对应段；size 非法时省略容量段。
    """
    parts = [p for p in (interface, model) if str(p).strip()]
    base = " ".join(parts)
    try:
        size_gb = float(size_gb)
        cap = f"({size_gb:.0f}GB)"
        # 型号末尾是右括号（如 "HYV512X4 (GR)"）时补一个空格，避免两个括号粘连
        if base.rstrip().endswith(")"):
            cap = " " + cap
        return f"{base}{cap}"
    except Exception:  # noqa: BLE001
        return base


def parse_time(time_str):
    """将 HH:MM:SS / MM:SS / SS 格式的时间字符串转换为秒数"""
    try:
        parts = list(map(float, time_str.split(":")))
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        elif len(parts) == 2:
            return parts[0] * 60 + parts[1]
        return float(parts[0])
    except Exception:
        return 0


def format_datetime(ts_str):
    """美化时间戳显示（收藏/历史记录用）。

    输入 "%Y-%m-%d %H:%M:%S"（或 %Y-%m-%d %H:%M）→ 输出：
    - 今天 → "今天 12:08:33"
    - 昨天 → "昨天 12:08:33"
    - 更早 → "2026-08-10 09:15:22"（含秒的完整时间）
    解析失败原样返回。
    """
    import datetime
    try:
        ts = str(ts_str or "").strip()
        if not ts:
            return ""
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                    "%Y-%m-%d %H:%M:%S.%f"):
            try:
                dt = datetime.datetime.strptime(ts, fmt)
                break
            except ValueError:
                continue
        else:
            return ts
        today = datetime.date.today()
        if dt.second:
            hm = dt.strftime("%H:%M:%S")
            full = dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            hm = dt.strftime("%H:%M")
            full = dt.strftime("%Y-%m-%d %H:%M")
        if dt.date() == today:
            return f"今天 {hm}"
        if dt.date() == today - datetime.timedelta(days=1):
            return f"昨天 {hm}"
        return full
    except Exception:  # noqa: BLE001
        return str(ts_str or "")


def format_time(seconds):
    """将秒数格式化为 HH:MM:SS.sss 字符串"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"
