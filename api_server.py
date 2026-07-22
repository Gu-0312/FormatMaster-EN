"""格式大师 API 服务器 — 供Postman / 前端调用"""
import os, sys, uuid, shutil, json, tempfile, threading

# 路径设置
if getattr(sys, 'frozen', False):
    base_dir = sys._MEIPASS
    sys.path.insert(0, base_dir)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, base_dir)

from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename

from utils.config import *
from core.video_converter import VideoConverter
from core.audio_converter import AudioConverter
from core.image_converter import ImageConverter
from core.doc_converter import DocumentConverter
from core.tools import pdf_merge, pdf_split, pdf_get_page_count, image_compress, batch_rename

app = Flask(__name__)

# 临时文件目录
UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "FormatMaster_API")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 转换器实例
video_conv = VideoConverter()
audio_conv = AudioConverter()
image_conv = ImageConverter()
doc_conv   = DocumentConverter()


# ═══════════════════════════════════════════════
#  工具函数
# ═══════════════════════════════════════════════
def _save_upload(file_storage):
    """保存上传文件到临时目录，返回路径"""
    filename = secure_filename(file_storage.filename) or f"{uuid.uuid4().hex}"
    path = os.path.join(UPLOAD_DIR, filename)
    file_storage.save(path)
    return path


def _ok(msg, data=None, file_path=None):
    """成功响应"""
    if file_path and os.path.exists(file_path):
        return send_file(file_path, as_attachment=True,
                         download_name=os.path.basename(file_path))
    resp = {"success": True, "message": msg}
    if data:
        resp.update(data)
    return jsonify(resp)


def _err(msg, code=400):
    return jsonify({"success": False, "message": msg}), code


# ═══════════════════════════════════════════════
#  健康检查 & 格式查询
# ═══════════════════════════════════════════════
@app.route("/api/health", methods=["GET"])
def health():
    from utils.ffmpeg_manager import FFmpegManager
    mgr = FFmpegManager()
    return jsonify({
        "status": "running",
        "app": APP_NAME,
        "version": APP_VERSION,
        "ffmpeg": mgr.is_available(),
    })


@app.route("/api/formats", methods=["GET"])
def formats():
    return jsonify({
        "video": SUPPORTED_VIDEO,
        "audio": SUPPORTED_AUDIO,
        "image": SUPPORTED_IMAGE,
        "doc_read": DOC_READ_FORMATS,
        "doc_convert": DOC_CONVERSION_MAP,
    })


# ═══════════════════════════════════════════════
#  视频转换
# ═══════════════════════════════════════════════
@app.route("/api/video/convert", methods=["POST"])
def api_video_convert():
    """
    POST /api/video/convert
    form-data:
      file: 视频文件
      format: 目标格式 (mp4/avi/mkv...)
      codec: 编码 (libx264/libx265/...) [可选]
      preset: 画质 (high/medium/low) [可选]
      resolution: 分辨率 (1920x1080) [可选]
      fps: 帧率 [可选]
      bitrate: 码率 (2M/5M) [可选]
    返回: 转换后的文件
    """
    f = request.files.get("file")
    if not f:
        return _err("请上传文件（file字段）")

    fmt = request.form.get("format", "mp4")
    ext = SUPPORTED_VIDEO.get(fmt.upper(), f".{fmt}")
    if not ext.startswith("."):
        ext = f".{fmt}"

    src = _save_upload(f)
    nm = os.path.splitext(os.path.basename(src))[0]
    out = os.path.join(UPLOAD_DIR, nm + ext)

    codec    = request.form.get("codec")
    preset   = request.form.get("preset")
    res_str  = request.form.get("resolution")
    resolution = None
    if res_str and "x" in res_str:
        w, h = res_str.split("x", 1)
        resolution = (int(w), int(h))
    fps      = request.form.get("fps", type=int)
    bitrate  = request.form.get("bitrate")

    ok = video_conv.convert(src, out, ext, codec, preset, resolution, bitrate, fps)
    if ok and os.path.exists(out):
        return _ok("转换成功", file_path=out)
    return _err("转换失败", 500)


# ═══════════════════════════════════════════════
#  音频转换
# ═══════════════════════════════════════════════
@app.route("/api/audio/convert", methods=["POST"])
def api_audio_convert():
    """
    POST /api/audio/convert
    form-data:
      file: 音频文件
      format: 目标格式 (mp3/wav/flac/aac...)
      bitrate: 比特率 (128k/192k/320k) [可选]
      sample_rate: 采样率 (44100/48000) [可选]
      channels: 声道数 (1/2) [可选]
    """
    f = request.files.get("file")
    if not f:
        return _err("请上传文件")

    fmt = request.form.get("format", "mp3")
    ext = SUPPORTED_AUDIO.get(fmt.upper(), f".{fmt}")
    if not ext.startswith("."):
        ext = f".{fmt}"

    src = _save_upload(f)
    nm = os.path.splitext(os.path.basename(src))[0]
    out = os.path.join(UPLOAD_DIR, nm + ext)

    codec_map = {"MP3":"libmp3lame","AAC":"aac","FLAC":"flac","WAV":"pcm_s16le",
                 "WMA":"wmav2","OGG":"libvorbis","M4A":"aac","OPUS":"libopus"}
    codec = codec_map.get(fmt.upper())
    br = request.form.get("bitrate", "192k")
    sr = request.form.get("sample_rate", type=int)
    ch = request.form.get("channels", type=int)

    ok = audio_conv.convert(src, out, codec, br, sr, ch)
    if ok and os.path.exists(out):
        return _ok("转换成功", file_path=out)
    return _err("转换失败", 500)


