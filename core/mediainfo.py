"""mediainfo — 媒体文件详细信息检测（MediaInfo 风格）。

用 ffprobe 读取容器格式、编码器、分辨率、帧率、码率、时长、
音视频流等字段，返回分节键值对列表供 UI 展示。
"""

import os

from core.ffmpeg_executor import get_ffprobe_raw


def _fmt_size(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "--"
    if n <= 0:
        return "--"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} PB"


def _fmt_ratio(r):
    """'30000/1001' → '29.97 fps'；非分数原样返回。"""
    if not r:
        return "--"
    r = str(r)
    if "/" in r:
        try:
            a, b = r.split("/")
            v = int(a) / max(int(b), 1)
        except (ValueError, ZeroDivisionError):
            return r
        return f"{v:.3f}".rstrip("0").rstrip(".") + " fps"
    return r + " fps"


def _fmt_brate(b):
    if not b:
        return "--"
    try:
        v = int(b)
    except (TypeError, ValueError):
        return str(b)
    if v >= 1_000_000:
        return f"{v / 1_000_000:.2f} Mbps"
    if v >= 1000:
        return f"{v / 1000:.0f} kbps"
    return f"{v} bps"


def _fmt_dur(sec):
    try:
        sec = float(sec)
    except (TypeError, ValueError):
        return "--"
    if sec <= 0:
        return "--"
    h = int(sec // 3600)
    m = int(sec % 3600 // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:05.2f}"


def _fmt_channels(s):
    ch = s.get("channels")
    layout = s.get("channel_layout")
    if ch:
        if layout:
            return f"{ch} 声道 ({layout})"
        return f"{ch} 声道"
    return layout or "--"


def get_mediainfo(path):
    """读取媒体详细信息 → 分节列表 [(节名, [(字段, 值), ...]), ...]。

    失败返回 None。
    """
    raw = get_ffprobe_raw(path)
    if not raw or not raw.get("streams"):
        return None
    fmt = raw.get("format", {})
    sections = []

    fsec = []
    tags = fmt.get("tags", {})
    if tags.get("title"):
        fsec.append(("标题", tags["title"]))
    fsec += [
        ("容器格式", fmt.get("format_long_name")
         or fmt.get("format_name") or "--"),
        ("文件大小", _fmt_size(fmt.get("size"))),
        ("时长", _fmt_dur(fmt.get("duration"))),
        ("总码率", _fmt_brate(fmt.get("bit_rate"))),
    ]
    if tags.get("encoder"):
        fsec.append(("编码软件", tags["encoder"]))
    sections.append(("文件", fsec))

    streams = raw.get("streams", [])
    for i, s in enumerate(streams):
        stags = s.get("tags", {})
        t = s.get("codec_type")
        if t == "video":
            vsec = [
                ("编码器", s.get("codec_long_name") or s.get("codec_name") or "--"),
            ]
            profile = s.get("profile")
            if profile:
                vsec.append(("规格", profile))
            vsec += [
                ("分辨率", f"{s.get('width')}×{s.get('height')}"),
                ("像素格式", s.get("pix_fmt") or "--"),
                ("帧率", _fmt_ratio(s.get("avg_frame_rate")
                                    or s.get("r_frame_rate"))),
                ("码率", _fmt_brate(s.get("bit_rate"))),
                ("色彩空间", s.get("color_space") or "--"),
                ("色彩传输", s.get("color_transfer") or "--"),
                ("位深", s.get("bits_per_raw_sample")
                 or s.get("bits_per_sample") or "--"),
            ]
            lang = stags.get("language")
            if lang:
                vsec.append(("语言", lang))
            sections.append((f"视频流 {i + 1}", vsec))
        elif t == "audio":
            asec = [
                ("编码器", s.get("codec_long_name") or s.get("codec_name") or "--"),
                ("采样率", (f"{s.get('sample_rate')} Hz"
                            if s.get("sample_rate") else "--")),
                ("声道", _fmt_channels(s)),
                ("位深", s.get("bits_per_sample") or "--"),
                ("码率", _fmt_brate(s.get("bit_rate"))),
                ("语言", stags.get("language") or "--"),
            ]
            sections.append((f"音频流 {i + 1}", asec))
        elif t == "subtitle":
            sections.append((f"字幕流 {i + 1}", [
                ("编码器", s.get("codec_long_name") or s.get("codec_name") or "--"),
                ("语言", stags.get("language") or "--"),
            ]))
        elif t == "data":
            sections.append((f"数据流 {i + 1}", [
                ("类型", s.get("codec_name") or "--"),
            ]))
    return sections
