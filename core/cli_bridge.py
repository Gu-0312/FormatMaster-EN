"""core/cli_bridge — 命令行格式转换桥接（不依赖 GUI，纯 logic）。

适合命令行参数（--quick-convert）与 Windows 右键菜单场景：
直接调用各 converter 在后台执行转换，不启动主窗口。
"""
import os

from core.audio_converter import AudioConverter
from core.image_converter import ImageConverter
from core.video_converter import VideoConverter
from utils.config import SUPPORTED_AUDIO, SUPPORTED_VIDEO

# 扩展名 → (converter 方法, 目标扩展名, 额外参数)
_EXT_HANDLERS = {}

# 视频 → MP4 软编
for _ext in set(SUPPORTED_VIDEO.values()):
    _EXT_HANDLERS[_ext] = ("video", ".mp4", {})

# 音频 → MP3 192k
for _ext in set(SUPPORTED_AUDIO.values()):
    _EXT_HANDLERS[_ext] = ("audio", ".mp3", {"bitrate": "192k"})

# 图片 → PNG
for _ext in ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp',
             '.ico', '.tga', '.avif'):
    _EXT_HANDLERS[_ext] = ("image", ".png", {})

_noop_cb = lambda pct, msg: None


def auto_convert(filepath, target_ext=None, output_dir=None,
                 progress_cb=None):
    """按文件类型自动选择转换目标并执行。

    filepath:   源文件路径
    target_ext: 目标扩展名（如 '.mp3'），None 按类型默认
    output_dir: 输出目录（默认源文件所在目录）
    progress_cb: (pct, msg) 进度回调，默认不回调

    返回 (ok: bool, output_path: str)。
    """
    ext = os.path.splitext(filepath)[1].lower()
    handler = _EXT_HANDLERS.get(ext)
    if handler is None:
        return False, ""

    kind, default_out_ext, default_params = handler
    out_ext = target_ext or default_out_ext
    out_dir = output_dir or os.path.dirname(os.path.abspath(filepath))

    name = os.path.splitext(os.path.basename(filepath))[0]
    out_path = os.path.join(out_dir, name + out_ext)

    # 防覆盖：输出目录不存在则创建；输出文件与源文件同名则加后缀
    os.makedirs(out_dir, exist_ok=True)
    if os.path.abspath(out_path).lower() == os.path.abspath(filepath).lower():
        out_path = os.path.join(out_dir, f"{name}_converted{out_ext}")

    cb = progress_cb or _noop_cb

    if kind == "video":
        vc = VideoConverter()
        ok = vc.convert(filepath, out_path, out_ext,
                        progress_callback=cb,
                        **default_params)
        return ok, out_path

    if kind == "audio":
        ac = AudioConverter()
        fmt_name = {v: k for k, v in SUPPORTED_AUDIO.items()}.get(
            out_ext, "mp3")
        codec = {"MP3": "libmp3lame", "AAC": "aac", "FLAC": "flac",
                 "WAV": "wav"}.get(fmt_name, "libmp3lame")
        ok = ac.convert(filepath, out_path, codec=codec,
                        bitrate=default_params.get("bitrate", "192k"),
                        progress_callback=cb)
        return ok, out_path

    if kind == "image":
        ic = ImageConverter()
        ok = ic.convert(filepath, out_path, quality=95,
                        progress_callback=cb)
        return ok, out_path

    return False, ""
