"""utils/shell_integration — Windows 右键菜单集成。

install_context_menu():    注册「格式大师 — 快捷转换」右键菜单
remove_context_menu():     移除所有右键注册表项
"""
import os
import sys
import winreg

_MENU_KEY = r"Software\Classes\*\shell\FormatMaster.Convert"
_CMD_KEY = r"Software\Classes\*\shell\FormatMaster.Convert\command"


def _python_cmd():
    """返回当前 Python 环境的启动命令行（含脚本路径）。"""
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}"'
    script = os.path.abspath(sys.argv[0])
    return f'"{sys.executable}" "{script}"'


def install_context_menu():
    """写入 HKCU\Software\Classes\*\shell\FormatMaster.Convert。

    右键任意文件 → 「格式大师 — 快捷转换」→ 后台自动转换（静默完成）。
    """
    try:
        cmd = f'{_python_cmd()} --quick-convert "%1"'
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _MENU_KEY) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "格式大师 — 快捷转换")
            winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ,
                              f'"{sys.executable}",0')
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _CMD_KEY) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, cmd)
        return True
    except Exception:  # noqa: BLE001
        return False


def remove_context_menu():
    """清理所有右键注册表残留。"""
    for key in (_CMD_KEY, _MENU_KEY):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
        except FileNotFoundError:
            pass


def is_installed():
    """右键菜单是否已注册。"""
    try:
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, _CMD_KEY)
        return True
    except FileNotFoundError:
        return False
