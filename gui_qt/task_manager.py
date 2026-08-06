"""TaskManager — 增强版任务调度器（Qt 信号驱动）。

对应 tkinter 版 main.py 的任务队列 + _run_task_video 链路：
- 状态机：WAITING / RUNNING / PAUSED / SUCCESS / FAILED / CANCELLED
- 串行队列 + 优先级排序
- 工作线程执行 core 转换器，进度/状态/日志经 Qt 信号回主线程
- 暂停：ffmpeg 进程不可原生暂停，采用「进度回调内轮询等待」冻结当前任务；
  等待中任务则移出调度序列，恢复时重新入队
- 取消：调用 VideoConverter.cancel()
- 速度：按进度增量与源文件大小估算 MB/s
"""
import os
import threading
import time
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal

from app.exceptions import _hint_ex
from utils.config import SUPPORTED_VIDEO, VIDEO_CODECS, VIDEO_PRESETS, RESOLUTIONS


# ── 任务状态 ─────────────────────────────────────
WAITING = "waiting"
RUNNING = "running"
PAUSED = "paused"
SUCCESS = "success"
FAILED = "failed"
CANCELLED = "cancelled"

_STATE_TEXT = {
    WAITING: "等待中", RUNNING: "转换中", PAUSED: "已暂停",
    SUCCESS: "已完成", FAILED: "失败", CANCELLED: "已取消",
}


def state_text(state: str) -> str:
    return _STATE_TEXT.get(state, state)


@dataclass
class Task:
    task_id: int
    name: str
    task_type: str            # "video" 走内置链路；其他类型由 runner 执行
    file_path: str
    output_path: str
    params: dict = field(default_factory=dict)
    priority: int = 0         # 越大越先执行
    state: str = WAITING
    progress: int = 0
    speed: str = ""
    error: str = ""
    input_size: int = 0
    created_at: float = field(default_factory=time.time)
    # 阶段2 通用任务扩展：runner(task, progress_cb) -> bool
    runner: object = None
    canceller: object = None  # 取消时调用的无参函数（如 converter.cancel）
    history_type: str = ""    # 历史记录类型文案，空则不记录
    history_target: str = ""
    # 失败重试
    retry_count: int = 0      # 已重试次数
    max_retries: int = 0      # 最大重试次数（0=不重试）
    last_progress: int = 0    # 失败时进度，用于判断是否可断点续传


def make_output_path(file_path: str, out_dir: str, ext: str) -> str:
    """生成输出路径：目标目录 + 源文件名新扩展名，自动避开同名冲突。

    与 tkinter 版 _go 的行为对齐：源目同路径时追加 _1；
    已存在时追加 _N 计数。目录不存在时由调用方在任务启动前创建。
    """
    nm = os.path.splitext(os.path.basename(file_path))[0]
    output_path = os.path.join(out_dir or os.path.dirname(file_path), nm + ext)
    if output_path.lower() == os.path.abspath(file_path).lower():
        output_path = os.path.splitext(output_path)[0] + "_1" + ext
    if os.path.exists(output_path):
        base, e = os.path.splitext(output_path)
        counter = 1
        while os.path.exists(f"{base}_{counter}{e}"):
            counter += 1
        output_path = f"{base}_{counter}{e}"
    return output_path


