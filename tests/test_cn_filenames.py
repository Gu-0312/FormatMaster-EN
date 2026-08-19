"""中文文件名全链路转换测试。

覆盖：中文文件名（含空格/括号/中文符号/&）作为输入与输出路径时，
视频/音频/图片/文档/PDF/场景/视频工具各转换链路均成功且输出中文名保留。

素材目录 tests/_media/cn（首次运行自动生成），输出 tests/_media/cn_out。
"""
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_media", "cn")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_media", "cn_out")

# 各种中文文件名（含空格/括号/符号）
VIDEO1 = os.path.join(CN_DIR, "测试视频.mp4")
VIDEO2 = os.path.join(CN_DIR, "电影 2024 (高清版).mp4")
VIDEO3 = os.path.join(CN_DIR, "【预告】中文&符号-测试.mp4")
# 带音轨的中文视频（提取音频用）
VIDEO_AUDIO = os.path.join(CN_DIR, "带声音的视频.mp4")
AUDIO = os.path.join(CN_DIR, "音频_测试.wav")
IMAGE = os.path.join(CN_DIR, "图片（风景）.png")
DOCX = os.path.join(CN_DIR, "文档-报告.docx")
XLSX = os.path.join(CN_DIR, "表格数据.xlsx")
PDF = os.path.join(CN_DIR, "PDF文件.pdf")

FF = None


def _ff():
    global FF
    if FF is None:
        from utils.config import get_ffmpeg_path
        FF = get_ffmpeg_path()
    return FF


