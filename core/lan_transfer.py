"""lan_transfer — 局域网文件传输与设备协作（标准库 http.server，无第三方依赖）。

- 发送：文件/文件夹（自动 zip）复制到临时共享目录 → HTTP 下载服务 + 二维码
- 接收：HTTP 上传服务，浏览器选择文件上传保存
- 密码保护：发送/接收服务可设访问密码（cookie 会话）
- 防火墙：启动服务时自动添加 Windows 防火墙入站放行规则（需管理员，
  失败返回 False 由面板提示手动放行）
- 传输回调：接收完成/下载记录回调（历史、通知、速度）

服务器在线程中运行，stop 时关闭。
"""

import http.server
import html
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request

_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def add_firewall_rule(port):
    """为 TCP 端口添加 Windows 防火墙入站放行规则（需管理员权限）。

    返回 True=已添加/已存在；False=失败（权限不足等，面板应提示手动放行）。
    """
    if os.name != "nt":
        return True
    try:
        r = subprocess.run(
            ["netsh", "advfirewall", "firewall", "add", "rule",
             f"name=FormatMaster LAN {port}", "dir=in", "action=allow",
             "protocol=TCP", f"localport={port}",
             f"program={sys.executable}"],
            capture_output=True, timeout=10, check=False,
            creationflags=_CREATE_NO_WINDOW)
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def remove_firewall_rule(port):
    """删除端口对应的防火墙规则（服务停止时调用，忽略失败）。"""
    if os.name != "nt":
        return
    try:
        subprocess.run(
            ["netsh", "advfirewall", "firewall", "delete", "rule",
             f"name=FormatMaster LAN {port}"],
            capture_output=True, timeout=10, check=False,
            creationflags=_CREATE_NO_WINDOW)
    except Exception:  # noqa: BLE001
        pass


