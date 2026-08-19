"""SafeWorker — QThread 后台任务安全基类（统一多线程样板）。

解决各面板 QThread 子类重复编写且不一致的问题：
- 异常兜底：子类只需实现 work()，run() 统一 try/except，
  异常写入全局日志并发 sig_error 信号（绝不静默丢失线程）
- 停止标志：stop() 设置中断，work() 内轮询 is_stopped() 协作退出
- 信号在基类定义（sig_error），子类扩展业务信号即可

用法：class MyWorker(SafeWorker): 定义业务信号 + 实现 work()。
"""
from PySide6.QtCore import QThread, Signal

from app.logger import ERROR, log


class SafeWorker(QThread):
    """带统一异常兜底与停止支持的 QThread 基类。"""

    # 后台任务异常（子类可连接以提示用户；未连接则仅写日志）
    sig_error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stopped = False

    def __del__(self):
        """析构保护：线程仍在运行时销毁会触发
        'QThread: Destroyed while thread is still running'（进程级崩溃隐患）。
        wait() 等待线程结束（含中断请求），确保安全回收。"""
        try:
            if self.isRunning():
                self.requestInterruption()
                self.wait(3000)
        except Exception:  # noqa: BLE001 - 析构兜底
            pass

    # ── 停止支持 ─────────────────────────────────
    def stop(self):
        """请求停止：置标志 + Qt 中断请求，work() 内用 is_stopped() 轮询。"""
        self._stopped = True
        self.requestInterruption()

    def is_stopped(self) -> bool:
        return self._stopped or self.isInterruptionRequested()

    # ── 统一执行入口 ─────────────────────────────
    def run(self):
        try:
            self.work()
        except Exception as exc:  # noqa: BLE001 - 兜底：线程异常不静默
            log(f"后台线程 {type(self).__name__} 异常: {exc}", ERROR, exc)
            try:
                self.sig_error.emit(str(exc))
            except Exception:  # noqa: BLE001
                pass
        finally:
            # 子类可能在 work() 中提前 return，确保终态信号不丢；
            # 具体终态信号由子类业务决定，基类仅兜底异常路径
            pass

    # ── 子类契约 ─────────────────────────────────
    def work(self):
        """子类实现后台业务逻辑；异常由基类统一兜底记录并发出 sig_error。"""
        raise NotImplementedError
