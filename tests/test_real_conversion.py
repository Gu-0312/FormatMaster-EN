"""带 FFmpeg 的真实转换链路测试（属性组合全覆盖）。

运行:venv/Scripts/python -m pytest tests/test_real_conversion.py -q
前置:bin/ffmpeg.exe 存在（无则跳过，不硬性要求）
"""
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import wave

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TMP = tempfile.mkdtemp(prefix="fm_real_")
FF = None


def _ff():
    global FF
    if FF is None:
        from utils.config import get_ffmpeg_path
        FF = get_ffmpeg_path()
    return FF


@pytest.fixture(scope="module", autouse=True)
def _check_ffmpeg():
    if not _ff() or not os.path.isfile(_ff()):
        pytest.skip("FFmpeg 不可用，跳过真实转换测试")
    yield
    shutil.rmtree(TMP, ignore_errors=True)


def _make_video(path, duration=1, size="160x120", rate=10, with_audio=False):
    ff = _ff()
    if with_audio:
        r = subprocess.run(
            [ff, "-y", "-f", "lavfi", "-i",
             f"testsrc=duration={duration}:size={size}:rate={rate}",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
             "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-shortest", path],
            capture_output=True, timeout=60)
    else:
        r = subprocess.run(
            [ff, "-y", "-f", "lavfi", "-i",
             f"testsrc=duration={duration}:size={size}:rate={rate}",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", path],
            capture_output=True, timeout=60)
    assert r.returncode == 0, r.stderr[-300:]


def _make_wav(path, seconds=1):
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        w.writeframes(b"".join(struct.pack("<h", 8000) for _ in range(8000 * seconds)))


def _make_png(path, size=(200, 120), color=(200, 100, 50)):
    from PIL import Image
    Image.new("RGB", size, color).save(path)


def _make_pdf(path):
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(path); c.drawString(50, 700, "hello pdf"); c.save()


def _make_docx(path):
    from docx import Document
    d = Document(); d.add_paragraph("hello 测试"); d.save(path)


class TestVideoParams:
    """视频转换属性组合：格式/编码/分辨率/帧率/画质。"""

    def test_formats(self):
        from core.video_converter import VideoConverter
        src = os.path.join(TMP, "vp.mp4"); _make_video(src)
        cv = VideoConverter()
        # webm 容器需 vp9 编码（libx264 不兼容），其余 libx264
        for ext in (".avi", ".mkv", ".mov", ".ts", ".flv"):
            out = os.path.join(TMP, f"vp{ext}")
            assert cv.convert(src, out, ext, "libx264", "medium"), f"{ext} 转换失败"
            assert os.path.isfile(out) and os.path.getsize(out) > 0
        out = os.path.join(TMP, "vp.webm")
        assert cv.convert(src, out, ".webm", "libvpx-vp9", "medium"), ".webm 转换失败"
        assert os.path.isfile(out) and os.path.getsize(out) > 0

    def test_resolution_and_fps(self):
        from core.video_converter import VideoConverter
        src = os.path.join(TMP, "vp2.mp4"); _make_video(src)
        cv = VideoConverter()
        out = os.path.join(TMP, "vp2_360.mp4")
        assert cv.convert(src, out, ".mp4", "libx264", "medium", resolution="360p", fps=24)
        ffprobe = _ff().replace("ffmpeg.exe", "ffprobe.exe")
        r = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", out], capture_output=True, timeout=30)
        w, h = r.stdout.decode().strip().split(",")
        assert int(h) <= 360, f"分辨率未生效 h={h}"

    def test_stream_copy(self):
        from core.video_converter import VideoConverter
        src = os.path.join(TMP, "vp3.mp4"); _make_video(src)
        out = os.path.join(TMP, "vp3_copy.mkv")
        assert VideoConverter().convert(src, out, ".mkv", "copy", "medium", copy_mode=True)


class TestVideoTools:
    """视频工具：剪辑/变速/去水印/抽帧/合并/反挤压。"""

    def test_clip(self):
        from core.video_tools import clip_video
        src = os.path.join(TMP, "vt.mp4"); _make_video(src, duration=2)
        out = os.path.join(TMP, "vt_clip.mp4")
        assert clip_video(src, out, start_sec=0, end_sec=1, progress_cb=lambda *a: None)
        assert os.path.isfile(out) and os.path.getsize(out) > 0

    def test_speed(self):
        from core.video_tools import change_speed
        src = os.path.join(TMP, "vt2.mp4"); _make_video(src, duration=2)
        out = os.path.join(TMP, "vt2_spd.mp4")
        assert change_speed(src, out, rate=2.0, progress_cb=lambda *a: None)

    def test_remove_logo(self):
        from core.video_tools import remove_logo
        src = os.path.join(TMP, "vt3.mp4"); _make_video(src)
        out = os.path.join(TMP, "vt3_delogo.mp4")
        assert remove_logo(src, out, 10, 10, 30, 30, progress_cb=lambda *a: None)

    def test_frame_extract(self):
        from core.video_frame_extract import extract_frames
        src = os.path.join(TMP, "vt4.mp4"); _make_video(src, duration=2)
        out_dir = os.path.join(TMP, "frames")
        os.makedirs(out_dir, exist_ok=True)
        assert extract_frames(src, out_dir, interval_sec=0.5, fmt="JPG")
        assert len(os.listdir(out_dir)) >= 1

    def test_merge(self):
        from core.video_merge import merge_videos
        a = os.path.join(TMP, "vm1.mp4"); _make_video(a, duration=1)
        b = os.path.join(TMP, "vm2.mp4"); _make_video(b, duration=1)
        out = os.path.join(TMP, "vm_merged.mp4")
        assert merge_videos([a, b], out, progress_cb=lambda *a: None)

    def test_unwarp(self):
        from core.video_unwarp import fix_aspect
        src = os.path.join(TMP, "vu.mp4"); _make_video(src)
        out = os.path.join(TMP, "vu_fixed.mp4")
        assert fix_aspect(src, out, target="auto", progress_cb=lambda *a: None)

    def test_compress(self):
        from core.video_compress import VideoCompressor
        src = os.path.join(TMP, "vc.mp4"); _make_video(src)
        out = os.path.join(TMP, "vc_c.mp4")
        assert VideoCompressor().compress(src, out, crf=30, max_height=120,
                                          progress_callback=lambda *a: None)


class TestAudioTools:
    """音频工具：裁剪/降噪/标准化/音量。"""

    def test_trim(self):
        from core.audio_trimmer import trim_audio
        src = os.path.join(TMP, "at.wav"); _make_wav(src, seconds=2)
        out = os.path.join(TMP, "at_trim.wav")
        assert trim_audio(src, out, start_sec=0, end_sec=1, progress_cb=lambda *a: None)

    def test_denoise(self):
        from core.audio_tools import denoise
        src = os.path.join(TMP, "at2.wav"); _make_wav(src)
        out = os.path.join(TMP, "at2_den.wav")
        assert denoise(src, out, strength=20, progress_cb=lambda *a: None)

    def test_normalize_loudnorm(self):
        from core.audio_norm import normalize_audio
        src = os.path.join(TMP, "at3.wav"); _make_wav(src)
        out = os.path.join(TMP, "at3_norm.wav")
        assert normalize_audio(src, out, target_lufs=-16, progress_cb=lambda *a: None)

    def test_volume(self):
        from core.audio_converter import AudioConverter
        src = os.path.join(TMP, "at4.wav"); _make_wav(src)
        out = os.path.join(TMP, "at4_vol.mp3")
        assert AudioConverter().convert(src, out, codec="libmp3lame", volume=150)


class TestPdfTools:
    """PDF 工具：加密/解密/合并/拆分/压缩/水印/页码。"""

    def _pdfs(self):
        a = os.path.join(TMP, "p1.pdf"); b = os.path.join(TMP, "p2.pdf")
        _make_pdf(a); _make_pdf(b)
        return a, b

    def test_encrypt_decrypt(self):
        from core.tools import pdf_encrypt, pdf_decrypt, pdf_is_encrypted
        a, _ = self._pdfs()
        enc = os.path.join(TMP, "p_enc.pdf")
        assert pdf_encrypt(a, enc, open_password="123", owner_password="456")
        assert pdf_is_encrypted(enc)
        dec = os.path.join(TMP, "p_dec.pdf")
        assert pdf_decrypt(enc, dec, password="123")
        assert not pdf_is_encrypted(dec)

    def test_merge_split(self):
        from core.tools import pdf_merge, pdf_split
        a, b = self._pdfs()
        merged = os.path.join(TMP, "p_merged.pdf")
        assert pdf_merge([a, b], merged)
        out_dir = os.path.join(TMP, "p_split")
        os.makedirs(out_dir, exist_ok=True)
        assert pdf_split(merged, out_dir, [(1, 1), (2, 2)])

    def test_compress(self):
        from core.tools import pdf_compress
        a, _ = self._pdfs()
        out = os.path.join(TMP, "p_c.pdf")
        assert pdf_compress(a, out, target_dpi=100, quality=70)

    def test_watermark_and_pagenum(self):
        from core.tools import pdf_add_watermark, pdf_add_page_numbers
        a, _ = self._pdfs()
        wm = os.path.join(TMP, "p_wm.pdf")
        assert pdf_add_watermark(a, wm, "水印TEST", pos="右下角")
        pn = os.path.join(TMP, "p_pn.pdf")
        assert pdf_add_page_numbers(a, pn, start=1, pos="底部居中")


class TestScene:
    def test_scene_all(self):
        from core.scene import convert_scene, SCENE_KEYS
        src = os.path.join(TMP, "sc.mp4"); _make_video(src)
        for key in SCENE_KEYS:
            out = os.path.join(TMP, f"sc_{key}.mp4")
            ok = convert_scene(src, out, key)
            assert ok, f"场景 {key} 转换失败"
            assert os.path.isfile(out), f"场景 {key} 无输出"