@pytest.fixture(scope="module", autouse=True)
def _ensure_media():
    """确保中文素材存在（缺则生成）。"""
    os.makedirs(CN_DIR, exist_ok=True)
    ff = _ff()

    def _mk_video(p, with_audio=False):
        if with_audio:
            subprocess.run(
                [ff, "-y", "-f", "lavfi", "-i",
                 "testsrc=duration=2:size=320x240:rate=10",
                 "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                 "-c:v", "libx264", "-preset", "ultrafast",
                 "-c:a", "aac", "-shortest", "-pix_fmt", "yuv420p", p],
                capture_output=True, timeout=60, check=True)
        else:
            subprocess.run(
                [ff, "-y", "-f", "lavfi", "-i",
                 "testsrc=duration=2:size=320x240:rate=10",
                 "-c:v", "libx264", "-preset", "ultrafast",
                 "-pix_fmt", "yuv420p", p],
                capture_output=True, timeout=60, check=True)

    # 逐文件确保素材存在（任何缺失都会补生成）
    for p, wa in ((VIDEO1, False), (VIDEO2, False), (VIDEO3, False),
                  (VIDEO_AUDIO, True)):
        if not os.path.isfile(p):
            _mk_video(p, wa)
    if not os.path.isfile(AUDIO):
        subprocess.run([ff, "-y", "-f", "lavfi", "-i",
                        "sine=frequency=440:duration=2", AUDIO],
                       capture_output=True, timeout=60, check=True)
    if not os.path.isfile(IMAGE):
        from PIL import Image
        Image.new("RGB", (300, 200), (120, 180, 90)).save(IMAGE)
    if not os.path.isfile(DOCX):
        from docx import Document
        d = Document(); d.add_paragraph("中文测试文档内容"); d.save(DOCX)
    if not os.path.isfile(XLSX):
        from openpyxl import Workbook
        wb = Workbook(); wb.active["A1"] = "值"; wb.save(XLSX)
    if not os.path.isfile(PDF):
        from reportlab.pdfgen import canvas
        c = canvas.Canvas(PDF); c.drawString(50, 700, "中文PDF"); c.save()
    shutil.rmtree(OUT_DIR, ignore_errors=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    yield
    shutil.rmtree(OUT_DIR, ignore_errors=True)


def _out(name):
    """输出路径：输出目录 + 中文名（自动避开同名冲突可交给转换器）。"""
    return os.path.join(OUT_DIR, name)


# ── 视频 ────────────────────────────────────────
class TestCnVideo:
    def test_convert_to_avi(self):
        """中文视频 → AVI（中文输出名保留）。"""
        from core.video_converter import VideoConverter
        out = _out("测试视频.avi")
        assert VideoConverter().convert(VIDEO1, out, ".avi", "libx264", "ultrafast")
        assert os.path.isfile(out) and os.path.getsize(out) > 0

    def test_convert_weird_name(self):
        """含空格/括号/中文符号/& 的视频名 → MKV。"""
        from core.video_converter import VideoConverter
        out = _out("电影 2024 (高清版).mkv")
        assert VideoConverter().convert(VIDEO2, out, ".mkv", "libx264", "ultrafast")
        assert os.path.isfile(out) and os.path.getsize(out) > 0

    def test_convert_symbol_name(self):
        """【预告】中文&符号-测试 → MP4（重编码）。"""
        from core.video_converter import VideoConverter
        out = _out("【预告】中文&符号-测试_转码.mp4")
        assert VideoConverter().convert(VIDEO3, out, ".mp4", "libx264", "medium")
        assert os.path.isfile(out) and os.path.getsize(out) > 0

    def test_stream_copy(self):
        """中文视频 copy 流模式。"""
        from core.video_converter import VideoConverter
        out = _out("测试视频_copy.mp4")
        assert VideoConverter().convert(VIDEO1, out, ".mp4", "copy", "medium", copy_mode=True)
        assert os.path.isfile(out) and os.path.getsize(out) > 0

    def test_scene_convert(self):
        """场景化转换（中文输入）。"""
        from core.scene import convert_scene
        out = _out("测试视频_场景.mp4")
        assert convert_scene(VIDEO1, out, "wechat")
        assert os.path.isfile(out) and os.path.getsize(out) > 0


# ── 视频工具 ─────────────────────────────────────
class TestCnVideoTools:
    def test_clip(self):
        from core.video_tools import clip_video
        out = _out("测试视频_剪辑.mp4")
        assert clip_video(VIDEO1, out, 0, 1, progress_cb=lambda *a: None)
        assert os.path.isfile(out) and os.path.getsize(out) > 0

    def test_speed(self):
        from core.video_tools import change_speed
        out = _out("测试视频_变速.mp4")
        assert change_speed(VIDEO1, out, rate=2.0, progress_cb=lambda *a: None)
        assert os.path.isfile(out) and os.path.getsize(out) > 0

    def test_compress(self):
        from core.video_compress import VideoCompressor
        out = _out("测试视频_压缩.mp4")
        assert VideoCompressor().compress(VIDEO1, out, crf=30, max_height=120,
                                          progress_callback=lambda *a: None)
        assert os.path.isfile(out) and os.path.getsize(out) > 0

    def test_frame_extract(self):
        """中文视频抽帧：帧文件也为中文名。"""
        from core.video_frame_extract import extract_frames
        d = _out("抽取帧")
        os.makedirs(d, exist_ok=True)
        assert extract_frames(VIDEO1, d, interval_sec=1, fmt="JPG")
        assert len(os.listdir(d)) >= 1

    def test_extract_audio(self):
        """中文视频（带音轨）提取音频。"""
        from core.video_converter import VideoConverter
        out = _out("测试视频_音频.mp3")
        assert VideoConverter().extract_audio(VIDEO_AUDIO, out, "mp3", "128k")
        assert os.path.isfile(out) and os.path.getsize(out) > 0

    def test_merge(self):
        """中文名视频合并。"""
        from core.video_merge import merge_videos
        out = _out("合并视频.mp4")
        assert merge_videos([VIDEO1, VIDEO2], out, progress_cb=lambda *a: None)
        assert os.path.isfile(out) and os.path.getsize(out) > 0


# ── 音频 ─────────────────────────────────────────
class TestCnAudio:
    def test_convert_mp3(self):
        from core.audio_converter import AudioConverter
        out = _out("音频_测试.mp3")
        assert AudioConverter().convert(AUDIO, out, codec="libmp3lame")
        assert os.path.isfile(out) and os.path.getsize(out) > 0

    def test_trim(self):
        from core.audio_trimmer import trim_audio
        out = _out("音频_测试_裁剪.wav")
        assert trim_audio(AUDIO, out, 0, 1, progress_cb=lambda *a: None)
        assert os.path.isfile(out) and os.path.getsize(out) > 0


# ── 图片 ─────────────────────────────────────────
class TestCnImage:
    def test_convert_jpg(self):
        from core.image_converter import ImageConverter
        out = _out("图片（风景）.jpg")
        assert ImageConverter().convert(IMAGE, out)
        assert os.path.isfile(out) and os.path.getsize(out) > 0

    def test_compress(self):
        from core.tools import image_compress
        out = _out("图片（风景）_压缩.jpg")
        assert image_compress(IMAGE, out, quality=60)
        assert os.path.isfile(out) and os.path.getsize(out) > 0


# ── 文档 / 表格 / PDF ────────────────────────────
class TestCnDocument:
    def test_docx_txt(self):
        from core.doc_converter import DocumentConverter
        out = _out("文档-报告.txt")
        assert DocumentConverter().convert(DOCX, out)
        assert os.path.isfile(out) and os.path.getsize(out) > 0

    def test_xlsx_csv(self):
        from core.doc_converter import DocumentConverter
        out = _out("表格数据.csv")
        assert DocumentConverter().convert(XLSX, out)
        assert os.path.isfile(out) and os.path.getsize(out) > 0

    def test_pdf_encrypt(self):
        """中文 PDF 加密/解密。"""
        from core.tools import pdf_encrypt, pdf_decrypt
        enc = _out("PDF文件_加密.pdf")
        assert pdf_encrypt(PDF, enc, open_password="123", owner_password="456")
        dec = _out("PDF文件_解密.pdf")
        assert pdf_decrypt(enc, dec, password="123")
        assert os.path.isfile(dec) and os.path.getsize(dec) > 0

    def test_pdf_merge(self):
        """中文 PDF 与另一 PDF 合并（复制一份做第二个源）。"""
        from core.tools import pdf_merge
        pdf2 = _out("PDF文件_副本.pdf")
        shutil.copy(PDF, pdf2)
        merged = _out("合并PDF文件.pdf")
        assert pdf_merge([PDF, pdf2], merged)
        assert os.path.isfile(merged) and os.path.getsize(merged) > 0
