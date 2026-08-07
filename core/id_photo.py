# -*- coding: utf-8 -*-
"""id_photo — 证件照换底色（双引擎）。

引擎 1（首选）：AI 人像抠图（MODNet onnx）
  人像分割得到 alpha 蒙版，再合成新底色。
  模型首次使用自动联网下载（约 26MB，多源镜像），下载失败/不可用自动回退算法。

引擎 2（兜底）：改进色度键
  自适应背景估计（四角候选 + 标准差选最小） + 自适应阈值 + 形态学清理 + 边缘羽化。
  适合纯色/近纯色背景照片；浅色衣服+浅色背景属物理极限，仍可能误伤。

纯 numpy + PIL + onnxruntime，无第三方抠图库依赖。
"""
import os
import time
import urllib.request

import numpy as np
from PIL import Image, ImageFilter

# ── 标准底色 ────────────────────────────────────
BG_COLORS = {
    "红底": (219, 64, 64),
    "蓝底": (67, 142, 219),
    "白底": (255, 255, 255),
}
DEFAULT_COLOR = "蓝底"

# ── AI 模型相关 ─────────────────────────────────
MODEL_DIR = os.path.join("data", "models", "idphoto")
MODEL_FILE = "modnet.onnx"
MODEL_URLS = [
    "https://hf-mirror.com/Xenova/modnet/resolve/main/onnx/model.onnx",
    "https://huggingface.co/Xenova/modnet/resolve/main/onnx/model.onnx",
]
_MODEL_MIN_SIZE = 20_000_000  # 正常模型 25.9MB；小于此视为下载不完整

# 进程级缓存（避免每次处理都重新加载模型/感知之前已永久失败）
_SESSION = None
_AI_FAILED = False
_AI_FAIL_MSG = ""

# matte 均值合理性窗口（防止预处理不匹配导致全 0/全 1）
_AI_REASON_LO = 0.05
_AI_REASON_HI = 0.95


def _model_path():
    return os.path.join(MODEL_DIR, MODEL_FILE)


def is_model_ready():
    p = _model_path()
    return os.path.isfile(p) and os.path.getsize(p) >= _MODEL_MIN_SIZE


def _ensure_model_dir():
    os.makedirs(MODEL_DIR, exist_ok=True)


