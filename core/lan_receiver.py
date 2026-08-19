"""lan_receiver — 局域网文件接收端（HTTP 上传服务）。

包含 _RecvHandler、_RecvServer、_BoundedReader、_parse_multipart_stream
及相关的辅助函数和模板。
"""

import http.server
import html
import os
import threading
import time
import urllib.parse

from core.lan_transfer import (_CLASSIFY_GROUPS, _start_idle_watch,
                               _unique_path, get_lan_ip)


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
min-width:0;background:var(--row);margin-bottom:8px;font-size:13px;color:var(--ink)}
.item .ic{flex:none;font-size:16px}
.item .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
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
function esc(s){return (s||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
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
      '<span class="nm" title="'+esc(f.name)+'">'+esc(f.name)+'</span>'+st+retry+
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
  x.open('POST','__UPLOAD_URL__');
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


def _decode_filename(name: str) -> str:
    """还原 multipart filename 的 percent-encoding。

    部分浏览器/微信 WebView/Android 小程序的 FormData 会把非 ASCII 文件名
    直接 percent-encode 后放在 `filename="..."`（而非 RFC 5987 ext-value）。
    解析器若不解码，落盘文件名将是 `%E6%95%99%E5%AD%A6.docx` 形式，
    桌面面板状态栏显示这一长串 percent-encoding 会挤压「启动/停止」按钮。
    """
    if not name or "%" not in name:
        return name
    # RFC 5987 ext-value：filename*="UTF-8''percent-encoded"
    if name.startswith("UTF-8''"):
        try:
            return urllib.parse.unquote(
                name[len("UTF-8''"):], encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            return name
    try:
        return urllib.parse.unquote(name, encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return name


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
                # 优先取 RFC 5987 `filename*=UTF-8''percent-encoded`（Chrome 等
                # 对非 ASCII 文件名的标准做法）；否则回退 `filename="..."`。
                # 部分 WebView 直接把 percent-encoded 放在 filename="..." 里，由
                # _decode_filename 统一还原。
                fn_star = None
                fn_plain = None
                for line in head.split(b"\r\n"):
                    low = line.lower()
                    if b"filename*=" in low:
                        s = line.decode("utf-8", errors="replace")
                        i = s.find("UTF-8''")
                        if i >= 0:
                            rest = s[i + len("UTF-8''"):]
                            j = rest.find('"')           # 引号截断
                            rest = rest[:j] if j >= 0 else rest.split(";", 1)[0]
                            fn_star = rest.strip()
                    elif b"filename=" in low and fn_plain is None:
                        s = line.decode("utf-8", errors="replace")
                        fn = s.split('filename="', 1)[-1].rsplit('"', 1)[0]
                        if fn:
                            fn_plain = fn
                fn = fn_star if fn_star else fn_plain
                if fn:
                    filename = _safe_rel(_decode_filename(fn))
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
        # 上传目标：旧版接收服务挂在根 /，统一服务挂在 /recv/upload（占位符覆盖）
        page = page.replace("__UPLOAD_URL__", "/")
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
        html_txt = (f'<!DOCTYPE html><meta charset="utf-8"><body style='
                f'"font-family:system-ui;display:flex;justify-content:center;'
                f'align-items:center;min-height:100vh">{msg}</body>')
        body = html_txt.encode("utf-8")
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