def get_lan_ip():
    """获取本机局域网 IP；失败返回 '127.0.0.1'。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:  # noqa: BLE001
        return "127.0.0.1"


def get_lan_ips():
    """返回本机所有可用 IPv4（非环回、非链路本地），默认路由出口排最前。

    多网卡场景（WiFi + USB 共享 + 虚拟网卡 + Tailscale 等）下，
    手机可达的 IP 未必是默认出口，需要列出全部供用户选择。
    """
    ips = []
    try:
        host = socket.gethostname()
        for info in socket.getaddrinfo(host, None, socket.AF_INET):
            ip = info[4][0]
            if (ip not in ips and not ip.startswith("127.")
                    and not ip.startswith("169.254.")):
                ips.append(ip)
    except Exception:  # noqa: BLE001
        pass
    default = get_lan_ip()
    if default and default not in ips:
        ips.insert(0, default)
    if default in ips and ips[0] != default:
        ips.remove(default)
        ips.insert(0, default)
    return ips


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
        import zipfile
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
        import zipfile
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
    var viewer='https://view.officeapps.live.com/op/embed.aspx?src='+encodeURIComponent(full);
    box.innerHTML='<iframe src="'+viewer+'" style="width:100%;height:80vh;border:none;"></iframe>';
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


def _start_idle_watch(handler_cls, timeout, on_idle):
    """空闲超时监视：timeout 秒无任何请求则回调 on_idle。timeout<=0 禁用。

    返回控制 dict（stop 置 True 停止监视），供服务 stop 时清理。
    """
    if not timeout or not callable(on_idle):
        return None
    flag = {"stop": False}

    def loop():
        while not flag["stop"]:
            time.sleep(5)
            try:
                if time.time() - handler_cls.last_visit > timeout:
                    on_idle()
                    return
            except Exception:  # noqa: BLE001
                return

    threading.Thread(target=loop, daemon=True).start()
    return flag


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


def _unique_path(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while os.path.exists(f"{base}_{i}{ext}"):
        i += 1
    return f"{base}_{i}{ext}"


def start_send_server(paths, port=8000, ip=None, progress_cb=None,
                      on_downloaded=None, on_all_done=None,
                      idle_timeout=0, on_idle=None):
    """把 paths（文件或文件夹）复制/打包到共享目录并启动下载服务。

    paths 含文件夹时自动打包 zip。返回 (url, server, share_dir)。
    on_all_done：全部文件下载完成时回调（触发一次）。
    idle_timeout：空闲秒数，超过则回调 on_idle（0=禁用）。
    """
    share_dir = tempfile.mkdtemp(prefix="fm_share_")
    files = []
    try:
        for p in paths:
            if os.path.isdir(p):
                z = make_zip([p], share_dir,
                             os.path.basename(p.rstrip("\\/")),
                             progress_cb=progress_cb)
                files.append(z)
            elif os.path.isfile(p):
                dst = os.path.join(share_dir, os.path.basename(p))
                if os.path.abspath(dst).lower() != os.path.abspath(p).lower():
                    shutil.copy2(p, dst)
                files.append(dst)
        if not files:
            shutil.rmtree(share_dir, ignore_errors=True)
            return None, None, None
        if progress_cb:
            progress_cb(90, f"共享 {len(files)} 个文件/压缩包…")
        server = _SendServer(share_dir, port, on_downloaded=on_downloaded,
                             on_all_done=on_all_done,
                             idle_timeout=idle_timeout, on_idle=on_idle).start()
        if ip:
            server.url = lambda _ip=None, _u=server.url, _ip0=ip: _u(_ip0)
    except Exception:  # noqa: BLE001
        shutil.rmtree(share_dir, ignore_errors=True)
        return None, None, None
    if progress_cb:
        progress_cb(100, "服务已启动")
    return server.url(), server, share_dir


# ── 接收服务 ────────────────────────────────────
# 接收页：渐变背景 + 卡片 + 拖拽上传 + 多文件进度条（内联，无外部依赖）
_UPLOAD_HTML = r"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>格式大师 · 局域网接收</title>
<style>
:root{
  --bg:linear-gradient(135deg,#eef2ff 0%,#fdf2f8 50%,#eef7ff 100%);
  --card:rgba(255,255,255,.85);--card-border:rgba(255,255,255,.6);
  --shadow:0 20px 60px rgba(99,102,241,.15),0 2px 8px rgba(0,0,0,.04);
  --ink:#1e293b;--ink2:#64748b;--ink3:#94a3b8;
  --row:#f8fafc;--row-hover:#eef2ff;--line:#e2e8f0;
  --ok:#059669;--err:#dc2626;
}
@media (prefers-color-scheme: dark){
  :root{
    --bg:linear-gradient(135deg,#141725 0%,#1b1425 50%,#0f1c29 100%);
    --card:rgba(30,33,48,.92);--card-border:rgba(255,255,255,.08);
    --shadow:0 20px 60px rgba(0,0,0,.5);
    --ink:#e6e8f2;--ink2:#9aa3b8;--ink3:#6b7280;
    --row:#1e2128;--row-hover:#272c3b;--line:#33384a;
    --ok:#34d399;--err:#f87171;
  }
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Segoe UI","PingFang SC","Microsoft YaHei",system-ui,sans-serif;
min-height:100vh;display:flex;justify-content:center;align-items:center;
padding:20px;background:var(--bg);color:var(--ink)}
.card{background:var(--card);backdrop-filter:blur(18px);
border-radius:24px;padding:30px 26px;width:100%;max-width:540px;
box-shadow:var(--shadow);text-align:center;border:1px solid var(--card-border)}
.head{display:flex;align-items:center;gap:12px;margin-bottom:2px;text-align:left}
.logo{width:52px;height:52px;flex:none;border-radius:15px;
background:linear-gradient(135deg,#6366f1,#a855f7);
display:flex;align-items:center;justify-content:center;
font-size:24px;box-shadow:0 8px 20px rgba(99,102,241,.35)}
h1{font-size:19px;font-weight:700;flex:1;letter-spacing:.3px}
.lang{flex:none;border:1px solid var(--line);background:transparent;color:var(--ink2);
border-radius:8px;padding:5px 11px;font-size:12px;cursor:pointer}
.lang:hover{border-color:#6366f1;color:#6366f1}
.sub{color:var(--ink2);font-size:13px;margin:6px 0 16px}
#saveInfo{margin:0 0 14px;padding:8px 12px;border-radius:10px;background:rgba(16,185,129,.08);
color:var(--ink2);font-size:12px;text-align:left;line-height:1.7;word-break:break-all}
#saveInfo b{color:var(--ink)}
.drop{border:2px dashed #c7d2fe;border-radius:16px;padding:24px 16px;cursor:pointer;
transition:all .2s;background:rgba(238,242,255,.5)}
.drop:hover,.drop.drag{border-color:#6366f1;background:rgba(99,102,241,.08)}
.drop .ic{font-size:28px}
.drop .t1{color:#4338ca;font-size:14px;font-weight:600;margin-top:8px}
.drop .t2{color:var(--ink3);font-size:12px;margin-top:4px}
.btns{margin-top:12px;display:flex;gap:8px;justify-content:center;flex-wrap:wrap}
.btn{display:inline-block;padding:10px 18px;border:0;border-radius:12px;
background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;font-size:14px;font-weight:600;
cursor:pointer;box-shadow:0 6px 16px rgba(99,102,241,.35);transition:transform .15s,box-shadow .15s}
.btn:hover{transform:translateY(-1px);box-shadow:0 8px 22px rgba(99,102,241,.45)}
.btn:disabled{opacity:.5;cursor:not-allowed;transform:none}
.btn.green{background:linear-gradient(135deg,#10b981,#0ea5e9);box-shadow:0 6px 16px rgba(16,185,129,.35)}
.btn.ghost{background:transparent;color:var(--ink2);border:1px solid var(--line);box-shadow:none}
#stats{margin-top:14px;font-size:12px;color:var(--ink2);display:none}
#stats b{color:var(--ink)}
#list{margin-top:10px;text-align:left;display:none}
.item{display:flex;align-items:center;gap:8px;padding:9px 12px;border-radius:12px;
background:var(--row);margin-bottom:8px;font-size:13px;color:var(--ink)}
.item .ic{flex:none;font-size:16px}
.item .nm{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.item .st{font-size:12px;color:var(--ink2);white-space:nowrap}
.bar{height:4px;border-radius:2px;background:var(--line);margin-top:6px;overflow:hidden}
.bar i{display:block;height:100%;width:0;background:linear-gradient(90deg,#6366f1,#a855f7);
border-radius:2px;transition:width .2s}
.item.ok .st{color:var(--ok)}.item.err .st{color:var(--err)}
.item .retry{border:1px solid var(--line);background:transparent;color:var(--err);
border-radius:6px;padding:3px 9px;font-size:12px;cursor:pointer;flex:none}
#done{display:none;margin-top:16px;padding:12px;border-radius:12px;background:rgba(16,185,129,.12);
color:var(--ok);font-size:13px;font-weight:600}
#tip{display:none;margin-top:10px;padding:9px 12px;border-radius:10px;
background:rgba(99,102,241,.1);color:var(--ink2);font-size:12px}
#dirWarn{display:none;margin-top:12px;padding:10px 14px;border-radius:10px;
background:#fef3c7;color:#92400e;font-size:13px;text-align:left;line-height:1.6}
#dirWarn b{color:#78350f}
#dirWarn .d2{color:#a16207;font-size:12px}
</style></head><body>
<div class="card">
  <div class="head">
    <div class="logo">📥</div>
    <h1 data-i18n="title2">发送文件到电脑</h1>
    <button class="lang" id="langBtn" onclick="toggleLang()">🌐 EN</button>
  </div>
  <p class="sub" data-i18n="sub">格式大师 · 局域网接收</p>
  <div id="saveInfo">📂 <span data-i18n="saveto">保存到电脑</span>：<b>__SAVE_DIR__</b><br>
    <span data-i18n="session">会话</span>：<b>#__SESSION_ID__</b></div>
  <div class="drop" id="drop">
    <div class="ic">📁</div>
    <div class="t1" data-i18n="d1">点击选择文件，或拖拽到此处</div>
    <div class="t2" data-i18n="d2">支持多文件，无需数据线</div>
  </div>
  <div class="btns">
    <button class="btn green" id="dir" data-i18n="dirbtn">📁 选择文件夹</button>
    <button class="btn" id="go" disabled data-i18n="go">⬆ 开始上传</button>
  </div>
  <div id="stats"><b id="stN">0</b> · <span id="stS">0 B</span></div>
  <div id="list"></div>
  <div id="dirWarn">
    ⚠ <b data-i18n="dw1">当前浏览器不支持「选择文件夹」</b><br>
    <span class="d2" data-i18n="dw2">常见原因：iOS Safari、夸克/UC、微信/QQ 内置浏览器（系统会弹「照片/拍照/文件」三选一面板，无文件夹入口）。</span><br>
    <span class="d2" data-i18n="dw3"><b>建议</b>：① 用上方「点击选择文件」多选上传；② 或在「文件」App 里把文件夹压成 zip 再传。</span>
  </div>
  <div class="btns">
    <button id="clearAll" style="display:none;border:1px solid var(--line);background:transparent;color:var(--ink2);
      padding:8px 18px;border-radius:10px;font-size:13px;cursor:pointer" data-i18n="clear">🗑 清除全部</button>
  </div>
  <div id="done"></div>
</div>
<input type="file" id="file" multiple hidden>
<input type="file" id="dirFile" webkitdirectory multiple hidden>
<script>
var I18N={
 zh:{title:'格式大师 · 局域网接收',title2:'发送文件到电脑',sub:'格式大师 · 局域网接收',
     saveto:'保存到电脑',session:'会话',d1:'点击选择文件，或拖拽到此处',d2:'支持多文件，无需数据线',
     dirbtn:'📁 选择文件夹',go:'⬆ 开始上传',clear:'🗑 清除全部',
     stats:'已选',ok:'✓ 完成',fail:'✗ 失败',retry:'↻ 重试',all_done:'全部上传完成（{n} 个文件）',
     dw1:'当前浏览器不支持「选择文件夹」',
     dw2:'常见原因：iOS Safari、夸克/UC、微信/QQ 内置浏览器（系统会弹「照片/拍照/文件」三选一面板，无文件夹入口）。',
     dw3:'<b>建议</b>：① 用上方「点击选择文件」多选上传；② 或在「文件」App 里把文件夹压成 zip 再传。'},
 en:{title:'FormatMaster · LAN Receive',title2:'Send Files to PC',sub:'FormatMaster · LAN receive',
     saveto:'Save to',session:'Session',d1:'Tap to pick files, or drag & drop',d2:'Multiple files, no cable needed',
     dirbtn:'📁 Pick folder',go:'⬆ Upload',clear:'🗑 Clear all',
     stats:'Selected',ok:'✓ Done',fail:'✗ Failed',retry:'↻ Retry',all_done:'All uploaded ({n} files)',
     dw1:'This browser does not support "Pick folder"',
     dw2:'Common: iOS Safari, Quark/UC, WeChat/QQ in-app browsers (system shows Photo/Camera/File picker only).',
     dw3:'<b>Tips</b>: ① use "Pick files" above; ② zip the folder in the Files app first.'}
};
var LANG=(navigator.language||'zh').toLowerCase().indexOf('en')===0?'en':'zh';
function t(k){return (I18N[LANG]&&I18N[LANG][k])||I18N.zh[k]||k}
function applyLang(){
  document.querySelectorAll('[data-i18n]').forEach(function(el){
    el.innerHTML=t(el.getAttribute('data-i18n'));
  });
  document.title=t('title');
  document.getElementById('langBtn').textContent='🌐 '+(LANG==='zh'?'EN':'中');
}
function toggleLang(){LANG=LANG==='zh'?'en':'zh';applyLang()}

var files=[],go=document.getElementById('go'),drop=document.getElementById('drop'),
    list=document.getElementById('list'),done=document.getElementById('done'),
    fi=document.getElementById('file'),df=document.getElementById('dirFile'),
    dirBtn=document.getElementById('dir'),
    clearAll=document.getElementById('clearAll'),dirWarn=document.getElementById('dirWarn'),
    statsEl=document.getElementById('stats'),
    stN=document.getElementById('stN'),stS=document.getElementById('stS');
var _upState={};   // fid -> 'ok' | 'err'（fid 为文件唯一 id，避免并发索引错乱）
var _doneTotal=0;  // 本次成功上传总数（供底部汇总）
var _nextId=0;     // 文件自增 id

// ── 浏览器能力检测：webkitdirectory 实际可用性 ──
function folderSupported(){
  var ua=navigator.userAgent||'';
  if(typeof df.webkitdirectory==='undefined')return false;
  if(/iPad|iPhone|iPod/.test(ua))return false;
  if(/MicroMessenger|MQQBrowser|QQBrowser\/|QQ\/|Quark|UCBrowser|UCWEB/i.test(ua))return false;
  return true;
}
if(!folderSupported()){
  dirBtn.style.display='none';
  dirWarn.style.display='block';
}
drop.onclick=function(){fi.click()};
dirBtn.onclick=function(){
  if(!folderSupported()){
    dirWarn.style.display='block';
    dirBtn.style.display='none';
    return;
  }
  df.webkitdirectory=true;
  df.click();
};

// ── 文件追加（去重）────────────────────────────
function addFiles(fl){
  Array.from(fl).forEach(function(f){
    var dup=files.some(function(x){return x.name===f.name&&x.size===f.size});
    if(!dup){f._fid=_nextId++;files.push(f);}
  });
}
df.onchange=function(){
  addFiles(df.files);
  df.value='';
  render();
};
fi.onchange=function(){
  addFiles(fi.files);
  fi.value='';
  render();
};
drop.ondragover=function(e){e.preventDefault();drop.classList.add('drag')};
drop.ondragleave=function(){drop.classList.remove('drag')};
drop.ondrop=function(e){e.preventDefault();drop.classList.remove('drag');
  addFiles(e.dataTransfer.files);render();};

// ── 类型图标 ──────────────────────────────────
function typeIcon(name){
  var e=(name.split('.').pop()||'').toLowerCase();
  if(/^(jpg|jpeg|png|gif|webp|bmp|svg|heic|heif|tif|tiff|avif|raw|cr2|nef|arw|dng|jxl)$/.test(e))return '📷';
  if(/^(psd|ai|eps|exr|hdr|tga)$/.test(e))return '🎨';
  if(/^(mp4|m4v|mkv|avi|mov|wmv|flv|webm|ts|m2ts|3gp|rmvb|mpg|mpeg|vob|ogv|mts)$/.test(e))return '🎬';
  if(/^(mp3|wav|flac|aac|ogg|m4a|m4b|wma|ape|opus|amr|aif|aiff)$/.test(e))return '🎵';
  if(/^(pdf|doc|docx|txt|md|rtf|pages|key)$/.test(e))return '📝';
  if(/^(xls|xlsx|csv|tsv|numbers)$/.test(e))return '📊';
  if(/^(ppt|pptx)$/.test(e))return '📑';
  if(/^(epub|mobi|azw|azw3|fb2|chm|djvu)$/.test(e))return '📚';
  if(/^(zip|zipx|rar|7z|tar|gz|bz2|xz|tgz|tbz2|txz|zst|lz|lzma|cab|iso|cbz|cbr)$/.test(e))return '🗜';
  if(/^(apk)$/.test(e))return '🤖';
  if(/^(ipa)$/.test(e))return '🍎';
  if(/^(exe|msi|dmg|deb|rpm)$/.test(e))return '⚙️';
  return '📄';
}
function fmt(n){return n<1024?n+' B':n<1048576?(n/1024).toFixed(1)+' KB':(n/1048576).toFixed(1)+' MB'}
function render(){
  list.style.display=files.length?'block':'none';
  go.disabled=!files.length;
  done.style.display='none';
  clearAll.style.display=files.length?'inline-block':'none';
  var sz=0;files.forEach(function(f){sz+=f.size});
  stN.textContent=files.length;
  stS.textContent=fmt(sz);
  statsEl.style.display=files.length?'block':'none';
  list.innerHTML=files.map(function(f){
    var fid=f._fid;
    if(_upState[fid]==='ok')return '';   // 成功项已从列表移除（见 uploadItem）
    var st=_upState[fid]==='err'?'<span class="st">✗ '+t('fail')+'</span>'
                               :'<span class="st">'+fmt(f.size)+'</span>';
    var retry=_upState[fid]==='err'
      ?'<button class="retry" onclick="uploadItem('+fid+')">↻ '+t('retry')+'</button>':'';
    return '<div class="item" id="it'+fid+'"><span class="ic">'+typeIcon(f.name)+'</span>'+
      '<span class="nm">'+f.name+'</span>'+st+retry+
      '<span style="cursor:pointer;color:var(--err);font-size:16px;padding:0 2px" '+
      'onclick="removeItem('+fid+')">✕</span></div>';
  }).join('');
}
function removeItem(fid){
  var idx=files.findIndex(function(x){return x._fid===fid});
  if(idx>-1)files.splice(idx,1);
  delete _upState[fid];
  render();
  if(!files.length)list.style.display='none';
}
clearAll.onclick=function(){files=[];_upState={};_doneTotal=0;render();list.style.display='none';};

// ── 上传（单项独立，支持失败重试）──────────────
function uploadItem(fid){
  if(_upState[fid]==='ok')return;
  var f=files.find(function(x){return x._fid===fid});
  if(!f)return;
  var it=document.getElementById('it'+fid);
  if(!it)return;   // 行尚未渲染时安全退出，不中断整批
  _upState[fid]='uploading';
  it.classList.remove('err');
  var fd=new FormData();
  fd.append('file',f,f.webkitRelativePath||f.name);
  var x=new XMLHttpRequest();
  x.open('POST','/');
  x.upload.onprogress=function(e){
    if(e.lengthComputable){
      var it0=document.getElementById('it'+fid);
      if(!it0)return;
      it0.querySelector('.bar')||it0.insertAdjacentHTML('beforeend','<div class="bar"><i></i></div>');
      var b=it0.querySelector('.bar i');
      if(b)b.style.width=(e.loaded/e.total*100)+'%';
    }
  };
  x.onload=function(){
    var it0=document.getElementById('it'+fid);
    if(!it0)return;
    var it_ok=(x.status===200&&x.responseText.indexOf('成功')>-1);
    if(it_ok){
      _upState[fid]='ok';
      it0.classList.add('ok');
      it0.querySelector('.st').textContent='✓ '+t('ok');
      it0.querySelector('.bar')&&it0.querySelector('.bar').remove();
      _doneTotal++;
      // 短暂显示 ✓ 后自动移出列表（按 fid 实时定位，并发完成不会错删）
      setTimeout(function(){
        if(_upState[fid]!=='ok')return;
        var idx=files.findIndex(function(x){return x._fid===fid});
        if(idx>-1)files.splice(idx,1);
        delete _upState[fid];
        render();
        if(!files.length){
          go.disabled=true;
          done.style.display='block';
          done.textContent=t('all_done').replace('{n}',_doneTotal);
        }
      },600);
    }else{
      _upState[fid]='err';
      it0.classList.add('err');
      it0.querySelector('.st').textContent='✗ '+t('fail');
      it0.querySelector('.bar')&&it0.querySelector('.bar').remove();
      it0.querySelector('.retry')||it0.insertAdjacentHTML('beforeend',
        '<button class="retry" onclick="uploadItem('+fid+')">↻ '+t('retry')+'</button>');
    }
    var left=Array.from(document.querySelectorAll('.item:not(.ok):not(.err)')).length;
    if(!left){
      var fails=Array.from(document.querySelectorAll('.item.err')).length;
      go.disabled=false;
      done.style.display='block';
      done.textContent=fails?('⚠ '+fails+' '+t('fail')):t('all_done').replace('{n}',files.length);
    }
  };
  x.onerror=function(){
    var it0=document.getElementById('it'+fid);
    if(!it0)return;
    _upState[fid]='err';
    it0.classList.add('err');
    it0.querySelector('.st').textContent='✗ '+t('fail');
    it0.insertAdjacentHTML('beforeend',
      '<button class="retry" onclick="uploadItem('+fid+')">↻ '+t('retry')+'</button>');
    go.disabled=false;
  };
  x.send(fd);
}
go.onclick=function(){
  go.disabled=true;done.style.display='none';
  files.forEach(function(f){
    try{uploadItem(f._fid)}catch(e){}
  });
};
applyLang();
</script></body></html>"""


