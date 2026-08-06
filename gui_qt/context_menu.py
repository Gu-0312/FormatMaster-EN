"""context_menu — Windows 文件右键菜单集成（"用格式大师转换"）。

写入 HKCU\\Software\\Classes\\*\\shell\\FormatMaster（当前用户级，
无需管理员权限）。命令调用应用入口并带 --convert <file> 参数，
由 gui_qt/app.run(convert_path=...) 在启动后自动打开对应面板并添加文件。
"""
import os
import sys

_SHELL_KEY = r"Software\Classes\*\shell\FormatMaster"


def _command_line():
    """构造右键命令：<解释器或 exe> main_qt.py --convert "%1"。"""
    exe = sys.executable
    if os.path.basename(exe).lower().endswith((".py",)):
        exe = sys.executable  # 不应出现
    if exe.lower().endswith(("pythonw.exe", "python.exe")):
        main_qt = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "main_qt.py")
        return f'"{exe}" "{main_qt}" --convert "%1"'
    return f'"{exe}" --convert "%1"'


def install():
    """安装右键菜单项（返回错误消息，None 表示成功）。"""
    try:
        import winreg
        shell = winreg.CreateKey(winreg.HKEY_CURRENT_USER, _SHELL_KEY)
        winreg.SetValueEx(shell, None, 0, winreg.REG_SZ, "用格式大师转换")
        winreg.SetValueEx(shell, "Icon", 0, winreg.REG_SZ,
                          f'"{sys.executable}",0')
        cmd_key = winreg.CreateKey(shell, "command")
        winreg.SetValueEx(cmd_key, None, 0, winreg.REG_SZ, _command_line())
        winreg.CloseKey(cmd_key)
        winreg.CloseKey(shell)
        return None
    except Exception as e:  # noqa: BLE001
        return str(e)


def uninstall():
    """卸载右键菜单项（返回错误消息，None 表示成功）。"""
    try:
        import winreg
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, _SHELL_KEY + r"\command")
        except FileNotFoundError:
            pass
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, _SHELL_KEY)
        return None
    except Exception as e:  # noqa: BLE001
        return str(e)


def installed():
    """是否已安装右键菜单。"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _SHELL_KEY) as k:
            return True
    except OSError:
        return False
