"""视频缩略图墙 — FFmpeg 提取帧 + Pillow 网格合成

从视频中按时间间隔提取多帧，生成 N×M 网格缩略图。
"""

import os
import subprocess
import tempfile
from utils.config import get_ffmpeg_path


def generate_thumbnail_sheet(video_path, output_path, cols=4, rows=4, width=1600, progress_cb=None):
    """从视频生成缩略图网格。

    参数:
      video_path: 视频文件路径
      output_path: 输出 PNG 路径
      cols: 列数
      rows: 行数
      width: 输出图片总宽度（像素）
      progress_cb: 进度回调 (pct: int, msg: str)

    返回 bool。
    """
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        if progress_cb:
            progress_cb(-1, "错误: FFmpeg 未安装")
        return False

    if not os.path.isfile(video_path):
        if progress_cb:
            progress_cb(-1, "错误: 找不到视频文件")
        return False

    # 获取视频时长
    from utils.config import get_ffprobe_path
    ffprobe = get_ffprobe_path()
    duration = 0
    if ffprobe:
        try:
            import json
            cmd = [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", video_path]
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                               errors="ignore", timeout=10,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            if r.returncode == 0 and r.stdout:
                d = json.loads(r.stdout)
                duration = float(d.get("format", {}).get("duration", 0))
        except Exception:
            duration = 0

    if duration <= 0:
        if progress_cb:
            progress_cb(-1, "错误: 无法获取视频时长")
        return False

    total_frames = cols * rows
    interval = duration / (total_frames + 1)

    # 创建临时目录存放帧
    tmp_dir = tempfile.mkdtemp(prefix="thumb_")
    frame_files = []

    try:
        if progress_cb:
            progress_cb(5, f"提取 {total_frames} 帧…")

        thumb_w = width // cols
        for i in range(total_frames):
            t = interval * (i + 1)
            hh = int(t // 3600)
            mm = int((t % 3600) // 60)
            ss = t % 60
            ts = f"{hh:02d}:{mm:02d}:{ss:06.3f}"
            frame_path = os.path.join(tmp_dir, f"frame_{i:03d}.png")
            cmd = [
                ffmpeg, "-y", "-ss", ts, "-i", video_path,
                "-vframes", "1", "-vf", f"scale={thumb_w}:-1", frame_path
            ]
            subprocess.run(cmd, capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            if os.path.exists(frame_path):
                frame_files.append(frame_path)
            pct = 5 + int((i + 1) / total_frames * 70)
            if progress_cb:
                progress_cb(pct, f"提取帧 {i + 1}/{total_frames}")

        if not frame_files:
            if progress_cb:
                progress_cb(-1, "错误: 未能提取任何帧")
            return False

        # 用 Pillow 合成网格
        if progress_cb:
            progress_cb(80, "合成缩略图网格…")

        from PIL import Image
        actual_cols = min(cols, len(frame_files))
        actual_rows = (len(frame_files) + actual_cols - 1) // actual_cols

        # 计算每格尺寸
        cell_w = 0
        cell_h = 0
        for fp in frame_files:
            img = Image.open(fp)
            cell_w = max(cell_w, img.size[0])
            cell_h = max(cell_h, img.size[1])
            img.close()

        # 创建画布
        canvas = Image.new("RGB", (cell_w * actual_cols, cell_h * actual_rows), (30, 30, 30))

        for i, fp in enumerate(frame_files):
            r, c = divmod(i, actual_cols)
            img = Image.open(fp)
            x = c * cell_w + (cell_w - img.size[0]) // 2
            y = r * cell_h + (cell_h - img.size[1]) // 2
            canvas.paste(img, (x, y))
            img.close()

        canvas.save(output_path, "PNG")
        if progress_cb:
            progress_cb(100, "缩略图生成完成")
        return True
    finally:
        # 清理临时帧
        for fp in frame_files:
            try:
                os.remove(fp)
            except OSError:
                pass
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass