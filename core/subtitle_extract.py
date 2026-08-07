# -*- coding: utf-8 -*-
"""subtitle_extract — 视频硬字幕提取（OCR → .srt）。

流程：FFmpeg 按固定帧率抽帧 → RapidOCR 逐帧识别 → 相邻帧文本去重合并 →
生成标准 .srt 字幕文件。适合外语视频、录播课等硬字幕场景。
"""
import glob
import os
import re
import subprocess

from utils.config import get_ffmpeg_path
from core.ffmpeg_executor import get_ffprobe_raw

SRT_TEMPLATE = "{idx}\n{start} --> {end}\n{text}\n\n"


def _duration_of(video):
    try:
        info = get_ffprobe_raw(video, timeout=10)
        if info and "format" in info:
            return float(info["format"].get("duration", 0))
    except Exception:
        pass
    return 0


def _normalize(text):
    """去除空白与标点，用于相邻帧文本比较。"""
    return re.sub(r"[\s\u3000，。！？、；：,.!?;:()（）\"'“”‘’\-]", "", text)


def _fmt_ts(sec):
    """秒 → SRT 时间戳 HH:MM:SS,mmm。"""
    sec = max(0, sec)
    ms = int(round((sec - int(sec)) * 1000))
    if ms >= 1000:
        sec += 1
        ms -= 1000
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _extract_frames(video, tmp_dir, fps, progress_cb=None, cancel_check=None):
    """ffmpeg 抽帧到临时目录，返回排序后的帧路径列表。"""
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        if progress_cb:
            progress_cb(-1, "错误: FFmpeg 未安装")
        return None
    pattern = os.path.join(tmp_dir, "frame_%05d.png")
    cmd = [ffmpeg, "-y", "-i", video, "-vf", f"fps={fps}",
           "-q:v", "2", pattern]
    try:
        subprocess.run(cmd, capture_output=True, timeout=600,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except Exception as e:
        if progress_cb:
            progress_cb(-1, f"抽帧失败：{e}")
        return None
    frames = sorted(glob.glob(os.path.join(tmp_dir, "frame_*.png")))
    if not frames:
        if progress_cb:
            progress_cb(-1, "未抽到任何帧（视频可能损坏或过短）")
        return None
    return frames


def _ocr_frames(frames, fps, lang, region="bottom", height=0.15,
                progress_cb=None, cancel_check=None):
    """逐帧 OCR，返回 [(start_sec, end_sec, text), ...]（已合并相邻相同文本）。

    region: "bottom" 只识别画面底部字幕区（默认，避免误提屏幕上 UI 文字）、
            "top" 顶部、"full" 全屏（会连屏幕上的其他文字一起识别）。
    height: bottom/top 模式的裁剪高度比例（0.05~0.4，默认 0.15）。
    """
    from core.ocr_tool import _get_engine
    engine = _get_engine()
    from PIL import Image
    import numpy as np
    total = len(frames)
    entries = []
    cur_text = ""
    cur_start = 0.0
    cur_end = 0.0
    try:
        height = max(0.05, min(0.4, float(height or 0.15)))
    except (TypeError, ValueError):
        height = 0.15

    for i, fp in enumerate(frames):
        if cancel_check and cancel_check():
            return None
        start = i / fps
        end = (i + 1) / fps
        text = ""
        try:
            img = Image.open(fp).convert("RGB")
            w, h = img.size
            if region == "bottom":
                # 字幕通常位于画面最底部，裁剪后 OCR 更快更准
                img = img.crop((0, int(h * (1 - height)), w, h))
            elif region == "top":
                img = img.crop((0, 0, w, int(h * height)))
            arr = np.asarray(img)
            img.close()
            result, _ = engine(arr)
            if result:
                text = "\n".join(item[1] for item in result).strip()
        except Exception:
            text = ""

        if progress_cb:
            progress_cb(int(30 + (i + 1) / total * 60), f"识别字幕 {i+1}/{total}…")

        if _normalize(text) == _normalize(cur_text) and text:
            # 与上一帧相同 → 延长结束时间
            cur_end = end
        else:
            if cur_text:
                entries.append((cur_start, cur_end, cur_text))
            cur_text = text
            cur_start = start
            cur_end = end

    if cur_text:
        entries.append((cur_start, cur_end, cur_text))
    return entries


def extract_subtitles(video, output_path, fps=1, lang="chi_sim+eng",
                      region="bottom", height=0.15,
                      progress_cb=None, cancel_check=None, tmp_dir=None):
    """提取视频硬字幕为 .srt 文件，返回是否成功。

    fps: 抽帧率（每秒多少帧），越大字幕时间轴越精确但 OCR 更慢（默认 1）。
    region: 字幕识别区域——"bottom"（底部，默认，避免误提屏幕 UI 文字）/
            "top"（顶部）/"full"（全屏，可能连屏幕其他文字一起提取）。
    height: bottom/top 模式的裁剪高度比例（默认 0.15=底部 15%）。
    tmp_dir: 临时目录，默认系统 temp（自动创建/清理）。
    """
    import tempfile
    import shutil

    duration = _duration_of(video)
    if duration <= 0:
        if progress_cb:
            progress_cb(-1, "无法读取视频时长")
        return False

    own_tmp = tmp_dir is None
    tmp_dir = tmp_dir or tempfile.mkdtemp(prefix="fm_sub_")
    os.makedirs(tmp_dir, exist_ok=True)
    try:
        if progress_cb:
            progress_cb(5, "抽取视频帧…")
        frames = _extract_frames(video, tmp_dir, float(fps) or 1.0,
                                 progress_cb, cancel_check)
        if frames is None:
            return False
        if cancel_check and cancel_check():
            return False
        entries = _ocr_frames(frames, float(fps) or 1.0, lang, region, height,
                              progress_cb, cancel_check)
        if entries is None:
            return False
        if not entries:
            if progress_cb:
                progress_cb(-1, "未识别到字幕文字（视频可能无硬字幕）")
            return False

        if progress_cb:
            progress_cb(95, "生成字幕文件…")
        with open(output_path, "w", encoding="utf-8") as f:
            for idx, (s, e, t) in enumerate(entries, 1):
                f.write(SRT_TEMPLATE.format(
                    idx=idx, start=_fmt_ts(s), end=_fmt_ts(e), text=t))
        if progress_cb:
            progress_cb(100, f"完成，共 {len(entries)} 条字幕")
        return True
    finally:
        if own_tmp and os.path.isdir(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)
