"""crash_report — 全局未捕获异常处理（崩溃上报对话框）。

安装 sys.excepthook：未捕获异常 → 写 debug.log → 主线程弹出
「错误反馈」对话框（错误类型/信息/堆栈 + 日志路径），支持
复制详情 / 继续运行 / 退出。子线程异常经 QTimer 安全切回主线程弹窗。
"""
import os
import sys
import traceback as _tb


def _error_text(exc_type, exc_value, exc_tb):
    """格式化错误详情文本。"""
    parts = [
        f"{exc_type.__name__}: {exc_value}",
        "",
        _tb.format_exc(),
    ]
    return "\n".join(parts)


def _log_dir():
    return os.path.join(os.environ.get("APPDATA",
                                       os.path.expanduser("~")), "FormatMaster")


def _write_debug(text):
    """追加到 debug.log（2MB 截断由 app.exceptions._debug_log 负责，
    这里兜底写入）。"""
    try:
        import datetime
        from app.exceptions import _debug_log
        _debug_log(text)
    except Exception:  # noqa: BLE001
        try:
            os.makedirs(_log_dir(), exist_ok=True)
            with open(os.path.join(_log_dir(), "debug.log"), "a",
                      encoding="utf-8") as f:
                f.write(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] "
                        f"{text}\n")
        except Exception:  # noqa: BLE001
            pass


def _show_dialog(error_text):
    """主线程弹出崩溃对话框。"""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout,
                                   QLabel, QPlainTextEdit, QPushButton,
                                   QVBoxLayout)
    from gui_qt.i18n import tr

    dlg = QDialog()
    dlg.setWindowTitle(tr("程序遇到错误", "Unexpected error"))
    dlg.resize(520, 380)
    v = QVBoxLayout(dlg)
    v.setSpacing(10)

    head = QLabel(tr("格式大师遇到未预期错误。", "FormatMaster hit an "
                    "unexpected error."))
    head.setStyleSheet("font-size: 14px; font-weight: 700;")
    v.addWidget(head)

    tip = QLabel(tr("错误已写入日志：{}", "Logged to {}").format(
        os.path.join(_log_dir(), "debug.log")))
    tip.setWordWrap(True)
    tip.setStyleSheet("font-size: 12px; color: #808080;")
    v.addWidget(tip)

    box = QPlainTextEdit()
    box.setReadOnly(True)
    box.setPlainText(error_text)
    v.addWidget(box, 1)

    row = QHBoxLayout()
    row.addStretch(1)
    btn_copy = QPushButton(tr("复制错误信息", "Copy details"))
    btn_copy.clicked.connect(
        lambda: QApplication.clipboard().setText(error_text))
    row.addWidget(btn_copy)
    btn_quit = QPushButton(tr("退出程序", "Quit"))
    btn_quit.setStyleSheet("color: #E5484D;")
    btn_quit.clicked.connect(dlg.reject)
    row.addWidget(btn_quit)
    v.addLayout(row)

    # 模态显示（父窗口可空）
    dlg.exec()


def _thread_excepthook(args):
    """子线程未捕获异常兜底。

    sys.excepthook 仅对主线程生效；Python 3.8+ 提供 threading.excepthook
    专门接收子线程未捕获异常。这里与主线程钩子走同一套：写日志 + 切回
    主线程弹窗，避免子线程异常静默消失。
    """
    try:
        exc_type, exc_value, exc_tb = (args.exc_type, args.exc_value,
                                       args.exc_traceback)
        if exc_type is not None and issubclass(exc_type, KeyboardInterrupt):
            return
        text = _error_text(exc_type, exc_value, exc_tb)
        _write_debug(text)
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            QTimer.singleShot(0, lambda: _show_dialog(text))
    except Exception:  # noqa: BLE001 - 兜底自身绝不抛
        pass


def install_crash_handler():
    """安装全局未捕获异常处理器（幂等，链式保留原 hook）。

    覆盖主线程（sys.excepthook）与子线程（threading.excepthook）。
    """
    if getattr(install_crash_handler, "_installed", False):
        return
    install_crash_handler._installed = True
    prev_hook = sys.excepthook   # 保留既有 hook（如 crash.log 写入）

    def _hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        text = _error_text(exc_type, exc_value, exc_tb)
        _write_debug(text)
        try:
            from PySide6.QtCore import QThread, QTimer
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None and \
                    QThread.currentThread() is app.thread():
                _show_dialog(text)
            elif app is not None:
                # 子线程异常：切回主线程弹窗
                QTimer.singleShot(0, lambda: _show_dialog(text))
        except Exception:  # noqa: BLE001
            pass
        # 链式调用原 hook（写 crash.log 等），确保日志不丢
        try:
            prev_hook(exc_type, exc_value, exc_tb)
        except Exception:  # noqa: BLE001
            sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook
    # 子线程未捕获异常同样纳入日志与弹窗（仅在存在该钩子时安装）
    try:
        import threading
        if hasattr(threading, "excepthook"):
            threading.excepthook = _thread_excepthook
    except Exception:  # noqa: BLE001
        pass
