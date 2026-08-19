# -*- coding: utf-8 -*-
"""lan_chat_page — 聊天式局域网互传网页（单文件 HTML/JS，无外部依赖）。

扫码进入（手机）或 /chat?side=pc（电脑）后，双方共用同一个 ChatSession：
- 发文字、选图片/文件、粘贴(clipboardData.files)、拖拽上传（电脑端额外支持选文件夹）
- 手机端只保留一个「文件」按钮（可传图片/视频/文件/任意格式），自动隐藏图片与文件夹按钮；页面响应式适配各种屏幕尺寸
- 轮询 /chat/history 近实时刷新；图片内联缩略图，其它文件（含各压缩包格式）给下载链接
- 用户数据一律 textContent 渲染，防 XSS
视觉：Aurora Mint —— 磨砂玻璃面板 + 缓慢漂移的极光渐变背景；我方气泡翡翠→青渐变，
对方玻璃白卡；消息错落弹入、连接点呼吸光、头像首字圆标。零外部依赖（离线可用）。
"""
import html

_CHAT_HTML = r"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,interactive-widget=resizes-content">
<title>格式大师 · 互传</title>
<style>
:root{
  --bg:#eef2f8;
  --glass:rgba(255,255,255,.70);
  --glass-brd:rgba(255,255,255,.65);
  --ink:#0f2233;--ink2:#5b7088;--ink3:#8aa0b6;
  --me1:#10b981;--me2:#06b6d4;          /* 翡翠 → 青 */
  --me-ink:#ffffff;
  --them:rgba(255,255,255,.82);--them-ink:#0f2233;
  --line:rgba(15,34,51,.10);
  --ok:#10b981;
  --glow:rgba(16,185,129,.40);
  --glow2:rgba(99,102,241,.16);
  --glow3:rgba(236,72,153,.12);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#0a1018;
    --glass:rgba(22,30,44,.58);
    --glass-brd:rgba(255,255,255,.09);
    --ink:#eaf1f8;--ink2:#9fb2c8;--ink3:#66788f;
    --me1:#10b981;--me2:#22d3ee;
    --me-ink:#04130d;
    --them:rgba(40,52,72,.64);--them-ink:#eaf1f8;
    --line:rgba(255,255,255,.10);
    --ok:#34d399;
    --glow:rgba(34,211,238,.34);
    --glow2:rgba(129,140,248,.20);
    --glow3:rgba(244,114,182,.16);
  }
}
:root[data-theme="dark"]{
  --bg:#0a1018;
  --glass:rgba(22,30,44,.58);
  --glass-brd:rgba(255,255,255,.09);
  --ink:#eaf1f8;--ink2:#9fb2c8;--ink3:#66788f;
  --me1:#10b981;--me2:#22d3ee;
  --me-ink:#04130d;
  --them:rgba(40,52,72,.64);--them-ink:#eaf1f8;
  --line:rgba(255,255,255,.10);
  --ok:#34d399;
  --glow:rgba(34,211,238,.34);
  --glow2:rgba(129,140,248,.20);
  --glow3:rgba(244,114,182,.16);
}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
html,body{height:100%;height:100dvh}
body{
  font-family:"PingFang SC","Microsoft YaHei",system-ui,-apple-system,"Segoe UI",sans-serif;
  background:var(--bg);color:var(--ink);
  display:flex;flex-direction:column;overflow:hidden;overflow-x:hidden;
  overscroll-behavior:none}
button,textarea,input{touch-action:manipulation}
/* 极光背景：缓慢漂移的低透明度光晕，营造氛围与纵深（不抢内容） */
body::before{content:"";position:fixed;inset:-25%;z-index:-1;pointer-events:none;
  background:
    radial-gradient(42% 40% at 16% 12%, var(--glow), transparent 60%),
    radial-gradient(48% 44% at 86% 16%, var(--glow2), transparent 62%),
    radial-gradient(52% 48% at 72% 94%, var(--glow3), transparent 64%);
  filter:blur(22px);
  animation:drift 20s ease-in-out infinite alternate}
@keyframes drift{0%{transform:translate3d(-3%,-2%,0) scale(1)}
  100%{transform:translate3d(4%,3%,0) scale(1.08)}}
#app{flex:1;display:flex;flex-direction:row;width:100%;min-height:0;position:relative;overflow:hidden}
#app.drag::after{content:"松开即可发送";position:absolute;inset:10px;z-index:9;
  border:2px dashed var(--me1);border-radius:20px;display:flex;align-items:center;
  justify-content:center;background:rgba(16,185,129,.10);backdrop-filter:blur(4px);
  -webkit-backdrop-filter:blur(4px);font-size:16px;font-weight:600;letter-spacing:.04em;
  color:var(--me1);pointer-events:none;animation:rise .2s ease both}
header{display:flex;align-items:center;gap:11px;padding:calc(11px + env(safe-area-inset-top)) 15px 11px;
  background:var(--glass);backdrop-filter:blur(20px) saturate(160%);
  -webkit-backdrop-filter:blur(20px) saturate(160%);
  border-bottom:1px solid var(--glass-brd);position:sticky;top:0;z-index:5;
  animation:rise .5s ease both}
header .logo{width:36px;height:36px;border-radius:11px;flex:none;color:#fff;
  display:flex;align-items:center;justify-content:center;font-size:19px;
  background:linear-gradient(135deg,var(--me1),var(--me2));
  box-shadow:0 6px 16px var(--glow)}
header .t{flex:1;min-width:0}
header .t b{font-size:15px;font-weight:700;display:block;letter-spacing:.01em}
header .t .st{font-size:12px;color:var(--ok);display:inline-flex;align-items:center;gap:6px}
header .t .st::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--ok);
  box-shadow:0 0 0 0 var(--ok);animation:pulse 2.2s infinite}
header .t .st.off{color:var(--ink3)}
header .t .st.off::before{background:var(--ink3);animation:none}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(16,185,129,.55)}
  70%{box-shadow:0 0 0 7px rgba(16,185,129,0)}100%{box-shadow:0 0 0 0 rgba(16,185,129,0)}}
header input.nick{width:98px;font-size:13px;padding:6px 9px;border:1px solid var(--glass-brd);
  border-radius:999px;background:rgba(255,255,255,.45);color:var(--ink);text-align:center;
  outline:none;transition:.18s}
header input.nick:focus{border-color:var(--me1);box-shadow:0 0 0 3px var(--glow)}
#msgs{flex:1;overflow-y:auto;padding:18px 16px;display:flex;flex-direction:column;gap:14px;
  animation:rise .5s .08s ease both}
