"""app/logger — 全局统一日志模块（线程安全）。

替代分散在各处的 open/print 写日志逻辑：
- 线程安全：内部 Lock 串行化写入，避免多线程写同一文件时内容交错/损坏
- 日志级别：FORMATMASTER_LOG_LEVEL 环境变量控制（debug/info/warning/error，默认 debug）
- 大小轮转：超过 MAX_BYTES(2MB) 时滚动为 debug.log.1（保留 1 份备份），
  不再用「读全文件截尾」的低效写法
- 结构化行：[时间] [级别] [线程名] 消息（可附加 traceback）
"""
import datetime
import os
import sys
import threading
import traceback

# 日志级别
DEBUG, INFO, WARNING, ERROR = 10, 20, 30, 40
_LEVEL_NAMES = {DEBUG: "DBG", INFO: "INF", WARNING: "WRN", ERROR: "ERR"}
# 全名 → 级别值（原实现 {缩写: 值} 导致 "info"/"error" 等全名查不到，
# FORMATMASTER_LOG_LEVEL 除 debug 外全部失效，静默退回 DEBUG）
_LEVEL_MAP = {
    "debug": DEBUG, "info": INFO, "warning": WARNING, "error": ERROR,
}

MAX_BYTES = 2 * 1024 * 1024   # 单个日志文件上限
BACKUP_COUNT = 1              # 保留备份份数（debug.log.1）
_LOG_NAME = "debug.log"

_LOG_LOCK = threading.Lock()
_LEVEL = _LEVEL_MAP.get(
    os.environ.get("FORMATMASTER_LOG_LEVEL", "debug").strip().lower()
    or "debug", DEBUG)
_DEBUG_STDERR = os.environ.get("FORMATMASTER_DEBUG", "") == "1"


def get_log_dir() -> str:
    """日志目录（%APPDATA%/FormatMaster）。"""
    return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                        "FormatMaster")


def get_log_path() -> str:
    """当前日志文件完整路径。"""
    return os.path.join(get_log_dir(), _LOG_NAME)


def configure(level=None, backup_count=None):
    """运行时调整日志级别与备份保留份数（供设置页调用）。

    level: None 保持当前；否则 "debug"/"info"/"warning"/"error"（或 DEBUG 等 int）。
    backup_count: None 保持当前；否则 >=1 的整数（保留份数）。
    """
    global _LEVEL, BACKUP_COUNT
    if level is not None:
        if isinstance(level, int):
            _LEVEL = level
        else:
            _LEVEL = _LEVEL_MAP.get(
                str(level).strip().lower() or "debug", DEBUG)
    if backup_count is not None:
        try:
            BACKUP_COUNT = max(1, int(backup_count))
        except (TypeError, ValueError):
            pass


def _rotate():
    """超过上限时滚动备份：debug.log → debug.log.1（仅保留 BACKUP_COUNT 份）。

    仅在持有 _LOG_LOCK 时调用，避免并发竞态。
    """
    path = get_log_path()
    try:
        size = os.path.getsize(path)
    except OSError:
        return
    if size <= MAX_BYTES:
        return
    # 已有备份向后滚动：.1 → .2 …（受 BACKUP_COUNT 上限约束）
    for i in range(BACKUP_COUNT - 1, 0, -1):
        src, dst = f"{path}.{i}", f"{path}.{i + 1}"
        try:
            if os.path.exists(src):
                if os.path.exists(dst):
                    os.remove(dst)
                os.rename(src, dst)
        except OSError:
            pass
    # 超出保留份数的旧备份删除
    try:
        old = f"{path}.{BACKUP_COUNT + 1}"
        if os.path.exists(old):
            os.remove(old)
    except OSError:
        pass
    # 主文件滚动为 .1（若已存在则覆盖，保留最新一份）
    try:
        dst1 = path + ".1"
        if os.path.exists(dst1):
            os.remove(dst1)
        os.rename(path, dst1)
    except OSError:
        pass


def log(msg, level=DEBUG, exc=None):
    """写一行日志。

    msg: 日志内容；level: DEBUG/INFO/WARNING/ERROR；
    exc: 异常对象（可选），附加其完整 traceback。
    """
    if level < _LEVEL:
        return
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        tname = threading.current_thread().name or "main"
    except Exception:
        tname = "?"
    lname = _LEVEL_NAMES.get(level, "??")
    body = f"[{ts}] [{lname}] [{tname}] {msg}"
    if exc is not None:
        body += "\n" + "".join(
            traceback.TracebackException.from_exception(exc).format())
    with _LOG_LOCK:
        try:
            os.makedirs(get_log_dir(), exist_ok=True)
            _rotate()
            with open(get_log_path(), "a", encoding="utf-8") as f:
                f.write(body.rstrip("\n") + "\n")
        except OSError:
            pass
    if _DEBUG_STDERR:
        try:
            sys.stderr.write(f"[FormatMaster Debug] {body}\n")
            sys.stderr.flush()
        except Exception:
            pass


def info(msg):
    log(msg, INFO)


def warning(msg, exc=None):
    log(msg, WARNING, exc)


def error(msg, exc=None):
    log(msg, ERROR, exc)
