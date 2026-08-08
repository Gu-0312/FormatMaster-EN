"""scene — 场景化一键处理。

按「使用场景」而非技术参数组织转换：选「发抖音/发微信/发邮件…」，
自动匹配格式/分辨率/码率/压缩强度。底层复用 VideoConverter /
AudioConverter / image_compress。

场景字段说明（video 的键取自 utils.config 的
VIDEO_CODECS / VIDEO_PRESETS / RESOLUTIONS）：
    video.codec / video.preset / video.res / video.br
    audio.codec(ffmpeg 编码器) / audio.bitrate
    image.quality / image.max_size (w,h)
    ext.video / ext.audio  目标扩展名
"""

import os

from utils.config import VIDEO_CODECS, VIDEO_PRESETS, RESOLUTIONS

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v",
              ".mpg", ".mpeg", ".ts"}
AUDIO_EXTS = {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma", ".opus"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".gif"}

SCENES = {
    "douyin": {
        "label": "发抖音",
        "desc": "H.264 1080p 高码率，适配竖屏短视频平台",
        "video": {"codec": "H.264", "preset": "中等质量", "res": "1080p (1920x1080)", "br": "5M"},
        "audio": {"codec": "mp3", "bitrate": "192k"},
        "image": {"quality": 85, "max_size": (1920, 1920)},
        "ext": {"video": "mp4", "audio": "mp3"},
    },
    "wechat": {
        "label": "发微信",
        "desc": "小体积快速发送，720p 压缩",
        "video": {"codec": "H.264", "preset": "低质量 (小文件)", "res": "720p (1280x720)", "br": "2M"},
        "audio": {"codec": "mp3", "bitrate": "128k"},
        "image": {"quality": 60, "max_size": (1280, 1280)},
        "ext": {"video": "mp4", "audio": "mp3"},
    },
    "mail": {
        "label": "发邮件",
        "desc": "控制在 25MB 内：720p 低码率",
        "video": {"codec": "H.264", "preset": "低质量 (小文件)", "res": "720p (1280x720)", "br": "1.5M"},
        "audio": {"codec": "mp3", "bitrate": "96k"},
        "image": {"quality": 45, "max_size": (1280, 1280)},
        "ext": {"video": "mp4", "audio": "mp3"},
    },
    "gongzhonghao": {
        "label": "传公众号",
        "desc": "H.264 1080p，主流清晰度",
        "video": {"codec": "H.264", "preset": "中等质量", "res": "1080p (1920x1080)", "br": "4M"},
        "audio": {"codec": "mp3", "bitrate": "192k"},
        "image": {"quality": 80, "max_size": (1920, 1920)},
        "ext": {"video": "mp4", "audio": "mp3"},
    },
    "bilibili": {
        "label": "B站投稿",
        "desc": "HEVC 1080p 高码率，高画质",
        "video": {"codec": "H.265/HEVC", "preset": "高质量 (大文件)", "res": "1080p (1920x1080)", "br": "8M"},
        "audio": {"codec": "mp3", "bitrate": "320k"},
        "image": {"quality": 92, "max_size": (1920, 1920)},
        "ext": {"video": "mp4", "audio": "mp3"},
    },
    "course": {
        "label": "网课存档",
        "desc": "720p 均衡清晰，兼顾体积",
        "video": {"codec": "H.264", "preset": "中等质量", "res": "720p (1280x720)", "br": "2M"},
        "audio": {"codec": "mp3", "bitrate": "128k"},
        "image": {"quality": 70, "max_size": (1600, 1600)},
        "ext": {"video": "mp4", "audio": "mp3"},
    },
    "archive": {
        "label": "长期存档",
        "desc": "接近原始质量，尽量少损失",
        "video": {"codec": "默认", "preset": "原始质量", "res": "原始分辨率", "br": None},
        "audio": {"codec": "mp3", "bitrate": "320k"},
        "image": {"quality": 95, "max_size": None},
        "ext": {"video": "mp4", "audio": "mp3"},
    },
    "fast": {
        "label": "极速转换",
        "desc": "最快出片：720p 低码率",
        "video": {"codec": "H.264", "preset": "低质量 (小文件)", "res": "720p (1280x720)", "br": "1M"},
        "audio": {"codec": "mp3", "bitrate": "96k"},
        "image": {"quality": 30, "max_size": (1024, 1024)},
        "ext": {"video": "mp4", "audio": "mp3"},
    },
}

SCENE_KEYS = list(SCENES.keys())


def scene_labels():
    return [f"{SCENES[k]['label']} — {SCENES[k]['desc']}" for k in SCENE_KEYS]


def detect_kind(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in IMAGE_EXTS:
        return "image"
    return "other"


def convert_scene(input_path, output_path, scene_key, progress_cb=None):
    """按场景模板转换单个文件。返回 bool。"""
    scene = SCENES.get(scene_key)
    if not scene:
        if progress_cb:
            progress_cb(-1, "错误: 未知场景")
        return False
    kind = detect_kind(input_path)
    if kind == "video":
        from core.video_converter import VideoConverter
        v = scene.get("video") or {}
        ext = os.path.splitext(output_path)[1].lstrip(".") or "mp4"
        return VideoConverter().convert(
            input_path, output_path, ext,
            codec=VIDEO_CODECS.get(v.get("codec", "默认")),
            preset=VIDEO_PRESETS.get(v.get("preset", "原始质量")),
            resolution=RESOLUTIONS.get(v.get("res", "原始分辨率")),
            bitrate=v.get("br"),
            progress_callback=progress_cb)
    if kind == "audio":
        from core.audio_converter import AudioConverter
        a = scene.get("audio") or {}
        return AudioConverter().convert(
            input_path, output_path,
            codec=a.get("codec", "mp3"),
            bitrate=a.get("bitrate", "192k"),
            progress_callback=progress_cb)
    if kind == "image":
        from core.tools import image_compress
        img = scene.get("image") or {}
        return image_compress(
            input_path, output_path,
            quality=int(img.get("quality", 80) or 80),
            max_size=img.get("max_size"),
            progress_cb=progress_cb)
    if progress_cb:
        progress_cb(-1, "错误: 不支持的场景类型")
    return False


def scene_output_ext(input_path, scene_key):
    """按场景与源类型决定输出扩展名。"""
    scene = SCENES.get(scene_key) or {}
    kind = detect_kind(input_path)
    ext = (scene.get("ext") or {}).get(kind)
    if kind == "image":
        return os.path.splitext(input_path)[1]   # 图片保持原格式
    return f".{ext}" if ext else os.path.splitext(input_path)[1]
