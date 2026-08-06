"""FFmpeg stderr 进度读取器 — 消除 8 处重复的进度解析代码。

所有 FFmpeg 子进程的 stderr 进度读取统一走此模块，
避免在 video_converter / audio_converter / audio_trimmer / m3u8_downloader
中各自复制相同的 regex + select + 时间解析 + 节流逻辑。
"""

import os
import re
import subprocess
import time as _time

# ── 预编译正则（模块级，只编译一次） ──────────────────────────────
_TIME_RE = re.compile(r'time=(\d+):(\d+):(\d+)\.(\d+)')
_OUT_TIME_US_RE = re.compile(r'out_time_us=(\d+)')
_OUT_TIME_MS_RE = re.compile(r'out_time_ms=(\d+)')
_SPEED_RE = re.compile(r'speed=\s*([\d.]+)x')


def _parse_time_line(line_str: str) -> float:
    """从 FFmpeg stderr 行中解析当前时间（秒），失败返回 -1。"""
    m = _OUT_TIME_US_RE.search(line_str)
    if m:
        return int(m.group(1)) / 1_000_000
    m = _OUT_TIME_MS_RE.search(line_str)
    if m:
        return int(m.group(1)) / 1_000
    m = _TIME_RE.search(line_str)
    if m:
        h, mi, s, ms = m.groups()
        return int(h) * 3600 + int(mi) * 60 + int(s) + int(ms) / 100
    return -1.0


class FFmpegProgressReader:
    """统一的 FFmpeg stderr 进度读取器。

    用法::

        reader = FFmpegProgressReader(process, duration, label="转换中")
        ok = reader.read_loop(cancel_check, progress_callback)
    """

    def __init__(
        self,
        process: subprocess.Popen,
        duration: float,
        label: str = "转换中",
        done_message: str = "",
        fail_message: str = "",
        update_interval: float = 0.3,
    ):
        self.process = process
        self.duration = duration
        self.label = label
        self.done_message = done_message or f"{label}完成"
        self.fail_message = fail_message or f"{label}失败"
        self.update_interval = update_interval
        self.error_output: list[str] = []
        self._last_pct = -1
        self._last_update_time = 0.0
        self._last_speed = 0.0

    def _read_stderr_line(self) -> bytes | None:
        """跨平台读取一行 stderr（Windows 不支持 select.select on pipes）。"""
        if os.name == 'nt':
            return self.process.stderr.readline()
        try:
            import select
            ready, _, _ = select.select([self.process.stderr], [], [], 0.1)
        except Exception:
            ready = [self.process.stderr]
        if not ready:
            return None
        return self.process.stderr.readline()

    def read_loop(
        self,
        cancel_check=None,
        progress_callback=None,
        speed_enabled: bool = False,
        progress_label: str | None = None,
    ) -> bool:
        """循环读取 stderr 并报告进度，直到进程结束。

        Args:
            cancel_check: 返回 True 表示用户取消（如 ``lambda: self._cancel``）
            progress_callback: ``(pct: int, msg: str) -> None``
            speed_enabled: 是否解析 speed= 字段用于 ETA 显示
            progress_label: 覆盖默认的进度文本标签（如 "裁剪中"）

        Returns:
            True = 成功（returncode == 0），False = 失败或取消
        """
        proc = self.process
        label = progress_label or self.label
        last_pct = -1
        last_update = 0.0
        last_speed = 0.0

        while True:
            if cancel_check and cancel_check():
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except Exception:
                    proc.kill()
                if progress_callback:
                    progress_callback(-1, "已取消")
                return None

            line = self._read_stderr_line()
            if not line:
                if proc.poll() is not None:
                    break
                continue

            line_str = line.decode('utf-8', errors='replace')
            self.error_output.append(line_str)

            if speed_enabled:
                sm = _SPEED_RE.search(line_str)
                if sm:
                    try:
                        last_speed = float(sm.group(1))
                    except Exception:
                        pass

            current = _parse_time_line(line_str)
            if current < 0:
                continue

            if self.duration > 0:
                pct = min(99, int(current * 100 / self.duration))
                now = _time.time()
                if progress_callback and (pct != last_pct or now - last_update >= self.update_interval):
                    eta_str = ""
                    if speed_enabled and last_speed > 0.05:
                        remain = (self.duration - current) / last_speed
                        if 0 < remain < 86400:
                            mm, ss = divmod(int(remain), 60)
                            hh, mm = divmod(mm, 60)
                            eta_str = f" 剩{hh}:{mm:02d}:{ss:02d}" if hh > 0 else f" 剩{mm}:{ss:02d}"
                    progress_callback(pct, f"{label} {pct}%{eta_str}")
                    last_pct = pct
                    last_update = now
            else:
                if progress_callback:
                    pct = min(99, int(current) % 100)
                    progress_callback(pct, f"处理中... ({int(current)}s)")

        if proc.returncode == 0:
            if progress_callback:
                progress_callback(100, self.done_message)
            return True
        else:
            err = ''.join(self.error_output[-5:])
            if progress_callback:
                progress_callback(-1, f"{self.fail_message}: {err[:200]}")
            return False


def run_ffmpeg(
    cmd: list,
    duration: float = 0,
    label: str = "转换中",
    cancel_check=None,
    progress_callback=None,
    speed_enabled: bool = False,
    progress_label: str | None = None,
) -> bool:
    """一键启动 FFmpeg 子进程并读取进度。

    Returns:
        True = 成功，False = 失败或取消
    """
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
    )
    reader = FFmpegProgressReader(process, duration, label=label)
    return reader.read_loop(cancel_check, progress_callback, speed_enabled, progress_label)
