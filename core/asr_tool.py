# -*- coding: utf-8 -*-
"""asr_tool — 语音转文字字幕（ASR，基于 sherpa-onnx + 中文流式模型）。

流程：FFmpeg 提取音频为 16k 单声道 WAV → sherpa-onnx OnlineRecognizer 识别
（输出带 token 级时间戳）→ 按标点/停顿切句生成 .srt。
模型首次使用时自动下载到用户数据目录 models/（约 126MB，离线后可复用）。
"""
import os
import subprocess
import tarfile
import urllib.request

from utils.config import get_ffmpeg_path, get_user_data_dir

# sherpa-onnx 引擎（延迟 import，缺失时给出明确提示而非笼统 ModuleNotFoundError）
try:
    import sherpa_onnx
    _ENGINE_OK = True
except ImportError:
    sherpa_onnx = None
    _ENGINE_OK = False

ENGINE_MISSING_MSG = ("语音识别引擎（sherpa-onnx）未安装。请用项目虚拟环境运行："
                      "venv\\Scripts\\python main_qt.py（或执行 pip install sherpa-onnx）")

# 中文流式 ASR 模型（sherpa-onnx 官方 zipformer transducer int8，126MB）
MODEL_VERSION = "sherpa-onnx-streaming-zipformer-zh-int8-2025-06-30"
MODEL_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
             "sherpa-onnx-streaming-zipformer-zh-int8-2025-06-30.tar.bz2")

_recognizer = None


def model_dir():
    """模型目录（用户数据目录 models/ 下）。"""
    d = os.path.join(get_user_data_dir(), "models")
    os.makedirs(d, exist_ok=True)
    return d


def _model_base():
    return os.path.join(model_dir(), MODEL_VERSION)


def _onnx(name):
    """兼容 encoder.onnx / encoder.int8.onnx 命名。"""
    base = _model_base()
    for n in (name + ".onnx", name + ".int8.onnx"):
        p = os.path.join(base, n)
        if os.path.isfile(p):
            return p
    return os.path.join(base, name + ".onnx")


def is_model_ready():
    """模型是否已就绪（encoder/decoder/joiner/tokens 齐全）。"""
    base = _model_base()
    return all(os.path.isfile(_onnx(n)) for n in ("encoder", "decoder", "joiner")) and \
        os.path.isfile(os.path.join(base, "tokens.txt"))


def download_model(progress_cb=None):
    """下载并解压模型（约 126MB）。返回模型是否就绪（存档清理失败不影响）。"""
    d = model_dir()
    dest = os.path.join(d, MODEL_VERSION)
    if is_model_ready():
        return True
    archive = os.path.join(d, MODEL_VERSION + ".tar.bz2")
    ready = False
    try:
        if not os.path.isfile(archive):
            if progress_cb:
                progress_cb(0, "下载语音模型（约 126MB，仅首次）…")
            tmp = archive + ".part"
            urllib.request.urlretrieve(MODEL_URL, tmp)
            os.replace(tmp, archive)
        if progress_cb:
            progress_cb(60, "解压模型…")
        with tarfile.open(archive, "r:bz2") as tf:
            tf.extractall(d)
        ready = is_model_ready()
    except Exception as e:
        if progress_cb:
            progress_cb(-1, f"模型下载失败：{e}")
    # 清理存档（失败不影响已就绪的模型）
    if os.path.isfile(archive):
        try:
            os.remove(archive)
        except Exception:
            pass
    return ready or is_model_ready()


def _get_recognizer():
    """懒加载识别器（流式 OnlineRecognizer，模型需已就绪）。"""
    global _recognizer
    if _recognizer is None:
        if not _ENGINE_OK:
            raise RuntimeError(ENGINE_MISSING_MSG)
        _recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=os.path.join(_model_base(), "tokens.txt"),
            encoder=_onnx("encoder"),
            decoder=_onnx("decoder"),
            joiner=_onnx("joiner"),
            num_threads=2,
            sample_rate=16000,
            feature_dim=80,
            enable_endpoint_detection=True,
        )
    return _recognizer


