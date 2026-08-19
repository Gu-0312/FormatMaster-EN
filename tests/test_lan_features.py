"""P1/P2 增强测试：访问密码守卫、多设备 device 字段、剪贴板 clip 消息、
聊天页新功能标记、面板访问密码接线。"""
import inspect
import os
import socket
import tempfile

from fastapi.testclient import TestClient

from core.lan_service import LanService


def _make_srv():
    srv = LanService(port=8787)
    recv = tempfile.mkdtemp(prefix="fm_test_recv_")
    srv.set_recv(recv, conflict="rename", classify=False)
    srv.chat_dir = tempfile.mkdtemp(prefix="fm_test_chat_")
    return srv, recv


# ── 访问密码 / Token 保护 ──────────────────────
def test_access_token_guard():
    srv, _ = _make_srv()
    srv.access_token = "123456"
    c = TestClient(srv._app)
    # 未授权：页面返回登录页（而非聊天页）
    r = c.get("/chat")
    assert r.status_code == 200
    assert "访问密码" in r.text and "/chat/login" in r.text
    # 未授权：API 一律 401
    assert c.get("/chat/history").status_code == 401
    assert c.post("/chat/message", json={"text": "x"}).status_code == 401
    # 错误 token 拒绝
    assert c.get("/chat/history?token=wrong").status_code == 401
    # 正确 query token 通过
    assert c.get("/chat/history?token=123456").status_code == 200
    # 登录表单 → 302 + Set-Cookie；带 cookie 后免 token（浏览器真实行为）
    c2 = TestClient(srv._app, follow_redirects=False)
    r2 = c2.post("/chat/login", data={"token": "123456"})
    assert r2.status_code == 302
    assert "fm_token=123456" in r2.headers.get("set-cookie", "")
    assert c2.get("/chat/history",
                  headers={"Cookie": "fm_token=123456"}).status_code == 200


def test_access_token_disabled_by_default():
    srv, _ = _make_srv()
    c = TestClient(srv._app)
    r = c.get("/chat")
    assert r.status_code == 200
    assert "访问密码" not in r.text
    assert c.get("/chat/history").status_code == 200


# ── 多设备群聊 ────────────────────────────────
def test_multidevice_device_field():
    srv, _ = _make_srv()
    c = TestClient(srv._app)
    c.post("/chat/message", json={"text": "a", "side": "phone",
                                  "from": "手机A", "device": "d1"})
    c.post("/chat/message", json={"text": "b", "side": "phone",
                                  "from": "手机B", "device": "d2"})
    h = c.get("/chat/history").json()
    assert h[0]["device"] == "d1" and h[0]["from"] == "手机A"
    assert h[1]["device"] == "d2" and h[1]["from"] == "手机B"
    # 无 device 的历史消息兼容（缺字段不炸）
    c.post("/chat/message", json={"text": "c", "side": "pc"})
    assert c.get("/chat/history").json()[-1].get("device") is None


# ── 剪贴板消息 type=clip ───────────────────────
def test_clip_message_type():
    srv, _ = _make_srv()
    c = TestClient(srv._app)
    r = c.post("/chat/message", json={"text": "粘贴内容", "type": "clip",
                                      "side": "pc", "device": "d9"})
    assert r.status_code == 200
    h = c.get("/chat/history").json()
    assert h[0]["type"] == "clip" and h[0]["text"] == "粘贴内容"
    assert h[0]["device"] == "d9"
    # 未知 type 回退 text
    c.post("/chat/message", json={"text": "zz", "type": "bogus"})
    assert c.get("/chat/history").json()[-1]["type"] == "text"