_CLASSIFY_GROUPS = {
    "图片": {
        # 常规位图/矢量
        "jpg", "jpeg", "jpe", "jfif", "png", "apng", "gif", "webp",
        "bmp", "ico", "svg", "avif", "heic", "heif", "tif", "tiff",
        "wbmp", "jxl", "bpg",
        # 相机 RAW
        "raw", "cr2", "cr3", "nef", "nrf", "arw", "srf", "srw",
        "orf", "rw2", "pef", "dng", "raf", "x3f", "kdc", "erf",
        "mrw", "mef", "mos", "iiq", "3fr",
        # 设计/特效/贴图
        "psd", "psb", "ai", "eps", "dds", "exr", "hdr", "tga",
        "pcx", "xcf",
    },
    "视频": {
        "mp4", "m4v", "mkv", "avi", "mov", "wmv", "flv", "f4v",
        "webm", "mpg", "mpeg", "mpe", "vob", "mts", "m2ts", "ts",
        "m2v", "ogv", "ogm", "3gp", "3g2", "asf", "asx", "rm",
        "rmvb", "divx", "xvid", "dv", "mxf", "m2p", "mod", "tod",
        "trp", "m1v", "nsv", "wtv",
    },
    "音频": {
        "mp3", "mp2", "mp1", "wav", "flac", "aac", "m4a", "m4b",
        "ogg", "oga", "opus", "wma", "ape", "mid", "midi", "amr",
        "wv", "tta", "mpc", "dsf", "dff", "aif", "aiff", "au",
        "caf", "spx", "ra",
        # 播放列表
        "m3u", "m3u8", "pls",
    },
    "文档": {
        # Office
        "doc", "docx", "docm", "dot", "dotx", "dotm",
        "xls", "xlsx", "xlsm", "xlsb", "xlt", "xltx", "xltm",
        "ppt", "pptx", "pptm", "pot", "potx", "potm", "xps",
        "csv", "tsv",
        # WPS 办公
        "wps", "et", "dps", "wpt",
        # PDF / 电子书
        "pdf", "epub", "mobi", "azw", "azw3", "fb2", "chm",
        "djvu", "oxps",
        # 文本 / 代码 / 数据
        "txt", "md", "rtf", "log", "ini", "conf", "cfg", "json",
        "xml", "yaml", "yml", "html", "htm", "css", "js",
        "jsx", "tsx", "vue", "py", "c", "cpp", "h", "hpp", "java",
        "go", "rs", "rb", "php", "sh", "bat", "cmd", "ps1", "vbs",
        "lua", "sql", "sqlite", "db", "mdb", "accdb", "ics", "vcf",
        "tex",
        # 苹果 iWork
        "pages", "numbers", "key",
    },
    "压缩包": {
        # 主流压缩格式
        "zip", "zipx", "rar", "7z", "tar", "gz", "bz2", "xz",
        "tgz", "tbz2", "txz", "zst", "lz", "lzma", "br",
        # 压缩/归档分卷与老格式
        "cab", "ace", "arc", "alz", "z", "lzh", "lha", "cpio",
        "iso", "uue",
        # 安装包 / 程序包（本质为归档）
        "msi", "wim", "swm", "jar", "war", "apk", "ipa", "deb",
        "rpm", "ar",
        # 扩展包 / 文档包 / 漫画包
        "xpi", "crx", "whl", "egg", "cbz", "cbr",
    },
}