def _extract_audio(video_or_audio, wav_path):
    """任意媒体 → 16k 单声道 WAV。"""
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        return False
    cmd = [ffmpeg, "-y", "-i", video_or_audio, "-ar", "16000",
           "-ac", "1", "-c:a", "pcm_s16le", wav_path]
    try:
        subprocess.run(cmd, capture_output=True, timeout=600,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        return os.path.isfile(wav_path)
    except Exception:
        return False


def _segments_to_srt(segments):
    """[(start, end, text)] → srt 文本。"""
    def ts(sec):
        ms = int(round((sec - int(sec)) * 1000))
        if ms >= 1000:
            sec += 1
            ms -= 1000
        h, rem = divmod(int(sec), 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for i, (s, e, t) in enumerate(segments, 1):
        t = t.strip()
        if t:
            lines.append(f"{i}\n{ts(s)} --> {ts(e)}\n{t}\n")
    return "\n".join(lines)


def _read_wav(path):
    """读 16k WAV → (int16 numpy 数组, 采样率)。"""
    import wave
    import numpy as np
    with wave.open(path, "rb") as wf:
        sr = wf.getframerate()
        n = wf.getnframes()
        data = wf.readframes(n)
    return np.frombuffer(data, dtype=np.int16), sr


def transcribe(audio_path, progress_cb=None, cancel_check=None):
    """识别音频（wav/mp3/视频均可），返回 [(start, end, text), ...]。

    模型未就绪时返回 None（需先 download_model）。
    """
    if not _ENGINE_OK:
        if progress_cb:
            progress_cb(-1, ENGINE_MISSING_MSG)
        return None
    if not is_model_ready():
        if progress_cb:
            progress_cb(-1, "语音模型未就绪，请先下载模型")
        return None
    import tempfile
    import shutil

    tmp = tempfile.mkdtemp(prefix="fm_asr_")
    wav = os.path.join(tmp, "audio.wav")
    try:
        if progress_cb:
            progress_cb(5, "提取音频…")
        if not _extract_audio(audio_path, wav):
            if progress_cb:
                progress_cb(-1, "音频提取失败")
            return None
        if cancel_check and cancel_check():
            return None

        samples, sr = _read_wav(wav)
        if progress_cb:
            progress_cb(25, "语音识别中…")
        try:
            recognizer = _get_recognizer()
        except RuntimeError as e:
            if progress_cb:
                progress_cb(-1, str(e))
            return None
        except Exception as e:
            if progress_cb:
                progress_cb(-1, f"语音引擎加载失败：{e}")
            return None
        stream = recognizer.create_stream()
        stream.accept_waveform(sr, samples)
        stream.input_finished()
        while recognizer.is_ready(stream):
            recognizer.decode_stream(stream)
        text = (recognizer.get_result(stream) or "").strip()
        timestamps = list(recognizer.timestamps(stream) or [])
        try:
            tokens = list(recognizer.tokens(stream) or [])
        except Exception:
            tokens = []
        if not text:
            if progress_cb:
                progress_cb(-1, "未识别到语音内容")
            return None

        # token 级时间戳 → 按标点/停顿切句
        segments = []
        if tokens and timestamps:
            cur = ""
            cur_t0 = timestamps[0] if timestamps else 0.0
            for tok, ts in zip(tokens, timestamps):
                cur += tok
                # 句子结束：句号/问号/感叹号 或 2s 以上停顿
                if tok.strip() in ("。", "？", "！", ".", "?", "!") or \
                        (cur and len(cur) > 15 and ts - cur_t0 > 8):
                    if cur.strip():
                        segments.append((cur_t0, ts, cur))
                    cur = ""
                    cur_t0 = ts
            if cur.strip():
                segments.append((cur_t0, timestamps[-1], cur))
        else:
            # 无时间戳：整段一条
            dur = len(samples) / sr if sr else 0
            segments.append((0.0, dur, text))

        if progress_cb:
            progress_cb(100, f"完成，共 {len(segments)} 条字幕")
        return segments
    finally:
        if os.path.isdir(tmp):
            shutil.rmtree(tmp, ignore_errors=True)


def audio_to_srt(audio_path, output_path, progress_cb=None, cancel_check=None):
    """语音转字幕文件（.srt），返回是否成功。"""
    segments = transcribe(audio_path, progress_cb, cancel_check)
    if segments is None:
        return False
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(_segments_to_srt(segments))
        return True
    except OSError:
        return False