# ── 聊天页新功能标记（前端静态锁） ──────────────
def test_chat_page_new_feature_markers():
    from core import lan_chat_page as lcp
    h = lcp._CHAT_HTML
    # 灯箱
    assert 'id="lb"' in h and 'id="lbView"' in h and "openLightbox" in h
    # 本机文件清单
    assert 'id="files"' in h and "openFiles" in h
    # 手动主题切换
    assert "btnTheme" in h and "data-theme" in h
    # 多设备
    assert "DEVICE_ID" in h and "isMe(" in h
    # 系统通知（含非安全上下文守卫）
    assert "notifyNew" in h and "'Notification' in window" in h
    # token 透传
    assert "function A(" in h
    # 在线设备显示（左侧 sidebar：WiFi 名称 + 设备列表 + 当前设备高亮）
    assert 'id="sidebar"' in h and 'id="wifiName"' in h and 'id="hostIc"' in h
    assert 'id="devsList"' in h and 'id="devCount"' in h
    assert "renderDevs" in h and "pollDevices" in h and "detectDeviceName" in h
    assert "devIcon" in h  # 📱/🖥 设备类型图标
    # 侧边栏折叠/展开（窄屏抽屉 + 宽屏折叠）
    assert 'id="btnToggleSide"' in h
    assert 'id="sbCollapse"' in h and 'id="sbExpand"' in h
    assert '#app.collapsed #sidebar{display:none}' in h
    # PC 名称注入（hostPcName 元素 + 读取 data-name 兜底）
    assert 'id="hostPcName"' in h and 'data-name' in h and '_hostPcName' in h
    # navigator.platform 旧值归一化（避免显示"Win32"）
    assert "Win32" in h and "MacIntel" in h
    # 响应式 sidebar 宽度（手机/平板/桌面三档）
    assert "min(72vw,300px)" in h and "min(72vw,260px)" in h
    # sidebar 不得用带 transform 的 rise 动画（动画帧 transform:none 覆盖收起
    # translateX，曾导致手机端默认展开、点击收不起来）→ 用只动透明度的 riseOp
    assert "animation:riseOp .4s ease both" in h
    assert "@keyframes riseOp{from{opacity:0}to{opacity:1}}" in h
    assert "translateX(-100%)" in h  # 收起位移仍在
    # ME 兜底：URL 无 side 时按触屏能力判手机/电脑
    assert "maxTouchPoints" in h
    # 文本消息复制：常驻按钮已移除 → 右键菜单 / 手机长按 + toast 提示
    assert "copyText" in h and "_execCopyNow" in h and "_prepCopyTa" in h and "复制" in h
    assert 'id="ctxMenu"' in h and 'id="ctxCopy"' in h
    assert "txt-bubble" in h and "showToast" in h
    assert "contextmenu" in h and "touchstart" in h and "navigator.vibrate" in h
    assert "var cp=E('a','dl','复制')" not in h  # 常驻复制链接已移除
    # 全格式预览（Office + PDF + 文本类）
    assert "canPreview" in h and "isAudio" in h
    # 旧在线设备弹层已移除（drawer #devs 不再出现）
    assert 'id="devsClose"' not in h
    assert 'id="devCnt"' not in h
    assert 'id="btnDevs"' not in h
    # 剪贴板同步功能已移除（pickClip/clipText 不再出现；📋 仅用于复制菜单图标）
    assert "pickClip" not in h
    assert "clipText" not in h


def test_login_page_eye_toggle():
    """登录页密码输入框带小眼睛（显示/隐藏切换）。"""
    from core import lan_service as ls
    h = ls._LOGIN_HTML
    assert 'id="eye"' in h
    assert 'type="password"' in h and 'id="tok"' in h
    assert "t.type==='password'" in h  # 切换逻辑存在
    assert "setSelectionRange" in h     # 切换后光标回到末尾


# ── WiFi 名称探测与注入 ─────────────────────────
def test_detect_wifi_ssid_and_chat_html():
    """探测函数永不抛异常；chat_html 接受 wifi_ssid/pc_name 替换占位符并 HTML 转义。"""
    from core import lan_service as ls
    from core import lan_chat_page as lcp
    # 探测：异常环境静默返回 ""（不抛）
    assert isinstance(ls.detect_wifi_ssid(), str)
    assert isinstance(ls.detect_pc_name(), str)
    # chat_html 占位符替换
    h = lcp.chat_html(wifi_ssid="CMCC-Test", pc_name="DESKTOP-X1")
    assert "CMCC-Test" in h and "DESKTOP-X1" in h
    assert "__WIFI_SSID__" not in h and "__PC_NAME__" not in h
    # 注入值需 HTML 转义
    h2 = lcp.chat_html(wifi_ssid="<x>", pc_name='A"B')
    assert "&lt;x&gt;" in h2 and "A&quot;B" in h2
    # 空值也能正常渲染（占位符消失，不抛）
    h3 = lcp.chat_html()
    assert "__WIFI_SSID__" not in h3 and "__PC_NAME__" not in h3


# ── 在线设备心跳 ──────────────────────────────
def test_chat_devices_heartbeat():
    srv, _ = _make_srv()
    c = TestClient(srv._app)
    # 心跳上报：轮询 history 带 device/frm/side
    c.get("/chat/history?after=0&device=d1&frm=手机A&side=phone")
    c.get("/chat/history?after=0&device=d2&frm=电脑&side=pc")
    devs = c.get("/chat/devices").json()
    by_id = {d["device"]: d for d in devs}
    assert set(by_id) == {"d1", "d2"}
    assert by_id["d1"]["nick"] == "手机A" and by_id["d1"]["side"] == "phone"
    assert by_id["d2"]["nick"] == "电脑" and by_id["d2"]["side"] == "pc"
    # 发消息也算在线
    c.post("/chat/message", json={"text": "hi", "side": "phone",
                                  "from": "手机A", "device": "d3"})
    assert "d3" in {d["device"] for d in c.get("/chat/devices").json()}


