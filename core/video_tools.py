"""video_tools — 视频处理工具集（剪辑 / 合并 / 字幕烧录 / 变速 / 去水印）。

统一基于 run_ffmpeg 进度解析，
复用 core/video_converter 的调用范式；不依赖 GUI。
各函数均接受 progress_cb(pct, msg) 进度回调，失败时回调 (-1, 原因)。
"""
import os

from core.ffmpeg_executor import get_ffprobe_info, get_ffprobe_raw
from core.ffmpeg_progress import run_ffmpeg
from utils.config import get_ffmpeg_path


def _duration_of(path):
    """用 ffprobe 获取媒体时长（秒），失败返回 0。"""
    try:
        info = get_ffprobe_info(path)
        if info:
            return float(info.get("duration") or 0.0)
    except Exception:
        pass
    return 0.0


def _has_audio_stream(path):
    """视频是否含音频流（filter_complex 引用 [0:a] 前必须确认）。"""
    try:
        info = get_ffprobe_raw(path)
        if info and info.get("streams"):
            return any(s.get("codec_type") == "audio"
                       for s in info["streams"])
    except Exception:
        pass
    return False


def _run(args, duration, label, progress_cb, cancel_check=None):
    """启动 ffmpeg 并读取进度，返回 bool。"""
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        if progress_cb:
            progress_cb(-1, "错误: FFmpeg 未安装")
        return False
    cmd = [ffmpeg, "-y", "-nostats", "-progress", "pipe:2"] + args
    result = run_ffmpeg(cmd, duration=duration, label=label,
                        cancel_check=cancel_check,
                        progress_callback=progress_cb,
                        translate_error=True)
    if result.success:
        return True
    if result.cancelled:
        return False
    if progress_cb:
        progress_cb(-1, f"失败: {result.error_cn}")
    return False


def clip_video(input_path, output_path, start_sec=None, end_sec=None,
               progress_cb=None, cancel_check=None, vf=None):
    """截取视频片段。start_sec/end_sec 为秒数（None 表示不限）。

    流复制优先（快），若失败自动降级为重编码。
    vf: 视频滤镜串（如 "transpose=1,hflip" / "eq=brightness=0.1"），
        非空时直接走重编码路径（流复制无法应用滤镜）。
    """
    duration = _duration_of(input_path)
    seg = (end_sec or duration) - (start_sec or 0.0)
    seg = max(seg, 1.0)

    # 带滤镜 → 必须重编码
    if vf:
        args = []
        if start_sec:
            args += ["-ss", str(float(start_sec))]
        args += ["-i", input_path]
        if end_sec:
            args += ["-to", str(float(end_sec))]
        args += ["-vf", vf, "-c:v", "libx264", "-preset", "fast",
                 "-c:a", "aac", "-map_metadata", "0", output_path]
        return _run(args, seg, "剪辑中", progress_cb, cancel_check)

    args = []
    if start_sec:
        args += ["-ss", str(float(start_sec))]
    args += ["-i", input_path]
    if end_sec:
        args += ["-to", str(float(end_sec))]
    args += ["-c", "copy", "-map_metadata", "0", output_path]
    if _run(args, seg, "剪辑中", progress_cb, cancel_check):
        return True
    # 流复制失败（如非关键帧起点）→ 重编码兜底
    args = []
    if start_sec:
        args += ["-ss", str(float(start_sec))]
    args += ["-i", input_path]
    if end_sec:
        args += ["-to", str(float(end_sec))]
    args += ["-c:v", "libx264", "-preset", "fast", "-c:a", "aac",
             "-map_metadata", "0", output_path]
    return _run(args, seg, "剪辑中(重编码)", progress_cb, cancel_check)