_MEDIA_EXTS = _CLASSIFY_GROUPS["图片"] | _CLASSIFY_GROUPS["视频"]

_PREVIEW_EXTS = {
    # 图片
    "jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "heic", "heif",
    # 视频
    "mp4", "webm", "ogg",
    # PDF
    "pdf",
    # Office文档（需要转换）
    "doc", "docx", "xls", "xlsx", "ppt", "pptx",
}


def _classify_dir(name):
    """按扩展名返回分类子目录名（未识别归「其他」）。"""
    ext = os.path.splitext(name)[1].lower().lstrip(".")
    for group, exts in _CLASSIFY_GROUPS.items():
        if ext in exts:
            return group
    return "其他"


def _safe_rel(name):
    """把 multipart 文件名安全化为相对路径（支持文件夹上传的子目录）。

    - 统一 / 分隔；. 跳过；.. 弹出一级（防路径穿越）
    - 返回空串表示不合法
    """
    name = (name or "").replace("\\", "/")
    parts = []
    for p in name.split("/"):
        if p in ("", "."):
            continue
        if p == "..":
            if parts:
                parts.pop()
            continue
        parts.append(p)
    return os.path.join(*parts) if parts else ""


class _BoundedReader:
    """按 Content-Length 限制读取的流包装。

    BufferedReader.read(n) 会阻塞到读满 n 字节或 EOF，而 multipart 结束标记
    后 body 剩余不足 1MB 时，固定 read(1MB) 会永远等不满 → 与等待响应的
    客户端互相死锁（表现为上传卡死/超时/极慢）。按剩余字节裁剪读取可根治。
    """

    def __init__(self, rfile, length):
        self._r = rfile
        self._left = max(length, 0)

    def read(self, n=-1):
        if self._left <= 0:
            return b""
        want = n if (n and n > 0) else self._left
        want = min(want, self._left)
        data = self._r.read(want)
        self._left -= len(data)
        return data