def test_chat_devices_expire():
    """超过存活窗口的设备不再计入在线（模拟 12s 无心跳）。"""
    import time
    srv, _ = _make_srv()
    srv.chat.heartbeat("d1", "旧设备", "phone")
    srv.chat._devices["d1"]["last"] = time.time() - 30  # 30s 前的心跳
    srv.chat.heartbeat("d2", "新设备", "pc")
    devs = srv.chat.devices()
    assert [d["device"] for d in devs] == ["d2"]


# ── 全格式预览（文本 / PDF） ──────────────────
def test_chat_preview_text_and_pdf():
    import os
    srv, _ = _make_srv()
    c = TestClient(srv._app)
    # 文本：写入 chat_dir 内的 .txt 并登记为 file 消息
    txt = os.path.join(srv.chat_dir, "notes.txt")
    with open(txt, "w", encoding="utf-8") as f:
        f.write("你好 <world> & 转义")
    m1 = srv.chat.add("phone", "file", name="notes.txt", size=20, local_path=txt)
    r = c.get(f"/chat/preview/{m1['id']}")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "你好" in r.text and "&lt;world&gt;" in r.text  # 已转义
    # PDF：返回内联 application/pdf
    pdf = os.path.join(srv.chat_dir, "doc.pdf")
    with open(pdf, "wb") as f:
        f.write(b"%PDF-1.4 fake")
    m2 = srv.chat.add("phone", "file", name="doc.pdf", size=12, local_path=pdf)
    r2 = c.get(f"/chat/preview/{m2['id']}")
    assert r2.status_code == 200
    assert r2.headers.get("content-type", "").startswith("application/pdf")
    # 不可预览格式 → 404
    bin_ = os.path.join(srv.chat_dir, "a.zip")
    with open(bin_, "wb") as f:
        f.write(b"PK")
    m3 = srv.chat.add("phone", "file", name="a.zip", size=2, local_path=bin_)
    assert c.get(f"/chat/preview/{m3['id']}").status_code == 404


def test_panel_token_static_lock():
    """访问密码以单一输入框呈现：ed_token 非空即启用（不再有 sw_token 开关）。"""
    from gui_qt.panels import lan_transfer_panel as ltp
    src = inspect.getsource(ltp.LanTransferPanelPage)
    # 输入框 + 偏好键必须存在
    assert "ed_token" in src and "_PREF_TOKEN" in src
    # 服务端 token 字段仍然使用
    assert "access_token" in src
    # 开关已移除（新版改为输入框非空即启用）
    assert "sw_token" not in src
    # 移动端 QR / 电脑打开 URL 都**不带 token**（统一进 /chat/login 密码页）
    assert "?token=" not in src
    assert "editingFinished" in src


def _tok_guard():
    """备份/重置访问密码相关 prefs（测试会真实落盘）。"""
    from utils.config import USER_PREFS
    keys = ("lan_token", "lan_recv_dir")
    old = {k: USER_PREFS.get("qt_app", k, None) for k in keys}
    USER_PREFS.set("qt_app", "lan_token", "")
    USER_PREFS.set("qt_app", "lan_recv_dir", "")

    def _restore():
        for k in keys:
            v = old.get(k)
            if v is None:
                v = ""
            USER_PREFS.set("qt_app", k, v)
    return _restore


def test_panel_access_token_wired(monkeypatch):
    """访问密码 ed_token 非空 → 服务端 token 生效、URL/二维码不带 token 走登录页。"""
    from PySide6.QtWidgets import QApplication
    from gui_qt.components.theme_manager import ThemeManager
    from gui_qt.panels.lan_transfer_panel import LanTransferPanelPage
    from gui_qt.services import QtServices
    from gui_qt.task_manager import TaskManager

    app = QApplication.instance() or QApplication([])
    services = QtServices()
    services.task_manager = TaskManager(services)
    services.theme_mgr = ThemeManager(services)

    class _Window:
        pass

    panel = LanTransferPanelPage(_Window(), services)
    app.processEvents()
    panel._open_firewall = lambda: True
    panel._show_ready = lambda u: None
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    panel.sb_port.setValue(port)
    panel.services.set_pref("lan_recv_dir", tempfile.mkdtemp(prefix="fm_tok_"))

    restore = _tok_guard()
    try:
        # 输入框非空即启用访问密码
        panel.ed_token.setText("888888")
        panel._toggle()
        assert panel._server is not None
        assert panel._server.access_token == "888888"
        # 手机/电脑 URL 都不带 token——扫码/打开都走密码登录页
        url = panel._display_url(panel._server)
        assert "token=" not in url
        assert "888888" not in url
        pc = panel._display_url_pc(panel._server)
        assert "token=" not in pc
        assert "side=pc" in pc
        # 服务端确实拦截：未授权 401，带正确 token 200
        c = TestClient(panel._server._app)
        assert c.get("/chat/history").status_code == 401
        assert c.get("/chat/history?token=888888").status_code == 200
        # 走登录页能进入
        assert c.get("/chat").status_code == 200
        assert "访问密码" in c.get("/chat").text
    finally:
        panel._stop_server()
        panel.deleteLater()
        app.processEvents()
        restore()


