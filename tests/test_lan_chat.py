"""聊天式局域网互传端点测试（FastAPI TestClient，无真实网络/端口绑定）。"""

import io
import os
import tempfile
import zipfile

from fastapi.testclient import TestClient

from core.lan_service import LanService


def _make_srv():
    """构造一个不启动 uvicorn 线程的 LanService，仅用于端点测试。"""
    srv = LanService(port=8799)
    recv = tempfile.mkdtemp(prefix="fm_test_recv_")
    srv.set_recv(recv, conflict="rename", classify=False)
    srv.chat_dir = tempfile.mkdtemp(prefix="fm_test_chat_")
    return srv, recv


def test_chat_page_loads():
    srv, _ = _make_srv()
    c = TestClient(srv._app)
    r = c.get("/chat")
    assert r.status_code == 200
    assert "格式大师" in r.text
    assert "chat/dl/" in r.text  # 含按 id 下载的脚本


def test_home_nav_page():
    """根路径渲染导航页：聚合聊天互传与文件分享两个入口（不再 302 跳转）。"""
    srv, _ = _make_srv()
    c = TestClient(srv._app)
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 200
    assert "聊天互传" in r.text          # 聊天式互传入口
    assert "文件分享" in r.text          # 旧分享入口（test_smoke 依赖）
    assert '/chat' in r.text             # 指向聊天页
    assert '/share/' in r.text           # 指向分享页


def test_message_and_history():
    srv, _ = _make_srv()
    c = TestClient(srv._app)
    r = c.post("/chat/message", json={"text": "你好", "side": "pc", "from": "电脑"})
    assert r.status_code == 200 and r.json()["ok"] is True
    h = c.get("/chat/history").json()
    assert len(h) == 1
    assert h[0]["type"] == "text" and h[0]["text"] == "你好"
    assert h[0]["side"] == "pc"
    # local_path 不泄露给客户端
    assert "local_path" not in h[0]


def test_history_incremental():
    srv, _ = _make_srv()
    c = TestClient(srv._app)
    c.post("/chat/message", json={"text": "a", "side": "phone"})
    c.post("/chat/message", json={"text": "b", "side": "pc"})
    h = c.get("/chat/history?after=1").json()
    assert [m["text"] for m in h] == ["b"]


def test_file_phone_to_pc_saved_and_downloadable():
    srv, recv = _make_srv()
    c = TestClient(srv._app)
    r = c.post("/chat/file?side=phone", files={"file": ("hello.txt", b"world")})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] and data["count"] == 1
    mid = data["ids"][0]
    dl = c.get(f"/chat/dl/{mid}")
    assert dl.status_code == 200
    assert dl.content == b"world"
    saved = [f for f in os.listdir(recv) if not f.startswith(".")]
    assert any(f == "hello.txt" for f in saved)


def test_file_pc_to_phone_lands_in_chat_dir():
    srv, _ = _make_srv()
    c = TestClient(srv._app)
    r = c.post("/chat/file?side=pc", files={"file": ("doc.pdf", b"%PDF-1.4")})
    assert r.status_code == 200
    mid = r.json()["ids"][0]
    dl = c.get(f"/chat/dl/{mid}")
    assert dl.status_code == 200 and dl.content == b"%PDF-1.4"
    files = [f for f in os.listdir(srv.chat_dir) if not f.startswith(".")]
    assert any(f == "doc.pdf" for f in files)


def test_bundle_zips_multiple_files():
    srv, _ = _make_srv()
    c = TestClient(srv._app)
    r = c.post("/chat/file?side=pc&bundle=1",
               files=[("file", ("a.txt", b"aa")), ("file", ("b.txt", b"bb"))])
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1  # 多文件合并为一条
    mid = data["ids"][0]
    dl = c.get(f"/chat/dl/{mid}")
    assert dl.status_code == 200
    assert dl.content[:2] == b"PK"  # zip 签名
    with zipfile.ZipFile(io.BytesIO(dl.content)) as zf:
        names = zf.namelist()
    assert "a.txt" in names and "b.txt" in names


def test_dl_unknown_id_404():
    srv, _ = _make_srv()
    c = TestClient(srv._app)
    assert c.get("/chat/dl/99999").status_code == 404
