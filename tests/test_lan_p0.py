"""P0 增强端点测试：分片上传（断点续传+SHA校验）、Office 离线预览。

FastAPI TestClient（不启 uvicorn）；convert_fn 注入避免依赖本机 Office。
"""
import hashlib
import os
import tempfile
import time
import urllib.parse

from fastapi.testclient import TestClient

from core.lan_service import LanService


def _make_srv():
    srv = LanService(port=8788)
    recv = tempfile.mkdtemp(prefix="fm_test_recv_")
    srv.set_recv(recv, conflict="rename", classify=False)
    srv.chat_dir = tempfile.mkdtemp(prefix="fm_test_chat_")
    return srv, recv


# ── 分片上传 ──────────────────────────────────
def test_chunked_upload_happy():
    srv, _ = _make_srv()
    c = TestClient(srv._app)
    content = b"x" * (5 * 1024 * 1024 + 123)
    sha = hashlib.sha256(content).hexdigest()
    total = 3
    ch = (len(content) + total - 1) // total
    r = c.post("/chat/upload/init", json={
        "name": "big.bin", "size": len(content), "total_chunks": total,
        "sha256": sha, "side": "phone", "from": "手机"})
    assert r.status_code == 200 and r.json()["ok"] is True
    sid = r.json()["sid"]
    for i in range(total):
        blob = content[i * ch:(i + 1) * ch] if i < total - 1 else content[i * ch:]
        rr = c.post(f"/chat/upload/chunk?sid={sid}&index={i}", content=blob)
        assert rr.status_code == 200 and rr.json()["ok"] is True
    cm = c.post(f"/chat/upload/commit?sid={sid}")
    assert cm.status_code == 200 and cm.json()["ok"] is True
    dl = c.get(f"/chat/dl/{cm.json()['ids'][0]}")
    assert dl.content == content


def test_chunked_resume_skips_received():
    srv, _ = _make_srv()
    c = TestClient(srv._app)
    content = b"abcdefghij" * 1000
    sha = hashlib.sha256(content).hexdigest()
    total = 4
    ch = (len(content) + total - 1) // total
    sid = c.post("/chat/upload/init", json={
        "name": "r.bin", "size": len(content), "total_chunks": total,
        "sha256": sha, "side": "pc", "from": "电脑"}).json()["sid"]
    for i in (0, 2):
        c.post(f"/chat/upload/chunk?sid={sid}&index={i}",
               content=content[i * ch:(i + 1) * ch])
    st = c.get(f"/chat/upload/status?sid={sid}").json()
    assert set(st["received"]) == {0, 2}
    # 缺失分片 → commit 失败并指明缺失
    cm = c.post(f"/chat/upload/commit?sid={sid}")
    assert cm.status_code == 400 and cm.json()["err"] == "missing"
    for i in (1, 3):
        c.post(f"/chat/upload/chunk?sid={sid}&index={i}",
               content=content[i * ch:(i + 1) * ch])
    cm2 = c.post(f"/chat/upload/commit?sid={sid}")
    assert cm2.status_code == 200 and cm2.json()["ok"] is True
    dl = c.get(f"/chat/dl/{cm2.json()['ids'][0]}")
    assert dl.content == content


def test_chunked_sha_mismatch_rejected():
    srv, _ = _make_srv()
    c = TestClient(srv._app)
    content = b"hello world"
    total = 2
    ch = (len(content) + 1) // 2
    sid = c.post("/chat/upload/init", json={
        "name": "m.bin", "size": len(content), "total_chunks": total,
        "sha256": "deadbeef", "side": "phone"}).json()["sid"]
    c.post(f"/chat/upload/chunk?sid={sid}&index=0", content=content[:ch])
    c.post(f"/chat/upload/chunk?sid={sid}&index=1", content=content[ch:])
    cm = c.post(f"/chat/upload/commit?sid={sid}")
    assert cm.status_code == 400 and cm.json()["err"] == "sha"


def test_chunked_size_mismatch_rejected():
    """声明大小与合并后不符（截断/丢分片）→ commit 400，即使无 sha 也拦截。"""
    srv, _ = _make_srv()
    c = TestClient(srv._app)
    content = b"0123456789abcdef"
    total = 2
    ch = (len(content) + 1) // 2
    sid = c.post("/chat/upload/init", json={
        "name": "s.bin", "size": 99999,   # 谎报大小
        "total_chunks": total, "sha256": "", "side": "phone"}).json()["sid"]
    c.post(f"/chat/upload/chunk?sid={sid}&index=0", content=content[:ch])
    c.post(f"/chat/upload/chunk?sid={sid}&index=1", content=content[ch:])
    cm = c.post(f"/chat/upload/commit?sid={sid}")
    assert cm.status_code == 400 and cm.json()["err"] == "size"


