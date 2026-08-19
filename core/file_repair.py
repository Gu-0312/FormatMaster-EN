"""core/file_repair — 文件损坏自动修复（独立模块，纯逻辑可测）。

供转换链路在检测到源文件损坏时调用，也可独立使用。

修复策略按类型分级：能无损重封装就复制，否则重编码。
支持类型：
- 图片（jpg/png/bmp/webp/tiff/gif/avif…）：PIL 容错加载 + 重新编码；
  对截断/尾部垃圾的损坏图片自动截短重读
- 视频/音频（mp4/mkv/avi/mov/ts/flv/mp3/wav/aac/flac/m4a…）：
  ffmpeg 流复制重封装（修复容器/moov atom 索引）→ 失败则重编码
- PDF：PyMuPDF(fitz) 逐页重建（跳过损坏页）
- 压缩文档（docx/xlsx/pptx/zip）：zipfile 容错重建（跳过 CRC 校验失败条目）

对外接口：repair_file(path, out_dir=None) -> RepairResult；detect_type(path)。
"""
import os
import subprocess
from dataclasses import dataclass

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tiff', '.gif',
              '.avif', '.ico', '.tga'}
VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm',
              '.m4v', '.mpg', '.mpeg', '.ts', '.3gp'}
AUDIO_EXTS = {'.mp3', '.wav', '.aac', '.flac', '.ogg', '.m4a', '.wma',
              '.opus', '.amr'}
MEDIA_EXTS = VIDEO_EXTS | AUDIO_EXTS
PDF_EXTS = {'.pdf'}
ZIP_EXTS = {'.docx', '.xlsx', '.pptx', '.docm', '.xlsm', '.pptm', '.zip'}


@dataclass
class RepairResult:
    success: bool = False     # 修复后文件是否可用
    path: str = ""            # 修复后的文件路径（修复副本；未损坏时为原路径）
    method: str = ""          # 使用的修复方式（中文描述）
    detail: str = ""          # 失败原因 / 补充说明