.row{display:flex;align-items:flex-end;gap:9px;max-width:82%;animation:pop .4s cubic-bezier(.22,1,.36,1) both}
.row.me{align-self:flex-end}
.row.them{align-self:flex-start}
.row .av{width:30px;height:30px;border-radius:50%;flex:none;display:flex;align-items:center;
  justify-content:center;font-size:13px;font-weight:700;color:#fff;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap;
  background:linear-gradient(135deg,#64748b,#475569);box-shadow:0 3px 8px rgba(15,34,51,.18)}
.row.me .av{background:linear-gradient(135deg,var(--me1),var(--me2));box-shadow:0 4px 12px var(--glow)}
.row .col{display:flex;flex-direction:column;min-width:0;max-width:100%}
.row.me .col{align-items:flex-end}
.who{font-size:11px;color:var(--ink3);margin:0 0 4px 4px;max-width:200px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:block}
.bubble{padding:10px 14px;border-radius:18px;line-height:1.5;font-size:14.5px;
  word-break:break-word;white-space:pre-wrap;border:1px solid var(--glass-brd);
  box-shadow:0 6px 18px rgba(15,34,51,.10);max-width:100%;overflow-wrap:anywhere}
.row.me .bubble{background:linear-gradient(135deg,var(--me1),var(--me2));color:var(--me-ink);
  border-bottom-right-radius:6px}
.row.them .bubble{background:var(--them);color:var(--them-ink);border-bottom-left-radius:6px}
.bubble img.thumb{max-width:230px;max-height:230px;border-radius:12px;display:block;cursor:pointer;
  border:1px solid rgba(255,255,255,.35)}
.bubble .fcard{display:flex;align-items:center;gap:11px}
.bubble .fchip{width:46px;height:46px;border-radius:13px;flex:none;display:flex;align-items:center;
  justify-content:center;font-size:24px;background:rgba(255,255,255,.20)}
.bubble .fmeta{display:flex;flex-direction:column;gap:3px;min-width:132px}
.bubble .fname{font-size:13.5px;font-weight:600;overflow:hidden;text-overflow:ellipsis}
.bubble .fsz{font-size:11px;opacity:.85}
.bubble a.dl{display:inline-flex;align-items:center;gap:4px;margin-top:7px;font-size:12px;
  text-decoration:none;padding:5px 11px;border-radius:999px;background:rgba(255,255,255,.22);
  transition:.16s}
.row.me .bubble a.dl{color:#fff;border:1px solid rgba(255,255,255,.55)}
.row.them .bubble a.dl{color:var(--me1);border:1px solid var(--me1)}
.bubble a.dl:active{transform:scale(.95)}
.bar{display:flex;gap:9px;padding:11px 13px calc(11px + env(safe-area-inset-bottom));
  background:var(--glass);backdrop-filter:blur(20px) saturate(160%);
  -webkit-backdrop-filter:blur(20px) saturate(160%);border-top:1px solid var(--glass-brd);
  align-items:flex-end;animation:rise .5s .16s ease both}
.bar textarea{flex:1;resize:none;height:44px;max-height:128px;font:14.5px/1.45 inherit;
  padding:11px 14px;border:1px solid var(--glass-brd);border-radius:15px;
  background:rgba(255,255,255,.50);color:var(--ink);outline:none;transition:.18s}
.bar textarea:focus{border-color:var(--me1);box-shadow:0 0 0 3px var(--glow)}
.bar .acts{display:flex;gap:7px}
.bar button.ico{display:inline-flex;align-items:center;justify-content:center;gap:5px;
  width:auto;height:44px;padding:0 13px;border:1px solid var(--glass-brd);border-radius:14px;
  background:rgba(255,255,255,.55);color:var(--ink2);font-size:15px;cursor:pointer;transition:.18s}
.bar button.ico span{font-size:13px;font-weight:600}
.bar button.ico:hover{transform:translateY(-2px);color:var(--me1);
  box-shadow:0 8px 18px var(--glow)}
.bar button.ico:active{transform:scale(.94)}
.bar button.send{width:auto;padding:0 18px;height:44px;border:0;border-radius:15px;
  background:linear-gradient(135deg,var(--me1),var(--me2));color:#fff;font-size:14px;
  font-weight:700;cursor:pointer;box-shadow:0 8px 20px var(--glow);transition:.18s}
.bar button.send:hover{transform:translateY(-2px);filter:brightness(1.05)}
.bar button.send:active{transform:scale(.97)}
.tip{text-align:center;color:var(--ink3);font-size:12px;padding:9px;opacity:.92}
@keyframes rise{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}
@keyframes pop{from{opacity:0;transform:translateY(12px) scale(.97)}to{opacity:1;transform:none}}
.bubble .upbar{width:160px;height:6px;border-radius:3px;background:rgba(255,255,255,.30);
  overflow:hidden;margin-top:8px}
.row.me .bubble .upbar{background:rgba(255,255,255,.35)}
.bubble .upfill{display:block;height:100%;width:0;background:#fff;transition:width .15s}
.bubble .upspeed{font-size:11px;opacity:.9;margin-top:4px}
/* 响应式 */
@media (max-width:899px){
  #sidebar{position:fixed;left:0;top:0;bottom:0;width:min(72vw,300px);z-index:50;
    transform:translateX(-100%);transition:transform .26s ease;
    box-shadow:6px 0 28px rgba(8,15,30,.18)}
  #sidebar.open{transform:none}
  #btnToggleSide{display:inline-flex}
  #app{position:relative}
}
@media (min-width:600px) and (max-width:899px){
  #sidebar{width:300px}
}
@media (max-width:599px){
  #sidebar{width:min(72vw,260px)}
}
@media (max-width:600px){
  #app{border-radius:0}
  header{gap:9px;padding:calc(9px + env(safe-area-inset-top)) 13px 9px}
  header .t b{font-size:14px}
  header input.nick{width:78px;font-size:12px;padding:5px 8px}
  #msgs{padding:12px 11px;gap:11px}
  .row{max-width:86%}
  .row .av{width:27px;height:27px;font-size:12px}
  .bubble{font-size:14px}
  .bubble img.thumb{max-width:170px;max-height:170px}
  .bar{gap:7px;padding:9px 11px calc(9px + env(safe-area-inset-bottom))}
  .bar textarea{height:42px;font-size:15px;padding:10px 12px}
  .bar .acts{gap:6px}
  .bar button.ico{height:42px;padding:0 12px;font-size:14px;border-radius:13px}
  .bar button.ico span{font-size:12px}
  .bar button.send{height:42px;padding:0 15px;border-radius:13px}
  .tip{padding:7px 8px}
}
@media (max-width:360px){
  header .t b{font-size:13px}
  header input.nick{width:66px}
  .row{max-width:90%}
  .bar button.ico{height:40px;padding:0 11px;font-size:13px}
  .bar button.ico span{font-size:11px}
  .bar button.send{padding:0 13px}
}
@media (min-width:900px){
  #app{flex:none;height:calc(100vh - 48px);height:calc(100dvh - 48px);
    margin:24px auto;border-radius:26px;overflow:hidden;
    border:1px solid var(--glass-brd);
    box-shadow:0 34px 90px rgba(8,15,30,.30)}
}
@media (min-width:601px) and (max-width:899px){
  header{gap:12px;padding:calc(14px + env(safe-area-inset-top)) 20px 14px}
  header .t b{font-size:16px}
  header input.nick{width:110px;font-size:14px;padding:7px 10px}
  #msgs{padding:20px 18px;gap:16px}
  .row{max-width:76%}
  .bubble{font-size:15.5px;padding:12px 16px}
  .bubble img.thumb{max-width:300px;max-height:300px}
  .bubble .fmeta{min-width:180px}
  .bubble .upbar{width:200px}
  .bar{gap:10px;padding:13px 18px calc(13px + env(safe-area-inset-bottom))}
  .bar textarea{height:46px;font-size:16px;padding:12px 15px}
  .bar button.ico{height:46px;padding:0 16px;font-size:16px}
  .bar button.send{height:46px;padding:0 22px}
  .tip{font-size:13px;padding:10px}
}
/* 极窄屏（≤340px）：图标按钮只留图标，进度条收紧 */
@media (max-width:340px){
  .row{max-width:92%}
  .bubble .upbar{width:130px}
  .bar .acts{gap:5px}
  .bar button.ico span{display:none}
  .bar button.ico{width:42px;padding:0}
  .bar button.send{padding:0 13px;font-size:13px}
  header .t b{font-size:12.5px}
  header input.nick{width:60px}
}
/* 横屏矮窗（键盘/小屏横放）：压扁头部与输入栏，保住可视区 */
@media (max-height:460px) and (orientation:landscape){
  header{padding:8px 13px 6px}
  header .logo{width:30px;height:30px;font-size:16px}
  #msgs{padding:10px 11px;gap:10px}
  .bar{padding:6px 11px}
  .bar textarea{height:38px}
  .bar button.ico,.bar button.send{height:38px}
  .tip{display:none}
}
/* 头部工具按钮 */
header .hbtns{display:flex;gap:6px;flex:none}
header button.hbtn{width:34px;height:34px;border:1px solid var(--glass-brd);border-radius:11px;
  background:rgba(255,255,255,.45);color:var(--ink2);font-size:16px;cursor:pointer;transition:.18s;
  display:inline-flex;align-items:center;justify-content:center}
header button.hbtn:hover{color:var(--me1);border-color:var(--me1)}
/* 侧边栏（设备列表）
   注意：不能用带 transform 的 rise 动画——动画帧的 transform:none 在级联中
   优先于普通声明（含 inline style），会把收起用的 translateX(-100%) 覆盖掉，
   导致手机端默认展开、点击收不起来。这里只做透明度渐入。 */
#sidebar{flex:none;width:270px;display:flex;flex-direction:column;
  background:var(--glass);backdrop-filter:blur(22px) saturate(160%);
  -webkit-backdrop-filter:blur(22px) saturate(160%);
  border-right:1px solid var(--glass-brd);min-height:0;z-index:4;
  animation:riseOp .4s ease both}
@keyframes riseOp{from{opacity:0}to{opacity:1}}
#sidebar .wifi-bar{display:flex;align-items:center;gap:9px;padding:18px 16px 12px;
  border-bottom:1px solid var(--glass-brd)}
