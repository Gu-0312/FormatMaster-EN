# -*- coding: utf-8 -*-
"""audio_waveform — pyqtgraph 音频波形可视化（懒加载 + 峰值桶化）。

ffmpeg 解码为 8kHz 单声道 PCM → 分段取峰值（~2000 桶）→ 折线填充绘制。
大文件也流畅；pyqtgraph 未装/ffmpeg 缺失时兜底提示。
"""
import os
import subprocess

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from gui_qt.i18n import tr


class AudioWaveformWidget(QWidget):
    """音频波形组件：load_audio(path) 后绘制。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(140)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._plot = None
        self._build()

    def _build(self):
        try:
            import pyqtgraph as pg
            pg.setConfigOptions(antialias=True)
            from pyqtgraph import PlotWidget
            self._plot = PlotWidget(self)
            self._plot.setBackground(None)
            self._plot.showGrid(x=True, y=True, alpha=0.15)
            self._plot.getPlotItem().hideButtons()
            self._plot.setLabel("left", tr("音量", "Amp"))
            self._plot.setLabel("bottom", tr("时间", "Time"))
            self.layout().addWidget(self._plot)
        except Exception as e:  # noqa: BLE001
            self._lb = QLabel(
                tr("波形组件不可用：{}", "Waveform unavailable: {}").format(e), self)
            self._lb.setAlignment(Qt.AlignCenter)
            self.layout().addWidget(self._lb)

    def has_data(self):
        return self._plot is not None

    # ── 公共接口 ────────────────────────────────
    def set_peaks(self, peaks, dur=0.0):
        """后台线程解码完成后回填绘制。peaks: [int 峰值, ...]。"""
        if self._plot is None:
            return
        self._plot.clear()
        self._plot.plot(peaks, pen="#5B5BD6", fillLevel=0, brush="#5B5BD633")
        self._plot.setXRange(0, len(peaks), padding=0.02)
        if dur:
            self._plot.setLabel("bottom", tr("时间（{}s）", "Time ({}s)").format(int(dur)))

    def load_audio(self, path):
        """解码并绘制波形；成功返回 (峰值点, 时长秒)，失败返回 None。"""
        if self._plot is None:
            return None
        samples, dur = _decode_pcm(path)
        if samples is None or len(samples) == 0:
            self._plot.clear()
            return None
        peaks = _bucket_peaks(samples, 2000)
        self.set_peaks(peaks, dur)
        return len(peaks), dur

    def clear(self):
        if self._plot is not None:
            self._plot.clear()


def _decode_pcm(path, sample_rate=8000):
    """ffmpeg 解码为 (numpy int16 数组, 时长秒)；失败返回 (None, 0)。"""
    try:
        import numpy as np
    except Exception:  # noqa: BLE001
        return None, 0
    try:
        from utils.config import get_ffmpeg_path
    except Exception:  # noqa: BLE001
        return None, 0
    ff = get_ffmpeg_path()
    if not ff or not os.path.isfile(path):
        return None, 0
    try:
        proc = subprocess.run(
            [ff, "-v", "error", "-i", path, "-f", "s16le", "-ac", "1",
             "-ar", str(sample_rate), "-acodec", "pcm_s16le", "-"],
            capture_output=True, timeout=60)
    except Exception:  # noqa: BLE001
        return None, 0
    if proc.returncode != 0 or not proc.stdout:
        return None, 0
    data = np.frombuffer(proc.stdout, dtype="<i2")
    dur = len(data) / sample_rate
    return data, dur


def _bucket_peaks(samples, buckets=2000):
    """把样本序列分成 buckets 段，每段取峰值（绝对值最大）。"""
    n = len(samples)
    if n == 0:
        return []
    chunk = max(1, n // buckets)
    out = []
    for i in range(0, n, chunk):
        seg = samples[i:i + chunk]
        out.append(int(max(abs(seg.min()), abs(seg.max()))))
    return out