def detect_type(path: str):
    """按扩展名判断文件类型：'image' / 'media' / 'pdf' / 'zip' / None。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in MEDIA_EXTS:
        return "media"
    if ext in PDF_EXTS:
        return "pdf"
    if ext in ZIP_EXTS:
        return "zip"
    return None


def _unique_path(out_dir, orig_path, suffix="_repaired"):
    """生成不与现有文件冲突的修复输出路径。"""
    name = os.path.splitext(os.path.basename(orig_path))[0]
    ext = os.path.splitext(orig_path)[1]
    p = os.path.join(out_dir, f"{name}{suffix}{ext}")
    n = 1
    while os.path.exists(p):
        p = os.path.join(out_dir, f"{name}{suffix}_{n}{ext}")
        n += 1
    return p


def _run_ffmpeg(cmd, timeout=180):
    """执行 ffmpeg 命令；成功返回 True（不抛、无窗口）。"""
    try:
        subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=timeout, check=False,
            creationflags=(subprocess.CREATE_NO_WINDOW
                           if os.name == "nt" else 0))
        return True
    except Exception:  # noqa: BLE001 - 任何失败均视为修复失败
        return False


def _probe_media(path):
    """ffprobe 读取媒体信息；能读出返回 dict（未损坏），失败返回 None。"""
    try:
        from core.ffmpeg_executor import get_ffprobe_raw
        return get_ffprobe_raw(path, timeout=5)
    except Exception:  # noqa: BLE001
        return None


# ── 图片 ─────────────────────────────────────────
def _load_image_by_truncating(path):
    """对截断/尾部带垃圾的损坏图片：逐步截短尾部后重读，返回内存副本。"""
    from PIL import Image
    size = os.path.getsize(path)
    for ratio in (0.95, 0.90, 0.80, 0.70):
        cut = int(size * ratio)
        if cut <= 0:
            break
        tmp = path + ".trunc.tmp"
        try:
            with open(path, "rb") as f:
                data = f.read(cut)
            with open(tmp, "wb") as f:
                f.write(data)
            im = Image.open(tmp)
            im.load()          # 强制完整解码
            im = im.copy()     # 复制到内存，与临时文件解耦
            im.close()
            return im
        except Exception:  # noqa: BLE001 - 尝试下一截断比例
            try:
                im.close()
            except Exception:  # noqa: BLE001
                pass
            try:
                os.remove(tmp)
            except OSError:
                pass
    return None


def _repair_image(path, out_dir):
    try:
        from PIL import Image, ImageFile
    except ImportError:
        return RepairResult(False, path, "", "缺少 Pillow，无法修复图片")
    # 完整解码检测：verify() 只查头，load() 才真正解码像素
    try:
        with Image.open(path) as im:
            im.load()
        return RepairResult(False, path, "")
    except Exception:  # noqa: BLE001 - 解码失败视为损坏
        pass
    # 容错加载（截断图片允许加载）+ 尾部截短重读
    img = None
    old_flag = getattr(ImageFile, "LOAD_TRUNCATED_IMAGES", False)
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    try:
        try:
            with Image.open(path) as _f:
                img = _f.copy()  # 强制完整解码 + 释放句柄
        except Exception:  # noqa: BLE001
            img = _load_image_by_truncating(path)
    finally:
        ImageFile.LOAD_TRUNCATED_IMAGES = old_flag
    if img is None:
        return RepairResult(False, path, "", "图片损坏且无法自动修复")
    out = _unique_path(out_dir, path)
    try:
        img.save(out)
        img.close()
        with Image.open(out) as v:
            v.load()           # 验证修复副本可完整解码
        return RepairResult(True, out, "图片损坏，已重新编码修复")
    except Exception as e:  # noqa: BLE001
        return RepairResult(False, path, "", f"图片修复失败：{e}")


# ── 视频 / 音频 ──────────────────────────────────
def _repair_media(path, out_dir):
    from utils.config import get_ffmpeg_path
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        return RepairResult(False, path, "", "FFmpeg 未就绪，无法修复")
    if _probe_media(path):
        return RepairResult(False, path, "")   # 能读取元数据，未损坏
    is_audio = os.path.splitext(path)[1].lower() in AUDIO_EXTS
    out = _unique_path(out_dir, path)

    # 1. 流复制重封装（修复容器索引/moov atom，无损）
    if is_audio:
        cmd = [ffmpeg, "-y", "-err_detect", "ignore_err",
               "-i", path, "-map", "0",
               "-c", "copy", "-map_metadata", "0", out]
    else:
        cmd = [ffmpeg, "-y", "-err_detect", "ignore_err",
               "-i", path, "-map", "0",
               "-c", "copy", "-map_metadata", "0", out]
    if (_run_ffmpeg(cmd, timeout=180)
            and os.path.isfile(out) and _probe_media(out)):
        return RepairResult(True, out, "媒体流复制重封装修复")

    # 2. 重编码（处理解码损坏的流，耗时兜底）
    if is_audio:
        cmd = [ffmpeg, "-y", "-err_detect", "ignore_err",
               "-i", path, "-c:a", "aac", "-b:a", "192k", out]
    else:
        cmd = [ffmpeg, "-y", "-err_detect", "ignore_err",
               "-i", path, "-c:v", "libx264", "-crf", "23",
               "-preset", "fast", "-c:a", "aac", "-b:a", "192k",
               "-movflags", "+faststart", out]
    if (_run_ffmpeg(cmd, timeout=600)
            and os.path.isfile(out) and _probe_media(out)):
        return RepairResult(True, out, "媒体重编码修复")
    try:
        if os.path.isfile(out):
            os.remove(out)   # 清理修复失败残留
    except OSError:
        pass
    return RepairResult(False, path, "", "媒体文件损坏且无法自动修复")


# ── PDF ──────────────────────────────────────────
def _repair_pdf(path, out_dir):
    try:
        import pymupdf
    except ImportError:
        return RepairResult(False, path, "", "缺少 PyMuPDF，无法修复 PDF")
    try:
        with pymupdf.open(path) as doc:
            if doc.page_count > 0:
                return RepairResult(False, path, "")
    except Exception:  # noqa: BLE001
        pass
    # 逐页重建，跳过损坏页
    try:
        src = pymupdf.open(path)
        new = pymupdf.open()
        for i in range(src.page_count):
            try:
                new.insert_pdf(src, from_page=i, to_page=i)
            except Exception:  # noqa: BLE001 - 单页损坏跳过
                continue
        if new.page_count > 0:
            out = _unique_path(out_dir, path)
            new.save(out)
            new.close()
            src.close()
            try:
                with pymupdf.open(out) as v:
                    if v.page_count > 0:
                        return RepairResult(True, out, "PDF 重建修复")
            except Exception:  # noqa: BLE001
                pass
            return RepairResult(False, path, "", "PDF 修复后仍无法打开")
        new.close()
        src.close()
    except Exception as e:  # noqa: BLE001
        return RepairResult(False, path, "", f"PDF 修复失败：{e}")
    return RepairResult(False, path, "", "PDF 损坏且无法自动修复")


# ── 压缩文档（docx/xlsx/pptx/zip）───────────────
def _repair_zip(path, out_dir):
    import zipfile
    try:
        with zipfile.ZipFile(path) as z:
            bad = z.testzip()   # 检查是否有 CRC 校验失败条目
        if bad is None:
            return RepairResult(False, path, "")   # 完整无损坏
    except Exception:  # noqa: BLE001 - 打不开即损坏
        pass
    try:
        z = zipfile.ZipFile(path)
        names = z.namelist()
    except Exception as e:  # noqa: BLE001
        return RepairResult(False, path, "", f"压缩包无法读取：{e}")
    out = _unique_path(out_dir, path)
    copied = 0
    try:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zo:
            for name in names:
                try:
                    data = z.read(name)
                    zo.writestr(name, data)
                    copied += 1
                except Exception:  # noqa: BLE001 - 跳过损坏条目
                    continue
        z.close()
    except Exception as e:  # noqa: BLE001
        return RepairResult(False, path, "", f"压缩包重建失败：{e}")
    if copied > 0:
        return RepairResult(True, out, f"压缩包重建修复（保留 {copied} 个条目）")
    return RepairResult(False, path, "", "压缩文档损坏且无法自动修复")


# ── 入口 ─────────────────────────────────────────
_HANDLERS = {
    "image": _repair_image,
    "media": _repair_media,
    "pdf": _repair_pdf,
    "zip": _repair_zip,
}


def repair_file(path, out_dir=None):
    """修复损坏文件。

    path: 源文件路径；out_dir: 修复副本输出目录（默认源文件所在目录）。
    返回 RepairResult；未损坏时 success=False 且 path=原路径。
    """
    if not path or not os.path.isfile(path):
        return RepairResult(False, path or "", "", "文件不存在")
    kind = detect_type(path)
    handler = _HANDLERS.get(kind)
    if handler is None:
        return RepairResult(False, path, "", "不支持自动修复的类型")
    out_dir = out_dir or os.path.dirname(os.path.abspath(path))
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as e:
        return RepairResult(False, path, "", f"无法创建输出目录：{e}")
    return handler(path, out_dir)