#sidebar .host-ic{width:30px;height:30px;border-radius:9px;display:flex;align-items:center;
  justify-content:center;font-size:15px;color:#fff;flex:none;
  background:linear-gradient(135deg,var(--me1),var(--me2));
  box-shadow:0 3px 8px var(--glow)}
#sidebar .wifi-name{flex:1;font-size:13.5px;font-weight:600;color:var(--ink);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#sidebar .wifi-name:empty::before{content:"未连接网络";color:var(--ink3);font-weight:400}
/* 侧边栏内「收起」按钮（所有宽度显示；宽屏折叠 sidebar，窄屏关闭抽屉） */
#sidebar .sb-collapse{flex:none;width:30px;height:30px;border:1px solid var(--glass-brd);
  background:rgba(255,255,255,.45);color:var(--ink2);border-radius:8px;font-size:16px;
  cursor:pointer;display:inline-flex;align-items:center;justify-content:center;transition:.15s}
#sidebar .sb-collapse:hover{color:var(--me1);border-color:var(--me1)}
/* 折叠后浮动展开按钮（仅宽屏折叠态显示） */
.sb-expand{position:absolute;left:10px;top:50%;transform:translateY(-50%);
  width:34px;height:48px;border:1px solid var(--glass-brd);border-radius:12px;
  background:var(--glass);backdrop-filter:blur(16px) saturate(160%);
  -webkit-backdrop-filter:blur(16px) saturate(160%);color:var(--ink2);
  font-size:18px;cursor:pointer;display:none;align-items:center;justify-content:center;
  z-index:6;box-shadow:0 4px 14px rgba(15,34,51,.12);transition:.15s}
.sb-expand:hover{color:var(--me1);border-color:var(--me1)}
/* 宽屏：header ☰ 隐藏（用 ‹› 折叠）；折叠态 sidebar 隐藏 + 展开按钮出现 */
@media (min-width:900px){
  #btnToggleSide{display:none}
  #app.collapsed #sidebar{display:none}
  #app.collapsed .sb-expand{display:inline-flex}
}
#sidebar .devs-h{display:flex;align-items:center;gap:8px;padding:14px 16px 8px;
  font-size:13px;color:var(--ink3)}
#sidebar .devs-h b{color:var(--ink);font-size:14px;flex:1;font-weight:600}
#sidebar .dcnt{background:var(--me1);color:#fff;font-size:11px;font-weight:700;
  padding:1px 7px;border-radius:999px;display:none}
#sidebar .dcnt.on{display:inline-block}
#sidebar .devs-list{flex:1;overflow-y:auto;padding:4px 12px 16px;min-height:0}
#sidebar .drow{display:flex;align-items:center;gap:10px;padding:10px 12px;margin:3px 0;
  border-radius:12px;font-size:13.5px;transition:.15s;cursor:default}
#sidebar .drow .ic{width:34px;height:34px;border-radius:50%;flex:none;display:flex;
  align-items:center;justify-content:center;font-size:15px;color:#fff;
  background:linear-gradient(135deg,var(--me1),var(--me2));box-shadow:0 3px 8px var(--glow)}
#sidebar .drow .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  color:var(--ink);font-weight:500}
#sidebar .drow .sz{color:var(--ink3);font-size:11px;flex:none;padding:2px 8px;
  border:1px solid var(--glass-brd);border-radius:999px}
#sidebar .drow.me{border:1.5px solid var(--me1);background:rgba(16,185,129,.06)}
#sidebar .drow.me .ic{box-shadow:0 0 0 3px var(--glow)}
#sidebar .dempty{text-align:center;color:var(--ink3);padding:30px 0;font-size:13px}
/* 主聊天区（侧边栏右侧） */
#chatMain{flex:1;min-width:0;display:flex;flex-direction:column;
  background:var(--bg);min-height:0}
#chatMain header{flex:none}
#chatMain #msgs{flex:1;min-height:0}
#chatMain .bar{flex:none}
#chatMain .tip{flex:none}
/* 侧边栏开关按钮：默认显示（手机/平板）；宽屏 sidebar 常驻，用 ‹› 折叠，隐藏 ☰ */
#btnToggleSide{display:inline-flex}
/* 灯箱 */
#lb{display:none;position:fixed;inset:0;z-index:99;background:rgba(0,0,0,.93);
  flex-direction:column;align-items:center;justify-content:center}
#lb.open{display:flex}
#lb .lbt{position:absolute;top:calc(12px + env(safe-area-inset-top));left:0;right:0;
  display:flex;align-items:center;gap:10px;padding:0 16px;color:#e2e8f0;font-size:13px;z-index:2}
#lb .lbt .n{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#lb .lbbtn{width:40px;height:40px;border:1px solid rgba(255,255,255,.25);border-radius:12px;
  background:rgba(255,255,255,.08);color:#fff;font-size:19px;cursor:pointer;flex:none}
#lb .lbbtn:active{transform:scale(.93)}
#lb .lv{width:100%;height:100%;display:flex;align-items:center;justify-content:center;overflow:auto;padding:64px 20px 20px}
#lb .lv img{max-width:96%;max-height:92%;border-radius:8px;cursor:zoom-in;transition:transform .2s}
#lb .lv img.zoom{transform:scale(2);cursor:zoom-out}
#lb .lv video{max-width:96%;max-height:92%;border-radius:10px}
#lb .lbnav{position:absolute;bottom:calc(18px + env(safe-area-inset-bottom));left:0;right:0;
  display:flex;justify-content:center;gap:10px;z-index:2}
/* 文件清单弹层（底部抽屉） */
#files{display:none;position:fixed;left:0;right:0;bottom:0;z-index:98;max-height:72vh;
  background:var(--glass);backdrop-filter:blur(22px) saturate(160%);
  -webkit-backdrop-filter:blur(22px) saturate(160%);
  border-top:1px solid var(--glass-brd);border-radius:20px 20px 0 0;
  box-shadow:0 -16px 50px rgba(8,15,30,.25);flex-direction:column;
  animation:rise .25s ease both}
#files.open{display:flex}
#files .fh{display:flex;align-items:center;gap:10px;padding:14px 16px 10px;
  border-bottom:1px solid var(--glass-brd)}
#files .fh b{font-size:15px;flex:1}
#files .fh .fc{font-size:12px;color:var(--ink3)}
#files .fl{flex:1;overflow-y:auto;padding:8px 12px;min-height:0}
#files .frow{display:flex;align-items:center;gap:10px;padding:9px 10px;border-radius:12px;font-size:13.5px}
#files .frow:active{background:rgba(99,102,241,.12)}
#files .frow .ic{font-size:18px;flex:none}
#files .frow .nm{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink)}
#files .frow .sz{color:var(--ink3);font-size:12px;flex:none}
#files .frow a.dl{text-decoration:none;color:var(--me1);font-size:12px;flex:none;
  padding:4px 10px;border:1px solid var(--me1);border-radius:999px}
#files .fempty{text-align:center;color:var(--ink3);padding:26px 0;font-size:13px}
/* 文本气泡：禁用原生长按选中/系统菜单，交给自定义复制 */
.bubble.txt-bubble{-webkit-user-select:none;user-select:none;-webkit-touch-callout:none;
  touch-action:manipulation}
/* 右键复制菜单 */
.ctx{display:none;position:fixed;z-index:120;min-width:150px;padding:6px;
  background:var(--glass);backdrop-filter:blur(22px) saturate(160%);
  -webkit-backdrop-filter:blur(22px) saturate(160%);
  border:1px solid var(--glass-brd);border-radius:12px;
  box-shadow:0 14px 40px rgba(8,15,30,.28);animation:pop .18s ease both}
.ctx-item{padding:9px 14px;border-radius:8px;font-size:13.5px;color:var(--ink);
  cursor:pointer;display:flex;align-items:center;gap:8px}
.ctx-item:hover{background:rgba(16,185,129,.12);color:var(--me1)}
.ctx-item:active{transform:scale(.97)}
/* 复制提示（toast） */
.toast{position:fixed;left:50%;bottom:120px;transform:translateX(-50%) translateY(8px);
  z-index:130;padding:9px 18px;border-radius:999px;font-size:13px;color:#fff;
  background:rgba(15,23,42,.86);box-shadow:0 8px 26px rgba(8,15,30,.30);
  opacity:0;pointer-events:none;transition:opacity .22s ease,transform .22s ease}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
