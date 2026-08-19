"""FFmpeg stderr 进度读取器 — 消除 8 处重复的进度解析代码。

所有 FFmpeg 子进程的 stderr 进度读取统一走此模块，
避免在 video_converter / audio_converter / audio_trimmer / m3u8_downloader
中各自复制相同的 regex + select + 时间解析 + 节流逻辑。
"""

import os
import re
import subprocess
import time as _time
from dataclasses import dataclass, field

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


@dataclass
class FFmpegResult:
    """run_ffmpeg() 的返回值，含成功/取消/失败原因。

    __bool__ 实现兼容旧代码的 ``if result:`` 判断。
    """
    success: bool = False
    cancelled: bool = False
    error_lines: list[str] = field(default_factory=list)
    error_cn: str = ""       # 经 translate_ffmpeg_error() 翻译的中文

    def __bool__(self):
        return self.success


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

        try:
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
                    pct = min(100, int(current * 100 / self.duration))
                    now = _time.time()
                    if progress_callback and (pct != last_pct or now - last_update >= self.update_interval):
                        eta_str = ""
                        if speed_enabled and last_speed > 0.05:
                            remain = (self.duration - current) / last_speed
                            if 0 < remain < 86400:
                                mm, ss = divmod(int(remain), 60)
                                hh, mm = divmod(mm, 60)
                                eta_str = f" 剩{hh}:{mm:02d}:{ss:02d}" if hh > 0 else f" 剩{mm}:{ss:02d}"
                        if pct >= 100:
                            msg = f"{label} 完成，正在写入文件…"
                        else:
                            msg = f"{label} {pct}%{eta_str}"
                        progress_callback(pct, msg)
                        last_pct = pct
                        last_update = now
                else:
                    if progress_callback:
                        pct = min(100, int(current) % 100)
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
        finally:
            # 非正常退出时（取消/异常），确保子进程被终止
            # 避免僵尸 ffmpeg 进程继续占用 CPU 和磁盘 IO
            if proc.poll() is None:
                try:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except Exception:
                        proc.kill()
                        proc.wait(timeout=3)
                except Exception:
                    pass  # 进程已结束，忽略


def _extra_ffmpeg_args() -> list:
    """读用户偏好「FFmpeg 附加参数」（空格分隔字符串 → 参数列表）。

    设置页「高级」可配，供高级用户追加 -threads 4 / -preset 等全局选项。
    读取失败/为空返回 []。注意：附加参数插在输出路径之前，只影响
    run_ffmpeg 启动的进程（不修改调用方 cmd 列表）。
    """
    try:
        from utils.config import USER_PREFS
        s = USER_PREFS.get("qt_app", "ffmpeg_extra_args", "") or ""
        return [a for a in str(s).split() if a]
    except Exception:  # noqa: BLE001 - 读取失败静默
        return []


def run_ffmpeg(
    cmd: list,
    duration: float = 0,
    label: str = "转换中",
    cancel_check=None,
    progress_callback=None,
    speed_enabled: bool = False,
    progress_label: str | None = None,
    translate_error: bool = True,
) -> FFmpegResult:
    """一键启动 FFmpeg 子进程并读取进度。

    Args:
        translate_error: 为 True 时自动调用 translate_ffmpeg_error()
                         填充 result.error_cn。
    Returns:
        FFmpegResult（`.success` / `.cancelled` / `.error_lines` / `.error_cn`）
    """
    # 全局附加参数（设置页「高级 → FFmpeg 附加参数」）：空格分隔的选项
    # 插入到输出路径之前（cmd 末位是输出文件）。不修改调用方列表。
    extra = _extra_ffmpeg_args()
    if extra and len(cmd) > 1:
        cmd = [*cmd[:-1], *extra, cmd[-1]]
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
    )
    reader = FFmpegProgressReader(process, duration, label=label)
    raw = reader.read_loop(cancel_check, progress_callback, speed_enabled, progress_label)

    result = FFmpegResult()
    result.error_lines = list(reader.error_output)
    if raw is None:
        result.cancelled = True
        result.success = False
    elif raw is True:
        result.success = True
    else:
        result.success = False
        # 取最近 5 行 stderr 作为错误上下文
        tail = reader.error_output[-5:]
        result.error_lines = tail.copy()
        if translate_error:
            err_text = ''.join(tail)
            from utils.config import translate_ffmpeg_error
            result.error_cn = translate_ffmpeg_error(err_text)
    return result
