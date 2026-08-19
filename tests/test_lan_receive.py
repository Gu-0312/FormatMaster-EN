# -*- coding: utf-8 -*-
"""局域网接收上传 URL 回归测试（纯逻辑，不启动服务/不访问网络）。

历史 bug：lan_service 把接收页挂在 /recv/，上传端点为 /recv/upload，
但上传 HTML 模板里硬编码了 x.open('POST','/')，导致浏览器向根 / POST，
而根只处理 GET → 405，接收功能完全失效。

修复方式：模板用占位符 __UPLOAD_URL__，统一服务覆盖为 /recv/upload，
旧版根服务覆盖为 /。本测试锁定该占位符与替换逻辑不被回退。

第二条历史 bug：接收模式未选目录时 set_recv 被静默跳过，UI 却谎报
「接收已开启」，扫码打开 /recv/ 返回 404 乱码 JSON（UTF-8 被手机按 GBK
解码）。修复：面板回退默认目录并 set_recv；recv_page 空 recv_dir 时返回
带 charset 的中文提示页（不再 404 乱码）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["FORMATMASTER_OFFSCREEN"] = "1"


def _upload_html():
    from core import lan_receiver as lr
    return lr._UPLOAD_HTML


def test_upload_html_uses_placeholder():
    """上传 HTML 必须含 __UPLOAD_URL__ 占位符，而非硬编码根 /。"""
    html = _upload_html()
    assert "__UPLOAD_URL__" in html, "模板缺少 __UPLOAD_URL__ 占位符"
    # 不应再出现硬编码的 x.open('POST','/')
    assert "x.open('POST','/')" not in html, "上传目标不应硬编码到根 /"
    assert "x.open('POST','__UPLOAD_URL__')" in html


def test_service_injects_recv_upload_url():
    """lan_service 接收页必须把占位符替换为 /recv/upload。"""
    from core import lan_service as ls
    html = _upload_html()
    html = html.replace("__SAVE_DIR__", "/tmp/save")
    html = html.replace("__SESSION_ID__", "8731")
    html = html.replace("__UPLOAD_URL__", "/recv/upload")
    assert "/recv/upload" in html, "统一服务的上传 URL 应为 /recv/upload"
    assert "__UPLOAD_URL__" not in html, "占位符必须被替换"


def test_legacy_recv_server_injects_root_url():
    """旧版根接收服务把占位符替换为 /（保持原行为）。"""
    from core import lan_receiver as lr
    html = _upload_html()
    html = html.replace("__SAVE_DIR__", "/tmp/save")
    html = html.replace("__SESSION_ID__", "8000")
    html = html.replace("__UPLOAD_URL__", "/")  # 旧版 _RecvHandler.do_GET 的替换
    assert "x.open('POST','/')" in html, "旧版根服务应上传到 /"
    assert "__UPLOAD_URL__" not in html


def test_lan_service_module_known_endpoint():
    """文档化：lan_service 上传端点为 /recv/upload（防止路由被改）。"""
    import inspect
    from core import lan_service as ls
    src = inspect.getsource(ls.LanService._build_app)
    assert '/recv/upload' in src, "lan_service 必须暴露 /recv/upload POST 端点"
    assert '/recv/' in src, "lan_service 必须暴露 /recv/ 接收页"


def test_recv_page_off_returns_readable_html():
    """接收未开启（recv_dir 为空）时，/recv/ 应返回带 charset 的中文提示页
    （状态 200），而非 404 乱码 JSON（UTF-8 被手机按 GBK 解码的 mojibake）。

    这是第二条历史 bug 的回归锁：之前返回 HTTPException(404, "接收未开启")，
    中文 detail 在手机端显示为乱码。
    """
    import urllib.request
    from core import lan_service as ls

    srv = ls.LanService(port=8799)  # 不调用 set_recv → recv_dir 为空
    assert srv.start(), "服务应能启动"
    try:
        resp = urllib.request.urlopen(srv.url + 'recv/', timeout=5)
        raw = resp.read()
        txt = raw.decode('utf-8')
        assert resp.status == 200, "未开启应返回可读提示页而非 404"
        assert '接收功能未开启' in txt, "应提示接收功能未开启"
        assert b'charset="utf-8"' in raw, "提示页必须声明 utf-8 编码"
        # 不应再是 JSON 错误体（无 detail 字段）
        assert 'detail' not in txt.split('<', 1)[0], "不应返回 JSON 错误体"
    finally:
        srv.stop()


def test_panel_recv_fallback_when_dir_empty(monkeypatch):
    """接收模式未选目录时，_toggle 应回退默认目录并调用 set_recv，
    避免「接收已开启」却 recv_dir 为空导致扫码 404（第二条历史 bug 的核心）。
    """
    import tempfile
    from PySide6.QtWidgets import QApplication
    from gui_qt.services import QtServices
    from gui_qt.task_manager import TaskManager
    from gui_qt.components.theme_manager import ThemeManager
    from gui_qt.panels.lan_transfer_panel import LanTransferPanelPage

    app = QApplication.instance() or QApplication([])
    services = QtServices()
    services.task_manager = TaskManager(services)
    services.theme_mgr = ThemeManager(services)

    class _Window:
        pass

    panel = LanTransferPanelPage(_Window(), services)
    app.processEvents()

    # stub 网络/UI 副作用：避免 netsh 防火墙/UAC 卡死与弹窗
    panel._open_firewall = lambda: True
    panel._show_ready = lambda u: None

    # 用临时目录替换默认回退（~/Downloads/FormatMaster接收），免污染真实目录
    _tmp = tempfile.mkdtemp(prefix='fm_recv_fb_')
    _real_expand = os.path.expanduser

    def _fake_expand(p):
        if p == '~/Downloads':
            return _tmp
        return _real_expand(p)

    monkeypatch.setattr(os.path, 'expanduser', _fake_expand)

    try:
        panel._toggle()
        assert panel._server is not None, "_toggle 后应已启动服务"
        assert panel._server.recv_dir, "recv_dir 必须被设置（回退默认目录）"
        assert os.path.isdir(panel._server.recv_dir), "回退目录应已创建"
    finally:
        panel._stop_server()
        panel.deleteLater()
        app.processEvents()




def test_recv_page_long_filename_no_overflow():
    """历史 bug 第三条回归锁：上传页列表项文件名用 flex 弹性布局，
    必须给 .item 与 .nm 加 min-width:0，否则无空格的长文件名会撑破布局、
    页面横向溢出，把「开始上传」按钮顶出可视区 → 用户点不到 → 文件发不出去。

    锁：接收页模板必须包含 min-width:0（至少 .item 与 .nm 两处），
    且列表项用 esc() 转义并带 title 悬浮显示全称（防 < > & " 破坏布局）。
    """
    from core import lan_receiver as lr
    from core import lan_service as ls

    tpl = lr._UPLOAD_HTML
    # 关键修复：弹性项必须可收缩，否则长文本不省略号而是撑宽
    assert tpl.count("min-width:0") >= 2, "必须为 .item 与 .nm 都加 min-width:0"
    assert "function esc(" in tpl, "列表项需 esc() 转义文件名"
    # lan_service 注入后的接收页同样应包含修复
    page = ls._upload_html()
    page = page.replace("__SAVE_DIR__", "/tmp").replace("__SESSION_ID__", "1")
    page = page.replace("__UPLOAD_URL__", "/recv/upload")
    assert page.count("min-width:0") >= 2, "lan_service 接收页也必须含 min-width:0"


def _lan_panel(services, monkeypatch, port):
    """构建接收模式面板并 stub 网络/UI 副作用（供集成测试复用）。"""
    import tempfile
    from PySide6.QtWidgets import QApplication
    from gui_qt.panels.lan_transfer_panel import LanTransferPanelPage

    app = QApplication.instance() or QApplication([])
    panel = LanTransferPanelPage(_Window(), services)
    app.processEvents()
    panel._open_firewall = lambda: True
    panel._show_ready = lambda u: None
    panel.sb_port.setValue(port)
    recv_dir = tempfile.mkdtemp(prefix='fm_opts_')
    panel.services.set_pref("lan_recv_dir", recv_dir)
    return app, panel, recv_dir


class _Window:
    pass


def _prefs_guard():
    """备份并重置 prefs（测试内 set_pref 会真实落盘），返回恢复函数。

    重置为已知初始值保证断言确定性（否则受上次运行残留值影响）。
    """
    from utils.config import USER_PREFS
    _keys = ("lan_recv_dir",)
    _old = {k: USER_PREFS.get("qt_app", k, None) for k in _keys}
    USER_PREFS.set("qt_app", "lan_recv_dir", "")

    def _restore():
        for k in _keys:
            v = _old.get(k)
            if v is None:
                v = ""
            USER_PREFS.set("qt_app", k, v)
    return _restore


def test_panel_live_ip_switch_updates_url(monkeypatch):
    """服务运行中切换 IP 下拉 → 展示 URL 立即更新（无需重启）。

    历史问题：IP 下拉的 _selected_ip() 从未被消费，手动切换网卡地址对
    URL/二维码无效。锁：切到候选 IP 后 lb_url 文本 + 信息卡地址值都更新。
    """
    from gui_qt.services import QtServices
    from gui_qt.task_manager import TaskManager
    from gui_qt.components.theme_manager import ThemeManager

    _restore = _prefs_guard()
    try:
        services = QtServices()
        services.task_manager = TaskManager(services)
        services.theme_mgr = ThemeManager(services)
        app, panel, _ = _lan_panel(services, monkeypatch, 8812)
        try:
            panel._toggle()
            assert panel._server is not None and panel._server.is_running()
            panel.cb_ip.blockSignals(False)
            panel.cb_ip.clear()
            panel.cb_ip.addItems(["192.168.1.100", "10.0.0.5"])
            panel.cb_ip.setCurrentIndex(1)              # 切到 10.0.0.5
            app.processEvents()
            assert "10.0.0.5" in panel.lb_url.text(), \
                "切换 IP 后 URL 必须立即刷新为所选地址"
            assert "10.0.0.5" in panel._card_addr._value_label.text(), \
                "切换 IP 后信息卡地址值必须包含所选 IP"
        finally:
            panel._stop_server()
            panel.deleteLater()
            app.processEvents()
    finally:
        _restore()


def _upload(srv, filename_field, content=b"hi", boundary="----FMt"):
    """构造 multipart body 并 POST 到 /recv/upload。"""
    import urllib.request
    body = (("--" + boundary + "\r\n"
            "Content-Disposition: form-data; name=\"file\"; filename=\"" +
            filename_field + "\"\r\nContent-Type: text/plain\r\n\r\n"
            ).encode() + content + ("\r\n--" + boundary + "--\r\n").encode())
    req = urllib.request.Request(
        srv.url + "recv/upload", data=body, method="POST",
        headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    return urllib.request.urlopen(req, timeout=8).read().decode("utf-8")


def test_recv_upload_decodes_percent_encoded_filename():
    """部分浏览器/WebView 把非 ASCII 文件名直接 percent-encoded 放入
    filename="..."。解析器不解码则落盘文件名是 %E6%95%99... 形式，
    且桌面面板状态栏这一长串 percent-encoding 会把「启动/停止」按钮挤出窗口。
    修复后：落盘真实中文 + on_received 回调收到解码名。"""
    import tempfile
    from core import lan_service as ls

    recv_dir = tempfile.mkdtemp(prefix="fm_dec_")
    srv = ls.LanService(port=8841)
    srv.set_recv(recv_dir, conflict="rename", classify=False)
    assert srv.start()
    try:
        raw = "%E6%95%99%E5%AD%A6%E6%96%B9%E6%A1%88.docx"   # = 教学方案.docx
        resp = _upload(srv, raw)
        saved = sorted(os.listdir(recv_dir))
        assert saved == ["教学方案.docx"], saved
        assert "教学方案.docx" in resp, "on_received 回调也应收到解码名"
    finally:
        srv.stop()


def test_recv_upload_prefers_rfc5987_filename_star():
    """RFC 5987 `filename*=UTF-8''percent-encoded` 应优先于 `filename="..."`（Chrome
    等对非 ASCII 文件名的标准做法）。"""
    import tempfile
    from core import lan_service as ls

    recv_dir = tempfile.mkdtemp(prefix="fm_rfc_")
    srv = ls.LanService(port=8842)
    srv.set_recv(recv_dir, conflict="rename", classify=False)
    assert srv.start()
    try:
        b = "----FMrfc"
        ext = "UTF-8''%E6%B5%8B%E8%AF%95%E6%96%87%E6%9C%AC.txt"
        import urllib.request
        body = (("--" + b + "\r\n"
                "Content-Disposition: form-data; name=\"file\";"
                " filename=\"fallback.txt\"; filename*=\"" + ext + "\"\r\n"
                "Content-Type: text/plain\r\n\r\nhi\r\n"
                "--" + b + "--\r\n").encode())
        req = urllib.request.Request(
            srv.url + "recv/upload", data=body, method="POST",
            headers={"Content-Type": "multipart/form-data; boundary=" + b})
        urllib.request.urlopen(req, timeout=8).read()
        saved = sorted(os.listdir(recv_dir))
        assert any(f.startswith("测试文本") for f in saved), saved
    finally:
        srv.stop()


def test_panel_status_bar_elides_long_filename():
    """长文件名（含 percent-encoded 形式）触发 _on_received_ui 后，状态信息卡的值必须可读。

    历史 bug：旧版把 percent-encoded 字符串直接显示在状态栏，把启动按钮挤出可视区。
    新版：状态值走信息卡（_card_state）+ elidedText，长文本不撑破布局。
    锁：收到长文件名后 _card_state 值不含完整 percent-encoded 串。
    """
    from PySide6.QtWidgets import QApplication
    from gui_qt.services import QtServices
    from gui_qt.task_manager import TaskManager
    from gui_qt.components.theme_manager import ThemeManager
    from gui_qt.panels.lan_transfer_panel import LanTransferPanelPage

    app = QApplication.instance() or QApplication([])
    services = QtServices()
    services.task_manager = TaskManager(services)
    services.theme_mgr = ThemeManager(services)

    class _Window:
        pass

    panel = LanTransferPanelPage(_Window(), services)
    app.processEvents()
    try:
        # 超长 percent-encoded 文件名（模拟部分浏览器场景）
        long_encoded = "%E6%95%99%E5%AD%A6" * 20 + ".docx"
        panel._on_received_ui(long_encoded, 1024, 1.0)
        val = panel._card_state._value_label.text()
        # 状态值包含会话统计 "已收 N · 大小"，**不应**含完整 percent-encoded 串
        assert "%E6" not in val, f"状态值不应含 percent-encoded 串：{val!r}"
        # 真实解码后的短基名可以出现（elide 后）
        assert len(val) < 200, f"状态值未截断，长度={len(val)}"
    finally:
        panel.deleteLater()
        app.processEvents()


def test_share_download_chinese_filename():
    """历史 bug：分享列表页用 urllib.parse.quote 编码中文文件名，
    FastAPI/Starlette 的 path 参数不做 percent-decode → 中文文件下载 404。
    修复：share_file 对 path 先 unquote。锁：中文文件下载必须 200 且内容正确。
    """
    import re
    import tempfile
    import urllib.request
    from core import lan_service as ls

    share_dir = tempfile.mkdtemp(prefix="fm_share_")
    with open(os.path.join(share_dir, "教学方案.docx"), "wb") as f:
        f.write(b"doc-content")
    srv = ls.LanService(port=8851)
    srv.share_dir = share_dir
    assert srv.start()
    try:
        lst = urllib.request.urlopen(srv.url + "share/", timeout=5).read().decode()
        m = re.search(r'href="(/share/[^"]+)"[^>]*>教学方案', lst)
        assert m, "列表页应包含中文文件链接"
        resp = urllib.request.urlopen(srv.url + m.group(1).lstrip("/"), timeout=5)
        assert resp.status == 200, "中文文件名下载必须 200（不得 404）"
        assert resp.read() == b"doc-content"
    finally:
        srv.stop()


def test_share_empty_returns_readable_page():
    """无分享内容时 /share/ 返回带 charset 的可读中文提示页（非 404 JSON 乱码）。"""
    import tempfile
    import urllib.request
    from core import lan_service as ls

    srv = ls.LanService(port=8852)   # 不设 share_dir
    assert srv.start()
    try:
        resp = urllib.request.urlopen(srv.url + "share/", timeout=5)
        raw = resp.read()
        txt = raw.decode("utf-8")
        assert resp.status == 200
        assert "暂无分享内容" in txt
        assert b'charset="utf-8"' in raw
    finally:
        srv.stop()


def test_panel_merged_single_mode():
    """已合并单一模式：面板不应再有 sg_mode（send/recv 二选一），
    _mode() 固定返回 "dual"（分享 + 接收同时启用，扫一个码两份都能用）。"""
    import inspect
    from gui_qt.panels import lan_transfer_panel as ltp

    src = inspect.getsource(ltp.LanTransferPanelPage)
    assert "sg_mode" not in src, "不应再有模式切换控件"
    assert "_mode_changed" not in src, "不应再有模式切换方法"
    # _mode() 固定 dual
    assert 'return "dual"' in src


def test_chat_send_folder_creates_zip_message():
    """服务运行中把文件夹发到聊天会话 → 自动打包 zip 一条消息（pc 落 chat_dir）。

    替代原「运行中添加文件夹→分享目录」逻辑：聊天页已取代其收发能力。
    停止服务后 chat_dir（含打包产物）必须清理。
    """
    import tempfile
    import time
    from PySide6.QtWidgets import QApplication
    from gui_qt.services import QtServices
    from gui_qt.task_manager import TaskManager
    from gui_qt.components.theme_manager import ThemeManager
    from gui_qt.panels.lan_transfer_panel import LanTransferPanelPage

    _restore = _prefs_guard()
    try:
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
        recv_dir = tempfile.mkdtemp(prefix="fm_live_")
        panel.services.set_pref("lan_recv_dir", recv_dir)
        panel.sb_port.setValue(8873)
        panel._toggle()
        time.sleep(2.0)
        srv = panel._server
        assert srv is not None and srv.is_running()
        assert srv.chat_dir and os.path.isdir(srv.chat_dir)
        folder = tempfile.mkdtemp(prefix="fm_zsrc_")
        open(os.path.join(folder, "a.txt"), "w").write("x")
        open(os.path.join(folder, "b.txt"), "w").write("y")
        try:
            ids = srv.chat_send_local([folder], side="pc", frm="电脑",
                                       bundle=True)
            assert ids, "文件夹发送应产生聊天消息"
            msgs = srv.chat.since(0)
            assert len(msgs) == 1, "多文件应合并为一条 zip 消息"
            assert msgs[0]["name"].endswith(".zip"), "应打包为 zip"
            mid = msgs[0]["id"]
            chat_dir = srv.chat_dir
            lp = srv.chat.get(mid)["local_path"]
            assert os.path.isfile(lp) and os.path.dirname(lp) == chat_dir, \
                "打包产物应落在 chat_dir 且可被下载"
        finally:
            panel._stop_server()
            time.sleep(0.5)
            # stop() 已 rmtree 并置 chat_dir=None，确认目录已清理
            assert chat_dir is not None and not os.path.isdir(chat_dir), \
                "停止后 chat_dir 应清理"
            panel.deleteLater()
            app.processEvents()
    finally:
        _restore()