def test_chunked_unknown_session_404():
    srv, _ = _make_srv()
    c = TestClient(srv._app)
    assert c.post("/chat/upload/commit?sid=missing",
                  json={}).status_code == 404


# ── Office 离线预览 ───────────────────────────
def test_office_preview_manager_states():
    from core import office_preview as op
    d = tempfile.mkdtemp()
    src = os.path.join(d, "a.docx")
    open(src, "wb").write(b"PK")
    calls = {"n": 0}

    def conv(s, out):
        open(out, "wb").write(b"%PDF-1.4")
        calls["n"] += 1
        return True, "内置引擎"

    mgr = op.OfficePreviewManager(d, convert_fn=conv)
    st, pdf, engine = mgr.request(src)
    assert st in ("pending", "ready")
    for _ in range(60):
        st, pdf, engine = mgr.request(src)
        if st == "ready":
            break
        time.sleep(0.05)
    assert st == "ready" and pdf and os.path.isfile(pdf)
    assert engine == "内置引擎"
    mgr.request(src)  # 已就绪不应重复转换
    assert calls["n"] == 1


def test_office_preview_endpoint_serves_pdf():
    srv, _ = _make_srv()
    sd = tempfile.mkdtemp()
    srv.share_dir = sd
    open(os.path.join(sd, "doc.docx"), "wb").write(b"PK")
    from core import office_preview as _op
    srv._office_preview = _op.OfficePreviewManager(
        sd, convert_fn=lambda s, out: (open(out, "wb").write(b"%PDF-1.4") or True, "内置"))
    c = TestClient(srv._app)
    r = None
    for _ in range(60):
        r = c.get("/office-pdf?file=" + urllib.parse.quote("doc.docx"))
        if r.headers.get("content-type", "").startswith("application/pdf"):
            break
        time.sleep(0.05)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content[:5] == b"%PDF-"


def test_chat_office_preview_serves_pdf():
    """聊天里 Office 文件 → /chat/preview 服务端转 PDF（离线）。"""
    srv, _ = _make_srv()
    c = TestClient(srv._app)
    mid = c.post("/chat/file?side=pc",
                 files={"file": ("报告.docx", b"PK")}).json()["ids"][0]
    from core import office_preview as _op
    srv._office_chat = _op.OfficePreviewManager(
        srv.chat_dir, convert_fn=lambda s, out: (
            open(out, "wb").write(b"%PDF-1.4") or True, "内置"))
    r = None
    for _ in range(60):
        r = c.get(f"/chat/preview/{mid}")
        if r.headers.get("content-type", "").startswith("application/pdf"):
            break
        time.sleep(0.05)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content[:5] == b"%PDF-"


def test_chat_office_preview_nonoffice_404():
    """不可预览格式（zip）→ 404；文本类（txt）现可预览 → 200。"""
    srv, _ = _make_srv()
    c = TestClient(srv._app)
    mid = c.post("/chat/file?side=pc",
                 files={"file": ("a.zip", b"PK")}).json()["ids"][0]
    assert c.get(f"/chat/preview/{mid}").status_code == 404
    mid2 = c.post("/chat/file?side=pc",
                  files={"file": ("note.txt", b"hello")}).json()["ids"][0]
    assert c.get(f"/chat/preview/{mid2}").status_code == 200


def test_chat_office_preview_unknown_404():
    srv, _ = _make_srv()
    c = TestClient(srv._app)
    assert c.get("/chat/preview/99999").status_code == 404


def test_chat_office_preview_outside_path_403():
    """local_path 越出 chat_dir/recv_dir → 拒绝。"""
    srv, _ = _make_srv()
    c = TestClient(srv._app)
    outside = tempfile.mkdtemp()
    m = srv.chat.add("pc", "file", name="x.docx",
                     local_path=os.path.join(outside, "x.docx"))
    assert c.get(f"/chat/preview/{m['id']}").status_code == 403


def test_office_preview_missing_404():
    srv, _ = _make_srv()
    srv.share_dir = tempfile.mkdtemp()
    c = TestClient(srv._app)
    assert c.get("/office-pdf?file=" + urllib.parse.quote("x.docx")
                ).status_code == 404


def test_office_preview_path_traversal_403():
    srv, _ = _make_srv()
    srv.share_dir = tempfile.mkdtemp()
    c = TestClient(srv._app)
    bad = urllib.parse.quote("../secret.docx")
    assert c.get("/office-pdf?file=" + bad).status_code == 403
