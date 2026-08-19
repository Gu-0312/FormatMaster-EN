"""core/auto_recover — 转换过程内部异常自动处理（规避程序自身 bug）。

当转换失败时先分类失败原因，再按类别自动恢复，避免任务直接失败：
- cancel：用户取消，不处理
- damage：源文件损坏 → 调用 core.file_repair 修复副本后重转；
  修复失败则用降级参数（去字幕/关硬件加速）对原文件重试
- bug / unknown：程序自身缺陷或环境异常 → 用降级参数重试
  （移除字幕烧录、关闭硬件加速、关闭 copy 模式等易出错选项）

纯逻辑模块，不依赖 GUI；转换器通过 convert_fn 注入。
"""
import os
from dataclasses import dataclass

from app import logger as _logger
from core.file_repair import repair_file

# FFmpeg stderr 中的文件损坏特征关键词
DAMAGE_KEYWORDS = (
    "invalid data found when processing input",
    "moov atom not found",
    "could not find codec parameters",
    "cannot determine",
    "error while decoding",
    "truncated",
    "malformed",
    "bad magic",
    "corrupt",
    "broken",
    "crc mismatch",
    "premature end",
    "unexpected eof",
    "damaged",
)

# 典型程序自身 bug 异常类型（内部逻辑缺陷，非环境/文件问题）
_BUG_EXC_NAMES = ("KeyError", "AttributeError", "TypeError", "IndexError",
                  "NameError", "AssertionError", "ValueError")


@dataclass
class RecoveryOutcome:
    handled: bool = False    # 是否尝试了恢复
    success: bool = False    # 恢复后转换是否成功
    message: str = ""        # 用户可见说明


def classify_failure(exc=None, error_text=""):
    """分类失败原因。返回 'cancel' / 'damage' / 'bug' / 'unknown'。"""
    if exc is not None:
        if isinstance(exc, (KeyboardInterrupt, InterruptedError)):
            return "cancel"
        if str(exc) == "已取消":
            return "cancel"
        if type(exc).__name__ in _BUG_EXC_NAMES:
            return "bug"
    text = (error_text or "").lower()
    if any(k in text for k in DAMAGE_KEYWORDS):
        return "damage"
    if "取消" in text or "cancelled" in text:
        return "cancel"
    return "unknown"


def build_fallback_params(params, stage="bug"):
    """生成降级参数：移除程序易出错的选项，保留目标格式与核心参数。"""
    p = dict(params or {})
    # 字幕烧录（滤镜语法/字体缺失）是常见失败源，一律移除
    p.pop("subtitle_path", None)
    if stage == "bug":
        # 程序 bug：关闭硬件加速与 copy 模式，走最稳的软编路径
        p["hw_accel"] = None
        p["copy_mode"] = False
    return p


def recover_video_failure(input_path, output_path, params, error_text,
                          convert_fn, progress_cb=None):
    """视频转换失败后的自动恢复。

    convert_fn(input_path, output_path, params_override=None) -> bool
    progress_cb(pct, msg)：复用原进度回调。
    """
    kind = classify_failure(None, error_text)
    if kind == "cancel":
        return RecoveryOutcome()

    if kind == "damage":
        _logger.warning("转换失败：源文件损坏特征，尝试自动修复重转")
        r = repair_file(input_path)
        if r.success:
            if progress_cb:
                progress_cb(0, "检测到源文件损坏，已自动修复，正在重新转换…")
            if convert_fn(r.path, output_path, dict(params)):
                _logger.info("自动恢复成功：源文件已修复并完成转换")
                return RecoveryOutcome(True, True,
                                       "源文件已自动修复并完成转换")
        # 修复失败或修复副本转换失败：降级参数重转原始文件
        if progress_cb:
            progress_cb(0, "源文件修复失败，尝试降级参数重转…")
        fb = build_fallback_params(params, "bug")
        _logger.warning(f"修复失败或副本转换失败，降级参数重试: {fb}")
        if convert_fn(input_path, output_path, fb):
            _logger.info("自动恢复成功：已用降级参数完成转换")
            return RecoveryOutcome(True, True, "已用降级参数完成转换")
        _logger.error("自动恢复失败：文件损坏且修复/降级均失败")
        return RecoveryOutcome(True, False, "文件损坏且自动修复/降级均失败")

    # bug / unknown：降级参数重试一次（规避程序自身 bug）
    _logger.warning(f"转换内部异常（{kind}），自动降级重试")
    if progress_cb:
        progress_cb(0, "转换遇到内部异常，已自动降级重试…")
    fb = build_fallback_params(params, "bug")
    if convert_fn(input_path, output_path, fb):
        _logger.info("自动恢复成功：已用降级参数完成转换")
        return RecoveryOutcome(True, True, "已用降级参数完成转换")
    _logger.error("降级重试仍失败，任务将以失败结束")
    return RecoveryOutcome(True, False, "")


def recover_generic_failure(task, error_text, run_fn, progress_cb=None):
    """通用任务失败恢复：源文件损坏 → 修复副本后重跑 runner。

    run_fn(task) -> bool：接收（临时替换 file_path 的）任务执行一次。
    """
    kind = classify_failure(None, error_text)
    if kind != "damage":
        return RecoveryOutcome()
    _logger.warning("通用任务失败：源文件损坏，尝试修复重跑")
    r = repair_file(task.file_path)
    if not r.success:
        _logger.error("源文件损坏且无法自动修复")
        return RecoveryOutcome(True, False, "源文件损坏且无法自动修复")
    if progress_cb:
        progress_cb(0, "检测到源文件损坏，已自动修复，正在重试…")
    old_path = task.file_path
    task.file_path = r.path
    try:
        ok = bool(run_fn(task))
    except Exception as ex:  # noqa: BLE001 - 重跑仍异常视为恢复失败
        _logger.error(f"修复后重跑异常: {ex}", ex)
        ok = False
    finally:
        task.file_path = old_path
    if ok:
        _logger.info("自动恢复成功：源文件已修复并完成转换")
        return RecoveryOutcome(True, True, "源文件已自动修复并完成转换")
    _logger.error("修复后重试仍失败")
    return RecoveryOutcome(True, False, "修复后重试仍失败")
