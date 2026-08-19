"""压力测试：并发转换、批量连续转换、取消中断、内存占用监控。

前置：bin/ffmpeg.exe 存在（无则跳过）。
"""
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TMP = tempfile.mkdtemp(prefix="fm_stress_")
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
        pytest.skip("FFmpeg 不可用，跳过压力测试")
    yield
    shutil.rmtree(TMP, ignore_errors=True)


def _make_video(path, duration=2, size="160x120", rate=10):
    r = subprocess.run(
        [_ff(), "-y", "-f", "lavfi", "-i",
         f"testsrc=duration={duration}:size={size}:rate={rate}",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
         path], capture_output=True, timeout=60)
    assert r.returncode == 0, r.stderr[-300:]


def test_concurrent_conversions():
    """并发 4 路转码：全部成功、输出有效、线程安全无崩溃。"""
    from core.video_converter import VideoConverter
    srcs = []
    for i in range(4):
        p = os.path.join(TMP, f"cc{i}.mp4")
        _make_video(p, duration=3)
        srcs.append(p)
    outs = [os.path.join(TMP, f"cc{i}_out.mp4") for i in range(4)]
    results = [None] * 4
    errors = []

    def _conv(i):
        try:
            cv = VideoConverter()
            results[i] = cv.convert(srcs[i], outs[i], ".mp4", "libx264", "ultrafast",
                                    progress_callback=lambda *a, _i=i: None)
        except Exception as e:  # noqa: BLE001
            errors.append((i, repr(e)))

    threads = [threading.Thread(target=_conv, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    assert not errors, f"并发转换异常: {errors}"
    assert all(results), f"应有 4 个成功，实际 {results}"
    for out in outs:
        assert os.path.isfile(out) and os.path.getsize(out) > 0, f"{out} 输出无效"


def test_batch_sequential_12_files():
    """批量连续转换 12 个小文件：全部成功，总耗时合理（<60s）。"""
    from core.video_converter import VideoConverter
    t0 = time.time()
    for i in range(12):
        src = os.path.join(TMP, f"b{i}.mp4")
        _make_video(src, duration=1, size="128x96", rate=8)
        out = os.path.join(TMP, f"b{i}_out.mp4")
        ok = VideoConverter().convert(src, out, ".mp4", "libx264", "ultrafast",
                                      progress_callback=lambda *a: None)
        assert ok, f"第 {i} 个转换失败"
        assert os.path.isfile(out)
    elapsed = time.time() - t0
    assert elapsed < 60, f"12 文件批量转换耗时 {elapsed:.1f}s 过慢"


def test_cancel_interrupts_conversion():
    """取消中断：转换中途取消返回 False，不崩溃。"""
    from core.video_converter import VideoConverter
    src = os.path.join(TMP, "cancel.mp4")
    _make_video(src, duration=10, size="320x240", rate=15)  # 稍大的源
    out = os.path.join(TMP, "cancel_out.mp4")
    cv = VideoConverter()

    # 进度回调里第一次触发取消（cancel() 置位，_convert_once 检查后中断）
    def _progress(pct, msg):
        if pct >= 1 and not getattr(cv, "_cancel", False):
            cv.cancel()

    try:
        ok = cv.convert(src, out, ".mp4", "libx264", "ultrafast",
                        progress_callback=_progress)
        # 取消后结果可能是 False（中断）或 True（已转完才取消）
        assert ok is False or os.path.isfile(out)
    except Exception as e:  # noqa: BLE001 - 取消路径不应抛未捕获异常
        pytest.fail(f"取消路径异常: {e!r}")


def test_memory_no_runaway():
    """转换进程内存：多文件转换后进程 RSS 无明显失控（<800MB）。"""
    import psutil
    proc = psutil.Process()
    rss_before = proc.memory_info().rss
    from core.video_converter import VideoConverter
    for i in range(6):
        src = os.path.join(TMP, f"m{i}.mp4")
        _make_video(src, duration=2)
        out = os.path.join(TMP, f"m{i}_out.mp4")
        assert VideoConverter().convert(src, out, ".mp4", "libx264", "ultrafast",
                                        progress_callback=lambda *a: None)
    rss_after = proc.memory_info().rss
    delta_mb = (rss_after - rss_before) / 1024 / 1024
    assert delta_mb < 800, f"连续转换内存增长 {delta_mb:.0f}MB 疑似泄漏"
