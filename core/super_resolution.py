"""super_resolution — AI 图像超分（Real-ESRGAN x4plus，ONNX Runtime）。

模型（~20MB）首次使用时从官方 GitHub Release 下载到用户数据目录：
  https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/RealESRGAN_x4plus.onnx
推理用 onnxruntime（rapidocr 已引入该依赖），无 torch 依赖。
"""
import os
import threading
import urllib.request

import numpy as np
from PIL import Image

from utils.config import get_user_data_dir

MODEL_URL = ("https://github.com/xinntao/Real-ESRGAN/releases/download/"
             "v0.2.5.0/RealESRGAN_x4plus.onnx")
MODEL_FILENAME = "RealESRGAN_x4plus.onnx"


def model_path():
    return os.path.join(get_user_data_dir(), "models", MODEL_FILENAME)


def model_ready():
    return os.path.isfile(model_path())


def _download(url, dest, progress_cb=None):
    """下载模型到 dest，progress_cb(percent, msg)。"""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 FormatMaster"})

    def _hook(blocks, block_size, total):
        if progress_cb and total > 0:
            progress_cb(min(99, int(blocks * block_size * 100 / total)),
                        "下载模型中…")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, \
                open(tmp, "wb") as f:
            total = int(resp.headers.get("Content-Length", 0) or 0)
            done = 0
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress_cb and total:
                    progress_cb(min(99, int(done * 100 / total)),
                                "下载模型中…")
        os.replace(tmp, dest)
        if progress_cb:
            progress_cb(100, "模型下载完成")
        return True
    except Exception as e:  # noqa: BLE001
        try:
            os.remove(tmp)
        except OSError:
            pass
        if progress_cb:
            progress_cb(-1, f"模型下载失败: {e}")
        return False


def download_model_async(progress_cb=None, done_cb=None):
    """后台线程下载模型（不阻塞 UI）。"""
    def _job():
        ok = _download(MODEL_URL, model_path(), progress_cb)
        if done_cb:
            done_cb(ok)
    threading.Thread(target=_job, daemon=True).start()


def _preprocess(img):
    """PIL → NCHW float [-1,1]，并补齐到 8 的倍数。"""
    import numpy as _np
    # Real-ESRGAN 要求输入宽高为 8 的倍数（缩放图内部下采样）
    w = (img.width // 8) * 8
    h = (img.height // 8) * 8
    img = img.resize((max(w, 8), max(h, 8)), Image.BICUBIC)
    arr = _np.asarray(img, dtype=_np.float32) / 127.5 - 1.0
    arr = arr.transpose(2, 0, 1)[None]  # (1,3,H,W)
    return arr


def _postprocess(out):
    arr = out[0].transpose(1, 2, 0)
    arr = (arr + 1.0) * 127.5
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def super_resolve(input_path, output_path, progress_cb=None):
    """对图片做 4 倍超分。返回 bool；失败回调 (-1, 原因)。"""
    mp = model_path()
    if not model_ready():
        if progress_cb:
            progress_cb(-1, "模型未下载，请先在面板下载模型")
        return False
    try:
        import onnxruntime as ort
    except ImportError:
        if progress_cb:
            progress_cb(-1, "缺少 onnxruntime 依赖")
        return False
    try:
        if progress_cb:
            progress_cb(5, "加载模型…")
        so = ort.SessionOptions()
        so.intra_op_num_threads = os.cpu_count() or 4
        sess = ort.InferenceSession(mp, so, providers=["CPUExecutionProvider"])

        img = Image.open(input_path).convert("RGB")
        x = _preprocess(img)
        if progress_cb:
            progress_cb(15, "AI 推理中…")
        inp_name = sess.get_inputs()[0].name
        out = sess.run(None, {inp_name: x})[0]
        result = _postprocess(out)
        if progress_cb:
            progress_cb(85, "保存结果…")
        result.save(output_path)
        if progress_cb:
            progress_cb(100, "超分完成")
        return True
    except Exception as e:  # noqa: BLE001
        if progress_cb:
            progress_cb(-1, f"超分失败: {e}")
        return False