# ═══════════════════════════════════════════════
#  图片转换
# ═══════════════════════════════════════════════
@app.route("/api/image/convert", methods=["POST"])
def api_image_convert():
    """
    POST /api/image/convert
    form-data:
      file: 图片文件
      format: 目标格式 (png/jpg/bmp/webp...)
      quality: 质量 1-100 [可选, 默认95]
    """
    f = request.files.get("file")
    if not f:
        return _err("请上传文件")

    fmt = request.form.get("format", "png")
    ext = SUPPORTED_IMAGE.get(fmt.upper(), f".{fmt}")
    if not ext.startswith("."):
        ext = f".{fmt}"

    src = _save_upload(f)
    nm = os.path.splitext(os.path.basename(src))[0]
    out = os.path.join(UPLOAD_DIR, nm + ext)
    quality = request.form.get("quality", 95, type=int)

    ok = image_conv.convert(src, out, quality)
    if ok and os.path.exists(out):
        return _ok("转换成功", file_path=out)
    return _err("转换失败", 500)


# ═══════════════════════════════════════════════
#  文档转换
# ═══════════════════════════════════════════════
@app.route("/api/doc/convert", methods=["POST"])
def api_doc_convert():
    """
    POST /api/doc/convert
    form-data:
      file: 文档文件
      format: 目标扩展名 (.pdf/.docx/.txt等)
    """
    f = request.files.get("file")
    if not f:
        return _err("请上传文件")

    target_ext = request.form.get("format", ".pdf")
    if not target_ext.startswith("."):
        target_ext = "." + target_ext

    src = _save_upload(f)
    nm = os.path.splitext(os.path.basename(src))[0]
    out = os.path.join(UPLOAD_DIR, nm + target_ext)

    ok = doc_conv.convert(src, out)
    if ok and os.path.exists(out):
        return _ok("转换成功", file_path=out)
    return _err("转换失败", 500)


# ═══════════════════════════════════════════════
#  视频提取音频
# ═══════════════════════════════════════════════
@app.route("/api/extract/audio", methods=["POST"])
def api_extract_audio():
    """
    POST /api/extract/audio
    form-data:
      file: 视频文件
      format: 音频格式 (mp3/aac/flac/wav) [默认mp3]
      bitrate: 比特率 [默认192k]
    """
    f = request.files.get("file")
    if not f:
        return _err("请上传文件")

    fmt = request.form.get("format", "mp3")
    ext_map = {"mp3":".mp3","aac":".aac","flac":".flac","wav":".wav"}
    codec_map = {"mp3":"mp3","aac":"aac","flac":"flac","wav":"wav"}
    ext = ext_map.get(fmt, ".mp3")
    codec = codec_map.get(fmt, "mp3")
    br = request.form.get("bitrate", "192k")

    src = _save_upload(f)
    nm = os.path.splitext(os.path.basename(src))[0]
    out = os.path.join(UPLOAD_DIR, nm + ext)

    ok = video_conv.extract_audio(src, out, codec, br)
    if ok and os.path.exists(out):
        return _ok("提取成功", file_path=out)
    return _err("提取失败", 500)


# ═══════════════════════════════════════════════
#  视频压缩
# ═══════════════════════════════════════════════
@app.route("/api/video/compress", methods=["POST"])
def api_video_compress():
    """
    POST /api/video/compress
    form-data:
      file: 视频文件
      preset: high/medium/low [默认medium]
      resolution: 1920x1080 [可选]
    """
    f = request.files.get("file")
    if not f:
        return _err("请上传文件")

    preset = request.form.get("preset", "medium")
    res_str = request.form.get("resolution")
    resolution = None
    if res_str and "x" in res_str:
        w, h = res_str.split("x", 1)
        resolution = (int(w), int(h))

    src = _save_upload(f)
    nm = os.path.splitext(os.path.basename(src))[0]
    out = os.path.join(UPLOAD_DIR, nm + "_compressed.mp4")

    ok = video_conv.convert(src, out, ".mp4", "libx264", preset, resolution)
    if ok and os.path.exists(out):
        return _ok("压缩成功", file_path=out)
    return _err("压缩失败", 500)