def merge_videos(input_paths, output_path, progress_cb=None,
                 cancel_check=None):
    """合并多个视频（concat demuxer，自动选用兼容编码）。"""
    if len(input_paths) < 2:
        if progress_cb:
            progress_cb(-1, "错误: 合并至少需要 2 个文件")
        return False
    total = sum(_duration_of(p) for p in input_paths) or 1.0
    list_path = os.path.join(
        os.path.dirname(output_path) or ".", "_fm_concat.txt")
    try:
        with open(list_path, "w", encoding="utf-8") as f:
            for p in input_paths:
                f.write(f"file '{os.path.basename(p).replace(chr(39), chr(39)+chr(39)+chr(39))}'\n")
        # concat demuxer 需要相对路径（相对 list 文件目录）
        with open(list_path, "r", encoding="utf-8") as f:
            content = f.read()
        # 改为绝对路径更稳（不同盘符时 ffmpeg 相对解析可能失败）
        content = "".join(
            f"file '{p.replace(chr(39), chr(39)+chr(39)+chr(39))}'\n"
            for p in input_paths)
        with open(list_path, "w", encoding="utf-8") as f:
            f.write(content)
        args = ["-f", "concat", "-safe", "0", "-i", list_path,
                "-c", "copy", "-map_metadata", "0", output_path]
        ok = _run(args, total, "合并中", progress_cb, cancel_check)
        if not ok:
            # 编码不一致 → 统一重编码
            args = ["-f", "concat", "-safe", "0", "-i", list_path,
                    "-c:v", "libx264", "-preset", "fast", "-c:a", "aac",
                    "-map_metadata", "0", output_path]
            ok = _run(args, total, "合并中(重编码)", progress_cb, cancel_check)
        return ok
    finally:
        try:
            os.remove(list_path)
        except OSError:
            pass


