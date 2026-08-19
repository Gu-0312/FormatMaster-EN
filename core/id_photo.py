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

# ── 目标底色 ────────────────────────────────────
# 键为中文名（面板下拉项与偏好存储统一用键，中英界面下语义一致）
BG_COLORS = {
    "红底": (219, 64, 64),
    "蓝底": (67, 142, 219),
    "白底": (255, 255, 255),
    "灰底": (200, 200, 200),
    "绿底": (0, 180, 90),
    "黑底": (40, 40, 40),
}
DEFAULT_COLOR = "蓝底"
# 透明输出：生成带 alpha 通道的 PNG（可叠加到任意画面）
TRANSPARENT_KEY = "透明PNG"

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
    """模型路径（打包兼容）：资源自带（只读）→ 用户数据目录（可写下载目标）。

    优先级：
    1. get_resource_path（打包后指向 _MEIPASS/data/models，只读；开发时
       即项目根 data/models）——打包随附的模型，命中则免下载；
    2. 用户数据目录 models/idphoto（可写，持久化）——打包后模型缺失时
       的下载目标，不写安装目录（符合项目数据文件规范）。
    """
    try:
        from utils.config import get_resource_path
        rp = get_resource_path(os.path.join(MODEL_DIR, MODEL_FILE))
        if os.path.isfile(rp) and os.path.getsize(rp) >= _MODEL_MIN_SIZE:
            return rp
    except Exception:  # noqa: BLE001 - 资源路径不可用时回退
        pass
    try:
        from utils.config import get_user_data_dir
        return os.path.join(get_user_data_dir(), "models", "idphoto",
                            MODEL_FILE)
    except Exception:  # noqa: BLE001 - 开发环境回退项目 data
        return os.path.join(MODEL_DIR, MODEL_FILE)


def is_model_ready():
    p = _model_path()
    return os.path.isfile(p) and os.path.getsize(p) >= _MODEL_MIN_SIZE


def _ensure_model_dir():
    os.makedirs(os.path.dirname(_model_path()), exist_ok=True)


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
    # 3. 距离 → alpha 渐变：距背景色越远越可能是前景
    #    alpha: 1=前景保留原图，0=背景换底色（与 AI 引擎语义一致）
    diff = f - bg
    dist = np.sqrt((diff * diff).sum(axis=2))
    a = np.clip((dist - t_full) / max(t_soft - t_full, 1.0), 0.0, 1.0)
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


# ── 标准证件照尺寸（像素，300dpi） ──────────────
# 键为中文名（面板直接用作下拉项），值 (宽, 高) 或 None=原尺寸
PHOTO_SIZES = {
    "原尺寸": None,
    "小1寸": (259, 377),       # 2.2×3.2cm  驾驶证
    "1寸": (295, 413),          # 2.5×3.5cm  身份证
    "大1寸": (390, 567),        # 3.3×4.8cm  护照/港澳通行证
    "小2寸": (413, 531),        # 3.5×4.5cm  港澳通行证/日本签证
    "2寸": (413, 579),          # 3.5×4.9cm  学位证/简历照
    "大2寸": (413, 626),        # 3.5×5.3cm  签证照
    "3寸": (550, 840),          # 4.7×7.1cm
    "美签照": (601, 601),       # 5.1×5.1cm  美国签证
    "4寸": (898, 1205),         # 7.6×10.2cm
    "5寸": (1051, 1500),        # 8.9×12.7cm
    "6寸": (1205, 1795),        # 10.2×15.2cm
}