</style></head><body>
<div id="app">
  <aside id="sidebar">
    <div class="wifi-bar">
      <span class="host-ic" id="hostIc">📱</span>
      <span class="wifi-name" id="wifiName" title="当前网络">__WIFI_SSID__</span>
      <span hidden id="hostPcName" data-name="__PC_NAME__"></span>
      <button class="sb-collapse" id="sbCollapse" title="收起侧边栏" onclick="setSide(false)">‹</button>
    </div>
    <div class="devs-h">
      <b>连接的设备</b>
      <span class="dcnt" id="devCount"></span>
    </div>
    <div class="devs-list" id="devsList"></div>
  </aside>
  <button class="sb-expand" id="sbExpand" title="展开侧边栏" onclick="setSide(true)">›</button>
  <main id="chatMain">
    <header>
      <button class="hbtn" id="btnToggleSide" title="设备列表" onclick="toggleSideClick()">☰</button>
      <div class="t"><b>格式大师 · 互传</b><span class="st" id="status">连接中…</span></div>
      <input class="nick" id="nick" maxlength="20" placeholder="昵称">
      <div class="hbtns">
        <button class="hbtn" id="btnTheme" title="切换主题">🌗</button>
        <button class="hbtn" id="btnFiles" title="本机文件清单">📄</button>
      </div>
    </header>
    <div id="msgs"></div>
    <div class="bar">
      <textarea id="input" placeholder="发消息，或粘贴 / 拖入文件…"></textarea>
      <div class="acts">
        <button class="ico" id="pickImg" title="图片">🖼<span>图片</span></button>
        <button class="ico" id="pickFile" title="文件">📎<span>文件</span></button>
        <button class="ico" id="pickDir" title="文件夹">📁<span>文件夹</span></button>
        <button class="send" id="send">发送</button>
      </div>
    </div>
    <div class="tip">同一 WiFi 下，扫码的手机与电脑实时互传</div>
  </main>
</div>
<div id="lb">
  <div class="lbt">
    <span class="n" id="lbName"></span>
    <button class="lbbtn" id="lbDl" title="下载">⬇</button>
    <button class="lbbtn" id="lbClose" title="关闭">✕</button>
  </div>
  <div class="lv" id="lbView"></div>
  <div class="lbnav">
    <button class="lbbtn" id="lbPrev" title="上一张">‹</button>
    <span style="color:#94a3b8;font-size:12px;align-self:center" id="lbIdx"></span>
    <button class="lbbtn" id="lbNext" title="下一张">›</button>
  </div>
</div>
<div id="files">
  <div class="fh">
    <b>本机文件清单</b><span class="fc" id="filesStat"></span>
    <button class="lbbtn" id="filesClose" style="width:34px;height:34px">✕</button>
  </div>
  <div class="fl" id="filesList"></div>
</div>
<div class="ctx" id="ctxMenu">
  <div class="ctx-item" id="ctxCopy">📋 复制消息</div>
</div>
<div class="toast" id="toast"></div>
<script>
var PARAMS=new URLSearchParams(location.search);
var _sideParam=PARAMS.get('side');
// URL 带 ?side=pc/phone 时以 URL 为准；无参数时按触屏能力兜底
// （PC 直开链接常漏 ?side=pc，按 navigator.maxTouchPoints 兜底避免误判为手机）
var ME=(_sideParam==='pc'||_sideParam==='phone')?_sideParam
  :((navigator.maxTouchPoints>0||/Mobi|Android|iPhone|iPad/.test(navigator.userAgent))?'phone':'pc');
var TOKEN=PARAMS.get('token')||'';
// 设备唯一 ID（多设备群聊：me 判定与昵称标签都靠它）
var DEVICE_KEY='fm_device';
var DEVICE_ID=localStorage.getItem(DEVICE_KEY)||(function(){
  var d='d'+Math.random().toString(36).slice(2,10)+Date.now().toString(36).slice(-4);
  try{localStorage.setItem(DEVICE_KEY,d);}catch(e){}
  return d;})();
var NICK_KEY='fm_chat_nick_'+ME;
var nick=localStorage.getItem(NICK_KEY)||(ME==='pc'?'电脑':'手机');
var lastId=0, nearBottom=true, pollTimer=null, lastNotified=0;
var MEDIA=[];   // 图片/视频媒体列表（灯箱用）
var $msgs=document.getElementById('msgs');
// 侧边栏展开/收起（定义在脚本最前：HTML 内联 onclick 依赖它，不受后续代码影响）
function setSide(open){
  var sb=document.getElementById('sidebar');
  var app=document.getElementById('app');
  if(window.innerWidth<900){
    if(open){ sb.classList.add('open'); sb.style.transform='none'; }
    else   { sb.classList.remove('open'); sb.style.transform='translateX(-100%)'; }
  }else{
    if(open) app.classList.remove('collapsed');
    else     app.classList.add('collapsed');
  }
}
function toggleSideClick(){
  var sb=document.getElementById('sidebar');
  var app=document.getElementById('app');
  var open=(window.innerWidth<900)?sb.classList.contains('open')
    :!app.classList.contains('collapsed');
  setSide(!open);
}
// 初始状态兜底：窄屏强制收起（inline style，不依赖 CSS 覆盖顺序）+ 主机图标
try{
  var _sb0=document.getElementById('sidebar');
  document.getElementById('hostIc').textContent=ME==='pc'?'🖥':'📱';
  if(window.innerWidth<900){ _sb0.classList.remove('open'); _sb0.style.transform='translateX(-100%)'; }
}catch(e){}
// 给 URL 追加访问 token（无 token 时原样返回）
function A(u){ if(!TOKEN) return u;
  return u+(u.indexOf('?')>-1?'&':'?')+'token='+encodeURIComponent(TOKEN); }
function isMe(m){ return m.device? m.device===DEVICE_ID : m.side===ME; }

function E(t,c,txt){var e=document.createElement(t);if(c)e.className=c;if(txt!=null)e.textContent=txt;return e;}
function fmt(n){n=+n||0;return n<1024?n+' B':n<1048576?(n/1024).toFixed(1)+' KB':(n/1048576).toFixed(1)+' MB';}
function iconFor(name){var n=(name||'').toLowerCase();
  if(/\.(png|jpe?g|gif|webp|bmp|svg|heic|heif|tiff?|avif|jxl)$/.test(n))return '🖼';
  if(/\.(mp4|m4v|mkv|avi|mov|wmv|flv|webm|3gp|rmvb|mpg|mpeg|ts|vob)$/.test(n))return '🎬';
  if(/\.(mp3|wav|flac|aac|ogg|m4a|wma|ape|opus|wv|tta)$/.test(n))return '🎵';
  if(/\.(pdf|docx?|txt|md|rtf|odt|pptx?|pages)$/.test(n))return '📝';
  if(/\.(xlsx?|csv|ods|numbers)$/.test(n))return '📊';
  if(/\.(zip|rar|7z|(tar\.(gz|bz2|xz))|t[bg]z2?|tar|gz|bz2|xz|lz4?|zst|z|iso|cab|wim|ace|apk|jar|dmg|ear|war|deb|rpm|xar|cpio|lzh|alz)$/.test(n))return '🗜';
  return '📄';}
function isOffice(n){return /\.(docx?|pptx?|xlsx?|wps|dps|xlsm)$/i.test(n);}
// 可预览扩展名：Office（转 PDF）、PDF（内联）、文本类（读文本页）
function canPreview(n){n=(n||'').toLowerCase();
  if(isOffice(n))return true;
  if(/\.pdf$/i.test(n))return true;
  return /\.(txt|md|markdown|log|json|py|js|ts|jsx|tsx|css|scss|less|html?|xml|ya?ml|toml|ini|cfg|conf|csv|tsv|sql|sh|bat|ps1|c|cpp|h|hpp|java|go|rs|rb|php|lua|pl|r|kt|swift|m|mm|dart|vue|srt|vtt|ass|lrc|nfo|env|gitignore|properties|m3u8?|lock)$/i.test(n);}