def burn_subtitle(input_path, subtitle_path, output_path,
                  progress_cb=None, cancel_check=None):
    """字幕烧录（软字幕合成进画面，需要重编码）。"""
    if not os.path.isfile(subtitle_path):
        if progress_cb:
            progress_cb(-1, "错误: 字幕文件不存在")
        return False
    duration = _duration_of(input_path) or 1.0
    # subtitles 滤镜：Windows 下路径需转义（: 和 \）
    esc = subtitle_path.replace("\\", "/").replace(":", "\\:")
    args = ["-i", input_path,
            "-vf", f"subtitles='{esc}'",
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac", "-map_metadata", "0", output_path]
    return _run(args, duration, "烧录字幕中", progress_cb, cancel_check)


def change_speed(input_path, output_path, rate, progress_cb=None,
                 cancel_check=None):
    """视频变速。rate>1 加速，0<rate<1 减速。"""
    try:
        rate = float(rate)
    except (TypeError, ValueError):
        rate = 1.0
    if rate <= 0:
        rate = 1.0
    duration = _duration_of(input_path) / rate or 1.0
    # 无音轨视频不能引用 [0:a]（否则 FFmpeg 报流不存在）
    has_audio = _has_audio_stream(input_path)
    if has_audio:
        fc = (f"[0:v]setpts=PTS/{rate}[v];[0:a]atempo={max(rate, 0.5)}[a]"
              if 0.5 <= rate <= 2.0 else
              f"[0:v]setpts=PTS/{rate}[v];[0:a]atempo={rate}[a]")
        maps = ["-map", "[v]", "-map", "[a]"]
    else:
        fc = f"[0:v]setpts=PTS/{rate}[v]"
        maps = ["-map", "[v]"]
    args = ["-i", input_path, "-filter_complex", fc, *maps,
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac", "-map_metadata", "0", output_path]
    return _run(args, duration, "变速处理中", progress_cb, cancel_check)


def remove_logo(input_path, output_path, x, y, w, h, progress_cb=None,
                cancel_check=None):
    """视频去水印：用 FFmpeg delogo 滤镜对指定区域做插值模糊。

    x/y/w/h 为水印区域（像素坐标与尺寸）。delogo 通过周围像素插值
    模糊覆盖，适合台标/角落水印；全屏大面积水印效果有限。
    区域自动钳制到画面内且不贴边（delogo 需 1px 插值边界）。
    """
    try:
        x, y, w, h = int(x), int(y), int(w), int(h)
    except (TypeError, ValueError):
        return False
    # 读取视频分辨率用于钳制区域
    width, height = 0, 0
    try:
        raw = get_ffprobe_raw(input_path, timeout=10)
        if raw and raw.get("streams"):
            for s in raw["streams"]:
                if s.get("codec_type") == "video" and s.get("width"):
                    width, height = int(s["width"]), int(s["height"])
                    break
    except Exception:
        pass
    if width > 0 and height > 0:
        # delogo 不允许区域贴边（内部插值需要边界），钳制到 [1, 尺寸-2]
        x = max(1, min(x, width - 2))
        y = max(1, min(y, height - 2))
        w = min(w, width - x - 2)
        h = min(h, height - y - 2)
    if w <= 0 or h <= 0:
        return False
    duration = _duration_of(input_path) or 1.0
    args = ["-i", input_path,
            "-vf", f"delogo=x={x}:y={y}:w={w}:h={h}:show=0",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy", "-map_metadata", "0", output_path]
    return _run(args, duration, "去水印处理中", progress_cb, cancel_check)
# ─────────────────────────────────────────────────────
#  扩展滤镜集（2026-08-15 合并进「视频处理」面板）
#  倒放 / 转GIF / 文字水印 / 视频稳定 / 画质增强 /
#  画面裁剪 / 补帧慢动作 / 去隔行 / 音轨替换与混音
# ─────────────────────────────────────────────────────

def _pick_cjk_font():
    """挑一个 drawtext 可用的中文字体文件（系统默认优先）。"""
    import os as _os
    cands = ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf",
             "C:/Windows/Fonts/arial.ttf"]
    for fp in cands:
        try:
            if _os.path.isfile(fp):
                return fp
        except Exception:
            continue
    return None


def reverse_video(input_path, output_path, keep_audio=True,
                  progress_cb=None, cancel_check=None):
    """视频倒放。keep_audio=True 时音轨同步倒放（鬼畜/复盘）。"""
    duration = _duration_of(input_path) or 1.0
    has_audio = _has_audio_stream(input_path) and keep_audio
    if has_audio:
        fc = "[0:v]reverse[v];[0:a]areverse[a]"
        maps = ["-map", "[v]", "-map", "[a]"]
    else:
        fc = "[0:v]reverse[v]"
        maps = ["-map", "[v]"]
    args = ["-i", input_path, "-filter_complex", fc, *maps,
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac" if has_audio else "copy",
            "-map_metadata", "0", output_path]
    return _run(args, duration, "倒放处理中", progress_cb, cancel_check)


def video_to_gif(input_path, output_path, fps=15, max_width=480,
                 progress_cb=None, cancel_check=None):
    """视频转 GIF（palettegen/paletteuse 两遍，高质量调色板）。

    max_width 限制输出宽度（等比缩放），控制体积。
    """
    duration = _duration_of(input_path) or 1.0
    try:
        fps = max(1, int(fps))
        max_width = max(32, int(max_width))
    except (TypeError, ValueError):
        fps, max_width = 15, 480
    pal = os.path.join(os.path.dirname(output_path) or ".",
                       "_fm_gif_pal.png")
    try:
        # 第一遍：生成调色板
        scale = (f"scale={max_width}:-1:flags=lanczos"
                 if max_width else "scale=-1:-1")
        args1 = ["-i", input_path, "-vf",
                 f"fps={fps},{scale},palettegen=max_colors=256",
                 "-y", pal]
        ok = _run(args1, duration, "生成调色板…", progress_cb, cancel_check)
        if not ok:
            return False
        # 第二遍：用调色板输出 GIF
        args2 = ["-i", input_path, "-i", pal, "-lavfi",
                 f"fps={fps},{scale}[x];[x][1:v]paletteuse=dither=bayer",
                 "-y", output_path]
        return _run(args2, duration, "生成GIF…", progress_cb, cancel_check)
    finally:
        try:
            os.remove(pal)
        except OSError:
            pass


def burn_text_watermark(input_path, output_path, text, font_size=48,
                        position="bottom_right", opacity=0.7,
                        progress_cb=None, cancel_check=None):
    """视频文字水印（drawtext 烧录，支持中文，用系统默认中文字体）。"""
    if not text:
        if progress_cb:
            progress_cb(-1, "错误: 水印文字不能为空")
        return False
    font = _pick_cjk_font()
    if not font:
        if progress_cb:
            progress_cb(-1, "错误: 未找到可用中文字体")
        return False
    duration = _duration_of(input_path) or 1.0
    # drawtext 参数转义：冒号/引号/逗号/方括号/反斜杠/百分号
    esc = (text.replace("\\", "\\\\").replace(":", "\\:")
           .replace("'", "\\'").replace(",", "\\,")
           .replace("[", "\\[").replace("]", "\\]")
           .replace("%", "\\%"))
    font_esc = font.replace("\\", "/").replace(":", "\\:")
    pos = {
        "top_left": "x=24:y=24",
        "top_right": "x=w-tw-24:y=24",
        "bottom_left": "x=24:y=h-th-24",
        "bottom_right": "x=w-tw-24:y=h-th-24",
        "center": "x=(w-tw)/2:y=(h-th)/2",
    }.get(position, "x=w-tw-24:y=h-th-24")
    alpha = max(0.0, min(1.0, float(opacity)))
    dt = (f"drawtext=fontfile='{font_esc}':text='{esc}'"
          f":fontsize={int(font_size)}:fontcolor=white@{alpha:.2f}"
          f":{pos}:shadowcolor=black@0.5:shadowx=2:shadowy=2")
    args = ["-i", input_path, "-vf", dt,
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "copy", "-map_metadata", "0", output_path]
    return _run(args, duration, "添加文字水印…", progress_cb, cancel_check)


def stabilize_video(input_path, output_path,
                    progress_cb=None, cancel_check=None):
    """视频稳定（deshake，修复手持抖动）。"""
    duration = _duration_of(input_path) or 1.0
    args = ["-i", input_path, "-vf", "deshake",
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac", "-map_metadata", "0", output_path]
    return _run(args, duration, "视频稳定中…", progress_cb, cancel_check)


def enhance_video(input_path, output_path, sharpen=0, denoise=0,
                  progress_cb=None, cancel_check=None):
    """画质增强：unsharp 锐化 + hqdn3d 降噪（0 表示关闭）。"""
    duration = _duration_of(input_path) or 1.0
    filters = []
    try:
        sharpen = float(sharpen)
    except (TypeError, ValueError):
        sharpen = 0.0
    try:
        denoise = float(denoise)
    except (TypeError, ValueError):
        denoise = 0.0
    if sharpen > 0:
        luma = min(5.0, sharpen)
        filters.append(f"unsharp=5:5:{luma:.2f}:5:5:0.0")
    if denoise > 0:
        strength = min(8.0, denoise)
        filters.append(f"hqdn3d={strength:.1f}:{strength:.1f}:{strength:.1f}:{strength:.1f}")
    if not filters:
        if progress_cb:
            progress_cb(-1, "错误: 锐化与降噪均为 0")
        return False
    args = ["-i", input_path, "-vf", ",".join(filters),
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "copy", "-map_metadata", "0", output_path]
    return _run(args, duration, "画质增强中…", progress_cb, cancel_check)


def crop_video(input_path, output_path, x, y, w, h,
               progress_cb=None, cancel_check=None):
    """画面裁剪（crop）。x/y/w/h 像素坐标，自动钳制到画面内。"""
    try:
        x, y, w, h = int(x), int(y), int(w), int(h)
    except (TypeError, ValueError):
        if progress_cb:
            progress_cb(-1, "错误: 裁剪参数无效")
        return False
    # 读取分辨率钳制
    width, height = 0, 0
    try:
        raw = get_ffprobe_raw(input_path, timeout=10)
        if raw and raw.get("streams"):
            for s in raw["streams"]:
                if s.get("codec_type") == "video" and s.get("width"):
                    width, height = int(s["width"]), int(s["height"])
                    break
    except Exception:
        pass
    if width > 0:
        x = max(0, min(x, width - 1))
        w = min(w, width - x)
    if height > 0:
        y = max(0, min(y, height - 1))
        h = min(h, height - y)
    if w <= 0 or h <= 0:
        if progress_cb:
            progress_cb(-1, "错误: 裁剪区域无效")
        return False
    duration = _duration_of(input_path) or 1.0
    args = ["-i", input_path, "-vf", f"crop={w}:{h}:{x}:{y}",
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "copy", "-map_metadata", "0", output_path]
    return _run(args, duration, "画面裁剪中…", progress_cb, cancel_check)


def slowmo_interp(input_path, output_path, rate, target_fps=60,
                  progress_cb=None, cancel_check=None):
    """补帧慢动作（minterpolate 运动补偿，0<rate<1 慢放且丝滑）。"""
    try:
        rate = float(rate)
        target_fps = max(1, int(target_fps))
    except (TypeError, ValueError):
        rate, target_fps = 0.5, 60
    if not (0 < rate < 1):
        if progress_cb:
            progress_cb(-1, "错误: 补帧慢动作需 0<倍速<1")
        return False
    duration = _duration_of(input_path) / rate or 1.0
    has_audio = _has_audio_stream(input_path)
    fc = (f"[0:v]setpts=PTS/{rate},minterpolate=fps={target_fps}:"
          f"mi_mode=mci:mc_mode=aobmc:vsync=vfr[v]")
    if has_audio:
        fc += f";[0:a]atempo={rate:.4f}[a]"
        maps = ["-map", "[v]", "-map", "[a]"]
    else:
        maps = ["-map", "[v]"]
    args = ["-i", input_path, "-filter_complex", fc, *maps,
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac" if has_audio else "copy",
            "-map_metadata", "0", output_path]
    return _run(args, duration, "补帧慢动作…", progress_cb, cancel_check)


def deinterlace_video(input_path, output_path,
                      progress_cb=None, cancel_check=None):
    """去隔行扫描（yadif，老电视/DV 视频修复）。"""
    duration = _duration_of(input_path) or 1.0
    args = ["-i", input_path, "-vf", "yadif=mode=1",
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "copy", "-map_metadata", "0", output_path]
    return _run(args, duration, "去隔行处理中…", progress_cb, cancel_check)


def replace_audio(input_path, audio_path, output_path, keep_video_codec=True,
                  progress_cb=None, cancel_check=None):
    """音轨替换：视频画面 + 新的音轨（-map 0:v -map 1:a）。"""
    if not os.path.isfile(audio_path):
        if progress_cb:
            progress_cb(-1, "错误: 音频文件不存在")
        return False
    duration = _duration_of(input_path) or 1.0
    args = ["-i", input_path, "-i", audio_path,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "copy" if keep_video_codec else "libx264",
            "-c:a", "aac", "-shortest", "-map_metadata", "0", output_path]
    return _run(args, duration, "替换音轨中…", progress_cb, cancel_check)


def mix_audio(input_path, audio_path, output_path, bg_volume=0.3,
              progress_cb=None, cancel_check=None):
    """音轨混音：原声 + 背景音乐 amix（可调背景音量比例）。"""
    if not os.path.isfile(audio_path):
        if progress_cb:
            progress_cb(-1, "错误: 音频文件不存在")
        return False
    try:
        bg_volume = max(0.0, min(1.0, float(bg_volume)))
    except (TypeError, ValueError):
        bg_volume = 0.3
    duration = _duration_of(input_path) or 1.0
    main_v = max(0.0, min(1.0, 1.0 - bg_volume))
    fc = (f"[0:a]volume={main_v:.2f}[a0];"
          f"[1:a]volume={bg_volume:.2f}[a1];"
          f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[a]")
    args = ["-i", input_path, "-i", audio_path,
            "-filter_complex", fc,
            "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac",
            "-shortest", "-map_metadata", "0", output_path]
    return _run(args, duration, "混音处理中…", progress_cb, cancel_check)