def test_panel_token_live_toggle(monkeypatch):
    """服务运行中改 ed_token（清空/填写）→ 实时生效：服务端 token 更新、URL/二维码立即刷新。"""
    from PySide6.QtWidgets import QApplication
    from gui_qt.components.theme_manager import ThemeManager
    from gui_qt.panels.lan_transfer_panel import LanTransferPanelPage
    from gui_qt.services import QtServices
    from gui_qt.task_manager import TaskManager

    app = QApplication.instance() or QApplication([])
    services = QtServices()
    services.task_manager = TaskManager(services)
    services.theme_mgr = ThemeManager(services)

    class _Window:
        pass

    panel = LanTransferPanelPage(_Window(), services)
    app.processEvents()
    panel._open_firewall = lambda: True
    panel._show_ready = lambda u: None
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    panel.sb_port.setValue(port)
    panel.services.set_pref("lan_recv_dir", tempfile.mkdtemp(prefix="fm_live_"))

    restore = _tok_guard()
    try:
        # 无密码启动
        panel.ed_token.setText("")
        panel._toggle()
        assert panel._server is not None
        assert panel._server.access_token is None

        # 运行中设置密码 → 服务端拦截生效；URL/QR 不带 token
        panel.ed_token.setText("666666")
        panel._on_token_changed()
        assert panel._server.access_token == "666666"
        assert "token=" not in (panel._current_url or "")  # QR 不携带 token
        c = TestClient(panel._server._app)
        assert c.get("/chat/history").status_code == 401
        assert c.get("/chat/history?token=666666").status_code == 200

        # 运行中清空密码 → 立即解除
        panel.ed_token.setText("")
        panel._on_token_changed()
        assert panel._server.access_token is None
        assert c.get("/chat/history").status_code == 200
    finally:
        panel._stop_server()
        panel.deleteLater()
        app.processEvents()
        restore()


def test_display_url_pc_separator():
    """手机/电脑都要输密码策略：
    _display_url（QR/展示）与 _display_url_pc 都**不带 token**——扫码/打开
    一律进 /chat/login 密码页。历史 bug：早期拼 ?token=X?side=pc 双问号已堵死。"""
    from gui_qt.panels.lan_transfer_panel import LanTransferPanelPage

    class _Srv:
        port = 8000
        url = "http://192.168.1.5:8000/"
        access_token = None

    panel = LanTransferPanelPage.__new__(LanTransferPanelPage)
    panel._selected_ip = lambda: "192.168.1.5"

    srv = _Srv()
    # 开密码：两边都不带 token
    srv.access_token = "123456"
    base = panel._display_url(srv)
    assert base == "http://192.168.1.5:8000/chat"
    assert "token=" not in base
    pc = panel._display_url_pc(srv)
    assert pc == "http://192.168.1.5:8000/chat?side=pc"
    assert "token=" not in pc
    assert pc.count("?") == 1

    # 关密码：同样不带 token
    srv.access_token = None
    assert panel._display_url(srv) == "http://192.168.1.5:8000/chat"
    assert panel._display_url_pc(srv) == "http://192.168.1.5:8000/chat?side=pc"


def test_chat_theme_two_state_no_auto():
    """主题切换已移除「跟随系统」：只剩 浅/深 两态，无 auto 分支
    （电脑版不再有跟随系统状态）。"""
    from core import lan_chat_page as lcp
    h = lcp._CHAT_HTML
    assert "btnTheme" in h and "data-theme" in h
    assert "theme==='dark'?'light':'dark'" in h
    # 不应残留 auto/跟随系统 分支
    assert "theme==='auto'" not in h
    assert "||'auto'" not in h
    assert "removeAttribute('data-theme')" not in h