def _download_model(progress_callback=None):
    """多源下载模型（含重试）。返回 True 成功。"""
    global _AI_FAIL_MSG
    _ensure_model_dir()
    dest = _model_path()
    tmp = dest + ".part"
    last_err = None
    for attempt in range(4):
        for url in MODEL_URLS:
            try:
                if progress_callback:
                    progress_callback(5, f"AI 模型下载中（{attempt + 1}/4）…")
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                r = urllib.request.urlopen(req, timeout=60)
                total = int(r.headers.get("Content-Length", 0))
                done = 0
                with open(tmp, "wb") as f:
                    while True:
                        chunk = r.read(1 << 16)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        if total and progress_callback:
                            # 下载阶段映射到总进度 5%~28%
                            pct = done * 100 // total
                            progress_callback(5 + pct * 23 // 100, "AI 模型下载中…")
                if os.path.getsize(tmp) >= _MODEL_MIN_SIZE:
                    os.replace(tmp, dest)
                    return True
            except Exception as e:
                last_err = e
                if progress_callback:
                    progress_callback(5, f"下载源失败，切换备用：{type(e).__name__}")
        time.sleep(2)  # 应对代理瞬时不可用
    _AI_FAIL_MSG = f"AI 模型下载失败：{last_err}"
    if progress_callback:
        progress_callback(-1, _AI_FAIL_MSG)
    return False


def _get_session(progress_callback=None):
    """懒加载 onnxruntime + 推理会话。失败返回 None，并把引擎标记为不可用。"""
    global _SESSION, _AI_FAILED, _AI_FAIL_MSG
    if _AI_FAILED:
        return None
    if _SESSION is not None:
        return _SESSION
    try:
        import onnxruntime as ort
    except ImportError as e:
        _AI_FAILED = True
        _AI_FAIL_MSG = f"需要 onnxruntime 才能运行 AI 引擎：{e}"
        return None
    if not is_model_ready():
        if progress_callback:
            progress_callback(5, "首次使用 AI 抠图，下载模型（约 26MB）…")
        if not _download_model(progress_callback):
            _AI_FAILED = True
            return None
    try:
        _SESSION = ort.InferenceSession(_model_path(), providers=["CPUExecutionProvider"])
    except Exception as e:
        _AI_FAILED = True
        _AI_FAIL_MSG = f"加载 AI 模型失败：{e}"
        return None
    return _SESSION


def _run_ai(arr, progress_callback=None):
    """MODNet 推理。返回 alpha（H,W 0~1）或 None（异常）。"""
    H, W = arr.shape[:2]
    if progress_callback:
        progress_callback(35, "AI 抠图：预处理…")
    # 短边 512 保持比例 bilinear（Xenova/modnet 预处理约定）
    scale = 512.0 / min(H, W)
    nw, nh = W * scale, H * scale
    # 长边封顶 1536：极长宽比（全景/长条图）避免推理输入过大变慢
    if max(nw, nh) > 1536:
        scale *= 1536.0 / max(nw, nh)
    nw, nh = int(round(W * scale)), int(round(H * scale))
    # 模型 Concat 节点要求尺寸能被 32 整除（U-Net 步幅 32）；向上对齐
    nw, nh = ((nw + 31) // 32) * 32, ((nh + 31) // 32) * 32
    pil = Image.fromarray(arr)
    small = pil.resize((nw, nh), Image.BILINEAR)
    x = np.asarray(small, dtype=np.float32).transpose(2, 0, 1)[None]  # 1x3xHxW
    x = x / 255.0 * 2.0 - 1.0  # mean/std=0.5 → [-1, 1]
    if progress_callback:
        progress_callback(55, "AI 抠图：推理…")
    out = _SESSION.run(None, {"input": x})[0]  # 1x1xhxw
    matte = out[0, 0]
    matte = np.clip(matte, 0.0, 1.0).astype(np.float32)
    # 合理性检查：均值极端或含 NaN → 视为预处理/模型不匹配，禁用
    m = float(matte.mean())
    if not np.isfinite(matte).all() or m < _AI_REASON_LO or m > _AI_REASON_HI:
        return None
    # 还原到原图尺寸
    matte_img = Image.fromarray((matte * 255).astype(np.uint8), "L")
    matte_img = matte_img.resize((W, H), Image.BILINEAR)
    return np.asarray(matte_img, dtype=np.float32) / 255.0


# ── 改进色度键（兜底） ──────────────────────────
def _alpha_chroma(arr):
    """自适应背景估计 + 色度键 + 形态学 + 羽化。返回 alpha（H,W 0~1）。"""
    f = arr.astype(np.float32)
    h, w = arr.shape[:2]
    # 1. 背景色估计：四角 16x16 候选块，取标准差最小者（更纯净）
    s = max(8, min(16, h // 8, w // 8))
    candidates = [f[:s, :s], f[:s, -s:], f[-s:, :s], f[-s:, -s:]]
    best_std, best_mean = float("inf"), candidates[0].reshape(-1, 3).mean(axis=0)
    for blk in candidates:
        flat = blk.reshape(-1, 3)
        std = float(flat.std(axis=0).mean())
        if std < best_std:
            best_std, best_mean = std, flat.mean(axis=0)
    bg = best_mean
    # 2. 距离阈值：基于背景块标准差自适应（夹到合理范围）
    sigma = max(8.0, best_std)
    t_full = float(np.clip(2.6 * sigma, 22.0, 80.0))
    t_soft = float(np.clip(5.0 * sigma, 60.0, 160.0))
    # 3. 距离 → alpha 渐变（背景=1，人像=0，便于后面合成时反转：alpha(前景)=1-a）
    diff = f - bg
    dist = np.sqrt((diff * diff).sum(axis=2))
    alpha_bg = np.clip((dist - t_full) / max(t_soft - t_full, 1.0), 0.0, 1.0)  # 0=背景
    a = 1.0 - alpha_bg  # 1=前景
    # 4. 形态学清理 + 边缘羽化
    a_img = Image.fromarray((a * 255).astype(np.uint8), "L")
    a_img = a_img.filter(ImageFilter.MaxFilter(3))  # 抹平前景内暗斑噪点
    a_img = a_img.filter(ImageFilter.MinFilter(3))  # 抹平背景内亮斑噪点
    a_img = a_img.filter(ImageFilter.GaussianBlur(1.5))  # 边缘羽化
    return np.asarray(a_img, dtype=np.float32) / 255.0


def _apply_alpha(arr, alpha, target_rgb):
    """alpha 合成：前景=原图，背景=target_rgb。"""
    a = alpha[..., None].astype(np.float32)
    return arr.astype(np.float32) * a + np.asarray(target_rgb, dtype=np.float32) * (1.0 - a)


# ── 统一入口 ────────────────────────────────────
def change_background(input_path, output_path, color=DEFAULT_COLOR,
                      progress_callback=None, use_ai=True):
    """换底色。use_ai=True 优先 AI 引擎，失败/异常自动回退色度键。"""
    if color not in BG_COLORS:
        return False
    target = BG_COLORS[color]
    try:
        img = Image.open(input_path).convert("RGB")
    except (OSError, IOError):
        if progress_callback:
            progress_callback(-1, "错误：无法打开图片，文件可能已损坏")
        return False
    arr = np.asarray(img, dtype=np.uint8)

    engine = ""
    alpha = None
    if use_ai:
        if progress_callback:
            progress_callback(3, "AI 人像抠图引擎…")
        sess = _get_session(progress_callback)
        if sess is not None:
            alpha = _run_ai(arr, progress_callback)
            if alpha is not None:
                engine = "AI 人像抠图"
    if alpha is None:
        if progress_callback:
            progress_callback(35, "色度键算法（兜底）…")
        alpha = _alpha_chroma(arr)
        if not engine:
            engine = "色度键算法"

    if progress_callback:
        progress_callback(80, "合成新底色…")
    out_arr = _apply_alpha(arr, alpha, target)
    out = Image.fromarray(np.clip(out_arr, 0, 255).astype(np.uint8), "RGB")
    try:
        out.save(output_path, quality=95)
    except (OSError, IOError) as e:
        if progress_callback:
            progress_callback(-1, f"保存失败：{e}")
        return False
    out.close()
    img.close()
    if progress_callback:
        progress_callback(100, f"完成（{engine}）")
    return True
