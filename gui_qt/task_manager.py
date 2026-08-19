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
from gui_qt.i18n import tr
import json
import os
import threading
import time
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal, QTimer

from app.exceptions import _hint_ex
from utils.config import (SUPPORTED_VIDEO, VIDEO_CODECS, VIDEO_PRESETS,
                          RESOLUTIONS, USER_PREFS)


# ── 任务状态 ─────────────────────────────────────
WAITING = "waiting"
RUNNING = "running"
PAUSED = "paused"
SUCCESS = "success"
FAILED = "failed"
CANCELLED = "cancelled"

_STATE_TEXT = {
    WAITING: tr("等待中", "Waiting"), RUNNING: tr("转换中", "Converting"), PAUSED: tr("已暂停", "Paused"),
    SUCCESS: "已完成", FAILED: tr("失败", "Failed"), CANCELLED: tr("已取消", "Cancelled"),
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
    ended_at: float = 0.0     # 终态时间戳（batch 失败汇总限定本次用）
    # 失败重试
    retry_count: int = 0      # 已重试次数
    max_retries: int = 0      # 最大重试次数（0=不重试）
    last_progress: int = 0    # 失败时进度，用于判断是否可断点续传
    runner_key: str = ""      # runner 重建标识（持久化恢复后按 key 重建，空=不可重建）


def make_output_path(file_path: str, out_dir: str, ext: str, name: str = None,
                     conflict: str | None = None) -> str:
    """生成输出路径：目标目录 + 源文件名新扩展名，按冲突策略处理同名。

    name: 可选自定义主文件名（不含扩展名），缺省用源文件名。
    conflict: 输出已存在时的处理策略——
      - "auto_rename"（默认）：追加 _N 计数避开（源目同路径时也走 _1）；
      - "overwrite"：直接返回同名路径，任务运行时覆盖旧文件。
      未指定时读用户偏好 qt_app/conflict_policy（设置页「转换」可配）。
    目录不存在时由调用方在任务启动前创建。
    """
    policy = conflict or USER_PREFS.get("qt_app", "conflict_policy",
                                        "auto_rename")
    nm = name if name else os.path.splitext(os.path.basename(file_path))[0]
    output_path = os.path.join(out_dir or os.path.dirname(file_path), nm + ext)
    if output_path.lower() == os.path.abspath(file_path).lower():
        output_path = os.path.splitext(output_path)[0] + "_1" + ext
    if os.path.exists(output_path) and policy != "overwrite":
        base, e = os.path.splitext(output_path)
        counter = 1
        while os.path.exists(f"{base}_{counter}{e}"):
            counter += 1
        output_path = f"{base}_{counter}{e}"
    return output_path


def _threads_per_task(max_parallel):
    """按并行度分配 ffmpeg 线程数，避免多任务抢占全部核心。

    单任务 max_parallel=1 返回 0（自动，用满全核）；
    并行 >1 时按「总核数/并行度」均分，至少 1。
    """
    if max_parallel <= 1:
        return 0
    import os as _os
    try:
        ncpu = _os.cpu_count() or 4
    except Exception:
        ncpu = 4
    return max(1, ncpu // max_parallel)


class TaskManager(QObject):
    """并行任务队列 + 信号通知（可配置 N 路并发）。"""

    # 内存中保留的任务记录上限：超出后删除最旧终态任务，
    # 防止长期使用导致 _tasks / 任务中心卡片无限累积
    MAX_TASKS = 200

    # (task_id, pct, msg, speed)
    sig_progress = Signal(int, int, str, str)
    # (task_id, state)
    sig_state = Signal(int, str)
    # (msg, level)  level: info/success/warning/error
    sig_log = Signal(str, str)
    # 批量任务全部完成（无正在运行/等待的任务时发射）
    sig_batch_done = Signal()
    # 任务记录被清理（超出保留上限删除最旧终态任务）时发射
    sig_task_pruned = Signal(int)

    def __init__(self, services, parent=None):
        super().__init__(parent)
        self.services = services
        self._tasks = {}            # task_id -> Task
        self._queue = []            # 待调度的 task_id（按优先级取最大）
        self._next_id = 1
        self._lock = threading.Lock()
        self._currents = []         # 运行中的 Task 列表（并行度上限内）
        self._workers = []          # 运行中的工作线程
        self._pause_events = {}     # task_id → threading.Event（暂停/恢复通知）
        # 快照持久化防抖定时器：批量任务频繁状态变化时合并写盘
        self._snapshot_timer = QTimer(self)
        self._snapshot_timer.setSingleShot(True)
        self._snapshot_timer.setInterval(2000)  # 2s 防抖
        self._snapshot_timer.timeout.connect(self._save_snapshot_now)
        # 并行度：默认 1（串行），可从偏好读取
        try:
            self.max_parallel = int(services.get_pref("parallel", 1))
        except Exception:
            self.max_parallel = 1
        self.max_parallel = max(1, min(self.max_parallel, 8))
        # 任务快照持久化：应用退出后恢复未完成任务（标记为中断，可一键重试）
        self._runner_factories = {}   # runner_key -> fn(task, progress_cb) -> bool
        self._load_snapshot()

    # ── 快照持久化 ─────────────────────────────
    @staticmethod
    def _snapshot_path():
        from utils.config import get_user_data_dir
        return os.path.join(get_user_data_dir(), "task_queue.json")

    def register_runner(self, runner_key, factory):
        """注册可重建的 runner 工厂（供持久化恢复任务重试用）。"""
        if runner_key:
            self._runner_factories[runner_key] = factory

    def save_snapshot(self):
        """触发快照保存（2s 防抖合并，批量任务高频写盘场景友好）。
        调用 flush_snapshot() 可立即写入（退出前兜底）。
        """
        self._snapshot_timer.start()

    def flush_snapshot(self):
        """立即写入快照（退出前兜底，跳过防抖）。"""
        self._snapshot_timer.stop()
        self._save_snapshot_now()

    def _save_snapshot_now(self):
        """实际写盘（防抖定时器到期后执行）。"""
        try:
            pending = [t for t in self._tasks.values()
                       if t.state in (WAITING, RUNNING, PAUSED)]
            if not pending:
                return
            data = [{
                "name": t.name, "task_type": t.task_type,
                "file_path": t.file_path, "output_path": t.output_path,
                "params": t.params, "priority": t.priority,
                "created_at": t.created_at, "history_type": t.history_type,
                "history_target": t.history_target, "runner_key": t.runner_key,
            } for t in pending]
            path = self._snapshot_path()
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
        except Exception:  # noqa: BLE001 - 快照失败不应影响任务
            pass

    def _load_snapshot(self):
        """启动时恢复未完成任务：标记为 FAILED（应用退出中断），用户可一键重试。"""
        try:
            path = self._snapshot_path()
            if not os.path.isfile(path):
                return
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            os.remove(path)
            for item in data:
                try:
                    task = Task(
                        task_id=self._next_id, name=item.get("name", ""),
                        task_type=item.get("task_type", ""),
                        file_path=item.get("file_path", ""),
                        output_path=item.get("output_path", ""),
                        params=dict(item.get("params") or {}),
                        priority=int(item.get("priority", 0)),
                        state=FAILED,
                        error=tr("应用上次退出时任务中断，可点击重试", "Interrupted by app exit, click retry"),
                        created_at=float(item.get("created_at", time.time())),
                        history_type=item.get("history_type", ""),
                        history_target=item.get("history_target", ""),
                        runner_key=item.get("runner_key", ""))
                    self._tasks[task.task_id] = task
                    self._next_id += 1
                except Exception:  # noqa: BLE001
                    continue
            if data:
                self.sig_log.emit(
                    tr("已恢复 {} 个中断任务（任务中心可重试）",
                       "Restored {} interrupted tasks (retry in Tasks)").format(len(data)),
                    "warning")
        except Exception:  # noqa: BLE001
            pass

    def _ensure_runner(self, task):
        """确保 task 有可执行的 runner（视频内置链路无需 runner）。"""
        if task.runner is not None or task.task_type == "video":
            return True
        factory = self._runner_factories.get(task.runner_key)
        if factory is None:
            return False
        try:
            task.runner = factory(task)
            return task.runner is not None
        except Exception:  # noqa: BLE001
            return False

    # ── 对外查询 ─────────────────────────────────
    def get_task(self, task_id: int):
        return self._tasks.get(task_id)

    def all_tasks(self):
        """按创建时间倒序返回全部任务（任务中心展示用）。"""
        return sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)

    def is_idle(self) -> bool:
        return not self._currents and not self._queue

    # ── 内存控制 ─────────────────────────────────
    def _prune_tasks(self):
        """任务记录上限控制：超出 MAX_TASKS 时删除最旧的终态任务。

        仅删除终态任务（SUCCESS/FAILED/CANCELLED），保证进行中任务安全；
        被删任务的 runner/canceller 闭包一并释放，避免其捕获的大对象
        长期驻留内存（这是转换类应用后台内存持续增长的常见来源）。
        """
        if len(self._tasks) <= self.MAX_TASKS:
            return
        finished = [t for t in self._tasks.values()
                    if t.state in (SUCCESS, FAILED, CANCELLED)]
        finished.sort(key=lambda t: t.created_at)
        excess = len(self._tasks) - self.MAX_TASKS
        for t in finished[:excess]:
            self._tasks.pop(t.task_id, None)
            t.runner = None
            t.canceller = None
            self.sig_task_pruned.emit(t.task_id)

    # ── 入队 ─────────────────────────────────────
    def add_task(self, name, task_type, file_path, output_path, params,
                 runner, canceller=None, history_type="", history_target="",
                 priority=0, need_ffmpeg=True, max_retries=0, runner_key=""):
        """通用入队入口（阶段2）：runner(task, progress_cb) -> bool。

        progress_cb(pct, msg) 内部已含暂停冻结与取消拦截（抛 InterruptedError）。
        FFmpeg 未就绪（need_ffmpeg=True 时）返回 None。
        max_retries：失败后自动重试次数（默认不重试）。
        runner_key：可重建 runner 的标识（持久化恢复后重试需要，可选）。
        """
        if need_ffmpeg and not self.services.ffmpeg_ready():
            self.sig_log.emit(tr("FFmpeg 未就绪，无法添加任务", "FFmpeg not ready, cannot add task"), "error")
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
                        max_retries=max(0, int(max_retries)),
                        runner_key=runner_key)
            self._tasks[task_id] = task
            self._queue.append(task_id)
        self.sig_log.emit(tr("任务已添加到队列：{}", "Task queued: {}").format(task.name), "info")
        self.sig_state.emit(task_id, WAITING)
        self._schedule_next()
        self.save_snapshot()
        self._prune_tasks()
        return task_id

    def add_video_task(self, file_path, output_path, params, priority=0,
                       max_retries=0):
        """添加一个视频转换任务，返回 task_id；FFmpeg 未就绪返回 None。"""
        if not self.services.ffmpeg_ready():
            self.sig_log.emit(tr("FFmpeg 未就绪，无法添加任务", "FFmpeg not ready, cannot add task"), "error")
            return None
        try:
            size = os.path.getsize(file_path)
        except OSError:
            size = 0
        with self._lock:
            task_id = self._next_id
            self._next_id += 1
            task = Task(task_id=task_id,
                        name=f"{tr('视频转换', 'Video Convert')} - {os.path.basename(file_path)}",
                        task_type="video", file_path=file_path,
                        output_path=output_path, params=dict(params),
                        priority=priority, input_size=size,
                        history_type=tr("视频转换", "Video Convert"),
                        history_target=params.get("fmt", "MP4"),
                        max_retries=max(0, int(max_retries)))
            self._tasks[task_id] = task
            self._queue.append(task_id)
        self.sig_log.emit(tr("任务已添加到队列：{}", "Task queued: {}").format(task.name), "info")
        self.sig_state.emit(task_id, WAITING)
        self._schedule_next()
        self.save_snapshot()
        self._prune_tasks()
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
        if state in (SUCCESS, FAILED, CANCELLED):
            task.ended_at = time.time()   # 终态时间，供 batch 失败统计限定本次
        # 业务日志落盘（debug.log，设置页「运行日志」可查看）：
        # 转换失败/成功/取消都记录，否则转换结果不写日志、日志页空白。
        try:
            from app import logger as _logger
            if state == FAILED:
                _logger.error(
                    f"[{task.task_type}] {task.name} 失败: "
                    f"{task.error or '未知错误'}")
            elif state == SUCCESS:
                _logger.info(f"[{task.task_type}] {task.name} 完成")
            elif state == CANCELLED:
                _logger.warning(f"[{task.task_type}] {task.name} 已取消")
        except Exception:  # noqa: BLE001 - 日志失败不影响任务状态
            pass
        self.sig_state.emit(task.task_id, state)
        self._check_batch_done()
        self.save_snapshot()
        self._prune_tasks()

    def _check_batch_done(self):
        """检查是否所有任务都已结束，若是则发射 sig_batch_done。"""
        active = [t for t in self._tasks.values()
                  if t.state in (WAITING, RUNNING, PAUSED)]
        if not active and self._tasks:
            self.sig_batch_done.emit()

    # ── 进度回调工厂（_run_video / _run_generic 共享）─────
    def _make_progress_callback(self, task, fn, track_speed=False):
        """创建统一的进度回调闭包：暂停冻结 / 取消拦截 / UI 节流。

        track_speed=True 时附带预估速度（视频任务用，依赖 task.input_size）。
        返回 (prog_fn, error_holder_dict)。error_holder 的 "err" 键在
        progress_callback(-1, msg) 时写入，供 runner 返回 False 后取具体原因。
        """
        pause_ev = self._pause_events.setdefault(task.task_id, threading.Event())
        # 非暂停状态下清除 event（避免上次暂停的残余信号导致立即跳过）
        if task.state != PAUSED:
            pause_ev.clear()

        th = {"ts": 0.0, "msg": "", "err": ""}
        last = {"pct": 0, "ts": time.time()}

        # 标志：pause_event.wait() 返回 True 表示被取消（由 cancel_task 设置），
        # 返回 False 表示超时（被 resume_task 的 set 唤醒）
        _cancel_flag = [False]

        def prog(pct, msg):
            # 暂停：等待 Event 通知（resume/cancel），~150ms 响应而非 500ms
            while task.state == PAUSED:
                if _cancel_flag[0]:
                    raise InterruptedError(tr("已取消", "Cancelled"))
                pause_ev.wait(0.15)
            if _cancel_flag[0] or task.state == CANCELLED:
                raise InterruptedError(tr("已取消", "Cancelled"))
            if pct < 0:
                th["err"] = msg
            speed = ""
            if pct >= 0:
                now = time.time()
                if track_speed:
                    dpct = pct - last["pct"]
                    dt = now - last["ts"]
                    if dpct > 0 and dt > 0.3 and task.input_size > 0:
                        mb = task.input_size / 1048576 * dpct / 100
                        speed = f"{mb / dt:.1f} MB/s"
                        task.speed = speed
                last["pct"], last["ts"] = pct, now
            task.progress = max(0, pct)
            # UI 节流：终态/错误/阶段消息变化强制刷新，其余 ~12fps
            now_e = time.time()
            if (pct < 0 or pct >= 100 or msg != th["msg"]
                    or now_e - th["ts"] >= 0.08):
                self.sig_progress.emit(task.task_id, max(0, pct),
                                       f"{fn}  {msg}", speed)
                th["ts"] = now_e
                th["msg"] = msg

        # 返回 cancel 注入句柄，供 cancel_task 设置取消标志
        prog._cancel_flag = _cancel_flag
        prog._pause_ev = pause_ev
        return prog, th

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
                task.error = tr("暂不支持的任务类型", "Unsupported task type")
                self._set_state(task, FAILED)
        except Exception as ex:  # noqa: BLE001 - 任务线程必须兜底
            hint = _hint_ex(ex) or str(ex)
            task.error = hint
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
                # 清理已结束的工作线程引用，避免 _workers 无限累积
                cur = threading.current_thread()
                if cur in self._workers:
                    self._workers.remove(cur)
                # 清理已完成任务的 pause event，避免内存泄漏
                self._pause_events.pop(task.task_id, None)
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
            tr("{} 失败，正在重试 ", "{} failed, retrying ").format(os.path.basename(task.file_path)) +
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
                task.error = tr("无法创建输出目录：{}（{}）",
                                "Cannot create output folder: {} ({})").format(
                    out_dir, e)
                self.sig_log.emit(task.error, "error")
                self._set_state(task, FAILED)
                self._record_history(task, False)
                return

        fn = os.path.basename(task.file_path)
        fmt_ext = SUPPORTED_VIDEO.get(params.get("fmt", "MP4"), ".mp4")
        prog, th = self._make_progress_callback(task, fn, track_speed=True)

        def convert_fn(input_path, output_path, params_override=None):
            """调用视频转换器；params_override 供自动恢复时传降级参数。"""
            p = params_override or task.params
            p_br = p.get("br", tr("自动", "Auto"))
            p_fps = p.get("fps", tr("原始帧率", "Original FPS"))
            return self.services.video_conv.convert(
                input_path, output_path, fmt_ext,
                VIDEO_CODECS.get(p.get("codec", tr("默认", "Default"))),
                VIDEO_PRESETS.get(p.get("preset", tr("原始质量", "Original quality"))),
                RESOLUTIONS.get(p.get("res", tr("原始分辨率", "Original resolution"))),
                None if p_br == tr("自动", "Auto") else p_br,
                None if p_fps == tr("原始帧率", "Original FPS") else int(p_fps),
                prog,
                copy_mode=bool(p.get("copy_mode", False)),
                selected_streams=p.get("selected_streams"),
                hw_accel=p.get("hw_accel"),
                subtitle_path=p.get("subtitle_path"),
                sub_font_size=p.get("sub_font_size"),
                max_threads=_threads_per_task(self.max_parallel),
                metadata=p.get("metadata"))

        try:
            ok = convert_fn(task.file_path, task.output_path)
        except InterruptedError:
            self.sig_log.emit(tr("文件 {} 已取消", "File {} cancelled").format(fn), "info")
            self._set_state(task, CANCELLED)
            return
        except Exception as ex:  # noqa: BLE001
            if str(ex) == "已取消":
                self.sig_log.emit(tr("文件 {} 已取消", "File {} cancelled").format(fn), "info")
                self._set_state(task, CANCELLED)
                return
            hint = _hint_ex(ex) or str(ex)
            task.error = hint
            # 自动恢复：修复源文件损坏 / 降级参数规避程序自身 bug
            if self._try_auto_recover_video(task, f"{hint} {str(ex)}",
                                            convert_fn, prog):
                return
            if self._maybe_retry(task):
                return
            self._set_state(task, FAILED)
            self._record_history(task, False)
            return

        if ok:
            task.progress = 100
            self.sig_progress.emit(task.task_id, 100, tr("{} 转换完成", "{} converted").format(fn), "")
            self.sig_log.emit(tr("{} 转换完成", "{} converted").format(fn), "success")
            self._set_state(task, SUCCESS)
        else:
            task.error = task.error or th["err"] or tr("转换失败", "Failed")
            if self._try_auto_recover_video(task, task.error,
                                            convert_fn, prog):
                return
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
                task.error = tr("无法创建输出目录：{}", "Cannot create output folder: {}").format(out_dir)
                self.sig_log.emit(task.error, "error")
                self._set_state(task, FAILED)
                self._record_history(task, False)
                return

        prog, th = self._make_progress_callback(task, fn)

        try:
            ok = bool(task.runner(task, prog))
        except InterruptedError:
            self.sig_log.emit(tr("任务已取消：{}", "Task cancelled: {}").format(task.name), "info")
            self._set_state(task, CANCELLED)
            return
        except Exception as ex:  # noqa: BLE001
            if str(ex) == "已取消":
                self.sig_log.emit(tr("任务已取消：{}", "Task cancelled: {}").format(task.name), "info")
                self._set_state(task, CANCELLED)
                return
            hint = _hint_ex(ex) or str(ex)
            task.error = hint
            # 自动恢复：源文件损坏 → 修复副本后重跑
            if self._try_auto_recover_generic(task, f"{hint} {str(ex)}", prog):
                return
            if self._maybe_retry(task):
                return
            self._set_state(task, FAILED)
            self._record_history(task, False)
            return

        # 运行中取消：转换器自行返回 False，此时直接结束（与视频取消一致，不记历史）
        if task.state == CANCELLED:
            self.sig_log.emit(tr("任务已取消：{}", "Task cancelled: {}").format(task.name), "info")
            return

        if ok:
            task.progress = 100
            self.sig_progress.emit(task.task_id, 100, tr("{} 处理完成", "{} done").format(fn), "")
            self.sig_log.emit(tr("{} 完成", "{} done").format(task.name), "success")
            self._set_state(task, SUCCESS)
        else:
            # 优先用 runner 通过 prog(-1, msg) 上报的具体原因
            task.error = task.error or th["err"] or tr("处理失败", "Failed")
            # toast 提示由 _on_state(FAILED) 统一发出，此处不再重复 sig_log
            if self._try_auto_recover_generic(task, task.error, prog):
                return
            if self._maybe_retry(task):
                return
            self._set_state(task, FAILED)
        self._record_history(task, ok)

    # ── 转换失败自动恢复（规避程序自身 bug / 修复源文件损坏）──
    def _try_auto_recover_video(self, task, error_text, convert_fn, prog):
        """视频转换失败自动恢复；返回 True 表示已处理（成功或已置终态）。

        经 core/auto_recover 分类：源文件损坏 → 修复副本重转；
        程序 bug/未知 → 降级参数（去字幕/关硬件加速）重转一次。
        """
        # 设置里关闭「失败自动修复」时跳过（仅提示失败）
        try:
            if not self.services.get_pref("auto_recover", True):
                return False
        except Exception:  # noqa: BLE001
            pass
        from core.auto_recover import recover_video_failure
        fn = os.path.basename(task.file_path)
        outcome = recover_video_failure(
            task.file_path, task.output_path, task.params, error_text,
            convert_fn, prog)
        if not outcome.handled:
            return False
        if outcome.success:
            task.progress = 100
            self.sig_progress.emit(task.task_id, 100,
                                   tr("{} 转换完成", "{} converted").format(fn), "")
            self.sig_log.emit(outcome.message, "success")
            self._set_state(task, SUCCESS)
            self._record_history(task, True)
            return True
        return False

    def _try_auto_recover_generic(self, task, error_text, prog):
        """通用任务失败自动恢复；返回 True 表示已处理（成功或已置终态）。

        源文件损坏时经 core/auto_recover 修复副本后重跑 runner 一次。
        """
        # 设置里关闭「失败自动修复」时跳过（仅提示失败）
        try:
            if not self.services.get_pref("auto_recover", True):
                return False
        except Exception:  # noqa: BLE001
            pass
        from core.auto_recover import recover_generic_failure
        fn = os.path.basename(task.file_path)

        def run_fn(t):
            return bool(t.runner(t, prog))

        outcome = recover_generic_failure(task, error_text, run_fn, prog)
        if not outcome.handled:
            return False
        if outcome.success:
            task.progress = 100
            self.sig_progress.emit(task.task_id, 100,
                                   tr("{} 处理完成", "{} done").format(fn), "")
            self.sig_log.emit(outcome.message, "success")
            self._set_state(task, SUCCESS)
            self._record_history(task, True)
            return True
        return False

    def _record_history(self, task, ok):
        if not task.history_type:
            return
        saved_bytes = 0
        if ok and task.output_path:
            # 节省空间：源文件 - 输出文件（转换后变小才算节省）
            try:
                src = (os.path.getsize(task.file_path)
                       if os.path.isfile(task.file_path) else 0)
                out = (os.path.getsize(task.output_path)
                       if os.path.isfile(task.output_path) else 0)
                saved_bytes = max(0, src - out)
            except OSError:
                saved_bytes = 0
        try:
            self.services.history.add({
                "type": task.history_type,
                "source": os.path.basename(task.file_path),
                "target": task.history_target,
                "status": "success" if ok else "failed",
                "output_path": task.output_path,
                "saved_bytes": saved_bytes,
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
            self.sig_log.emit(tr("{} 已暂停", "{} paused").format(os.path.basename(task.file_path)), "info")
        elif task.state == WAITING:
            self._set_state(task, PAUSED)

    def resume_task(self, task_id):
        task = self._tasks.get(task_id)
        if task is None or task.state != PAUSED:
            return
        # 通知暂停中的回调线程继续执行
        ev = self._pause_events.get(task_id)
        if ev:
            ev.set()
            ev.clear()
        if task in self._currents:
            self._set_state(task, RUNNING)
        else:
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
            # 通知暂停中的回调线程退出（设置取消标志 + 唤醒 Event）
            ev = self._pause_events.get(task_id)
            if ev:
                ev.set()
            task.state = RUNNING
        if task in self._currents:
            self._set_state(task, CANCELLED)
            # 注入取消标志到回调闭包，确保下次 prog 调用时立即抛 InterruptedError
            # 同时唤醒暂停中的回调（通过 Event）
            ev = self._pause_events.get(task_id)
            if ev:
                ev.set()
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
            self.sig_log.emit(tr("{} 已取消", "{} cancelled").format(os.path.basename(task.file_path)), "info")

    # ── 一键重试 ─────────────────────────────────
    def retry_task(self, task_id):
        """重试失败/取消的任务：重新入队执行。

        内存任务 runner 闭包仍有效可直接重跑；持久化恢复的任务（runner 丢失）
        通过 runner_key 工厂重建；两者都不可用时提示回面板重新添加。
        """
        task = self._tasks.get(task_id)
        if task is None or task.state not in (FAILED, CANCELLED):
            return False
        if not os.path.isfile(task.file_path):
            self.sig_log.emit(
                tr("无法重试：源文件不存在", "Cannot retry: source file missing"), "error")
            return False
        if not self._ensure_runner(task):
            self.sig_log.emit(
                tr("该任务需在对应面板重新添加", "Re-add this task from its panel"), "warning")
            return False
        task.retry_count = 0
        task.progress = 0
        task.speed = ""
        task.error = ""
        task.state = WAITING
        with self._lock:
            if task.task_id not in self._queue:
                self._queue.append(task.task_id)
        self.sig_log.emit(tr("任务已重新入队：{}", "Task requeued: {}").format(task.name), "info")
        self.sig_state.emit(task.task_id, WAITING)
        self._schedule_next()
        self.save_snapshot()
        return True
