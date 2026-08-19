"""格式大师 — PySide6 + Fluent Widgets UI 入口。

运行：python main_qt.py
支持：
  python main_qt.py --convert "文件路径"          右键菜单 → 打开面板 + 路由文件
  python main_qt.py --quick-convert "文件路径"    CLI 后台静默转换（不显示 GUI）
  python main_qt.py --install-shell              注册 Windows 右键菜单
  python main_qt.py --remove-shell               移除 Windows 右键菜单
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


def _print_crypto_hint():
    print("=" * 60)
    print("[提示] 当前 Python 环境缺少 cryptography 模块，文件安全工具（加密/解密）将不可用。")
    print("        请改用项目虚拟环境运行：venv\\Scripts\\python.exe main_qt.py")
    print("        或执行：pip install cryptography")
    print("=" * 60)


def _ensure_crypto_env():
    """缺失 cryptography 时自动改用项目 venv 重启（无论用哪个 Python 启动）。

    - 当前环境有 cryptography → 正常继续
    - 缺 cryptography 且存在项目 venv → 静默用 venv 的 python 拉起本程序后退出
      （CREATE_NO_WINDOW 避免 Windows 下闪现黑框；仅 venv 也缺时打印指引）
    - venv 也缺 → 控制台打印明确指引（FM_NO_REEXEC 防止无限重启）
    """
    if os.environ.get("FM_NO_REEXEC"):
        return
    try:
        import cryptography  # noqa: F401
        return
    except Exception:  # noqa: BLE001
        pass
    root = os.path.dirname(os.path.abspath(__file__))
    venv_py = os.path.join(root, "venv", "Scripts", "python.exe")
    if not os.path.isfile(venv_py):
        _print_crypto_hint()
        return
    try:
        import subprocess
        env = dict(os.environ)
        env["FM_NO_REEXEC"] = "1"
        # CREATE_NO_WINDOW：静默拉起 venv，不闪现控制台黑框
        flags = 0x08000000 if os.name == "nt" else 0
        subprocess.Popen(
            [venv_py, os.path.abspath(__file__)] + sys.argv[1:],
            cwd=root, env=env, creationflags=flags)
        sys.exit(0)
    except Exception:  # noqa: BLE001
        _print_crypto_hint()


if __name__ == "__main__":
    _ensure_crypto_env()

    # ── CLI 命令（无需 GUI）─────────────────
    args = sys.argv[1:]
    if "--install-shell" in args:
        _setup_high_dpi()
        from utils.shell_integration import install_context_menu, is_installed
        ok = install_context_menu()
        print("右键菜单注册成功" if ok else "右键菜单注册失败（请以管理员权限重试）")
        sys.exit(0 if ok else 1)

    if "--remove-shell" in args:
        from utils.shell_integration import remove_context_menu
        remove_context_menu()
        print("已移除右键菜单")
        sys.exit(0)

    if "--quick-convert" in args:
        i = args.index("--quick-convert")
        if i + 1 < len(args):
            path = args[i + 1]
            if not os.path.isfile(path):
                print(f"[错误] 文件不存在: {path}")
                sys.exit(1)
            from core.cli_bridge import auto_convert
            print(f"[格式大师] 正在后台转换: {os.path.basename(path)}")
            ok, out = auto_convert(path)
            if ok:
                print(f"[完成] → {out}")
                sys.exit(0)
            else:
                print("[失败] 转换未完成，请检查文件是否损坏或格式是否支持")
                sys.exit(1)
        sys.exit(1)

    # ── GUI 模式 ───────────────────────────
    _setup_high_dpi()
    from gui_qt.app import run  # noqa: E402
    # --convert <path>：右键菜单集成入口
    convert_path = None
    if "--convert" in args:
        i = args.index("--convert")
        if i + 1 < len(args):
            convert_path = args[i + 1]
    run(convert_path=convert_path)
