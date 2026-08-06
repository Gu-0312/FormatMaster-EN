"""格式大师 — PySide6 + Fluent Widgets UI 入口。

运行：python main_qt.py
支持：python main_qt.py --convert "文件路径"（右键菜单集成，启动后自动打开）
（旧 tkinter 入口 main.py 已删除，本文件为唯一入口）
"""
import os
import sys

# 确保项目根目录在 sys.path（支持任意工作目录启动）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 提前加载语言偏好（必须在 import gui_qt.app / utils.config 之前执行——
# config 等模块的模块级 tr() 需要正确的语言；延迟到 MainWindow 构造会拿到中文）
try:
    import json as _json
    from gui_qt.i18n import set_language
    from utils.config import get_user_data_dir
    _prefs_path = os.path.join(get_user_data_dir(), "user_prefs.json")
    _lang = "zh"
    if os.path.isfile(_prefs_path):
        with open(_prefs_path, encoding="utf-8") as _f:
            _lang = _json.load(_f).get("language", "zh")
    set_language(_lang)
except Exception:  # noqa: BLE001 - 语言加载失败不影响启动（默认中文）
    pass


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
    # --convert <path>：右键菜单集成入口
    convert_path = None
    args = sys.argv[1:]
    if "--convert" in args:
        i = args.index("--convert")
        if i + 1 < len(args):
            convert_path = args[i + 1]
    run(convert_path=convert_path)
