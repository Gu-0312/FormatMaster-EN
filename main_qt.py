"""格式大师 — PySide6 + Fluent Widgets UI 入口。

运行：python main_qt.py
（旧 tkinter 入口 main.py 已删除，本文件为唯一入口）
"""
import os
import sys

# 确保项目根目录在 sys.path（支持任意工作目录启动）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _setup_high_dpi():
    """在 QApplication 创建前配置高 DPI 行为。

    Qt 6 默认以 DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 创建进程
    DPI 感知，无需（也不应）手动调用 SetProcessDpiAwareness——手动设置
    会锁定感知级别，阻止 Qt 使用 V2 上下文并触发 '拒绝访问' 警告。

    这里只做 Qt 提供的纯缩放策略配置：PassThrough 让 125%/150% 等
    非整数缩放按真实比例渲染，避免取整导致的模糊。
    """
    try:
        from PySide6.QtCore import Qt
        Qt.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except Exception:
        pass


if __name__ == "__main__":
    _setup_high_dpi()
    from gui_qt.app import run  # noqa: E402
    run()