class TaskManager(QObject):
    """并行任务队列 + 信号通知（可配置 N 路并发）。"""

    # (task_id, pct, msg, speed)
    sig_progress = Signal(int, int, str, str)
    # (task_id, state)
    sig_state = Signal(int, str)
    # (msg, level)  level: info/success/warning/error
    sig_log = Signal(str, str)
    # 批量任务全部完成（无正在运行/等待的任务时发射）
    sig_batch_done = Signal()

    def __init__(self, services, parent=None):
        super().__init__(parent)
        self.services = services
        self._tasks = {}            # task_id -> Task
        self._queue = []            # 待调度的 task_id（按优先级取最大）
        self._next_id = 1
        self._lock = threading.Lock()
        self._currents = []         # 运行中的 Task 列表（并行度上限内）
        self._workers = []          # 运行中的工作线程
        # 并行度：默认 1（串行），可从偏好读取
        try:
            self.max_parallel = int(services.get_pref("parallel", 1))
        except Exception:
            self.max_parallel = 1
        self.max_parallel = max(1, min(self.max_parallel, 8))

    # ── 对外查询 ─────────────────────────────────
    def get_task(self, task_id: int):
        return self._tasks.get(task_id)

    def all_tasks(self):
        """按创建时间倒序返回全部任务（任务中心展示用）。"""
        return sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)

    def is_idle(self) -> bool:
        return not self._currents and not self._queue

    # ── 入队 ─────────────────────────────────────
    def add_task(self, name, task_type, file_path, output_path, params,
                 runner, canceller=None, history_type="", history_target="",
                 priority=0, need_ffmpeg=True, max_retries=0):
        """通用入队入口（阶段2）：runner(task, progress_cb) -> bool。

        progress_cb(pct, msg) 内部已含暂停冻结与取消拦截（抛 InterruptedError）。
        FFmpeg 未就绪（need_ffmpeg=True 时）返回 None。
        max_retries：失败后自动重试次数（默认不重试）。
        """
        if need_ffmpeg and not self.services.ffmpeg_ready():
            self.sig_log.emit("FFmpeg 未就绪，无法添加任务", "error")
            return None
        try:
            size = os.path.getsize(file_path) if file_path else 0
        except OSError:
            size = 0
        with self._lock:
            task_id = self._next_id
            self._next_id += 1
            task = Task(task_id=task_id, name=name,
                        task_type=task_type, file_path=file_path,
                        output_path=output_path, params=dict(params),
                        priority=priority, input_size=size,
                        runner=runner, canceller=canceller,
                        history_type=history_type,
                        history_target=history_target,
                        max_retries=max(0, int(max_retries)))
            self._tasks[task_id] = task
            self._queue.append(task_id)
        self.sig_log.emit(f"任务已添加到队列：{task.name}", "info")
        self.sig_state.emit(task_id, WAITING)
        self._schedule_next()
        return task_id

    def add_video_task(self, file_path, output_path, params, priority=0,
                       max_retries=0):
        """添加一个视频转换任务，返回 task_id；FFmpeg 未就绪返回 None。"""
        if not self.services.ffmpeg_ready():
            self.sig_log.emit("FFmpeg 未就绪，无法添加任务", "error")
            return None
        try:
            size = os.path.getsize(file_path)
        except OSError:
            size = 0
        with self._lock:
            task_id = self._next_id
            self._next_id += 1
            task = Task(task_id=task_id,
                        name=f"视频转换 - {os.path.basename(file_path)}",
                        task_type="video", file_path=file_path,
                        output_path=output_path, params=dict(params),
                        priority=priority, input_size=size,
                        history_type="视频转换",
                        history_target=params.get("fmt", "MP4"),
                        max_retries=max(0, int(max_retries)))
            self._tasks[task_id] = task
            self._queue.append(task_id)
        self.sig_log.emit(f"任务已添加到队列：{task.name}", "info")
        self.sig_state.emit(task_id, WAITING)
        self._schedule_next()
        return task_id

    # ── 调度 ─────────────────────────────────────
    def _schedule_next(self):
        """在并行度允许范围内持续启动任务，直到队列空或槽位满。"""
        to_run = []
        with self._lock:
            while len(self._currents) < self.max_parallel:
                # 优先级最高者先执行（跳过暂停的等待任务）
                runnable = [tid for tid in self._queue
                            if self._tasks[tid].state == WAITING]
                if not runnable:
                    break
                tid = max(runnable, key=lambda i: self._tasks[i].priority)
                self._queue.remove(tid)
                task = self._tasks[tid]
                task.state = RUNNING
                self._currents.append(task)
                to_run.append(task)
        # 锁外发射信号 + 启动线程，避免信号回调重入锁
        for task in to_run:
            self.sig_state.emit(task.task_id, RUNNING)
            worker = threading.Thread(
                target=self._worker_run, args=(task,), daemon=True)
            self._workers.append(worker)
            worker.start()

    def set_parallel(self, n):
        """运行时调整并行度（1~8）。"""
        self.max_parallel = max(1, min(int(n), 8))
        self._schedule_next()

    def _set_state(self, task, state):
        task.state = state
        self.sig_state.emit(task.task_id, state)
        self._check_batch_done()

    def _check_batch_done(self):
        """检查是否所有任务都已结束，若是则发射 sig_batch_done。"""
        active = [t for t in self._tasks.values()
                  if t.state in (WAITING, RUNNING, PAUSED)]
        if not active and self._tasks:
            self.sig_batch_done.emit()

    # ── 工作线程 ─────────────────────────────────
    def _worker_run(self, task):
        # 重置重试标志：本次运行结束时的 finally 按当前状态决定是否清队列
        task._retrying = False
        try:
            if task.task_type == "video":
                self._run_video(task)
            elif task.runner is not None:
                self._run_generic(task)
            else:
                task.error = "暂不支持的任务类型"
                self._set_state(task, FAILED)
        except Exception as ex:  # noqa: BLE001 - 任务线程必须兜底
            hint = _hint_ex(ex) or str(ex)
            task.error = hint
            self.sig_log.emit(f"{os.path.basename(task.file_path)} 处理失败：{hint}", "error")
            self._set_state(task, FAILED)
            self._record_history(task, False)
        finally:
            with self._lock:
                if task in self._currents:
                    self._currents.remove(task)
                # 重试中的任务已重新入队，这里不能移除
                if not getattr(task, "_retrying", False) \
                        and task.task_id in self._queue:
                    self._queue.remove(task.task_id)
            self._schedule_next()

    def _maybe_retry(self, task) -> bool:
        """任务失败后判断是否重试。返回 True 表示已重新入队。"""
        if task.max_retries <= 0 or task.retry_count >= task.max_retries:
            return False
        if task.state in (SUCCESS, CANCELLED):
            return False
        task.retry_count += 1
        task.state = WAITING
        task.progress = 0
        task.error = ""
        task._retrying = True
        with self._lock:
            if task.task_id not in self._queue:
                self._queue.append(task.task_id)
        self.sig_log.emit(
            f"{os.path.basename(task.file_path)} 失败，正在重试 "
            f"({task.retry_count}/{task.max_retries})…", "warning")
        self.sig_state.emit(task.task_id, WAITING)
        self._schedule_next()
        return True

    def _run_video(self, task):
        params = task.params
        # 输出目录可能不存在（用户自定义目录），先创建
        out_dir = os.path.dirname(task.output_path)
        if out_dir:
            try:
                os.makedirs(out_dir, exist_ok=True)
            except OSError as e:
                task.error = f"无法创建输出目录：{out_dir}"
                self.sig_log.emit(task.error, "error")
                self._set_state(task, FAILED)
                self._record_history(task, False)
                return

        fn = os.path.basename(task.file_path)
        fmt_ext = SUPPORTED_VIDEO.get(params.get("fmt", "MP4"), ".mp4")
        br = params.get("br", "自动")
        fps = params.get("fps", "原始帧率")
        last = {"pct": 0, "ts": time.time()}

        def prog(pct, msg):
            # 暂停冻结：ffmpeg 无法原生暂停，回调内轮询等待（进程随管道阻塞而停摆）
            while task.state == PAUSED:
                time.sleep(0.5)
            if task.state == CANCELLED:
                raise InterruptedError("已取消")
            speed = ""
            if pct >= 0:
                now = time.time()
                dpct = pct - last["pct"]
                dt = now - last["ts"]
                if dpct > 0 and dt > 0.3 and task.input_size > 0:
                    mb = task.input_size / 1048576 * dpct / 100
                    speed = f"{mb / dt:.1f} MB/s"
                    task.speed = speed
                last["pct"], last["ts"] = pct, now
            task.progress = max(0, pct)
            self.sig_progress.emit(task.task_id, max(0, pct), f"{fn}  {msg}", speed)

        try:
            ok = self.services.video_conv.convert(
                task.file_path, task.output_path, fmt_ext,
                VIDEO_CODECS.get(params.get("codec", "默认")),
                VIDEO_PRESETS.get(params.get("preset", "原始质量")),
                RESOLUTIONS.get(params.get("res", "原始分辨率")),
                None if br == "自动" else br,
                None if fps == "原始帧率" else int(fps),
                prog,
                copy_mode=bool(params.get("copy_mode", False)),
                selected_streams=params.get("selected_streams"),
                hw_accel=params.get("hw_accel"),
                subtitle_path=params.get("subtitle_path"))
        except InterruptedError:
            self.sig_log.emit(f"文件 {fn} 已取消", "info")
            self._set_state(task, CANCELLED)
            return
        except Exception as ex:  # noqa: BLE001
            if str(ex) == "已取消":
                self.sig_log.emit(f"文件 {fn} 已取消", "info")
                self._set_state(task, CANCELLED)
                return
            hint = _hint_ex(ex) or str(ex)
            task.error = hint
            self.sig_log.emit(f"文件 {fn} 处理失败：{hint}", "error")
            if self._maybe_retry(task):
                return
            self._set_state(task, FAILED)
            self._record_history(task, False)
            return

        if ok:
            task.progress = 100
            self.sig_progress.emit(task.task_id, 100, f"{fn}  转换完成", "")
            self.sig_log.emit(f"{fn} 转换完成", "success")
            self._set_state(task, SUCCESS)
        else:
            task.error = task.error or "转换失败"
            self.sig_log.emit(f"文件 {fn} 转换失败：{task.error}", "error")
            if self._maybe_retry(task):
                return
            self._set_state(task, FAILED)
        self._record_history(task, ok)

    # ── 通用任务执行（阶段2）─────────────────
    def _run_generic(self, task):
        fn = os.path.basename(task.file_path)
        # 输出目录可能不存在（用户自定义目录），先创建
        out_dir = os.path.dirname(task.output_path)
        if out_dir:
            try:
                os.makedirs(out_dir, exist_ok=True)
            except OSError:
                task.error = f"无法创建输出目录：{out_dir}"
                self.sig_log.emit(task.error, "error")
                self._set_state(task, FAILED)
                self._record_history(task, False)
                return

        def prog(pct, msg):
            # 与视频任务一致的暂停冻结 / 取消拦截语义
            while task.state == PAUSED:
                time.sleep(0.5)
            if task.state == CANCELLED:
                raise InterruptedError("已取消")
            task.progress = max(0, pct)
            self.sig_progress.emit(task.task_id, max(0, pct), f"{fn}  {msg}", "")

        try:
            ok = bool(task.runner(task, prog))
        except InterruptedError:
            self.sig_log.emit(f"任务已取消：{task.name}", "info")
            self._set_state(task, CANCELLED)
            return
        except Exception as ex:  # noqa: BLE001
            if str(ex) == "已取消":
                self.sig_log.emit(f"任务已取消：{task.name}", "info")
                self._set_state(task, CANCELLED)
                return
            hint = _hint_ex(ex) or str(ex)
            task.error = hint
            self.sig_log.emit(f"{fn} 处理失败：{hint}", "error")
            if self._maybe_retry(task):
                return
            self._set_state(task, FAILED)
            self._record_history(task, False)
            return

        # 运行中取消：转换器自行返回 False，此时直接结束（与视频取消一致，不记历史）
        if task.state == CANCELLED:
            self.sig_log.emit(f"任务已取消：{task.name}", "info")
            return

        if ok:
            task.progress = 100
            self.sig_progress.emit(task.task_id, 100, f"{fn}  处理完成", "")
            self.sig_log.emit(f"{task.name} 完成", "success")
            self._set_state(task, SUCCESS)
        else:
            task.error = task.error or "处理失败"
            self.sig_log.emit(f"{fn} 处理失败：{task.error}", "error")
            if self._maybe_retry(task):
                return
            self._set_state(task, FAILED)
        self._record_history(task, ok)

    def _record_history(self, task, ok):
        if not task.history_type:
            return
        try:
            self.services.history.add({
                "type": task.history_type,
                "source": os.path.basename(task.file_path),
                "target": task.history_target,
                "status": "success" if ok else "failed",
                "output_path": task.output_path,
            })
        except Exception:  # noqa: BLE001
            pass

    # ── 暂停 / 恢复 / 取消 ───────────────────────
    def pause_task(self, task_id):
        task = self._tasks.get(task_id)
        if task is None:
            return
        if task.state == RUNNING:
            self._set_state(task, PAUSED)
            self.sig_log.emit(f"{os.path.basename(task.file_path)} 已暂停", "info")
        elif task.state == WAITING:
            self._set_state(task, PAUSED)

    def resume_task(self, task_id):
        task = self._tasks.get(task_id)
        if task is None or task.state != PAUSED:
            return
        if task in self._currents:
            # 运行中被冻结：解除回调等待即可继续
            self._set_state(task, RUNNING)
        else:
            # 等待中被暂停：重新入队
            self._set_state(task, WAITING)
            with self._lock:
                if task_id not in self._queue:
                    self._queue.append(task_id)
            self._schedule_next()

    def cancel_task(self, task_id):
        task = self._tasks.get(task_id)
        if task is None or task.state in (SUCCESS, FAILED, CANCELLED):
            return
        if task.state == PAUSED and task in self._currents:
            # 冻结中取消：先解冻让回调抛出取消
            task.state = RUNNING
        if task in self._currents:
            self._set_state(task, CANCELLED)
            if task.canceller is not None:
                try:
                    task.canceller()
                except Exception:  # noqa: BLE001
                    pass
            # 并行场景下不能调用全局 video_conv.cancel()（会误伤其他任务），
            # 依赖 runner 回调内的 CANCELLED 检查自行退出。
        else:
            with self._lock:
                if task_id in self._queue:
                    self._queue.remove(task_id)
            self._set_state(task, CANCELLED)
            self.sig_log.emit(f"{os.path.basename(task.file_path)} 已取消", "info")
