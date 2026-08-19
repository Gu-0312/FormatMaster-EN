"""带 FFmpeg 的扩展滤镜真实链路测试（2026-08-15 新增）。

覆盖：视频倒放 / 转GIF / 文字水印 / 稳定 / 画质 / 裁剪 / 去隔行 /
音轨替换 / 混音 / 音频人声·伴奏提取 / EQ / 压限 / 去静音 / 变调 /
音频拼接 / 转换元数据写入。

运行:venv/Scripts/python -m pytest tests/test_ffmpeg_fx.py -q
前置:bin/ffmpeg.exe 存在（无则跳过）。
"""
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TMP = tempfile.mkdtemp(prefix="fm_fx_")
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


@pytest.fixture(scope="module")
def src_video():
    """带音频的测试视频。"""
    ff = _ff()
    p = os.path.join(TMP, "src.mp4")
    subprocess.run(
        [ff, "-y", "-f", "lavfi", "-i",
         "testsrc=duration=2:size=160x90:rate=15",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", p],
        capture_output=True)
    return p


@pytest.fixture(scope="module")
def src_audio():
    """单声道测试音频（人声提取用）。"""
    ff = _ff()
    p = os.path.join(TMP, "voice.m4a")
    subprocess.run(
        [ff, "-y", "-f", "lavfi", "-i",
         "sine=frequency=440:duration=1", "-c:a", "aac", p],
        capture_output=True)
    return p


def _ok(fn):
    return fn() is True


class TestVideoFx:
    def test_reverse(self, src_video):
        from core.video_tools import reverse_video
        out = os.path.join(TMP, "rev.mp4")
        assert _ok(lambda: reverse_video(src_video, out, keep_audio=True))
        assert os.path.isfile(out) and os.path.getsize(out) > 0

    def test_video_to_gif(self, src_video):
        from core.video_tools import video_to_gif
        out = os.path.join(TMP, "out.gif")
        assert _ok(lambda: video_to_gif(src_video, out, fps=10, max_width=160))
        assert os.path.isfile(out) and os.path.getsize(out) > 0
        with open(out, "rb") as f:
            assert f.read(6) in (b"GIF87a", b"GIF89a"), "不是有效 GIF"

    def test_text_watermark(self, src_video):
        from core.video_tools import burn_text_watermark
        out = os.path.join(TMP, "wm.mp4")
        assert _ok(lambda: burn_text_watermark(
            src_video, out, "格式大师", font_size=24))
        assert os.path.isfile(out) and os.path.getsize(out) > 0

    def test_stabilize(self, src_video):
        from core.video_tools import stabilize_video
        out = os.path.join(TMP, "stab.mp4")
        assert _ok(lambda: stabilize_video(src_video, out))
        assert os.path.isfile(out) and os.path.getsize(out) > 0

    def test_enhance(self, src_video):
        from core.video_tools import enhance_video
        out = os.path.join(TMP, "enh.mp4")
        assert _ok(lambda: enhance_video(src_video, out, sharpen=0.8, denoise=2))
        assert os.path.isfile(out) and os.path.getsize(out) > 0

    def test_crop(self, src_video):
        from core.video_tools import crop_video
        out = os.path.join(TMP, "crop.mp4")
        assert _ok(lambda: crop_video(src_video, out, 10, 10, 80, 60))
        assert os.path.isfile(out) and os.path.getsize(out) > 0

    def test_deinterlace(self, src_video):
        from core.video_tools import deinterlace_video
        out = os.path.join(TMP, "deint.mp4")
        assert _ok(lambda: deinterlace_video(src_video, out))
        assert os.path.isfile(out) and os.path.getsize(out) > 0

    def test_replace_audio(self, src_video, src_audio):
        from core.video_tools import replace_audio
        out = os.path.join(TMP, "rep.mp4")
        assert _ok(lambda: replace_audio(src_video, src_audio, out))
        assert os.path.isfile(out) and os.path.getsize(out) > 0

    def test_mix_audio(self, src_video, src_audio):
        from core.video_tools import mix_audio
        out = os.path.join(TMP, "mix.mp4")
        assert _ok(lambda: mix_audio(src_video, src_audio, out, bg_volume=0.3))
        assert os.path.isfile(out) and os.path.getsize(out) > 0


class TestAudioFx:
    def test_extract_vocal(self, src_audio):
        from core.audio_tools import extract_vocal
        out = os.path.join(TMP, "voc.m4a")
        assert _ok(lambda: extract_vocal(src_audio, out))
        assert os.path.isfile(out) and os.path.getsize(out) > 0

    def test_extract_music(self, src_audio):
        from core.audio_tools import extract_music
        out = os.path.join(TMP, "mus.m4a")
        assert _ok(lambda: extract_music(src_audio, out))
        assert os.path.isfile(out) and os.path.getsize(out) > 0

    def test_equalizer(self, src_audio):
        from core.audio_tools import audio_equalizer
        out = os.path.join(TMP, "eq.m4a")
        assert _ok(lambda: audio_equalizer(src_audio, out, low=3, high=2))
        assert os.path.isfile(out) and os.path.getsize(out) > 0

    def test_compress(self, src_audio):
        from core.audio_tools import audio_compress
        out = os.path.join(TMP, "comp.m4a")
        assert _ok(lambda: audio_compress(src_audio, out))
        assert os.path.isfile(out) and os.path.getsize(out) > 0

    def test_remove_silence(self, src_audio):
        from core.audio_tools import remove_silence
        out = os.path.join(TMP, "sil.m4a")
        assert _ok(lambda: remove_silence(src_audio, out))
        assert os.path.isfile(out) and os.path.getsize(out) > 0

    def test_pitch(self, src_audio):
        from core.audio_tools import audio_pitch
        out = os.path.join(TMP, "pitch.m4a")
        assert _ok(lambda: audio_pitch(src_audio, out, semitones=2))
        assert os.path.isfile(out) and os.path.getsize(out) > 0

    def test_concat_audio(self, src_audio):
        from core.audio_tools import concat_audio
        out = os.path.join(TMP, "aconcat.m4a")
        assert _ok(lambda: concat_audio([src_audio, src_audio], out))
        assert os.path.isfile(out) and os.path.getsize(out) > 0


class TestMetadata:
    def test_convert_writes_metadata(self, src_video):
        from core.video_converter import VideoConverter
        from core.ffmpeg_executor import get_ffprobe_raw
        out = os.path.join(TMP, "meta.mp4")
        cv = VideoConverter()
        ok = cv.convert(src_video, out, ".mp4", "libx264", "medium",
                        None, None, None, None,
                        metadata={"title": "测试标题", "artist": "格式大师"})
        assert ok
        raw = get_ffprobe_raw(out)
        tags = (raw or {}).get("format", {}).get("tags", {})
        assert tags.get("title") == "测试标题"
        assert tags.get("artist") == "格式大师"