function isAudio(n){return /\.(mp3|wav|flac|aac|ogg|m4a|wma|ape|opus|wv|tta)$/i.test(n);}
function whoLabel(side,frm){if(frm)return frm;return side==='pc'?'电脑':'手机';}
function avatarOf(side,frm){
  var n=(side===ME)? nick : (frm||whoLabel(side,frm));
  n=String(n||'');
  // 30px 圆头像最多 2 字符；超长昵称（Windows 电脑名 63 字符）
  // 必须截断，否则挤压气泡、破坏布局（用户反馈 bug）。
  if(n.length>2) n=n.slice(0,2);
  return n;
}

function renderMsg(m){
  var me=isMe(m);
  var row=E('div','row '+(me?'me':'them'));
  var _atxt=avatarOf(m.side,m.from);
  var av=E('div','av',_atxt);
  // avatarOf 已截到 ≤2 字；按长度微调字号使 1/2 字都居中饱满
  av.style.fontSize=(_atxt.length>=2?'11px':'13px');
  var col=E('div','col');
  if(!me) col.appendChild(E('div','who',whoLabel(m.side,m.from)));
  var b=E('div','bubble');
  if(m.type==='text'){
    b.textContent=m.text;
    // 文本气泡标记 + 存原文：复制入口改为「右键菜单 / 手机长按」（不再常驻按钮）
    b.className='bubble txt-bubble';
    b.__txt=m.text||'';
  }
  else{
    var fn=(m.name||'').toLowerCase();
    var isImg=/\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(fn);
    var isVid=/\.(mp4|m4v|mkv|avi|mov|wmv|flv|webm|3gp|rmvb|mpg|mpeg|ts|vob)$/i.test(fn);
    if(isImg){
      var img=E('img','thumb'); img.src=A('/chat/dl/'+m.id); img.alt=m.name||'';
      img.onclick=function(){openLightbox(m.id);};
      b.appendChild(img);
    }else{
      var fc=E('div','fcard');
      fc.appendChild(E('div','fchip',iconFor(m.name)));
      var meta=E('div','fmeta');
      var nm=E('div','fname'); nm.textContent=m.name||'文件'; meta.appendChild(nm);
      if(m.size!=null) meta.appendChild(E('div','fsz',fmt(m.size)));
      fc.appendChild(meta); b.appendChild(fc);
      if(isVid||isAudio(fn)){
        var pl=E('a','dl',isVid?'▶ 播放':'🎵 播放'); pl.href='javascript:;';
        pl.onclick=function(e){e.preventDefault();openLightbox(m.id);};
        b.appendChild(pl);
      }
    }
    var dl=E('a','dl','⬇ 下载'); dl.href=A('/chat/dl/'+m.id); dl.setAttribute('download',m.name||'');
    b.appendChild(dl);
    if(canPreview(m.name||'')){
      var pv=E('a','dl','👁 预览'); pv.href=A('/chat/preview/'+m.id); pv.target='_blank';
      pv.style.marginLeft='6px'; b.appendChild(pv);
    }
  }
  col.appendChild(b);
  if(me){ row.appendChild(col); row.appendChild(av); }
  else{ row.appendChild(av); row.appendChild(col); }
  return row;
}
function appendMsgs(list){
  for(var i=0;i<list.length;i++){var m=list[i];
      if(m.id>lastId){
        $msgs.appendChild(renderMsg(m));
        if(m.type==='file'){
          var n=(m.name||'').toLowerCase();
          var v=/\.(mp4|m4v|mkv|avi|mov|wmv|flv|webm|3gp|rmvb|mpg|mpeg|ts|vob)$/i.test(n);
          var au=/\.(mp3|wav|flac|aac|ogg|m4a|wma|ape|opus|wv|tta)$/i.test(n);
          if(/\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(n)||v||au){
            MEDIA.push({id:m.id,name:m.name||'',url:'/chat/dl/'+m.id,
              video:v,audio:au});
          }
        }
      if(lastNotified>0 && m.id>lastNotified && !isMe(m)){ notifyNew(m); }
      lastId=m.id;
    }}
  if(nearBottom) $msgs.scrollTop=$msgs.scrollHeight;
}
function setStatus(ok){var s=document.getElementById('status');
  s.textContent=ok?'已连接':'重连中…'; s.className=ok?'st':'st off';}
function poll(){
  // 轮询即心跳：上报设备身份，服务端据此统计在线设备
  fetch(A('/chat/history?after='+lastId
    +'&device='+encodeURIComponent(DEVICE_ID)
    +'&frm='+encodeURIComponent(nick)
    +'&side='+ME)).then(function(r){return r.json();}).then(function(l){
    setStatus(true); appendMsgs(l); lastNotified=lastId;
  }).catch(function(){ setStatus(false); });
}
/* ── 在线设备列表（侧边栏） ── */
function devIcon(side){ return side==='pc'?'🖥':'📱'; }
function renderDevs(list){
  var cnt=document.getElementById('devCount');
  cnt.textContent=list.length||'';
  cnt.className=list.length?'dcnt on':'dcnt';
  var box=document.getElementById('devsList');
  box.innerHTML='';
  if(!list.length){ box.appendChild(E('div','dempty','暂无在线设备')); return; }
  list.forEach(function(d){
    var me=d.device===DEVICE_ID;
    var nm=d.nick||(d.side==='pc'?'电脑':'手机');
    var row=E('div','drow'+(me?' me':''));
    row.appendChild(E('div','ic',devIcon(d.side)));
    var lab=E('div','nm'); lab.textContent=nm+(me?'（你）':''); row.appendChild(lab);
    row.appendChild(E('div','sz',d.side==='pc'?'电脑':'手机'));
    box.appendChild(row);
  });
}
function pollDevices(){
  fetch(A('/chat/devices')).then(function(r){return r.json();}).then(function(l){
    renderDevs(l||[]);
  }).catch(function(){});
}