def _parse_multipart_stream(src, boundary, save_dir, conflict, t0,
                            on_file=None, ip="", classify=False,
                            on_bytes=None):
    """流式解析 multipart：从 src（文件句柄）分块读，文件内容直接写盘。

    大文件不占内存（边收边写）。conflict: rename/overwrite/skip。
    classify: 按扩展名存入 图片/视频/音频/文档/压缩包/其他 子目录。
    on_file(relpath, size, seconds, ip, renamed_from) 每完成一个文件回调一次；
    relpath 相对 save_dir（含分类子目录），renamed_from 非空表示冲突改名
    （原名 → 实际名）。
    """
    sep = b"--" + boundary
    buf = b""
    state = "head"          # head → content → head
    fout = None
    cur_path = None
    cur_size = 0
    orig_name = None
    _MAX_HEAD = 1 << 16

    def _close():
        nonlocal fout, cur_path, cur_size, orig_name
        if fout is not None:
            try:
                fout.close()
            except Exception:  # noqa: BLE001
                pass
            if on_file and cur_path and conflict != "skip":
                try:
                    rel = os.path.relpath(cur_path, save_dir)
                    renamed = (orig_name if (orig_name and
                              os.path.basename(rel) != orig_name) else None)
                    on_file(rel, cur_size, time.time() - t0, ip, renamed)
                except Exception:  # noqa: BLE001
                    pass
            fout, cur_path, cur_size = None, None, 0
            orig_name = None

    while True:
        data = src.read(1 << 20)
        if not data:
            break
        if on_bytes:
            try:
                on_bytes(len(data))
            except Exception:  # noqa: BLE001
                pass
        buf += data
        while True:
            if state == "head":
                idx = buf.find(b"\r\n\r\n")
                if idx == -1:
                    if len(buf) > _MAX_HEAD:
                        buf = buf[-_MAX_HEAD:]
                    break
                head = buf[:idx]
                buf = buf[idx + 4:]
                filename = None
                for line in head.split(b"\r\n"):
                    if b"filename=" in line.lower():
                        s = line.decode("utf-8", errors="replace")
                        fn = s.split('filename="', 1)[-1].rsplit('"', 1)[0]
                        if fn:
                            filename = _safe_rel(fn)   # 保留相对路径（文件夹上传），并防穿越
                if filename:
                    orig_name = filename
                    # 文件夹上传：webkitRelativePath 携带子目录，这里恢复目录结构
                    target = os.path.join(save_dir, filename)
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    if classify:
                        target = os.path.join(save_dir,
                                              _classify_dir(filename),
                                              os.path.basename(filename))
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                    if conflict == "overwrite":
                        cur_path = target
                        fout = open(target, "wb")
                    elif conflict == "skip" and os.path.exists(target):
                        cur_path = None
                        fout = None
                    else:
                        cur_path = _unique_path(target)
                        fout = open(cur_path, "wb")
                state = "content"
            else:  # content
                idx = buf.find(sep)
                if idx == -1:
                    # 无分隔符：保留末尾 2 字节（可能是 \r\n 分隔前缀）
                    if fout is not None:
                        if len(buf) > 2:
                            fout.write(buf[:-2])
                            cur_size += len(buf) - 2
                            buf = buf[-2:]
                        elif len(buf) >= 2:
                            fout.write(buf[:-2])
                            cur_size += len(buf) - 2
                            buf = buf[-2:]
                        else:
                            fout.write(buf)
                            cur_size += len(buf)
                            buf = b""
                    else:
                        buf = (buf[-2:] if len(buf) > 2 else b"")
                    break
                content = buf[:idx]
                if content.endswith(b"\r\n"):
                    content = content[:-2]
                if fout is not None:
                    fout.write(content)
                    cur_size += len(content)
                _close()
                after = buf[idx + len(sep):]
                if after.startswith(b"--"):
                    return
                buf = after[2:] if after.startswith(b"\r\n") else after
                state = "head"
    _close()