def crop_to_size(pil_img, target, offset=0.0):
    """按目标比例中心裁剪（垂直偏移可调），再缩放到目标像素。

    offset: -1~1，正=裁切窗口上移（保留更多顶部，人像偏下），负=下移。
    返回新 PIL 图像；target 为 None 时原样返回。
    """
    if target is None:
        return pil_img
    tw, th = target
    W, H = pil_img.size
    r_src, r_tgt = W / H, tw / th
    if abs(r_src - r_tgt) < 1e-4:  # 比例一致：直接缩放
        return pil_img.resize((tw, th), Image.LANCZOS)
    if r_src > r_tgt:  # 源图更宽：裁左右两侧
        cw = int(round(H * r_tgt))
        box = ((W - cw) // 2, 0, (W - cw) // 2 + cw, H)
    else:  # 源图更高：裁上下，支持垂直偏移
        ch = int(round(W / r_tgt))
        max_off = (H - ch) / 2.0
        cy = int(round((H - ch) / 2.0 + max_off * offset))
        cy = max(0, min(H - ch, cy))
        box = (0, cy, W, cy + ch)
    return pil_img.crop(box).resize((tw, th), Image.LANCZOS)


# ── 统一入口 ────────────────────────────────────
def _get_alpha(arr, progress_callback=None, use_ai=True):
    """AI 人像抠图优先，失败/异常自动回退色度键。返回 (alpha, 引擎名)。"""
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
    return alpha, engine


def change_background(input_path, output_path, color=DEFAULT_COLOR,
                      progress_callback=None, use_ai=True,
                      size=None, offset=0.0, dpi=300, quality=95):
    """换底色（可选按标准证件照尺寸裁剪缩放）。

    color: BG_COLORS 的键、TRANSPARENT_KEY（透明 PNG）或任意 RGB 元组 (r,g,b)；
    use_ai=True 优先 AI 引擎，失败/异常自动回退色度键。
    size: PHOTO_SIZES 的像素元组 (w, h) 或 None 不裁剪；
    offset: 裁剪窗口垂直偏移 -1~1（正=保留更多顶部）；
    dpi: 输出 DPI（写入图像元数据，决定打印物理尺寸）；quality: JPG 质量 1~100。
    """
    if color == TRANSPARENT_KEY:
        target = None
    elif isinstance(color, (tuple, list)) and len(color) == 3:
        target = tuple(max(0, min(255, int(round(c)))) for c in color)
    elif color in BG_COLORS:
        target = BG_COLORS[color]
    else:
        return False
    try:
        with Image.open(input_path) as _f:
            img = _f.convert("RGB")
    except (OSError, IOError):
        if progress_callback:
            progress_callback(-1, "错误：无法打开图片，文件可能已损坏")
        return False
    arr = np.asarray(img, dtype=np.uint8)

    alpha, engine = _get_alpha(arr, progress_callback, use_ai)

    if target is None:
        # 透明 PNG：RGB 原样 + alpha 通道（背景区域透明）
        if progress_callback:
            progress_callback(80, "生成透明 PNG…")
        a = np.clip((alpha * 255).astype(np.uint8), 0, 255)
        out = Image.fromarray(np.dstack([arr, a]), "RGBA")
    else:
        if progress_callback:
            progress_callback(80, "合成新底色…")
        out_arr = _apply_alpha(arr, alpha, target)
        out = Image.fromarray(np.clip(out_arr, 0, 255).astype(np.uint8), "RGB")
    if size is not None:
        if progress_callback:
            progress_callback(85, f"裁剪缩放 {size[0]}×{size[1]}…")
        out = crop_to_size(out, size, offset)
    try:
        save_kw = {"dpi": (int(dpi), int(dpi))}
        if str(output_path).lower().endswith((".jpg", ".jpeg")):
            save_kw["quality"] = int(quality)
        out.save(output_path, **save_kw)
    except (OSError, IOError) as e:
        if progress_callback:
            progress_callback(-1, f"保存失败：{e}")
        return False
    out.close()
    img.close()
    if progress_callback:
        progress_callback(100, f"完成（{engine}）")
    return True


# ── 自定义尺寸（像素换算，300dpi） ──────────────
DPI = 300


def size_to_px(w, h, unit="px"):
    """将用户自定义尺寸换算为像素元组 (宽, 高)。

    unit: "px" 像素 / "cm" 厘米 / "inch" 英寸；按 DPI 换算。
    入参非法或非正返回 None。
    """
    try:
        fw, fh = float(w), float(h)
    except (TypeError, ValueError):
        return None
    if fw <= 0 or fh <= 0:
        return None
    if unit == "inch":
        fw, fh = fw * DPI, fh * DPI
    elif unit == "cm":
        fw, fh = fw / 2.54 * DPI, fh / 2.54 * DPI
    return int(round(fw)), int(round(fh))


# ── 证照预设套餐（类型 → 尺寸键 + 底色键） ──────
CARD_PRESETS = {
    "身份证":     {"size": "1寸",   "bg": "白底"},
    "驾照":       {"size": "小1寸", "bg": "白底"},
    "护照":       {"size": "大1寸", "bg": "白底"},
    "港澳通行证": {"size": "小2寸", "bg": "蓝底"},
    "简历/学位证": {"size": "2寸",   "bg": "蓝底"},
    "签证通用":    {"size": "大2寸", "bg": "白底"},
    "美国签证":    {"size": "美签照", "bg": "白底"},
}

# ── 冲印相纸（物理尺寸 宽×高 cm） ───────────────
PAPER_SIZES = {
    "A6": (10.5, 14.8),   # A6 照片纸 105×148mm
    "4寸": (7.6, 10.2),
    "5寸": (8.9, 12.7),
    "6寸": (10.2, 15.2),
}


# ── 头部比例参考线（仅预览辅助，不写入输出） ───
def draw_head_guides(pil_img, color=(220, 30, 30)):
    """在最终比例图上绘制标准头部占比参考框。

    头顶距上边约 10%，头部高度约占照片高度 65%，头部宽度约占 55%。
    仅用于辅助裁剪定位，预览显示，不写入正式输出。
    """
    try:
        from PIL import ImageDraw
    except ImportError:
        return pil_img
    img = pil_img.convert("RGB").copy()
    W, H = img.size
    top = int(H * 0.10)
    head_h = int(H * 0.65)
    head_w = int(W * 0.55)
    x0 = (W - head_w) // 2
    y1 = min(top + head_h, H - int(H * 0.05))
    d = ImageDraw.Draw(img)
    d.rectangle([x0, top, x0 + head_w, y1], outline=color, width=2)
    # 头顶基准线
    d.line([x0, top, x0 + head_w, top], fill=color, width=1)
    return img


# ── 一键冲印排版 ────────────────────────────────
def layout_print(pil_img, paper_wh, dpi=300, margin_mm=3.0, gap_mm=2.0):
    """将单张证件照平铺到相纸上，返回白底排版图（RGB）。

    paper_wh: 相纸物理尺寸 (宽cm, 高cm)，如 6寸=(10.2, 15.2)；
    margin_mm/gap_mm: 边距/间距（毫米）。自动计算行列并居中排布。
    """
    from PIL import Image
    paper_w = int(round(paper_wh[0] / 2.54 * dpi))
    paper_h = int(round(paper_wh[1] / 2.54 * dpi))
    m = int(round(margin_mm / 25.4 * dpi))
    g = int(round(gap_mm / 25.4 * dpi))
    sw, sh = pil_img.size
    avail_w, avail_h = paper_w - 2 * m, paper_h - 2 * m
    cols = max(1, (avail_w + g) // (sw + g))
    rows = max(1, (avail_h + g) // (sh + g))
    if cols * sw + (cols - 1) * g > avail_w:
        cols = max(1, cols - 1)
    if rows * sh + (rows - 1) * g > avail_h:
        rows = max(1, rows - 1)
    used_w = cols * sw + (cols - 1) * g
    used_h = rows * sh + (rows - 1) * g
    ox, oy = (paper_w - used_w) // 2, (paper_h - used_h) // 2
    paper = Image.new("RGB", (paper_w, paper_h), (255, 255, 255))
    for r in range(rows):
        for c in range(cols):
            x = ox + c * (sw + g)
            y = oy + r * (sh + g)
            paper.paste(pil_img, (x, y))
    return paper


def layout_print_multi(paper_wh, cells, dpi=300, margin_mm=3.0, gap_mm=2.0):
    """多尺寸混排：一张相纸排多种尺寸的证件照，返回白底 RGB 图。

    paper_wh: 相纸物理尺寸 (宽cm, 高cm)，如 6寸=(10.2, 15.2)；
    cells: [(PIL Image, count), ...]，每种尺寸排 count 张；
    每种尺寸内部按接近方形的行列排布，块之间按行贪心放置、居中。
    """
    from PIL import Image
    paper_w = int(round(paper_wh[0] / 2.54 * dpi))
    paper_h = int(round(paper_wh[1] / 2.54 * dpi))
    m = int(round(margin_mm / 25.4 * dpi))
    g = int(round(gap_mm / 25.4 * dpi))
    avail_w, avail_h = paper_w - 2 * m, paper_h - 2 * m

    # 每种尺寸 → 块（内部行列尽量接近方形）
    blocks = []
    for img, count in cells:
        sw, sh = img.size
        if count <= 0 or sw <= 0 or sh <= 0:
            continue
        best = (count, 1)
        for cols in range(1, count + 1):
            rows = (count + cols - 1) // cols
            if abs(cols - rows) < abs(best[0] - best[1]):
                best = (cols, rows)
        cols, rows = best
        bw = cols * sw + (cols - 1) * g
        bh = rows * sh + (rows - 1) * g
        blocks.append((bw, bh, img, count, cols, rows))
    if not blocks:
        return Image.new("RGB", (paper_w, paper_h), (255, 255, 255))

    paper = Image.new("RGB", (paper_w, paper_h), (255, 255, 255))
    cx, cy, row_h = m, m, 0
    for bw, bh, img, count, cols, rows in blocks:
        if bw > avail_w or bh > avail_h:
            continue  # 单块超出相纸则跳过该种
        if cx + bw > m + avail_w:  # 换行
            cx = m
            cy += row_h + g
            row_h = 0
        if cy + bh > m + avail_h:  # 相纸已满
            break
        for i in range(count):
            r, c = divmod(i, cols)
            x = cx + c * (img.width + g)
            y = cy + r * (img.height + g)
            paper.paste(img, (x, y))
        cx += bw + g
        row_h = max(row_h, bh)
    return paper


# ── 合规自检 ────────────────────────────────────
def check_compliance(img_path, size=None, offset=0.0, use_ai=True,
                     progress_callback=None):
    """证件照合规自检：基于人像前景蒙版检测头部位置与占比。

    size: 目标像素 (w, h) 或 None（原尺寸）；offset: 裁剪偏移。
    返回 dict：ok、head_top_pct（头顶距上边%）、person_h_pct（人像高占比%）、
    person_w_pct、issues（问题列表）；处理失败返回 None。
    """
    try:
        with Image.open(img_path) as _f:
            img = _f.convert("RGB")
    except (OSError, IOError):
        return None
    arr = np.asarray(img, dtype=np.uint8)
    alpha, _ = _get_alpha(arr, progress_callback, use_ai)
    if size is not None:
        a_img = Image.fromarray((alpha * 255).astype(np.uint8), "L")
        a_img = crop_to_size(a_img, size, offset)
        alpha = np.asarray(a_img, dtype=np.float32) / 255.0
    mask = alpha > 0.5
    H, W = mask.shape
    if H <= 0 or W <= 0 or not mask.any():
        return {"ok": False, "issues": ["未检测到人像，无法自检"]}
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    top, bottom = int(rows[0]), int(rows[-1])
    head_top_pct = round(top / H * 100)
    person_h_pct = round((bottom - top) / H * 100)
    person_w_pct = round((cols[-1] - cols[0]) / W * 100)
    issues = []
    if head_top_pct < 5:
        issues.append("头顶距上边缘过近（{}%），可能被裁切，建议裁剪位置偏下".format(head_top_pct))
    elif head_top_pct > 15:
        issues.append("头顶距上边缘过远（{}%），人像偏小，建议裁剪位置偏上".format(head_top_pct))
    if person_h_pct < 60:
        issues.append("人像偏小（高度占 {}%），建议裁剪位置偏上或放大".format(person_h_pct))
    elif person_h_pct > 95:
        issues.append("人像过大（高度占 {}%），可能超出取景，建议裁剪位置偏下".format(person_h_pct))
    return {
        "ok": not issues,
        "head_top_pct": head_top_pct,
        "person_h_pct": person_h_pct,
        "person_w_pct": person_w_pct,
        "issues": issues,
    }

