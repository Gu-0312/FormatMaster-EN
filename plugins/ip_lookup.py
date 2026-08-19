"""插件：IP 地址查询（本机 / 公网 / 手动域名或 IP，后台线程不卡界面）。"""

import json
from plugins._i18n import t
import socket
import threading
import urllib.request

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLineEdit, QPlainTextEdit,
                               QVBoxLayout, QWidget)
from qfluentwidgets import PrimaryPushButton

PLUGIN_INFO = {
    "name": "IP 地址查询",
    "description": "本机 / 公网 IP，域名解析与反查（不卡界面）",
    "version": "1.1.0",
}

_PUBLIC_APIS = [
    "https://api.ipify.org?format=json",
    "https://ipinfo.io/json",
]


def local_ips():
    """本机局域网 IPv4 列表（去重）。"""
    ips = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip not in ips:
            ips.insert(0, ip)
    except OSError:
        pass
    return ips or ["127.0.0.1"]


def public_ip():
    """公网 IPv4，失败返回 None。"""
    for url in _PUBLIC_APIS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
            with urllib.request.urlopen(req, timeout=6) as r:
                data = json.loads(r.read().decode("utf-8"))
            ip = data.get("ip")
            if ip:
                return ip
        except Exception:  # noqa: BLE001
            continue
    return None


def _is_ip(text):
    try:
        socket.inet_aton(text)
        return True
    except OSError:
        return False


def resolve_host(query):
    """域名 → IP 列表；IP → 反查域名。返回展示文本。"""
    query = query.strip()
    if not query:
        return t("请输入域名或 IP 地址")
    socket.setdefaulttimeout(5)   # DNS 不无限等待
    try:
        if _is_ip(query):
            try:
                host = socket.gethostbyaddr(query)[0]
                return f"{query} → {host}"
            except OSError:
                return f"{query}（无反查记录）"
        infos = socket.getaddrinfo(query, None, socket.AF_INET)
        ips = sorted({i[4][0] for i in infos})
        if not ips:
            return f"{query}：无解析结果"
        return f"{query} →\n" + "\n".join(f"  {ip}" for ip in ips)
    except Exception as e:  # noqa: BLE001
        return t("解析失败：{e}").format(e=e)


class _IpWorker(QObject):
    """后台查询（公网 / 手动解析），结果经信号回主线程。"""

    sig_done = Signal(object)   # 结果文本

    def __init__(self, kind, query="", parent=None):
        super().__init__(parent)
        self._kind = kind
        self._query = query

    def run(self):
        if self._kind == "public":
            ip = public_ip()
            text = (t("公网 IP：{ip}").format(ip=ip) if ip
                    else t("查询失败：无法访问公网（检查网络连接）"))
        else:
            text = resolve_host(self._query)
        self.sig_done.emit(text)


class IpLookupPanel(QWidget):
    """IP 查询面板（本机同步，公网/手动查询后台线程）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        row = QHBoxLayout()
        row.setSpacing(8)
        btn_local = PrimaryPushButton(t("本机 IP"))
        btn_local.clicked.connect(self._local)
        row.addWidget(btn_local)
        self.btn_public = PrimaryPushButton(t("查询公网 IP"))
        self.btn_public.clicked.connect(self._public)
        row.addWidget(self.btn_public)
        row.addStretch(1)
        v.addLayout(row)

        q_row = QHBoxLayout()
        q_row.setSpacing(8)
        self.ed_query = QLineEdit()
        self.ed_query.setPlaceholderText(t("输入域名（如 example.com）或 IP 地址查询…"))
        self.ed_query.returnPressed.connect(self._lookup)
        q_row.addWidget(self.ed_query, 1)
        self.btn_lookup = PrimaryPushButton(t("查询"))
        self.btn_lookup.clicked.connect(self._lookup)
        q_row.addWidget(self.btn_lookup)
        v.addLayout(q_row)

        self.ed_out = QPlainTextEdit()
        self.ed_out.setReadOnly(True)
        v.addWidget(self.ed_out, 1)
        self._worker = None
        self._busy = False
        self._apply_theme()
        from gui_qt.components import design_system as ds
        ds.bind_theme(self, self._apply_theme)
        self._local()

    def _apply_theme(self):
        from gui_qt.components import design_system as ds
        t = ds.tokens()
        self.setStyleSheet(
            f"QLineEdit, QPlainTextEdit {{ background: {t['card_bg']};"
            f" color: {t['ink']}; border: 1px solid {t['border']};"
            f" border-radius: 6px; padding: 4px; font-size: 13px; }}")

    def _local(self):
        ips = local_ips()
        self.ed_out.setPlainText("本机局域网 IP：\n" + "\n".join(f"  {ip}"
                                                                for ip in ips))

    def _spawn(self, kind, query=""):
        """启动后台查询线程（防重入）。"""
        if self._busy:
            return
        self._busy = True
        self.btn_public.setEnabled(False)
        self.btn_lookup.setEnabled(False)
        self.ed_out.setPlainText(t("查询中…"))
        self._worker = _IpWorker(kind, query)
        self._worker.sig_done.connect(self._done)
        threading.Thread(target=self._worker.run, daemon=True).start()

    def _done(self, text):
        self._busy = False
        self.btn_public.setEnabled(True)
        self.btn_lookup.setEnabled(True)
        self.ed_out.setPlainText(text)

    def _public(self):
        self._spawn("public")

    def _lookup(self):
        self._spawn("lookup", self.ed_query.text())


PANEL_CLASS = IpLookupPanel


def on_load(ctx):
    pass


def on_unload():
    pass