/* ── 设备机型自动识别（navigator.userAgentData → UA 解析 → 默认） ── */
function detectDeviceName(){
  return new Promise(function(resolve){
    var fallback=function(){
      var ua=navigator.userAgent||'';
      // Android Chrome 通常形如 "...; <厂商/型号> Build/..."
      var am=ua.match(/Android[^;]*;\s*([^)]+?)\s+(Build|AppleWebKit)/);
      if(am) return resolve(am[1].trim());
      // iOS
      if(/iPad/.test(ua)) return resolve('iPad');
      if(/iPhone/.test(ua)) return resolve('iPhone');
      if(/iPod/.test(ua)) return resolve('iPod');
      // PC：取 OS 平台名（归一化 navigator.platform 旧值）
      var p=(navigator.userAgentData&&navigator.userAgentData.platform)||navigator.platform||'';
      p=({Win32:'Windows',Win64:'Windows',MacIntel:'macOS',MacPPC:'macOS',
          MacARM64:'macOS','Linux x86_64':'Linux','Linux i686':'Linux',
          'Linux armv7l':'Linux','Linux armv8l':'Linux','Linux aarch64':'Linux'})[p]||p;
      if(p) return resolve(p);
      resolve(ME==='pc'?'电脑':'手机');
    };
    try{
      if(navigator.userAgentData&&navigator.userAgentData.getHighEntropyValues){
        navigator.userAgentData.getHighEntropyValues(['model','platform','uaFullVersion'])
          .then(function(h){
            if(h.model){ resolve(h.model); return; }
            if(h.platform){
              // userAgentData.platform 也是 Windows/macOS/Linux，已是友好名
              resolve(h.platform); return;
            }
            fallback();
          }).catch(fallback);
        return;
      }
    }catch(e){}
    fallback();
  });
}
function notifyNew(m){
  var body=m.type==='text'?(m.text||'').slice(0,60):(m.name||'收到文件');
  var label=whoLabel(m.side,m.from);
  try{
    if('Notification' in window && Notification.permission==='granted'){
      new Notification(label+' · 格式大师',{body:body});
      return;
    }
  }catch(e){}
  // 兜底：后台标签标题闪烁
  if(document.hidden && document.title.indexOf('📩')!==0){
    var old=document.title;
    document.title='📩 新消息';
    setTimeout(function(){document.title=old;},4000);
  }
}
function sendText(){
  var ta=document.getElementById('input'), t=ta.value.trim(); if(!t)return;
  ta.value='';
  fetch(A('/chat/message'),{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({text:t,side:ME,from:nick,device:DEVICE_ID})}).catch(function(){});
}
function uploadFiles(files,bundle){
  if(!files||!files.length)return;
  var bf=bundle||files.length>1;
  // 逐文件顺序分片上传（便于进度展示与断点续传）
  for(var i=0;i<files.length;i++){
    sendChunked(files[i], bf);
  }
}
// 紧凑增量 SHA-256（无外部依赖，LAN http 无 WebCrypto 也能算）
function Sha256(){
  var K=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
         0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
         0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
         0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
         0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
         0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
         0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
         0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
  var h0=0x6a09e667,h1=0xbb67ae85,h2=0x3c6ef372,h3=0xa54ff53a,
      h4=0x510e527f,h5=0x9b05688c,h6=0x1f83d9ab,h7=0x5be0cd19;
  var total=0, buf=new Uint8Array(64), bl=0;
  function rotr(x,n){return ((x>>>n)|(x<<(32-n)))>>>0;}
  function compress(){
    var w=new Array(64),i;
    for(i=0;i<16;i++) w[i]=((buf[i*4]<<24)|(buf[i*4+1]<<16)|(buf[i*4+2]<<8)|buf[i*4+3])>>>0;
    for(;i<64;i++){
      var s0=rotr(w[i-15],7)^rotr(w[i-15],18)^(w[i-15]>>>3);
      var s1=rotr(w[i-2],17)^rotr(w[i-2],19)^(w[i-2]>>>10);
      w[i]=(w[i-16]+s0+w[i-7]+s1)>>>0;
    }
    var a=h0,b=h1,c=h2,d=h3,e=h4,f=h5,g=h6,hh=h7;
    for(i=0;i<64;i++){
      var S1=rotr(e,6)^rotr(e,11)^rotr(e,25);
      var ch=(e&f)^((~e)&g);
      var t1=(hh+S1+ch+K[i]+w[i])>>>0;
      var S0=rotr(a,2)^rotr(a,13)^rotr(a,22);
      var maj=(a&b)^(a&c)^(b&c);
      var t2=(S0+maj)>>>0;
      hh=g;g=f;f=e;e=(d+t1)>>>0;d=c;c=b;b=a;a=(t1+t2)>>>0;
    }
    h0=(h0+a)>>>0;h1=(h1+b)>>>0;h2=(h2+c)>>>0;h3=(h3+d)>>>0;
    h4=(h4+e)>>>0;h5=(h5+f)>>>0;h6=(h6+g)>>>0;h7=(h7+hh)>>>0;
  }
  return {
    update:function(u8){
      total+=u8.length;
      var i=0;
      while(i<u8.length){
        var n=Math.min(u8.length-i,64-bl);
        buf.set(u8.subarray(i,i+n),bl); bl+=n; i+=n;
        if(bl===64){compress();bl=0;}
      }
    },
    digestHex:function(){
      var totalBits=total*8;
      var bitHi=Math.floor(totalBits/0x100000000), bitLo=totalBits>>>0;
      buf[bl++]=0x80;
      if(bl>56){ while(bl<64){buf[bl++]=0;} compress(); bl=0; }
      while(bl<56){ buf[bl++]=0; }
      buf[56]=(bitHi>>>24)&255; buf[57]=(bitHi>>>16)&255; buf[58]=(bitHi>>>8)&255; buf[59]=bitHi&255;
      buf[60]=(bitLo>>>24)&255; buf[61]=(bitLo>>>16)&255; buf[62]=(bitLo>>>8)&255; buf[63]=bitLo&255;
      compress();
      var out='', hs=[h0,h1,h2,h3,h4,h5,h6,h7];
      for(var i=0;i<8;i++) out+=('00000000'+hs[i].toString(16)).slice(-8);
      return out;
    }
  };
}
function uploadChunk(sid,index,blob,onprog){
  return new Promise(function(resolve){
    var x=new XMLHttpRequest();
    x.open('POST',A('/chat/upload/chunk?sid='+encodeURIComponent(sid)+'&index='+index));
    x.upload.onprogress=function(e){ if(e.lengthComputable&&onprog)onprog(e.loaded); };
    x.onload=function(){ resolve(x.status>=200&&x.status<300); };
    x.onerror=function(){ resolve(false); };
    x.send(blob);
  });
}
function addUploadBubble(name,size){
  var row=E('div','row me');
  var av=E('div','av','↑');
  var col=E('div','col');
  var b=E('div','bubble');
  var nm=E('div','fname'); nm.textContent=name; b.appendChild(nm);
  var bar=E('div','upbar'); var fill=E('div','upfill'); bar.appendChild(fill); b.appendChild(bar);
  var sp=E('div','upspeed'); b.appendChild(sp);
  col.appendChild(b); row.appendChild(col); row.appendChild(av);
  $msgs.appendChild(row);
  if(nearBottom) $msgs.scrollTop=$msgs.scrollHeight;
  return {
    progress:function(pct,spd){ fill.style.width=pct+'%';
      sp.textContent=pct+'% · '+spd.toFixed(1)+' MB/s'; },
    done:function(){ row.remove(); },
    fail:function(m){ fill.style.width='100%'; fill.style.background='#ef4444'; sp.textContent=m; }
  };
}
async function sendChunked(file, bundle){
  var CH=2*1024*1024, total=Math.max(1,Math.ceil(file.size/CH));
  var bubble=addUploadBubble(file.name, file.size);
  if(!file.size){ bubble.fail('空文件无法上传'); return; }
  try{
    // 纯 JS 增量 SHA-256：分片喂入，不占整文件内存，LAN http 也可用
    var hasher=Sha256();
    for(var i=0;i<total;i++){
      var ab=await file.slice(i*CH,(i+1)*CH).arrayBuffer();
      hasher.update(new Uint8Array(ab));
    }
    var sha=hasher.digestHex();
    var init=await fetch(A('/chat/upload/init'),{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({name:file.name,size:file.size,total_chunks:total,
        sha256:sha,side:ME,from:nick,device:DEVICE_ID,bundle:bundle})}).then(function(r){return r.json();});
    if(!init.ok){ bubble.fail('初始化失败'); return; }
    var sid=init.sid;
    // 断点续传：只补传缺失分片
    var st=await fetch(A('/chat/upload/status?sid='+sid)).then(function(r){return r.json();});
    var received=st.received||[];
    var loaded=received.length*CH, t0=performance.now();
    for(var j=0;j<total;j++){
      if(received.indexOf(j)>=0) continue;
      var blob=file.slice(j*CH,(j+1)*CH);
      var ok=await uploadChunk(sid,j,blob,function(sent){
        loaded+=sent;
        var pct=Math.min(100,Math.round(loaded/Math.max(file.size,1)*100));
        var sec=(performance.now()-t0)/1000;
        var spd=sec>0?((loaded/sec)/1048576):0;
        bubble.progress(pct,spd);
      });
      if(!ok){ bubble.fail('上传中断，可重试'); return; }
    }
    var cm=await fetch(A('/chat/upload/commit?sid='+sid),{method:'POST'})
      .then(function(r){return r.json();});
    if(cm.ok){ bubble.done(); }
    else if(cm.err==='sha'){ bubble.fail('校验失败，请重试'); }
    else { bubble.fail('提交失败：'+(cm.err||'未知')); }
  }catch(e){ bubble.fail('上传失败'); }
}
document.getElementById('send').onclick=sendText;
document.getElementById('input').addEventListener('keydown',function(e){
  if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendText();}});
var _fi=null;
function pick(accept,dir){
  if(!_fi){_fi=document.createElement('input');_fi.type='file';_fi.style.display='none';
    document.body.appendChild(_fi);
    _fi.addEventListener('change',function(){var f=_fi.files;
      if(f&&f.length) uploadFiles(f,dir||f.length>1); _fi.value='';});}
  _fi.accept=accept||'';
  if('webkitdirectory' in _fi){try{_fi.webkitdirectory=dir;_fi.mozdirectory=dir;}catch(e){}}
  _fi.click();
}
document.getElementById('pickImg').onclick=function(){pick('image/*',false);};
document.getElementById('pickFile').onclick=function(){pick('',false);};
document.getElementById('pickDir').onclick=function(){pick('',true);};
// 手机端：隐藏「图片」「文件夹」，只留「文件」「剪贴板」「发送」
if(ME!=='pc'){['pickImg','pickDir'].forEach(function(id){var b=document.getElementById(id);if(b)b.style.display='none';});}
document.addEventListener('paste',function(e){
  var items=(e.clipboardData||window.clipboardData).items||[], fs=[];
  for(var i=0;i<items.length;i++) if(items[i].kind==='file'){var f=items[i].getAsFile(); if(f)fs.push(f);}
  if(fs.length) uploadFiles(fs,fs.length>1);
});
var app=document.getElementById('app');
app.addEventListener('dragover',function(e){e.preventDefault();app.classList.add('drag');});
app.addEventListener('dragleave',function(e){if(e.target===app)app.classList.remove('drag');});
app.addEventListener('drop',function(e){e.preventDefault();app.classList.remove('drag');
  var f=e.dataTransfer.files; if(f&&f.length) uploadFiles(f,f.length>1);});
