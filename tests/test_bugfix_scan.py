"""2026-08-16 全项目排查修复的 3 个 bug 回归测试。

1. core/audio_norm.py：缺 `import subprocess` → 批量标准化测量阶段 NameError；
2. core/lan_transfer.py：模块顶层 import lan_receiver/lan_sender → 循环导入
   （按字母序 import 时 ImportError）→ 改为函数内惰性导入；
3. core/video_converter.py：selected_streams 只选音频流时误加 -an 把音频
   也禁用（has_audio 计算了却没用）→ 改为 has_audio 时 -vn。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["FORMATMASTER_OFFSCREEN"] = "1"

import gc

gc.disable()  # offscreen 下规避 Python 3.11 增量 GC 与 Shiboken 回收竞态


class TestAudioNormImport:
    """audio_norm 缺 subprocess 导入（测量阶段 NameError）。"""

    def test_subprocess_imported(self):
        import core.audio_norm as an
        assert hasattr(an, "subprocess"), "audio_norm 缺少 import subprocess"

    def test_measure_loudness_calls_subprocess(self, monkeypatch):
        """_measure_loudness 走 subprocess.run 路径，不抛 NameError。"""
        import core.audio_norm as an
        called = {}

        class _Proc:
            returncode = 0
            stderr = ('{"input_i": -20.0, "input_tp": -1.0, '
                      '"input_lra": 11.0, "input_thresh": -30.0, '
                      '"target_offset": 0.5}')
            stdout = ""

        monkeypatch.setattr(an, "get_ffmpeg_path", lambda: "ffmpeg")

        def fake_run(cmd, **kw):
            called["cmd"] = cmd
            return _Proc()

        monkeypatch.setattr(an.subprocess, "run", fake_run)
        m = an._measure_loudness("x.wav", -14)
        assert called, "应调用 subprocess.run"
        assert m is not None and abs(m["input_i"] - (-20.0)) < 1e-6
        cmd_text = " ".join(called["cmd"])
        assert "-af" in cmd_text and "loudnorm" in cmd_text


class TestLanTransferCircularImport:
    """lan_transfer 顶层 import 子模块 → 循环导入（字母序必炸）。"""

    def test_import_order_lan_receiver_first(self):
        """模拟按字母序导入（lan_receiver 先于 lan_transfer）不报错。"""
        # 用子进程独立验证（当前进程可能已有部分模块缓存）
        import subprocess
        code = (
            "import sys; sys.path.insert(0, r'%s'); "
            "import core.lan_receiver; import core.lan_transfer; "
            "import core.lan_sender; print('CIRCULAR OK')"
            % os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        r = subprocess.run([sys.executable, "-c", code],
                           capture_output=True, text=True, timeout=60)
        assert "CIRCULAR OK" in r.stdout, f"循环导入未修复: {r.stderr[-300:]}"

    def test_import_order_lan_transfer_first(self):
        """lan_transfer 先导入也不报错。"""
        import subprocess
        code = (
            "import sys; sys.path.insert(0, r'%s'); "
            "import core.lan_transfer; import core.lan_receiver; "
            "print('ORDER OK')"
            % os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        r = subprocess.run([sys.executable, "-c", code],
                           capture_output=True, text=True, timeout=60)
        assert "ORDER OK" in r.stdout, f"导入失败: {r.stderr[-300:]}"


class _FakeRunResult:
    success = True
    duration = 1.0


class TestVideoConverterStreamSelect:
    """selected_streams 只选音频流 → 应 -vn（修复前误加 -an 输出空文件）。"""

    def test_audio_only_stream_uses_vn(self):
        from core.video_converter import VideoConverter
        import core.video_converter as vc

        captured = {}

        def fake_run_ffmpeg(cmd, **kw):
            captured["cmd"] = cmd
            return _FakeRunResult()

        orig = vc.run_ffmpeg
        vc.run_ffmpeg = fake_run_ffmpeg
        try:
            cv = VideoConverter()
            cv.has_audio_stream = lambda p: True   # 文件有音轨（现实场景）
            cv._get_stream_type = lambda p, idx: "audio" if idx == 1 else "video"
            ok = cv.convert("a.mp4", "b.mp4", ".mp4", "libx264", "ultrafast",
                            selected_streams={0: False, 1: True})
            assert ok
            cmd = captured["cmd"]
            assert "-map" in cmd and "0:1" in cmd
            assert "-vn" in cmd, f"仅音频流应 -vn，命令: {cmd}"
            assert "-an" not in cmd, f"仅音频流不应 -an（会把音频也禁掉）: {cmd}"
        finally:
            vc.run_ffmpeg = orig

    def test_both_streams_no_vn_an(self):
        from core.video_converter import VideoConverter
        import core.video_converter as vc

        captured = {}

        def fake_run_ffmpeg(cmd, **kw):
            captured["cmd"] = cmd
            return _FakeRunResult()

        orig = vc.run_ffmpeg
        vc.run_ffmpeg = fake_run_ffmpeg
        try:
            cv = VideoConverter()
            cv._get_stream_type = lambda p, idx: "video" if idx == 0 else "audio"
            ok = cv.convert("a.mp4", "b.mp4", ".mp4", "libx264", "ultrafast",
                            selected_streams={0: True, 1: True})
            assert ok
            cmd = captured["cmd"]
            assert "-vn" not in cmd and "-an" not in cmd, f"全选不应禁流: {cmd}"
        finally:
            vc.run_ffmpeg = orig
