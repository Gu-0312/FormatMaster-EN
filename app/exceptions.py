"""异常 → 中文提示映射与调试日志

从 main.py 提取的纯函数模块。
"""
import sys

from app.logger import log as _log, DEBUG as _DBG

# 短类名 → 提示（如 "FileNotFoundError"），优先于完整名查找
_EX_HINT_SHORT = {
    "FileNotFoundError": "找不到输入文件，请检查路径",
    "PermissionError": "没有访问权限，请检查文件/目录权限",
    "KeyError": "缺少必要参数，请检查设置",
    "ValueError": "参数值不合法，请检查输入",
    "OSError": "系统错误，文件可能被占用或路径无效",
    "IndexError": "索引越界，数据可能不完整",
    "TypeError": "类型错误，数据格式不匹配",
    "AttributeError": "功能暂不支持此操作",
    "CalledProcessError": "子进程执行失败，请检查FFmpeg安装",
    "RuntimeError": "运行时错误，文件可能已损坏或不支持",
    "JSONDecodeError": "媒体信息解析失败，文件可能已损坏",
    "MemoryError": "内存不足，请关闭其他程序后重试",
    "TimeoutError": "操作超时，文件可能过大或已损坏",
    "ImportError": "缺少必要组件或依赖库，请重新安装",
    "ModuleNotFoundError": "缺少功能模块，请重新安装程序",
    "ConnectionError": "网络连接失败，请检查网络",
    "UnicodeDecodeError": "文件编码不兼容，请尝试其他格式",
    "UnicodeEncodeError": "文件名包含不兼容字符，请重命名",
    "PDFSyntaxError": "PDF文件语法错误，文件可能已损坏",
    "FileDataError": "PDF文件已损坏，无法打开",
    "EmptyFileError": "PDF文件为空",
    "PdfReadError": "PDF文件读取失败，文件可能已损坏或加密",
}

# 完整限定名 → 提示（如 "requests.exceptions.ConnectionError"），优先于短名
_EX_HINT_FULL = {
    "requests.exceptions.ConnectionError": "网络连接失败，请检查网络",
    "urllib.error.URLError": "网络连接失败，请检查网络",
    "pdfminer.pdfparser.PDFSyntaxError": "PDF文件语法错误，文件可能已损坏",
    "fitz.FileDataError": "PDF文件已损坏，无法打开",
    "fitz.EmptyFileError": "PDF文件为空",
}

# 合并导出，兼容既有 import（from app.exceptions import EX_HINT）
EX_HINT = dict(_EX_HINT_SHORT)
EX_HINT.update(_EX_HINT_FULL)
# 兼容旧键：完整限定名；_hint_ex 按短名命中同一提示
EX_HINT["subprocess.CalledProcessError"] = _EX_HINT_SHORT["CalledProcessError"]


def _hint_ex(ex):
    """为常见异常生成中文说明，帮助用户理解错误原因。

    先按完整限定名（O(1)），再按短类名（O(1)）查找，避免线性遍历。
    """
    en = type(ex).__name__
    return _EX_HINT_FULL.get(f"{type(ex).__module__}.{en}") \
        or _EX_HINT_SHORT.get(en)


def _debug_log(msg):
    """写调试日志（兼容旧接口，转发到统一线程安全 logger）。

    保持旧语义：若调用点正处于异常上下文，自动附带当前异常 traceback。
    """
    exc = sys.exc_info()
    _log(str(msg), _DBG, exc[1] if exc and exc[0] is not None else None)