var nk=document.getElementById('nick'); nk.value=nick;
nk.addEventListener('change',function(){nick=nk.value.trim()||nick;localStorage.setItem(NICK_KEY,nick);});
$msgs.addEventListener('scroll',function(){
  nearBottom=$msgs.scrollHeight-$msgs.scrollTop-$msgs.clientHeight<60;});

/* ── 手动主题切换（浅 → 深，两态，无跟随系统） ── */
var THEME_KEY='fm_theme';
var theme=localStorage.getItem(THEME_KEY);
if(theme!=='light'&&theme!=='dark') theme='light';
function applyTheme(){
  var el=document.documentElement;
  el.setAttribute('data-theme',theme);
  var b=document.getElementById('btnTheme');
  b.textContent=theme==='dark'?'🌙':'☀️';
}
function cycleTheme(){ theme=theme==='dark'?'light':'dark';
  try{localStorage.setItem(THEME_KEY,theme);}catch(e){} applyTheme(); }
applyTheme();
document.getElementById('btnTheme').onclick=cycleTheme;

/* ── 图片/视频灯箱 ── */
var lbIdx=-1;
function openLightbox(mid){
  for(var i=0;i<MEDIA.length;i++) if(MEDIA[i].id===mid){lbIdx=i;break;}
  if(lbIdx<0) return;
  document.getElementById('lb').classList.add('open');
  renderLb();
}
function renderLb(){
  if(lbIdx<0||lbIdx>=MEDIA.length) return;
  var it=MEDIA[lbIdx], v=document.getElementById('lbView');
  v.innerHTML='';
  document.getElementById('lbName').textContent=it.name;
  document.getElementById('lbIdx').textContent=(lbIdx+1)+'/'+MEDIA.length;
  var dl=document.getElementById('lbDl');
  dl.href=A('/chat/dl/'+it.id); dl.setAttribute('download',it.name);
  if(it.video){
    var vd=document.createElement('video'); vd.src=A(it.url); vd.controls=true;
    vd.autoplay=true; vd.playsInline=true; v.appendChild(vd);
  }else if(it.audio){
    var ad=document.createElement('audio'); ad.src=A(it.url); ad.controls=true;
    ad.autoplay=true; ad.style.width='min(420px,88vw)'; v.appendChild(ad);
  }else{
    var im=document.createElement('img'); im.src=A(it.url); im.alt=it.name;
    im.onclick=function(){this.classList.toggle('zoom');};
    v.appendChild(im);
  }
}
function lbStep(d){ if(!MEDIA.length) return;
  lbIdx=(lbIdx+d+MEDIA.length)%MEDIA.length; renderLb(); }
document.getElementById('lbClose').onclick=function(){document.getElementById('lb').classList.remove('open');};
document.getElementById('lbView').addEventListener('click',function(e){
  if(e.target===this) document.getElementById('lb').classList.remove('open');});
document.getElementById('lbPrev').onclick=function(){lbStep(-1);};
document.getElementById('lbNext').onclick=function(){lbStep(1);};

/* ── 本机文件清单 ── */
document.getElementById('btnFiles').onclick=openFiles;
document.getElementById('filesClose').onclick=function(){
  document.getElementById('files').classList.remove('open');};
function openFiles(){
  var box=document.getElementById('filesList');
  fetch(A('/chat/history?after=0')).then(function(r){return r.json();}).then(function(list){
    var files=list.filter(function(m){return m.type==='file';});
    var tot=0; files.forEach(function(f){tot+=f.size||0;});
    document.getElementById('filesStat').textContent=files.length+' 个 · '+fmt(tot);
    box.innerHTML='';
    if(!files.length){ box.appendChild(E('div','fempty','暂无文件')); }
    files.forEach(function(f){
      var row=E('div','frow');
      row.appendChild(E('div','ic',iconFor(f.name)));
      var nm=E('div','nm'); nm.textContent=f.name||'文件'; nm.title=f.name||''; row.appendChild(nm);
      row.appendChild(E('div','sz',fmt(f.size)));
      var dl=E('a','dl','下载'); dl.href=A('/chat/dl/'+f.id); dl.setAttribute('download',f.name||'');
      row.appendChild(dl);
      box.appendChild(row);
    });
    document.getElementById('files').classList.add('open');
  }).catch(function(){});
}

/* ── 系统通知：首次交互申请权限（http 非安全上下文无 Notification 时自动跳过） ── */
function askNotify(){
  try{
    if('Notification' in window && Notification.permission==='default'){
      Notification.requestPermission().catch(function(){});
    }
  }catch(e){}
}
document.addEventListener('click',askNotify,{once:true});

/* ── 访问 token：URL 带 token 时静默种 cookie（后续免 token） ── */
if(TOKEN){
  try{
    var fd=new URLSearchParams(); fd.append('token',TOKEN);
    fetch('/chat/login',{method:'POST',body:fd,
      headers:{'Content-Type':'application/x-www-form-urlencoded'}}).catch(function(){});
  }catch(e){}
}

/* ── 文本复制（复制到本机剪贴板，不跨设备） ── */
// 铁律：user-gesture API（execCommand('copy') / clipboard.writeText）必须在
// touchend/click 事件处理函数的**同步调用栈**内执行。
// 上一版教训：LAN HTTP（非 secure context）下 writeText 必然 reject，而 reject
// 回调跑在 microtask 里 —— 跨 microtask 后 iOS Safari 判定 user activation 已
// 失效，execCommand 静默返回 false → 提示"复制失败"（用户反馈 bug）。
// 方案：非 secure context 直接同步 execCopy；手机长按在 touchstart（gesture
// 最强）预建选区，touchend 只同步执行 execCommand。
var _ltTa=null; // 隐藏 textarea（仅 PC 右键/菜单点击复制时创建）
function _prepCopyTa(t){
  try{
    if(_ltTa){ try{document.body.removeChild(_ltTa);}catch(e){} _ltTa=null; }
    var ta=document.createElement('textarea');
    ta.value=t;
    ta.setAttribute('readonly','');   // readonly：iOS 聚焦不弹键盘
    ta.style.position='fixed'; ta.style.top='0'; ta.style.left='0';
    ta.style.width='2em'; ta.style.height='2em'; ta.style.padding='0';
    ta.style.border='0'; ta.style.outline='0';
    ta.style.background='transparent'; ta.style.opacity='0';
    ta.style.zIndex='-1'; ta.style.pointerEvents='none';
    ta.style.fontSize='16px';         // ≥16px：iOS 聚焦不触发自动缩放页面
    document.body.appendChild(ta);
    ta.focus(); ta.select();
    // iOS Safari 必须显式 setSelectionRange 才认 selection
    try{ ta.setSelectionRange(0, t.length); }catch(e){}
    _ltTa=ta;
  }catch(e){ _ltTa=null; }
}
function _execCopyNow(fallbackEl){
  var ok=false;
  try{ ok=document.execCommand('copy'); }catch(e){ ok=false; }
  // 兜底1：textarea 选区失败（部分 iOS/WebView）→ 改选真实文本节点再试。
  // iOS 对真实选中节点的 execCommand('copy') 支持最稳（系统长按复制同路径）。
  if(!ok && fallbackEl){
    try{
      var el=fallbackEl;
      var oldSel=el.style.webkitUserSelect, oldCall=el.style.webkitTouchCallout;
      el.style.webkitUserSelect='text'; el.style.userSelect='text';
      el.style.webkitTouchCallout='default';
      var r=document.createRange(); r.selectNodeContents(el);
      var s=window.getSelection(); s.removeAllRanges(); s.addRange(r);
      try{ ok=document.execCommand('copy'); }catch(e2){ ok=false; }
      // 恢复样式（选中高亮瞬闪可接受）
      el.style.webkitUserSelect=oldSel; el.style.userSelect=oldSel;
      el.style.webkitTouchCallout=oldCall;
      try{ s.removeAllRanges(); }catch(e3){}
    }catch(e4){ ok=false; }
  }
  if(_ltTa){ try{document.body.removeChild(_ltTa);}catch(e){} _ltTa=null; }
  return ok===true;
}
function copyText(t){
  return new Promise(function(resolve){
    // secure context（HTTPS/localhost）：writeText 可成功，走异步链
    if(window.isSecureContext && navigator.clipboard && navigator.clipboard.writeText){
      navigator.clipboard.writeText(t).then(
        function(){ resolve(true); },
        function(){ _prepCopyTa(t); resolve(_execCopyNow()); }
      );
      return;
    }
    // 非 secure context（LAN HTTP）：同步 execCopy，保持 user activation
    _prepCopyTa(t);
    resolve(_execCopyNow());
  });
}