def _unique_path(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while os.path.exists(f"{base}_{i}{ext}"):
        i += 1
    return f"{base}_{i}{ext}"


class _RecvHandler(http.server.BaseHTTPRequestHandler):
    save_dir = ""
    conflict = "rename"      # rename / overwrite / skip
    classify = False         # 按扩展名分类到子目录
    on_received = None       # (filename, size, seconds, client_ip)
    on_progress = None       # (done_bytes, total_bytes) 上传进度
    last_visit = time.time() # 最近访问时间（空闲超时判定）

    def log_message(self, *a):  # 静默访问日志
        pass

    def do_GET(self):
        _RecvHandler.last_visit = time.time()
        page = _UPLOAD_HTML
        # 注入保存目录与会话标识，页面显示「保存到电脑的…」便于确认连对了设备
        save_show = self.save_dir or ""
        page = page.replace("__SAVE_DIR__", html.escape(save_show) or "-")
        try:
            session = str(getattr(self.server, "server_port", ""))
        except Exception:  # noqa: BLE001
            session = ""
        page = page.replace("__SESSION_ID__", html.escape(session))
        data = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        _RecvHandler.last_visit = time.time()
        self._do_upload()

    def _do_upload(self):
        """流式接收：rfile 分块直连 multipart 解析写盘（单次磁盘 IO，快）。

        旧版先写临时文件再解析（2 写 1 读），局域网大文件明显变慢；
        新版边收边解析边落盘，同时上报实时进度。
        """
        try:
            length = int(self.headers.get("Content-Length", 0))
            ctype = self.headers.get("Content-Type", "")
            boundary = ctype.split("boundary=", 1)[-1].encode()
            t0 = time.time()
            saved = []
            client_ip = self.client_address[0] if self.client_address else ""

            def on_file(name, size, sec, ip, renamed_from=None):
                saved.append(name)
                cb = type(self).on_received   # 类属性非绑定
                if cb:
                    try:
                        cb(name, size, sec, ip, renamed_from)
                    except Exception:  # noqa: BLE001
                        pass

            prog = type(self).on_progress
            done_b = [0]

            def on_bytes(n):
                done_b[0] += n
                if prog:
                    try:
                        prog(done_b[0], length)
                    except Exception:  # noqa: BLE001
                        pass

            _parse_multipart_stream(_BoundedReader(self.rfile, length),
                                    boundary, self.save_dir,
                                    type(self).conflict, t0,
                                    on_file=on_file, ip=client_ip,
                                    classify=type(self).classify,
                                    on_bytes=on_bytes)
            self._respond_html(f"✅ 上传成功：{len(saved)} 个文件<br>"
                               + "<br>".join(saved))
        except Exception as e:  # noqa: BLE001
            self._respond_html(f"❌ 上传失败：{e}")

    def _respond_html(self, msg):
        html = (f'<!DOCTYPE html><meta charset="utf-8"><body style='
                f'"font-family:system-ui;display:flex;justify-content:center;'
                f'align-items:center;min-height:100vh">{msg}</body>')
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _RecvServer:
    def __init__(self, save_dir, port, on_received=None, conflict="rename",
                 classify=False, on_progress=None, idle_timeout=0,
                 on_idle=None):
        _RecvHandler.save_dir = save_dir
        _RecvHandler.on_received = on_received
        _RecvHandler.conflict = conflict
        _RecvHandler.classify = classify
        _RecvHandler.on_progress = on_progress
        _RecvHandler.last_visit = time.time()
        self.port = 0
        self._server = None
        for p in range(port, min(port + 10, 65536)):
            try:
                self._server = http.server.ThreadingHTTPServer(
                    ("0.0.0.0", p), _RecvHandler)
            except OSError:
                continue
            self.port = p
            break
        if self._server is None:
            raise OSError("端口被占用")
        self._thread = None
        self._idle_watch = _start_idle_watch(_RecvHandler, idle_timeout,
                                             on_idle)

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


def start_recv_server(save_dir, port=8001, ip=None, on_received=None,
                      conflict="rename", classify=False,
                      on_progress=None, idle_timeout=0, on_idle=None):
    """启动接收服务（端口被占自动 +1）。

    classify: 按扩展名分类子目录。on_progress: (done, total) 实时进度。
    idle_timeout: 空闲秒数超时回调 on_idle（0=禁用）。
    返回 (url, server)；失败返回 (None, None)。
    """
    os.makedirs(save_dir, exist_ok=True)
    try:
        server = _RecvServer(save_dir, port, on_received, conflict,
                             classify, on_progress, idle_timeout,
                             on_idle).start()
    except OSError:
        return None, None
    if ip:
        server.url = lambda _ip=None, _u=server.url, _ip0=ip: _u(_ip0)
    return server.url(), server

