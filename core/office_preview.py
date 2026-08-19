# -*- coding: utf-8 -*-
"""office_preview — 局域网 Office 文档离线网页预览管理器。

把 doc/docx/xls/xlsx/ppt/pptx 在服务端转成 PDF，供网页 <iframe> 内嵌预览，
完全离线、文件不出本机（替换旧的微软 Office Online 外网依赖）。

设计：
- 转换慢（秒级），故后台线程转换 + 内存状态（pending/ready/error）；
- 转换结果缓存到 cache_root（分享临时目录）下 .fm_preview/，随服务停止自动清理；
- 按 (源路径, mtime) 去重，同一文件只转一次；
- convert_fn 可注入（测试用），默认走 core.doc_office_pdf 多引擎降级。
"""
import os
import re
import threading


def _convert_office(src, out):
    """按扩展名选引擎把 Office 转 PDF，返回 (ok, engine_msg)。"""
    from core import doc_office_pdf as dp
    ext = os.path.splitext(src)[1].lower()
    try:
        if ext in (".doc", ".docx", ".wps"):
            return dp.docx_to_pdf(src, out)
        if ext in (".ppt", ".pptx", ".dps"):
            return dp.ppt_to_pdf(src, out)
        if ext in (".xls", ".xlsx", ".xlsm"):
            return dp.excel_to_pdf(src, out)
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"
    return False, "不支持的格式"


class OfficePreviewManager:
    """Office→PDF 预览缓存管理器（线程安全）。"""

    def __init__(self, cache_root, convert_fn=None):
        self._cache_root = cache_root
        self._convert_fn = convert_fn  # (src, out) -> (ok, msg)，测试注入
        self._lock = threading.Lock()
        self._entries = {}  # key -> {status, pdf, engine, thread}

    def _key(self, src):
        try:
            return (os.path.realpath(src), os.path.getmtime(src))
        except OSError:
            return (os.path.realpath(src), 0)

    def request(self, src):
        """返回 (status, pdf_path|None, engine|None)。首次调用触发后台转换。"""
        key = self._key(src)
        with self._lock:
            e = self._entries.get(key)
            if e is None:
                e = {"status": "pending", "pdf": None, "engine": None,
                     "thread": None}
                self._entries[key] = e
                self._start(e, src)
            return e["status"], e["pdf"], e["engine"]

    def _start(self, e, src):
        t = threading.Thread(target=self._convert, args=(e, src),
                             daemon=True, name="office-preview")
        e["thread"] = t
        t.start()

    def _convert(self, e, src):
        out_dir = os.path.join(self._cache_root, ".fm_preview")
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError:  # noqa: BLE001
            with self._lock:
                e["status"] = "error"
            return
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_",
                      os.path.basename(src)) or "doc"
        pdf = os.path.join(out_dir, safe + ".pdf")
        try:
            if self._convert_fn is not None:
                ok, msg = self._convert_fn(src, pdf)
            else:
                ok, msg = _convert_office(src, pdf)
            if ok and os.path.isfile(pdf):
                with self._lock:
                    e["status"], e["pdf"], e["engine"] = "ready", pdf, msg
                return
        except Exception:  # noqa: BLE001
            pass
        with self._lock:
            e["status"] = "error"