/* ── 复制提示 toast ── */
var _toastTimer=null;
function showToast(msg){
  var t=document.getElementById('toast');
  t.textContent=msg;
  t.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer=setTimeout(function(){ t.classList.remove('show'); },1600);
}

/* ── 文本消息复制：右键菜单 / 手机长按 ── */
var _ctxText='';
function hideCtx(){ document.getElementById('ctxMenu').style.display='none'; }
function showCtx(x,y){
  var m=document.getElementById('ctxMenu');
  m.style.display='block';
  // 越界修正：菜单不超出视口
  var rw=m.offsetWidth, rh=m.offsetHeight;
  m.style.left=Math.min(x, window.innerWidth-rw-6)+'px';
  m.style.top =Math.min(y, window.innerHeight-rh-6)+'px';
}
// 菜单项：复制
document.getElementById('ctxCopy').onclick=function(){
  var t=_ctxText; hideCtx();
  // click 事件本身就是 user gesture，Promise 链保持激活
  copyText(t).then(function(ok){
    showToast(ok ? '已复制' : '复制失败，请重试');
  });
};
// 关闭菜单：点击别处 / 滚动 / Esc
document.addEventListener('click',function(e){
  var m=document.getElementById('ctxMenu');
  if(m.style.display==='none') return;
  if(e.target.closest&&e.target.closest('#ctxMenu')) return;
  // 长按弹菜单后松手的合成 click 不关闭（800ms 内忽略）
  if(Date.now()-_lastLongPress<800) return;
  hideCtx();
});
window.addEventListener('scroll',hideCtx,true);
// PC：右键文本气泡 → 自定义复制菜单
// 长按弹菜单后 800ms 内抑制（iOS 长按后还会再触发一次 contextmenu，避免双弹）
var _lastLongPress=0;
document.addEventListener('contextmenu',function(e){
  if(Date.now()-_lastLongPress<800) return;
  var t=(e.target&&e.target.closest)?e.target.closest('.txt-bubble'):null;
  if(!t) return;
  e.preventDefault();
  _ctxText=t.__txt||t.textContent||'';
  showCtx(e.clientX,e.clientY);
});
// 手机：长按文本气泡 → 弹出复制菜单（长按 550ms，松手后点「复制」）
// 说明：不做长按直接复制——iOS 上 timer 内 execCommand 依赖 transient activation
// 窗口，各版本行为不一，且预建 textarea 的 focus() 会触发 iOS 自动缩放页面
// （用户反馈"网页直接放大了"）。改弹自定义菜单，点「复制」走 click 手势
// （真实 user gesture，execCommand 成功率最高）。
var _ltEl=null, _ltX=0, _ltY=0, _ltTriggered=false;
function _lpHit(e){ return (e.target&&e.target.closest)?e.target.closest('.txt-bubble'):null; }
document.addEventListener('touchstart',function(e){
  var b=_lpHit(e); if(!b||!e.touches[0]) return;
  _ltEl=b;
  _ltX=e.touches[0].clientX; _ltY=e.touches[0].clientY;
  _ltTriggered=false;
  setTimeout(function(){
    if(_ltEl===b){  // 期间未被 touchmove 取消
      _ltTriggered=true;
      _ctxText=b.__txt||b.textContent||'';
      showCtx(_ltX,_ltY);   // 弹复制菜单（与 PC 右键共用）
      try{ if(navigator.vibrate) navigator.vibrate(20); }catch(err){}
      _lastLongPress=Date.now();
    }
  },550);
},{passive:true});
document.addEventListener('touchmove',function(e){
  if(!_ltEl||!e.touches[0]) return;
  var dx=e.touches[0].clientX-_ltX, dy=e.touches[0].clientY-_ltY;
  // 滑动超阈值 → 取消长按（普通滚动/拖动）
  if(dx*dx+dy*dy>100){ _ltEl=null; _ltTriggered=false; }
},{passive:true});
document.addEventListener('touchend',function(){
  // 松手：仅清状态。不 preventDefault、不关闭菜单——菜单由点击别处/滚动/Esc 关闭。
  // 长按后松手不触发 click（iOS），合成 click 已被上方 _lastLongPress 800ms 抑制。
  _ltEl=null; _ltTriggered=false;
},{passive:true});
// touchcancel 同样兜底清理（iOS 上某些场景会发 touchcancel 而非 touchend）
document.addEventListener('touchcancel',function(){
  _ltEl=null; _ltTriggered=false;
});

/* ── 侧边栏：按钮用 HTML 内联 onclick（脚本开头已定义 setSide/toggleSideClick） ── */
// 点击遮罩外区域关闭抽屉（窄屏）
document.addEventListener('click',function(e){
  var sb=document.getElementById('sidebar');
  if(window.innerWidth>=900) return;
  if(!sb.classList.contains('open')) return;
  if(e.target.id==='btnToggleSide'||e.target.id==='sbCollapse') return;
  if(sb.contains(e.target)) return;
  setSide(false);
});

/* ── 机型自动识别 → 默认昵称（用户未自定义时使用） ── */
// PC 优先用服务端注入的真实电脑名（避免显示"Win32"），否则用 UA/平台
// Windows 电脑名最长 63 字符（NetBIOS 上限），不截断会撑爆头像与气泡列宽。
// 默认昵称上限 16 字符（与输入框 maxlength=20 留余量；超长加 … 视觉提示）
var _hostPcName='';
var _hostPcEl=document.getElementById('hostPcName');
if(_hostPcEl&&_hostPcEl.dataset&&_hostPcEl.dataset.name) _hostPcName=_hostPcEl.dataset.name.trim();
function _shortName(s,n){
  s=String(s||'').trim();
  if(!s) return '';
  return s.length>n ? s.slice(0,n-1)+'…' : s;
}
if(!localStorage.getItem(NICK_KEY)){
  if(ME==='pc'&&_hostPcName){
    nick=_shortName(_hostPcName,16);
    var nk=document.getElementById('nick');
    if(nk&&!nk.value) nk.value=nick;
  }else{
    detectDeviceName().then(function(name){
      if(!name) return;
      var sn=_shortName(name,16);
      nick=sn; var nk=document.getElementById('nick');
      if(nk&&!nk.value) nk.value=sn;
    });
  }
}

/* ── Esc 关闭浮层 / 抽屉 / 菜单 ── */
document.addEventListener('keydown',function(e){
  if(e.key==='Escape'){
    document.getElementById('lb').classList.remove('open');
    document.getElementById('files').classList.remove('open');
    setSide(false);
    hideCtx();
  }
});

poll(); pollTimer=setInterval(poll,1500);
pollDevices(); setInterval(pollDevices,3000);
</script></body></html>"""


def chat_html(wifi_ssid="", pc_name=""):
    """返回聊天式互传网页 HTML。

    wifi_ssid / pc_name 由服务端探测并注入（首次请求时探测并缓存）。
    pc_name 通过 hidden #hostPcName 元素的 data-name 传给前端，仅在
    ME==='pc' 且无 UA 机型时作为兜底默认昵称（避免显示"Win32"）。
    """
    return (_CHAT_HTML
            .replace("__WIFI_SSID__", html.escape(wifi_ssid or ""))
            .replace("__PC_NAME__", html.escape(pc_name or "")))