# ═══════════════════════════════════════════════
#  视频转GIF
# ═══════════════════════════════════════════════
@app.route("/api/video/gif", methods=["POST"])
def api_video_to_gif():
    """
    POST /api/video/gif
    form-data:
      file: 视频文件
      width: 宽度 [默认480]
      fps: 帧率 [默认15]
      start: 开始秒数 [默认0]
      duration: 时长秒数 [默认10]
    """
    import subprocess
    f = request.files.get("file")
    if not f:
        return _err("请上传文件")

    src = _save_upload(f)
    nm = os.path.splitext(os.path.basename(src))[0]
    out = os.path.join(UPLOAD_DIR, nm + ".gif")

    w = request.form.get("width", "480")
    fps = request.form.get("fps", "15")
    start = request.form.get("start", "0")
    dur = request.form.get("duration", "10")

    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        return _err("FFmpeg未安装", 500)

    cmd = [ffmpeg, "-y"]
    if start != "0":
        cmd += ["-ss", start]
    cmd += ["-i", src]
    if dur and dur != "all":
        cmd += ["-t", dur]
    vf = f"fps={fps}"
    if w and w != "original":
        vf += f",scale={w}:-1:flags=lanczos"
    cmd += ["-vf", vf, "-loop", "0", out]

    proc = subprocess.run(cmd, capture_output=True,
                          creationflags=0x08000000 if os.name == 'nt' else 0)
    if proc.returncode == 0 and os.path.exists(out):
        return _ok("GIF生成成功", file_path=out)
    return _err("GIF生成失败", 500)


# ═══════════════════════════════════════════════
#  PDF 合并
# ═══════════════════════════════════════════════
@app.route("/api/pdf/merge", methods=["POST"])
def api_pdf_merge():
    """
    POST /api/pdf/merge
    form-data:
      files: 多个PDF文件（同名字段上传多个）
    """
    uploaded = request.files.getlist("files")
    if len(uploaded) < 2:
        return _err("请上传至少2个PDF文件")

    paths = [_save_upload(f) for f in uploaded]
    out = os.path.join(UPLOAD_DIR, "merged.pdf")

    ok = pdf_merge(paths, out)
    if ok and os.path.exists(out):
        return _ok("合并成功", file_path=out)
    return _err("合并失败", 500)


# ═══════════════════════════════════════════════
#  PDF 拆分
# ═══════════════════════════════════════════════
@app.route("/api/pdf/split", methods=["POST"])
def api_pdf_split():
    """
    POST /api/pdf/split
    form-data:
      file: PDF文件
      ranges: 页码范围 (如 "1-3,5,7-10")
    """
    f = request.files.get("file")
    if not f:
        return _err("请上传文件")

    ranges_str = request.form.get("ranges", "1-999")
    src = _save_upload(f)

    ranges = []
    for part in ranges_str.split(","):
        part = part.strip()
        if "-" in part:
            s, e = part.split("-", 1)
            ranges.append((int(s.strip()), int(e.strip())))
        else:
            n = int(part)
            ranges.append((n, n))

    out_dir = os.path.join(UPLOAD_DIR, "split_" + uuid.uuid4().hex[:8])
    os.makedirs(out_dir, exist_ok=True)

    ok = pdf_split(src, out_dir, ranges)
    if ok:
        files = os.listdir(out_dir)
        return jsonify({"success": True, "message": f"拆分为{len(files)}个文件",
                        "files": files, "output_dir": out_dir})
    return _err("拆分失败", 500)


# ═══════════════════════════════════════════════
#  图片压缩
# ═══════════════════════════════════════════════
@app.route("/api/image/compress", methods=["POST"])
def api_image_compress():
    """
    POST /api/image/compress
    form-data:
      file: 图片文件
      quality: 质量 1-100 [默认75]
      max_width: 最大宽度 [可选]
      max_height: 最大高度 [可选]
    """
    f = request.files.get("file")
    if not f:
        return _err("请上传文件")

    quality = request.form.get("quality", 75, type=int)
    mw = request.form.get("max_width", type=int)
    mh = request.form.get("max_height", type=int)
    max_sz = (mw, mh) if mw and mh else None

    src = _save_upload(f)
    ext = os.path.splitext(src)[1]
    nm = os.path.splitext(os.path.basename(src))[0]
    out = os.path.join(UPLOAD_DIR, nm + "_compressed" + ext)

    ok = image_compress(src, out, quality, max_sz)
    if ok and os.path.exists(out):
        orig = os.path.getsize(src)
        new = os.path.getsize(out)
        return jsonify({
            "success": True,
            "message": "压缩成功",
            "original_size": f"{orig/1024:.1f}KB",
            "compressed_size": f"{new/1024:.1f}KB",
            "saved": f"{(1-new/orig)*100:.0f}%",
        }) if not request.args.get("download") else _ok("压缩成功", file_path=out)
    return _err("压缩失败", 500)


# ═══════════════════════════════════════════════
#  启动
# ═══════════════════════════════════════════════
def start_api_server(port=5000, debug=False):
    print(f"\n{'='*50}")
    print(f"  {APP_NAME} API Server")
    print(f"  http://localhost:{port}")
    print(f"  用 Postman 测试各个接口")
    print(f"{'='*50}\n")
    app.run(host="0.0.0.0", port=port, debug=debug)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="格式大师 API 服务器")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    start_api_server(args.port, args.debug)
