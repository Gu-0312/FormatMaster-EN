"""异常 → 中文提示映射与调试日志

从 main.py 提取的纯函数模块。
"""
import os

EX_HINT = {
    "FileNotFoundError": "找不到输入文件，请检查路径",
    "PermissionError": "没有访问权限，请检查文件/目录权限",
    "KeyError": "缺少必要参数，请检查设置",
    "ValueError": "参数值不合法，请检查输入",
    "OSError": "系统错误，文件可能被占用或路径无效",
    "IndexError": "索引越界，数据可能不完整",
    "TypeError": "类型错误，数据格式不匹配",
    "AttributeError": "功能暂不支持此操作",
    "subprocess.CalledProcessError": "子进程执行失败，请检查FFmpeg安装",
    "RuntimeError": "运行时错误，文件可能已损坏或不支持",
    "json.JSONDecodeError": "媒体信息解析失败，文件可能已损坏",
    "MemoryError": "内存不足，请关闭其他程序后重试",
    "TimeoutError": "操作超时，文件可能过大或已损坏",
    "ImportError": "缺少必要组件或依赖库，请重新安装",
    "ModuleNotFoundError": "缺少功能模块，请重新安装程序",
    "ConnectionError": "网络连接失败，请检查网络",
    "UnicodeDecodeError": "文件编码不兼容，请尝试其他格式",
    "UnicodeEncodeError": "文件名包含不兼容字符，请重命名",
    "requests.exceptions.ConnectionError": "网络连接失败，请检查网络",
    "pdfminer.pdfparser.PDFSyntaxError": "PDF文件语法错误，文件可能已损坏",
    "fitz.FileDataError": "PDF文件已损坏，无法打开",
    "fitz.EmptyFileError": "PDF文件为空",
    "PdfReadError": "PDF文件读取失败，文件可能已损坏或加密",
}

def _hint_ex(ex):
    """为常见异常生成中文说明，帮助用户理解错误原因"""
    en = type(ex).__name__
    full_name = f"{type(ex).__module__}.{en}"
    for k, v in EX_HINT.items():
        # 支持完整类名（如 subprocess.CalledProcessError）和类名（如 CalledProcessError）
        if k == full_name or k == en:
            return v
    return None

def _debug_log(msg):
    """写调试日志到文件和 stderr，不影响 UI。"""
    import traceback as _tb
    import sys as _sys
    import datetime as _dt
    ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    try:
        log_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "FormatMaster")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "debug.log")
        with open(log_path, "a", encoding="utf-8") as _f:
            _f.write(line)
            _tb.print_exc(file=_f)
        if os.path.getsize(log_path) > 2 * 1024 * 1024:
            with open(log_path, "r", encoding="utf-8") as _f:
                _f.seek(max(0, os.path.getsize(log_path) - 1024 * 1024))
                _f.readline()
                tail = _f.read()
            with open(log_path, "w", encoding="utf-8") as _f:
                _f.write(tail)
    except Exception:
        pass
    if os.environ.get("FORMATMASTER_DEBUG", "") == "1":
        try:
            _sys.stderr.write(f"[FormatMaster Debug] {line}")
            _tb.print_exc(file=_sys.stderr)
            _sys.stderr.flush()
        except Exception:
            pass
