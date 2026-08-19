"""lan_sender — 局域网文件发送端（HTTP 下载服务）。

包含 _SendHandler、_SendServer、make_zip 及相关的辅助函数和模板。
"""

import http.server
import html
import io
import os
import threading
import time
import urllib.parse
import zipfile

from core.lan_transfer import (_CLASSIFY_GROUPS, _PREVIEW_EXTS,
                               _start_idle_watch, _unique_path, get_lan_ip)


def _human_size(n):
    """字节数 → 人类可读（KB/MB/GB）。"""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n /= 1024


def _get_file_icon(ext):
    """根据文件扩展名返回图标。"""
    if ext in _CLASSIFY_GROUPS["图片"]:
        return "🖼️"
    elif ext in _CLASSIFY_GROUPS["视频"]:
        return "🎬"
    elif ext in _CLASSIFY_GROUPS["音频"]:
        return "🎵"
    elif ext in _CLASSIFY_GROUPS["文档"]:
        if ext == "pdf":
            return "📕"
        elif ext in {"doc", "docx"}:
            return "📘"
        elif ext in {"xls", "xlsx"}:
            return "📗"
        elif ext in {"ppt", "pptx"}:
            return "📙"
        else:
            return "📄"
    else:
        return "📄"


_LIST_HTML = r"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>格式大师 · 局域网共享</title>
<style>
:root{
  --bg:linear-gradient(135deg,#eef2ff 0%,#fdf2f8 50%,#eef7ff 100%);
  --card:rgba(255,255,255,.85);--card-border:rgba(255,255,255,.6);
  --shadow:0 20px 60px rgba(99,102,241,.15),0 2px 8px rgba(0,0,0,.04);
  --ink:#1e293b;--ink2:#64748b;--ink3:#94a3b8;
  --row:#ffffff;--row-hover:#eef2ff;--line:#e2e8f0;
}
@media (prefers-color-scheme: dark){
  :root{
    --bg:linear-gradient(135deg,#141725 0%,#1b1425 50%,#0f1c29 100%);
    --card:rgba(30,33,48,.92);--card-border:rgba(255,255,255,.08);
    --shadow:0 20px 60px rgba(0,0,0,.5);
    --ink:#e6e8f2;--ink2:#9aa3b8;--ink3:#6b7280;
    --row:#1e2128;--row-hover:#272c3b;--line:#33384a;
  }
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Segoe UI","PingFang SC","Microsoft YaHei",system-ui,sans-serif;
min-height:100vh;display:flex;justify-content:center;align-items:center;
padding:20px;background:var(--bg);color:var(--ink)}
.card{background:var(--card);backdrop-filter:blur(18px);
border-radius:24px;padding:30px 26px;width:100%;max-width:540px;
box-shadow:var(--shadow);border:1px solid var(--card-border)}
.head{display:flex;align-items:center;gap:12px;margin-bottom:2px}
.logo{width:52px;height:52px;flex:none;border-radius:15px;
background:linear-gradient(135deg,#6366f1,#a855f7);
display:flex;align-items:center;justify-content:center;
font-size:24px;box-shadow:0 8px 20px rgba(99,102,241,.35)}
h1{font-size:19px;font-weight:700;flex:1;letter-spacing:.3px}
.lang{flex:none;border:1px solid var(--line);background:transparent;color:var(--ink2);
border-radius:8px;padding:5px 11px;font-size:12px;cursor:pointer}
.lang:hover{border-color:#6366f1;color:#6366f1}
.sub{color:var(--ink2);font-size:13px;text-align:center;margin:6px 0 18px}
.zipbtn{display:block;width:100%;text-align:center;margin:0 0 10px;padding:12px;border:0;
border-radius:12px;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;
font-size:14px;font-weight:600;cursor:pointer;box-shadow:0 6px 16px rgba(99,102,241,.3);
text-decoration:none}
.zipbtn:active{transform:translateY(1px)}
#selbar{display:none;align-items:center;gap:8px;margin-bottom:10px;padding:8px 12px;
background:rgba(99,102,241,.12);border-radius:10px;font-size:13px;color:var(--ink2)}
#selbar b{color:var(--ink)}
.sbtn{border:0;border-radius:8px;padding:6px 12px;font-size:12px;cursor:pointer;
background:linear-gradient(135deg,#10b981,#0ea5e9);color:#fff;font-weight:600}
.sbtn2{background:transparent;color:var(--ink2);border:1px solid var(--line)}
.search{width:100%;padding:11px 14px;border:1px solid var(--line);border-radius:12px;
font-size:14px;margin-bottom:14px;outline:none;background:var(--row);color:var(--ink)}
.search:focus{border-color:#6366f1}
.row{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:12px;
color:var(--ink);font-size:14px;transition:background .15s}
.row:hover{background:var(--row-hover)}
.row .cb{flex:none;width:17px;height:17px;accent-color:#6366f1;cursor:pointer}
.row .ic{font-size:18px;flex:none;width:22px;text-align:center}
.row .nm{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
text-decoration:none;color:var(--ink);cursor:pointer}
.row .pv{flex:none;border:0;background:transparent;font-size:16px;cursor:pointer;opacity:.7}
.row .pv:hover{opacity:1}
.row .sz{color:var(--ink3);font-size:12px;flex:none}
.empty{text-align:center;color:var(--ink3);padding:24px 0;font-size:14px}
.tip{margin-top:18px;text-align:center;color:var(--ink3);font-size:12px}
#prog{display:none;margin-top:12px;padding:10px 12px;border-radius:12px;
background:rgba(99,102,241,.12);font-size:12px;color:var(--ink2)}
#prog .pb{height:6px;border-radius:3px;background:var(--line);margin-top:6px;overflow:hidden}
#prog .pb i{display:block;height:100%;width:0;background:linear-gradient(90deg,#6366f1,#a855f7)}
#lb{display:none;position:fixed;inset:0;background:rgba(0,0,0,.86);z-index:99;
align-items:center;justify-content:center;padding:20px}
#lb img,#lb video{max-width:96vw;max-height:86vh;border-radius:12px;box-shadow:0 10px 40px rgba(0,0,0,.6)}
#lb .close{position:absolute;top:14px;right:18px;color:#fff;font-size:30px;cursor:pointer;line-height:1}
</style></head><body>
<div class="card">
  <div class="head">
    <div class="logo">📦</div>
    <h1 data-i18n="title2">共享文件下载</h1>
    <button class="lang" id="langBtn" onclick="toggleLang()">🌐 EN</button>
  </div>
  <p class="sub" data-i18n="sub">格式大师 · 局域网共享 · 点击文件即可下载</p>
  <button class="zipbtn" id="dlAll" onclick="downloadAll()">⬇ <span data-i18n="dlall">打包下载全部</span></button>
  <div id="selbar">
    <b id="selCount">0</b><span data-i18n="sel">已选</span>
    <button class="sbtn" onclick="downloadSelected()" data-i18n="dlsel">下载选中</button>
    <button class="sbtn sbtn2" onclick="clearSel()" data-i18n="cancel">取消</button>
  </div>
  <input class="search" id="q" placeholder="🔍 搜索…" oninput="filterRows(this.value)">
  <div id="rows">__ROWS__</div>
  <div class="tip" data-i18n="tip">💡 文件由「格式大师」局域网传输提供</div>
  <div id="prog"><span id="progTxt"></span><div class="pb"><i id="progBar"></i></div></div>
</div>
<div id="lb" onclick="closeLb()"><span class="close">✕</span>
  <div id="lbBox" onclick="event.stopPropagation()"></div>
</div>
<script>
var I18N={
 zh:{title:'格式大师 · 局域网共享',title2:'共享文件下载',sub:'格式大师 · 局域网共享 · 点击文件即可下载',
     dlall:'打包下载全部',sel:'已选',dlsel:'下载选中',cancel:'取消',tip:'💡 文件由「格式大师」局域网传输提供',
     search:'🔍 搜索文件…',empty:'📭 目录为空',dl:'下载',dlfail:'下载失败，请重试'},
 en:{title:'FormatMaster · LAN Share',title2:'Shared Files',sub:'FormatMaster · LAN sharing · tap a file to download',
     dlall:'Download all (zip)',sel:'Selected',dlsel:'Download selected',cancel:'Cancel',
     tip:'💡 Powered by FormatMaster LAN transfer',search:'🔍 Search files…',
     empty:'📭 Folder is empty',dl:'Download',dlfail:'Download failed, retry'}
};
var LANG=(navigator.language||'zh').toLowerCase().indexOf('en')===0?'en':'zh';
function t(k){return (I18N[LANG]&&I18N[LANG][k])||I18N.zh[k]||k}
function applyLang(){
  document.querySelectorAll('[data-i18n]').forEach(function(el){
    el.innerHTML=t(el.getAttribute('data-i18n'));
  });
  document.title=t('title');
  document.getElementById('q').placeholder=t('search');
  var e=document.querySelector('.empty');
  if(e)e.textContent=t('empty');
  document.getElementById('langBtn').textContent='🌐 '+(LANG==='zh'?'EN':'中');
}
function toggleLang(){LANG=LANG==='zh'?'en':'zh';applyLang()}

var sel=new Set();
function onSel(cb){
  var fn=cb.closest('.row').dataset.fn;
  if(cb.checked)sel.add(fn);else sel.delete(fn);
  var n=sel.size;
  document.getElementById('selbar').style.display=n?'flex':'none';
  document.getElementById('selCount').textContent=n;
}
function clearSel(){
  sel.clear();
  document.querySelectorAll('.row .cb').forEach(function(c){c.checked=false});
  document.getElementById('selbar').style.display='none';
}
function isImg(n){return /\.(jpe?g|png|gif|webp|bmp|svg|heic|heif)$/i.test(n)}
function isVid(n){return /\.(mp4|webm|ogg)$/i.test(n)}
function isPdf(n){return /\.pdf$/i.test(n)}
function isDoc(n){return /\.(doc|docx|xls|xlsx|ppt|pptx)$/i.test(n)}
function preview(row){
  var nm=row.querySelector('.nm'),full=new URL(nm.getAttribute('href'),location.href).href;
  var box=document.getElementById('lbBox');
  var fn=row.dataset.fn;
  
  if(isImg(fn)){
    box.innerHTML='<img src="'+full+'">';
  } else if(isVid(fn)){
    box.innerHTML='<video src="'+full+'" controls autoplay playsinline></video>';
  } else if(isPdf(fn)){
    box.innerHTML='<iframe src="'+full+'" style="width:100%;height:80vh;border:none;"></iframe>';
  } else if(isDoc(fn)){
    // 离线预览：服务端转 PDF 后内嵌（文件不出本机，无需外网）
    box.innerHTML='<iframe src="/office-pdf?file='+encodeURIComponent(fn)
      +'" style="width:100%;height:82vh;border:none;"></iframe>';
  }
  
  document.getElementById('lb').style.display='flex';
}
function closeLb(){document.getElementById('lb').style.display='none';document.getElementById('lbBox').innerHTML=''}
function onNm(a){
  var row=a.closest('.row');
  if(row.dataset.dir==='1')return true;
  var fn=row.dataset.fn;
  if(isImg(fn)||isVid(fn)||isPdf(fn)||isDoc(fn)){preview(row);return false}
  fetchDL(a.getAttribute('href'),fn);
  return false;
}
function fetchDL(url,name){
  var prog=document.getElementById('prog'),txt=document.getElementById('progTxt'),
      bar=document.getElementById('progBar');
  function show(p,m){prog.style.display='block';bar.style.width=(p||0)+'%';txt.textContent=m}
  fetch(url).then(function(r){
    if(!r.ok)throw new Error('bad');
    var total=parseInt(r.headers.get('Content-Length')||'0',10)||0;
    if(total>512*1048576){location.href=url;return}
    var cd=r.headers.get('Content-Disposition')||'';
    var m=cd.match(/filename="?([^";]+)"?/i);
    var fname=(m&&m[1])||name||'download';
    fname=decodeURIComponent(fname);
    if(!total){show(100,t('dl')+'…');return r.blob().then(function(b){saveBlob(b,fname);prog.style.display='none'})}
    var reader=r.body.getReader(),chunks=[],loaded=0;
    function pump(){
      reader.read().then(function(res){
        if(res.done){
          var blob=new Blob(chunks);saveBlob(blob,fname);prog.style.display='none';return
        }
        chunks.push(res.value);loaded+=res.value.length;
        show(loaded/total*100,t('dl')+' '+Math.round(loaded/1048576)+'/'+Math.round(total/1048576)+' MB');
        pump();
      }).catch(function(){fail()});
    }
    pump();
  }).catch(function(){fail()});
  function fail(){prog.style.display='none';alert(t('dlfail'));location.href=url}
}
function saveBlob(b,name){
  var a=document.createElement('a');
  a.href=URL.createObjectURL(b);a.download=name;
  document.body.appendChild(a);a.click();
  setTimeout(function(){URL.revokeObjectURL(a.href);a.remove()},1200);
}
function downloadAll(){fetchDL('/all.zip','all.zip')}
function downloadSelected(){
  if(!sel.size)return;
  fetchDL('/selected.zip?files='+Array.from(sel).map(encodeURIComponent).join('&'),'selected.zip');
}
function filterRows(v){
  v=(v||'').toLowerCase().trim();
  var rows=document.getElementById('rows').querySelectorAll('.row'),n=0;
  rows.forEach(function(r){
    var hit=r.dataset.fn.toLowerCase().indexOf(v)>-1;
    r.style.display=hit?'':'none';if(hit)n++;
  });
  var e=document.querySelector('.empty');
  if(e)e.style.display=n?'none':'';
}
applyLang();
</script></body></html>"""


class _SendHandler(http.server.SimpleHTTPRequestHandler):
    on_downloaded = None      # (filename, size, seconds)
    total = frozenset()       # 共享目录全部文件名（用于全部下载完判定）
    downloaded = None         # 已下载文件名集合（线程安全）
    on_all_done = None        # 全部下载完成回调（触发一次后置空）
    last_visit = time.time()  # 最近访问时间（空闲超时判定）
    _done_lock = threading.Lock()

    def log_message(self, *a):  # 静默访问日志
        pass

    def do_GET(self):
        _SendHandler.last_visit = time.time()
        path = urllib.parse.urlparse(self.path).path
        # 打包下载全部：/all.zip（下载即视为全部完成）
        if path == "/all.zip":
            self._send_all_zip()
            return
        # 打包下载选中：/selected.zip?files=a.mp4&files=b.png
        if path == "/selected.zip":
            self._send_selected_zip()
            return
        # 记录下载：文件请求（非目录列表）
        if self.on_downloaded and path != "/" and not path.endswith("/"):
            t0 = time.time()
            try:
                super().do_GET()
                return
            finally:
                full = os.path.join(self.directory, path.lstrip("/"))
                if os.path.isfile(full):
                    name = os.path.basename(full)
                    self.on_downloaded(
                        name, os.path.getsize(full), time.time() - t0)
                    self._note_download(name)
            return
        super().do_GET()

    def do_POST(self):
        self.send_response(404)
        self.end_headers()

    def _note_download(self, name):
        """记录一次文件下载；全部下载完时触发 on_all_done（仅一次）。

        状态存类属性（线程共享、跨 handler 实例累计）；显式类访问避免
        实例绑定多传 self。
        """
        if not _SendHandler.total or not name:
            return
        with _SendHandler._done_lock:
            if _SendHandler.downloaded is None:
                _SendHandler.downloaded = set()
            _SendHandler.downloaded.add(name)
            if (_SendHandler.total <= _SendHandler.downloaded
                    and _SendHandler.on_all_done):
                cb = _SendHandler.on_all_done
                _SendHandler.on_all_done = None
            else:
                cb = None
        if cb:
            try:
                cb()
            except Exception:  # noqa: BLE001
                pass

    def _trigger_all_done(self):
        """（all.zip 场景）直接触发全部下载完成。"""
        with _SendHandler._done_lock:
            cb = _SendHandler.on_all_done
            _SendHandler.on_all_done = None
        if cb:
            try:
                cb()
            except Exception:  # noqa: BLE001
                pass

    def _send_selected_zip(self):
        """打包下载勾选的文件：/selected.zip?files=a.mp4&files=b.png。

        仅允许共享目录内的真实文件，防路径穿越；空选返回 400。
        """
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        names = qs.get("files", []) or []
        base = os.path.realpath(self.directory)
        paths = []
        for n in names:
            try:
                p = os.path.realpath(os.path.join(base, n))
            except Exception:  # noqa: BLE001
                continue
            if (os.path.commonpath([base, p]) == base
                    and os.path.isfile(p)):
                paths.append(p)
        if not paths:
            self.send_error(400)
            return
        import io
        try:
            with io.BytesIO() as bio:
                with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
                    for p in paths:
                        zf.write(p, os.path.basename(p))
                data = bio.getvalue()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition",
                             'attachment; filename="selected.zip"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            _SendHandler.last_visit = time.time()
        except Exception:  # noqa: BLE001
            self.send_error(500)

    def _send_all_zip(self):
        """把共享目录全部文件打包成 zip 返回（一键下载全部）。"""
        try:
            import io
            with io.BytesIO() as bio:
                with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
                    for root, _dirs, files in os.walk(self.directory):
                        for fn in files:
                            fp = os.path.join(root, fn)
                            rel = os.path.relpath(fp, self.directory)
                            zf.write(fp, rel)
                data = bio.getvalue()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition",
                             'attachment; filename="all.zip"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            if self.on_downloaded:
                self.on_downloaded("all.zip", len(data), 0)
            self._trigger_all_done()
        except Exception:  # noqa: BLE001
            self.send_error(500)

    def list_directory(self, path):
        """渲染美观的文件下载列表页（替代默认 Directory listing）。"""
        try:
            entries = list(os.scandir(path))
        except OSError:
            self.send_error(404)
            return None
        entries = [e for e in entries if not e.name.startswith(".")]
        entries.sort(key=lambda e: (not e.is_dir(), e.name.lower()))
        rows = []
        for e in entries:
            ext = os.path.splitext(e.name)[1].lower().lstrip(".")
            icon = "📁" if e.is_dir() else _get_file_icon(ext)
            if e.is_dir():
                size_txt = "—"
            else:
                try:
                    size_txt = _human_size(os.path.getsize(e.path))
                except OSError:
                    size_txt = "?"
            href = urllib.parse.quote(e.name)
            link = href + "/" if e.is_dir() else href
            is_preview = (not e.is_dir()) and ext in _PREVIEW_EXTS
            pv = (f"<button class='pv' onclick=\"preview(this.closest('.row'))\">👁</button>"
                  if is_preview else "")
            rows.append(
                f'<div class="row" data-fn="{html.escape(e.name)}" '
                f'data-dir="{1 if e.is_dir() else 0}">'
                f'<input class="cb" type="checkbox" onchange="onSel(this)">'
                f'<span class="ic">{icon}</span>'
                f'<a class="nm" href="{link}" '
                f'onclick="return onNm(this)">{html.escape(e.name)}</a>{pv}'
                f'<span class="sz">{size_txt}</span></div>')
        rows_html = "\n".join(rows) if rows else \
            '<div class="empty">📭 目录为空</div>'
        page_html = _LIST_HTML.replace("__ROWS__", rows_html)
        data = page_html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        return None


class _SendServer:
    """把共享目录暴露为 HTTP 下载服务（端口被占自动 +1，最多试 10 个）。"""

    def __init__(self, share_dir, port, on_downloaded=None,
                 on_all_done=None, idle_timeout=0, on_idle=None):
        self._share_dir = share_dir
        handler = _SendHandler
        handler.on_downloaded = on_downloaded
        handler.on_all_done = on_all_done
        handler.downloaded = None
        handler.total = frozenset(
            n for n in os.listdir(share_dir)
            if os.path.isfile(os.path.join(share_dir, n))
            and not n.startswith("."))
        handler.last_visit = time.time()
        self.port = 0
        self._server = None
        for p in range(port, min(port + 10, 65536)):
            try:
                self._server = http.server.ThreadingHTTPServer(
                    ("0.0.0.0", p),
                    lambda *a, **k: handler(*a, directory=share_dir, **k))
            except OSError:
                continue
            self.port = p
            break
        if self._server is None:
            raise OSError("端口被占用")
        self._thread = None
        self._idle_watch = _start_idle_watch(handler, idle_timeout, on_idle)

    def start(self):
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        if self._idle_watch:
            self._idle_watch["stop"] = True
        try:
            self._server.shutdown()
            self._server.server_close()
        except Exception:  # noqa: BLE001
            pass

    def url(self, ip=None):
        return f"http://{ip or get_lan_ip()}:{self.port}/"


def make_zip(src_paths, dest_dir, zip_name="batch", progress_cb=None):
    """把多个文件/文件夹打包成一个 zip，返回 zip 路径。

    progress_cb(pct, msg)：按文件数统计打包进度（大文件夹不假死）。
    """
    zpath = os.path.join(dest_dir, zip_name + ".zip")
    zpath = _unique_path(zpath)
    zipfile = __import__("zipfile")
    # 统计总文件数（进度分母）
    total_files = 0
    for src in src_paths:
        if os.path.isdir(src):
            for _root, _dirs, files in os.walk(src):
                total_files += len(files)
        else:
            total_files += 1
    done = 0
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        seq = 0
        for src in src_paths:
            seq += 1
            if os.path.isdir(src):
                base = os.path.basename(src.rstrip("\\/")) or f"folder{seq}"
                for root, _dirs, files in os.walk(src):
                    for fn in files:
                        fp = os.path.join(root, fn)
                        rel = os.path.relpath(fp, os.path.dirname(src))
                        zf.write(fp, os.path.join(base, rel))
                        done += 1
                        if progress_cb and total_files:
                            progress_cb(
                                int(done * 100 / total_files),
                                f"打包 {done}/{total_files}…")
            else:
                zf.write(src, os.path.basename(src))
                done += 1
                if progress_cb:
                    progress_cb(
                        int(done * 100 / total_files) if total_files else 100,
                        "打包中…")
    return zpath
