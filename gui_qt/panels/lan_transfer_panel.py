"""lan_transfer_panel — 局域网传输面板（扫码聊天互传控制台）。

启动/停止局域网服务 + 手机扫码进聊天页实时互传。启动后展示二维码、
访问地址与连接信息。版本号不显示在面板。
"""

import os
import time
import urllib.parse

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics, QImage, QPixmap
from PySide6.QtWidgets import (QApplication, QDialog, QFrame, QHBoxLayout,
                               QLabel, QLineEdit, QVBoxLayout, QWidget)
from qfluentwidgets import (CaptionLabel, ComboBox, FluentIcon, IconWidget,
                            PrimaryPushButton, PushButton, SpinBox,
                            SubtitleLabel, ToolButton)

from gui_qt.components import toast
from gui_qt.i18n import tr
from gui_qt.panels.base_panel import BaseQtPanel

_PREF_RECV_DIR = "lan_recv_dir"           # 接收目录记忆
_PREF_TOKEN = "lan_token"                 # 访问密码（留空=不启用）


def _human_size(n):
    """字节数 → 人类可读。"""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n /= 1024


def _qr_pixmap(url, size=200):
    """URL → 二维码 QPixmap。"""
    try:
        import qrcode
        img = qrcode.make(url)
        img = img.convert("RGBA")
        data = img.tobytes("raw", "RGBA")
        qimg = QImage(data, img.width, img.height, QImage.Format_RGBA8888)
        return QPixmap.fromImage(qimg).scaled(
            size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    except Exception:  # noqa: BLE001
        return QPixmap()


class LanGuideDialog(QDialog):
    """连接引导：四种把手机连到电脑的方式 + 注意事项。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("连接引导 · 手机如何连到电脑",
                               "Connection guide"))
        from gui_qt.components import design_system as ds
        w, h = ds.screen_ratio_size(0.82, max_w=580, max_h=680)
        self.resize(w, h)
        self.setStyleSheet(_guide_qss())
        ds.bind_theme(self, _guide_qss)

        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(12)

        title = SubtitleLabel(tr("手机怎么连到电脑？", "How to connect?"))
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        v.addWidget(title)

        items = [
            ("① 同一 WiFi / 路由器",
             tr("手机连接和电脑相同的 WiFi，直接扫二维码即可。",
                "Join the same WiFi and scan the QR code.")),
            ("② 手机开热点",
             tr("没有路由器时：手机开「个人热点」，电脑 WiFi 连上它，再扫二维码。",
                "No router? Turn on phone hotspot, PC joins it.")),
            ("③ USB 网络共享（推荐）",
             tr("数据线连电脑，手机开「USB 网络共享」，电脑出现新网卡，"
                "在下方 IP 下拉选 USB 网卡地址，扫码即可。稳定且不占 WiFi。",
                "Plug USB, enable USB tethering, pick the USB IP below.")),
            ("④ 虚拟组网（异地也能连）",
             tr("电脑和手机都装 Tailscale 或 ZeroTier，用虚拟 IP 互访，"
                "不在同一网络也能传文件。",
                "Install Tailscale/ZeroTier on both, use the virtual IP.")),
        ]
        for i, (t, d) in enumerate(items):
            card = QWidget()
            cv = QVBoxLayout(card)
            cv.setContentsMargins(14, 10, 14, 10)
            cv.setSpacing(4)
            lt_ = CaptionLabel(t)
            lt_.setStyleSheet("font-size: 14px; font-weight: 600;")
            lb_ = CaptionLabel(d)
            lb_.setWordWrap(True)
            lb_.setStyleSheet("font-size: 13px; line-height: 1.6;")
            cv.addWidget(lt_)
            cv.addWidget(lb_)
            card.setObjectName(f"guideCard{i}")
            v.addWidget(card)

        tip = CaptionLabel(
            tr("💡 连不上？① 检查电脑防火墙放行 Python；② 路由器/热点是否开了"
               "「AP 隔离」（会禁止设备互访）；③ 本机有多个网卡时，在 IP 下拉里"
               "换成手机可达的那个地址。",
               "Tips: firewall, AP isolation, or pick the right IP below."))
        tip.setWordWrap(True)
        tip.setStyleSheet("font-size: 12px;")
        v.addWidget(tip)
        v.addStretch(1)


def _guide_qss():
    """引导对话框样式（浅/深主题自适应）。"""
    try:
        from qfluentwidgets import isDarkTheme
        if isDarkTheme():
            bg, card, fg, sec = "#1E2128", "#2A2F3E", "#E6E8F2", "#9AA3B8"
        else:
            bg, card, fg, sec = "#FFFFFF", "#F1F4FA", "#242424", "#64748B"
    except Exception:  # noqa: BLE001
        bg, card, fg, sec = "#FFFFFF", "#F1F4FA", "#242424", "#64748B"
    return f"""
        QDialog {{ background: {bg}; }}
        QLabel {{ color: {fg}; }}
        QWidget#guideCard0, QWidget#guideCard1,
        QWidget#guideCard2, QWidget#guideCard3 {{
            background: {card}; border-radius: 10px;
        }}
    """


class LanTransferPanelPage(BaseQtPanel):
    """局域网传输页。"""

    panel_key = "lan_transfer"

    # 自动停止信号（core 回调在工作线程 → 信号回主线程安全操作 UI）
    sig_auto_stop = Signal(str)   # "done" 全部下载完 / "idle" 空闲超时
    # 传输回调信号：core HTTP 工作线程 emit → 主线程 UI slot
    sig_received = Signal(str, int, float, str, object)   # name, size, sec, ip, renamed_from
    sig_downloaded = Signal(str, int, float, str)          # name, size, sec, ip
    sig_progress = Signal(int, int)                        # done, total

    def build(self):
        from gui_qt.components import design_system as ds
        # 内容容器：占满窗口宽度（不封顶、不居中留白），外边距随窗口缩放。
        self.inner = QWidget()
        self.inner.setObjectName("lan_inner")
        il = QVBoxLayout(self.inner)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(18)
        self._inner_lay = il        # 供 _apply_paddings 动态调间距
        self.content_layout.addWidget(self.inner, 0)
        self._current_url = None
        self._token_visible = False
        lay = il

        # ===== 1. 标题行：左标题+副标题 / 右状态徽章+启动按钮 =====
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(12)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_lbl = SubtitleLabel(tr("文件传输", "File Transfer"))
        title_lbl.setStyleSheet(
            f"font-size: 24px; font-weight: 700")
        title_box.addWidget(title_lbl)
        sub_lbl = QLabel(tr("手机与电脑之间实时互传消息与文件",
                            "Real-time message & file transfer between phone and PC"))
        sub_lbl.setStyleSheet(
            f"font-size: 13px")
        title_box.addWidget(sub_lbl)
        title_row.addLayout(title_box)
        title_row.addStretch(1)
        # 状态徽章：圆点 + 文字（运行中绿、停止灰）
        self.lb_status_badge = QLabel()
        self.lb_status_badge.setObjectName("lan_status_badge")
        self.lb_status_badge.setAlignment(Qt.AlignCenter)
        title_row.addWidget(self.lb_status_badge)
        # 启动 / 停止服务按钮
        self.btn_toggle = PrimaryPushButton(
            FluentIcon.PLAY, tr("启动服务", "Start"))
        self.btn_toggle.clicked.connect(self._toggle)
        title_row.addWidget(self.btn_toggle)
        lay.addLayout(title_row)

        # ===== 2. 配置卡：端口 + 访问密码（带眼睛切换）+ 引导图标 =====
        cfg_card = QWidget()
        cfg_card.setObjectName("lan_cfg_card")

        def _cfg_card_qss():
            return (
                f"#lan_cfg_card{{background:{ds.card_bg()};"
                f"border:1px solid {ds.border_color()};border-radius:12px;}}"
            )
        cfg_card.setStyleSheet(_cfg_card_qss())
        ds.bind_theme(cfg_card, _cfg_card_qss)
        cfg_lay = QHBoxLayout(cfg_card)
        cfg_lay.setContentsMargins(24, 16, 24, 16)
        cfg_lay.setSpacing(18)
        self._cfg_lay = cfg_lay      # 供 _apply_paddings 动态调内边距
        # 端口
        cfg_lay.addWidget(CaptionLabel(tr("端口", "Port")))
        self.sb_port = SpinBox()
        self.sb_port.setRange(1024, 65535)
        self.sb_port.setValue(8000)
        self.sb_port.setFixedWidth(110)
        cfg_lay.addWidget(self.sb_port)
        port_hint = CaptionLabel("1 ~ 65535")
        port_hint.setStyleSheet(f"; font-size: 12px;")
        cfg_lay.addWidget(port_hint)
        cfg_lay.addWidget(self._vdiv())
        # 访问密码（可选）：非空即启用，不再用开关
        cfg_lay.addWidget(CaptionLabel(
            tr("访问密码（可选）", "Access password (optional)")))
        self.ed_token = QLineEdit()
        self.ed_token.setPlaceholderText(
            tr("不输入默认为空（无访问密码）",
               "Leave empty for no password"))
        self.ed_token.setMaxLength(16)
        self.ed_token.setEchoMode(QLineEdit.Password)
        self.ed_token.setFixedWidth(200)
        cfg_lay.addWidget(self.ed_token)
        self.btn_eye = ToolButton(FluentIcon.VIEW)
        self.btn_eye.setCheckable(True)
        self.btn_eye.setToolTip(
            tr("显示/隐藏密码", "Show/hide password"))
        self.btn_eye.toggled.connect(self._toggle_token_echo)
        cfg_lay.addWidget(self.btn_eye)
        cfg_lay.addStretch(1)
        # 连接引导小图标
        self.btn_guide = ToolButton(FluentIcon.INFO)
        self.btn_guide.setToolTip(
            tr("连接引导：如何让手机连到电脑", "Connection guide"))
        self.btn_guide.clicked.connect(self._open_guide)
        cfg_lay.addWidget(self.btn_guide)
        lay.addWidget(cfg_card)

        # ===== 3. 二维码卡（启动后显示）：QR + 标题+副标题+URL+按钮 =====
        self.url_wrap = QWidget()
        self.url_wrap.setObjectName("lan_url_card")

        def _url_wrap_qss():
            return (
                f"#lan_url_card{{background:{ds.card_bg()};"
                f"border:1px solid {ds.border_color()};border-radius:12px;}}"
            )
        self.url_wrap.setStyleSheet(_url_wrap_qss())
        ds.bind_theme(self.url_wrap, _url_wrap_qss)
        self.url_h = QHBoxLayout(self.url_wrap)
        self.url_h.setContentsMargins(32, 28, 32, 28)
        self.url_h.setSpacing(36)
        self._url_lay = self.url_h    # 供 _apply_paddings 动态调内边距
        # 左侧 QR 卡片
        self.qr_card = QWidget()
        self.qr_card.setObjectName("lan_qr_card")
        self.qr_card.setStyleSheet(
            f"#lan_qr_card{{background:#FFFFFF;"
            f"border:1px solid {ds.border_color()};border-radius:8px;}}")
        qcv = QVBoxLayout(self.qr_card)
        qcv.setContentsMargins(16, 16, 16, 16)
        qcv.setSpacing(0)
        self.lb_qr = QLabel()
        self.lb_qr.setAlignment(Qt.AlignCenter)
        self.lb_qr.setFixedSize(200, 200)
        qcv.addWidget(self.lb_qr)
        self.url_h.addWidget(self.qr_card, 0, Qt.AlignTop)
        # 右侧文字 + URL + 按钮
        self.url_right = QWidget()
        rv = QVBoxLayout(self.url_right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(8)
        qr_title = QLabel(tr("手机扫码 进入聊天页面", "Scan to enter chat"))
        qr_title.setStyleSheet(
            f"font-size: 18px; font-weight: 600")
        rv.addWidget(qr_title)
        qr_sub = QLabel(tr("在手机浏览器中打开聊天页面，即可与电脑互传消息与文件",
                           "Open the chat in your phone browser to transfer with PC"))
        qr_sub.setWordWrap(True)
        qr_sub.setStyleSheet(
            f"font-size: 13px")
        rv.addWidget(qr_sub)
        rv.addSpacing(6)
        # URL 行：地球图标 + URL + 复制
        url_row = QHBoxLayout()
        url_row.setSpacing(8)
        url_box = QWidget()
        url_box.setObjectName("lan_url_box")
        url_box.setStyleSheet(
            "#lan_url_box{background:rgba(16,185,129,0.10);"
            "border-radius:8px;}")
        ub_lay = QHBoxLayout(url_box)
        ub_lay.setContentsMargins(16, 12, 16, 12)
        ub_lay.setSpacing(10)
        gl = QLabel("🌐")
        gl.setStyleSheet("font-size: 16px; background: transparent;")
        ub_lay.addWidget(gl)
        self.lb_url = QLabel("")
        self.lb_url.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # 强制单行：wordWrap 会让 QLabel 的 sizeHint 宽度坍缩，url_box 被压窄
        # 后 URL 疯狂换行（实测 30 字符被拆成 30+ 行）。超长地址用省略号兜底。
        self.lb_url.setWordWrap(False)
        self.lb_url.setStyleSheet(
            "font-size: 14px; font-weight: 600; color: #10b981;"
            "background: transparent;")
        ub_lay.addWidget(self.lb_url, 1)
        url_row.addWidget(url_box, 1)
        self.btn_copy_url = PushButton(
            FluentIcon.COPY, tr("复制地址", "Copy URL"))
        self.btn_copy_url.clicked.connect(self._copy_url)
        url_row.addWidget(self.btn_copy_url)
        rv.addLayout(url_row)
        # 按钮行：在浏览器中打开 / 使用手机扫码
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.btn_open_chat = PushButton(
            FluentIcon.LINK, tr("在浏览器中打开", "Open in browser"))
        self.btn_open_chat.clicked.connect(self._open_chat_browser)
        btn_row.addWidget(self.btn_open_chat)
        self.btn_use_phone = PushButton(
            FluentIcon.PHONE, tr("使用手机扫码", "Use phone to scan"))
        self.btn_use_phone.clicked.connect(self._show_phone_scan_hint)
        btn_row.addWidget(self.btn_use_phone)
        btn_row.addStretch(1)
        rv.addLayout(btn_row)
        rv.addStretch(1)
        self.url_h.addWidget(self.url_right, 1)
        self.url_wrap.hide()
        lay.addWidget(self.url_wrap)

        # ===== 4. 信息三列：局域网地址 / 连接方式 / 服务状态 =====
        info_row = QHBoxLayout()
        info_row.setSpacing(0)
        self._info_lay = info_row     # 供 _apply_paddings 动态调间距
        self._card_addr = self._make_info_card(
            FluentIcon.WIFI, tr("局域网地址", "LAN address"), "—")
        self._card_mode = self._make_info_card(
            FluentIcon.PHONE, tr("连接方式", "Connection"),
            tr("手机扫码", "Phone scan"))
        self._card_state = self._make_info_card(
            FluentIcon.HEART, tr("服务状态", "Status"),
            tr("未启动", "Idle"), accent=True)
        info_row.addWidget(self._card_addr)
        info_row.addWidget(self._vdiv())
        info_row.addWidget(self._card_mode)
        info_row.addWidget(self._vdiv())
        info_row.addWidget(self._card_state)
        info_row.addStretch(1)
        lay.addLayout(info_row)

        # ===== 5. 提示条 =====
        tip_bar = QWidget()
        tip_bar.setObjectName("lan_tip")
        tip_bar.setStyleSheet(
            "#lan_tip{background:rgba(16,185,129,0.08);"
            "border:1px solid rgba(16,185,129,0.20);border-radius:8px;}")
        tip_lay = QHBoxLayout(tip_bar)
        tip_lay.setContentsMargins(18, 12, 18, 12)
        tip_lay.setSpacing(10)
        self._tip_lay = tip_lay      # 供 _apply_paddings 动态调内边距
        tip_ic = QLabel("💡")
        tip_ic.setStyleSheet("font-size: 15px; background: transparent;")
        tip_lay.addWidget(tip_ic)
        tip_txt = QLabel(
            tr("请确保手机和电脑连接到同一 Wi-Fi 网络",
               "Make sure your phone and PC are on the same Wi-Fi"))
        tip_txt.setStyleSheet(
            f"font-size: 13px background: transparent;")
        tip_lay.addWidget(tip_txt, 1)
        lay.addWidget(tip_bar)

        # ===== 内部状态 =====
        self._server = None
        self._share_dir = None
        self._guide_dialog = None   # 连接引导弹窗（惰性创建）
        self._last_prog = None      # 实时进度节流状态
        self._last_prog_ts = 0.0
        self._recv_dir = ""         # 本次接收目录
        self._session_count = 0     # 本次接收会话统计
        self._session_size = 0
        self._session_t0 = time.time()
        # 内部 cb_ip：多网卡手动切换（不对外展示，保留对象供 _refresh_ips /
        # _selected_ip / _on_ip_changed 共用）
        self.cb_ip = ComboBox()
        self.cb_ip.hide()
        self.cb_ip.currentIndexChanged.connect(self._on_ip_changed)

        # 访问密码记忆（仅密码；非空即启用，无需开关）
        saved_tok = self.services.get_pref(_PREF_TOKEN, "")
        if isinstance(saved_tok, str) and saved_tok:
            self.ed_token.setText(saved_tok)
        self.ed_token.editingFinished.connect(self._on_token_changed)
        # 信号接线
        self.sig_auto_stop.connect(self._on_auto_stop_signal)
        self.sig_received.connect(self._on_received_ui)
        self.sig_downloaded.connect(self._on_downloaded_ui)
        self.sig_progress.connect(self._on_progress_ui)
        # 初始徽章 + 按钮
        self._refresh_status_badge(running=False)
        self.btn_toggle.setText(tr("启动服务", "Start"))
        self.sb_port.setValue(8000)
        self._refresh_ips()

    # ── 辅助：UI 装饰 ─────────────────────────
    def _vdiv(self):
        """浅色竖直分隔线。"""
        from gui_qt.components import design_system as ds
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setStyleSheet(
            f"QFrame {{ color: {ds.border_color()}; }}"
            f"QFrame::line {{ background: {ds.border_color()}; }}")
        line.setFixedHeight(24)
        return line

    def _make_info_card(self, icon, label, value, accent=False):
        """构建信息三列中的单卡：图标 + 小标题 + 数值。"""
        from gui_qt.components import design_system as ds
        card = QWidget()
        card.setObjectName("lan_info_card")

        def _info_card_qss():
            return (
                f"#lan_info_card{{background:{ds.card_bg()};"
                f"border:1px solid {ds.border_color()};border-radius:10px;}}"
            )
        card.setStyleSheet(_info_card_qss())
        ds.bind_theme(card, _info_card_qss)
        h = QHBoxLayout(card)
        h.setContentsMargins(18, 14, 18, 14)
        h.setSpacing(14)
        card._info_lay = h          # 供 _apply_paddings 动态调内边距
        # 圆形图标背景
        icon_bg = QWidget()
        icon_bg.setFixedSize(40, 40)
        icon_bg.setStyleSheet(
            f"background:rgba(16,185,129,0.10);border-radius:20px;")
        ib_lay = QVBoxLayout(icon_bg)
        ib_lay.setContentsMargins(0, 0, 0, 0)
        ib_lay.setSpacing(0)
        ib_lay.addStretch(1)
        iw = IconWidget(icon, icon_bg)
        iw.setFixedSize(20, 20)
        iw.setStyleSheet("color: #10b981; background: transparent;")
        ib_lay.addWidget(iw, 0, Qt.AlignCenter)
        ib_lay.addStretch(1)
        h.addWidget(icon_bg, 0, Qt.AlignVCenter)
        v = QVBoxLayout()
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        lbl = CaptionLabel(label)
        lbl.setStyleSheet(
            f"font-size: 12px background: transparent;")
        v.addWidget(lbl)
        # value 用 QLabel 以便动态更新
        val = QLabel(value)
        val.setObjectName("lan_info_value")
        val.setStyleSheet(
            f"font-size: 15px; font-weight: 600"
            f"background: transparent;")
        v.addWidget(val)
        h.addLayout(v, 1)
        # 保存 value 引用供后续更新
        card._value_label = val
        return card

    def _set_info_value(self, card, value, color=None):
        """更新信息卡片的数值。"""
        if card is None:
            return
        lbl = getattr(card, "_value_label", None)
        if lbl is None:
            return
        lbl.setText(value)
        if color:
            lbl.setStyleSheet(
                f"font-size: 14px; font-weight: 600; color: {color};"
                f"background: transparent;")

    def _refresh_status_badge(self, running: bool):
        """状态徽章：运行中=绿点，停止=灰点。"""
        from gui_qt.components import design_system as ds
        is_dark = False
        try:
            from qfluentwidgets import isDarkTheme
            is_dark = isDarkTheme()
        except Exception:  # noqa: BLE001
            pass
        if running:
            dot, text, bg, fg = "#10b981", tr("服务运行中", "Running"), \
                ("rgba(16,185,129,0.12)" if not is_dark
                 else "rgba(16,185,129,0.20)"), "#10b981"
        else:
            dot, text, bg, fg = "#9AA3B8", tr("服务未启动", "Idle"), \
                ("rgba(154,163,184,0.12)" if not is_dark
                 else "rgba(154,163,184,0.20)"), ds.ink_sec()
        self.lb_status_badge.setText(f"  ●  {text}  ")
        self.lb_status_badge.setStyleSheet(
            f"background:{bg};color:{fg};"
            f"font-size:12px;font-weight:600;"
            f"border-radius:10px;padding:3px 4px;")

    def _toggle_token_echo(self, checked: bool):
        """密码可见性切换。"""
        self.ed_token.setEchoMode(
            QLineEdit.Normal if checked else QLineEdit.Password)
        self._token_visible = checked
        try:
            from qfluentwidgets import FluentIcon as _FI
            self.btn_eye.setIcon(_FI.HIDE if checked else _FI.VIEW)
        except Exception:  # noqa: BLE001
            pass

    def _copy_url(self):
        """复制当前 URL 到剪贴板。"""
        if not self._current_url:
            toast.show_info(self, tr("服务未启动", "Server not started"))
            return
        try:
            from PySide6.QtGui import QGuiApplication
            QGuiApplication.clipboard().setText(self._current_url)
            toast.show_success(self, tr("已复制地址", "URL copied"))
        except Exception:  # noqa: BLE001
            toast.show_error(self, tr("复制失败", "Copy failed"))

    def _show_phone_scan_hint(self):
        """使用手机扫码按钮：提示手机对准二维码。"""
        if not self._current_url:
            toast.show_info(self, tr("请先启动服务", "Start server first"))
            return
        toast.show_info(
            self,
            tr("请用手机相机或浏览器对准二维码扫码",
               "Point your phone camera or browser at the QR code"))

    def _ink_sec(self):
        from gui_qt.components import design_system as ds
        return ds.ink_sec()

    def _mode(self):
        """合并单一模式：分享 + 接收同时启用。"""
        return "dual"

    # ── 多网卡 IP ──────────────────────────────
    def _refresh_ips(self):
        """刷新可用 IP 列表（注入隐藏 cb_ip，多网卡时供切 IP 触发 _on_ip_changed）。"""
        try:
            from core.lan_transfer import get_lan_ips
            ips = get_lan_ips()
        except Exception:  # noqa: BLE001
            ips = []
        cur = self.cb_ip.currentText()
        self.cb_ip.blockSignals(True)
        self.cb_ip.clear()
        if ips:
            self.cb_ip.addItems(ips)
        self.cb_ip.blockSignals(False)
        if cur and cur in ips:
            self.cb_ip.setCurrentText(cur)

    def _selected_ip(self):
        """当前选择的 IP；无下拉（单网卡）返回 None 用默认出口。"""
        return self.cb_ip.currentText() if self.cb_ip.count() else None

    # ── 服务器生命周期 ──────────────────────────
    def _open_firewall(self):
        """尝试自动放行防火墙；失败提示手动放行。"""
        from core.lan_transfer import add_firewall_rule
        port = (self._server.port if self._server is not None
                else self.sb_port.value())
        if add_firewall_rule(port):
            return True
        toast.show_warning(
            self, tr("请在 Windows 防火墙中放行 Python（控制面板 → "
                     "Windows Defender 防火墙 → 允许应用 → Python），"
                     "否则手机无法访问",
                     "Allow Python in Windows Firewall so phones can connect"))
        return False

    def _toggle(self):
        if self._server is not None:
            self._stop_server()
            return
        self._start_server()

    def _start_server(self):
        """启动统一局域网服务（端口占用自动 +1）。"""
        self._last_prog = None
        self._last_prog_ts = 0.0

        from core.lan_service import LanService
        srv = LanService(host="0.0.0.0",
                         port=int(self.sb_port.value() or 8000))
        # 回调接线（工作线程 → 信号回主线程）
        srv.on_received = self._on_received
        srv.on_downloaded = self._on_downloaded
        srv.on_progress = self._on_progress
        srv.on_all_done = self._on_all_done

        # 接收端：手机→电脑文件落盘到「记忆目录 或 默认下载目录」
        saved_dir = self.services.get_pref(_PREF_RECV_DIR, "")
        if saved_dir and os.path.isdir(saved_dir):
            out_dir = saved_dir
        else:
            out_dir = os.path.join(
                os.path.expanduser("~/Downloads"),
                tr("FormatMaster接收", "FormatMasterReceived"))
            try:
                os.makedirs(out_dir, exist_ok=True)
            except OSError:
                out_dir = ""
        if not out_dir:
            toast.show_warning(
                self, tr("默认下载目录不可用，请检查写入权限",
                         "Default download folder unavailable; check write permission"))
            return False
        # 默认同名文件策略=自动改名；自动分类默认关闭（功能已从 UI 移除）
        srv.set_recv(out_dir, conflict="rename")
        self._recv_dir = out_dir
        self.services.set_pref(_PREF_RECV_DIR, out_dir)

        # 访问密码：输入框非空时启用（不开关），留空则不启用
        tok = self.ed_token.text().strip()
        if tok:
            srv.access_token = tok
            self.services.set_pref(_PREF_TOKEN, tok)
        else:
            srv.access_token = None
        # 启动统一服务
        if not srv.start():
            toast.show_error(self, tr("服务启动失败：端口不可用或参数错误",
                                      "Failed: port unavailable or bad args"))
            return False
        self._server = srv
        self._share_dir = srv.share_dir
        self._open_firewall()
        if srv.port != int(self.sb_port.value() or 8000):
            self.sb_port.setValue(srv.port)
            toast.show_info(self, tr("端口 {} 已被占用，已改用 {}",
                                     "Port {} busy; using {} instead").format(
                int(self.sb_port.value()) or 8000, srv.port))
        self._show_ready(self._display_url(srv))
        return True

    def _show_ready(self, url):
        """启动后展示二维码卡 + 状态徽章 + 信息三列。"""
        self._update_url_display(url)
        self.url_wrap.show()
        # 立即按当前窗口做一次自适应：QR 尺寸/方向/padding 与窗口匹配，
        # 不等下一次 resizeEvent（否则服务启动瞬间二维码可能偏小/布局未就绪）
        self._apply_responsive()
        self._refresh_status_badge(running=True)
        self.btn_toggle.setText(tr("停止服务", "Stop"))
        self.btn_toggle.setIcon(FluentIcon.CANCEL)
        # 信息三列
        sel = self._selected_ip()
        ip_text = (sel if sel else (self._server.url.split('://')[-1].split(':')[0]
                                     if hasattr(self._server, "url") else "—"))
        self._set_info_value(
            self._card_addr,
            f"{ip_text}:{self._server.port}",
            color="#10b981")
        self._set_info_value(self._card_mode,
                             tr("手机扫码", "Phone scan"))
        self._set_info_value(self._card_state,
                             tr("运行中", "Running"), color="#10b981")
        toast.show_success(self, tr("局域网服务已启动", "LAN server started"))

    def _stop_server(self):
        if self._server is not None:
            try:
                self._server.stop()
            except Exception:  # noqa: BLE001
                pass
            try:
                clear = getattr(self._server, "clear_share", None)
                if callable(clear):
                    clear()
            except Exception:  # noqa: BLE001
                pass
            self._server = None
        if self._share_dir:
            import shutil
            shutil.rmtree(self._share_dir, ignore_errors=True)
            self._share_dir = None
        self.url_wrap.hide()
        self.lb_url.setText("")
        self._current_url = None
        self._refresh_status_badge(running=False)
        self.btn_toggle.setText(tr("启动服务", "Start"))
        self.btn_toggle.setIcon(FluentIcon.PLAY)
        # 信息三列回到未启动态
        self._set_info_value(self._card_addr, "—")
        self._set_info_value(
            self._card_mode, tr("手机扫码", "Phone scan"))
        self._set_info_value(
            self._card_state, tr("未启动", "Idle"), color="#9AA3B8")

    def _on_token_changed(self, *_):
        """服务运行中改密码 → 实时生效，无需重启服务。

        历史 bug 修复：访问密码只在启动时快照，运行中改值，服务端与二维码
        都不更新——手机扫到的还是旧码。这里实时写入并刷新 URL/二维码。
        """
        srv = self._server
        tok = self.ed_token.text().strip()
        if tok:
            if srv is not None and getattr(srv, "is_running", lambda: False)():
                srv.access_token = tok
            self.services.set_pref(_PREF_TOKEN, tok)
        else:
            if srv is not None and getattr(srv, "is_running", lambda: False)():
                srv.access_token = None
        if srv is not None and getattr(srv, "is_running", lambda: False)():
            self._update_url_display(self._display_url(srv))

    def _display_url(self, srv):
        """展示 URL：优先用户选中的 IP（多网卡手动切换），否则用服务自动探测。

        聊天式互传：根路径与二维码都指向 /chat（手机扫码即进入聊天页）。

        访问密码：开启时 URL/二维码**不嵌入 token**——手机扫码与电脑一样
        都被服务端拦截到 /chat/login 密码页。
        """
        sel = self._selected_ip()
        base = (f"http://{sel}:{srv.port}/" if sel
                else (srv.url if hasattr(srv, "url") else f"http://{srv.port}/"))
        return base + "chat"

    def _display_url_pc(self, srv):
        """电脑端在浏览器打开聊天页：同样不带 token，走密码登录页。"""
        url = self._display_url(srv)
        sep = "&" if "?" in url else "?"
        return url + sep + "side=pc"

    def _open_chat_browser(self):
        """在电脑默认浏览器打开聊天页（与手机共用同一 ChatSession）。"""
        srv = self._server
        if srv is None or not getattr(srv, "is_running", lambda: False)():
            toast.show_info(self, tr("请先启动服务", "Start server first"))
            return
        try:
            import webbrowser
            webbrowser.open(self._display_url_pc(srv))
        except Exception:  # noqa: BLE001
            toast.show_error(self, tr("无法打开浏览器", "Cannot open browser"))

    # ── 二维码 / 响应式 ────────────────────────
    def _qr_size(self):
        """二维码按窗口宽度响应式缩放（窗口化/全屏都更清晰）。

        阶梯：<800→200 / <1000→240 / <1400→260 / <1800→300 / ≥1800→340。
        注意 1400 以下不能给太大：URL 完整文本约 420px，QR 过大（如 300）
        会把 URL 挤到省略号，1100 窗口下地址显示不全。
        """
        w = self.width() or 1200
        if w < 800:
            return 200
        if w < 1000:
            return 240
        if w < 1400:
            return 260
        if w < 1800:
            return 300
        return 340

    def _set_qr(self, url):
        """生成并铺设当前尺寸的二维码，记住 URL 供 resize 时重绘。"""
        size = self._qr_size()
        self.lb_qr.setFixedSize(size, size)
        self.lb_qr.setPixmap(_qr_pixmap(url, size))
        self._current_url = url

    def _update_url_display(self, url):
        """刷新 URL 文本与二维码（URL 单行，超长省略号，toolTip 保留完整地址）。"""
        self._raw_url = url
        self.lb_url.setToolTip(url)
        self._elide_url()
        self._set_qr(url)

    def _elide_url(self):
        """按当前可用宽度把 URL 省略为单行（避免长地址撑破/换行）。"""
        raw = getattr(self, "_raw_url", "")
        if not raw:
            return
        avail = self.lb_url.width()
        if avail <= 0:
            self.lb_url.setText(raw)
            return
        elided = self.lb_url.fontMetrics().elidedText(
            raw, Qt.ElideMiddle, avail)
        self.lb_url.setText(elided)

    def resizeEvent(self, e):
        """窗口尺寸变化（含全屏/最大化）时重算布局与二维码。"""
        super().resizeEvent(e)
        self._apply_responsive()

    def showEvent(self, e):
        """首次显示兜底：build 时 self.width() 可能为 0/小值。"""
        super().showEvent(e)
        self._apply_responsive()

    def _apply_responsive(self):
        """响应式：内容占满窗口（不封顶、不居中留白），URL 区横/竖排，
        二维码按宽度阶梯放大，内外边距随窗口缩放。

        历史：曾用 min(1180, w) 封顶 + 水平居中，全屏下内容缩在中间一小块、
        两侧大片空白——用户明确要求往两边扩散，故移除封顶，inner 占满窗口。
        """
        w = self.width()
        if w > 0:
            # inner 不设最大宽度：占满窗口（QWIDGETSIZE_MAX 默认）
            self._apply_paddings(w)
        if getattr(self, "url_h", None) is not None:
            self.url_h.setDirection(
                QVBoxLayout.TopToBottom if w < 820 else QHBoxLayout.LeftToRight)
        if getattr(self, "_current_url", None):
            self._set_qr(self._current_url)
        # 布局稳定后（下一事件循环）重算 URL 省略——resize 刚发生时
        # lb_url.width() 还是旧布局的值，立即 elide 会误判可用宽度
        try:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._elide_url)
        except Exception:  # noqa: BLE001
            self._elide_url()

    def _apply_paddings(self, w):
        """按窗口宽度阶梯调节外边距/内边距/间距（窗口大→宽松，窗口小→紧凑）。

        参数（left, top, right, bottom）统一顺序；仅在有引用时设置，防部分
        控件尚未构建（build 早期 resizeEvent）时报错。
        """
        if w < 820:
            outer, gap, cfg_p, url_p, info_p, tip_p, url_gap = \
                16, 12, (16, 12, 16, 12), (20, 16, 20, 16), \
                (14, 12, 14, 12), (14, 10, 14, 10), 20
        elif w < 1200:
            outer, gap, cfg_p, url_p, info_p, tip_p, url_gap = \
                24, 14, (20, 14, 20, 14), (24, 20, 24, 20), \
                (16, 13, 16, 13), (16, 11, 16, 11), 28
        elif w < 1600:
            outer, gap, cfg_p, url_p, info_p, tip_p, url_gap = \
                32, 16, (24, 16, 24, 16), (28, 24, 28, 24), \
                (18, 14, 18, 14), (18, 12, 18, 12), 36
        else:
            outer, gap, cfg_p, url_p, info_p, tip_p, url_gap = \
                40, 18, (28, 18, 28, 18), (32, 28, 32, 28), \
                (20, 15, 20, 15), (20, 13, 20, 13), 40
        # 内容区外边距（跟随窗口）
        self.content_layout.setContentsMargins(outer, outer, outer, outer)
        # 区块间间距
        if getattr(self, "_inner_lay", None) is not None:
            self._inner_lay.setSpacing(gap)
        # 配置卡内边距
        if getattr(self, "_cfg_lay", None) is not None:
            self._cfg_lay.setContentsMargins(*cfg_p)
        # 二维码卡内边距 + 左右间距
        if getattr(self, "_url_lay", None) is not None:
            self._url_lay.setContentsMargins(*url_p)
            self._url_lay.setSpacing(url_gap)
        # 信息三列卡内边距（各自卡片）
        for card in (getattr(self, "_card_addr", None),
                     getattr(self, "_card_mode", None),
                     getattr(self, "_card_state", None)):
            if card is not None:
                h = getattr(card, "_info_lay", None)
                if h is not None:
                    h.setContentsMargins(*info_p)
        # 提示条内边距
        if getattr(self, "_tip_lay", None) is not None:
            self._tip_lay.setContentsMargins(*tip_p)

    def _on_ip_changed(self, _i):
        """服务运行中手动切换 IP → 立即刷新展示 URL 与二维码。"""
        srv = self._server
        if srv is None or not getattr(srv, "is_running", lambda: False)():
            return
        self._update_url_display(self._display_url(srv))
        sel = self._selected_ip()
        if sel:
            self._set_info_value(
                self._card_addr, f"{sel}:{srv.port}", color="#10b981")

    # ── 传输回调 / 通知 ────────────────────────
    def _on_received(self, name, size, sec, ip="", renamed_from=None):
        """HTTP 工作线程回调 → emit 信号回主线程。"""
        try:
            self.sig_received.emit(name, size, sec, ip, renamed_from)
        except Exception:  # noqa: BLE001
            pass

    def _on_received_ui(self, name, size, sec, ip="", renamed_from=None):
        """主线程：收到文件 → 通知 + 改名冲突提示 + 信息卡片更新。"""
        self._session_count += 1
        self._session_size += size
        decoded = (urllib.parse.unquote(name, encoding="utf-8", errors="replace")
                   if name else "")
        basename = os.path.basename(decoded) if decoded else ""
        self._notify(tr("收到文件", "File received"), decoded, size, sec)
        # 服务状态卡：本次会话统计
        short = self._elide(basename, 32)
        self._set_info_value(
            self._card_state,
            tr("已收 {} · {}", "Recv {} · {}").format(
                self._session_count, _human_size(self._session_size)),
            color="#10b981")
        if renamed_from:
            toast.show_info(self,
                            tr("{} 已存在，已存为 {}", "{} exists, saved as {}")
                            .format(renamed_from, basename))
        self._alert_window()

    def _on_downloaded(self, name, size, sec, ip=""):
        """HTTP 工作线程回调 → emit 信号回主线程。"""
        try:
            self.sig_downloaded.emit(name, size, sec, ip)
        except Exception:  # noqa: BLE001
            pass

    def _on_downloaded_ui(self, name, size, sec, ip=""):
        """主线程：文件被下载 → 通知。"""
        self._notify(tr("文件被下载", "File downloaded"), name, size, sec)
        self._alert_window()

    def _on_progress(self, done, total):
        """HTTP 工作线程实时进度 → emit 信号回主线程。"""
        try:
            self.sig_progress.emit(done, total)
        except Exception:  # noqa: BLE001
            pass

    def _on_progress_ui(self, done, total):
        """主线程：实时接收进度 → 信息卡片状态值（带节流）。"""
        if self._server is None:
            return
        now = time.time()
        try:
            pct = int(done * 100 / total) if total else 0
        except Exception:  # noqa: BLE001
            return
        if self._last_prog is None:
            self._last_prog, self._last_prog_ts = done, now
            return
        if now - self._last_prog_ts < 0.3:
            return
        speed = (done - self._last_prog) / max(now - self._last_prog_ts,
                                               0.001) / 1048576
        self._last_prog, self._last_prog_ts = done, now
        self._set_info_value(
            self._card_state,
            tr("接收中… {}% · {:.1f} MB/s", "Receiving… {}% · {:.1f} MB/s")
            .format(pct, speed), color="#10b981")

    def _on_all_done(self):
        """core 工作线程：全部下载完 → 信号回主线程停止。"""
        try:
            self.sig_auto_stop.emit("done")
        except Exception:  # noqa: BLE001
            pass

    def _on_idle(self):
        """core 工作线程：空闲超时 → 信号回主线程停止。"""
        try:
            self.sig_auto_stop.emit("idle")
        except Exception:  # noqa: BLE001
            pass

    def _on_auto_stop_signal(self, kind):
        """主线程：自动停止服务并提示。"""
        if self._server is None:
            return
        if kind == "done":
            toast.show_info(self, tr("全部文件已下载，服务自动停止",
                                     "All downloaded, server stopped"))
        else:
            if self._session_count:
                toast.show_info(
                    self, tr("本次收到 {} 个文件 · 共 {} · 用时 {} 秒",
                             "{} files · {} · {}s")
                    .format(self._session_count,
                            _human_size(self._session_size),
                            int(time.time() - self._session_t0)))
            toast.show_info(self, tr("服务长时间无访问，已自动停止",
                                     "Idle timeout, server stopped"))
        self._stop_server()

    def _alert_window(self):
        """任务栏闪烁提醒。"""
        try:
            win = self.main_window
            QApplication.alert(win, 3000)
        except Exception:  # noqa: BLE001
            pass

    def _notify(self, title, name, size, sec):
        """通知：toast + 蜂鸣（不再写状态栏，状态栏已改为信息三列）。"""
        speed = size / max(sec, 0.01) / 1048576
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_OK)
        except Exception:  # noqa: BLE001
            pass

    def _elide(self, text, max_px):
        """长文本省略号（避免撑破信息卡片）。"""
        if not text:
            return ""
        try:
            fm = QFontMetrics(self._card_state._value_label.font())
            return fm.elidedText(text, Qt.ElideMiddle, max_px * 8)
        except Exception:  # noqa: BLE001
            return text

    def _open_guide(self):
        """打开连接引导弹窗。"""
        if self._guide_dialog is None:
            self._guide_dialog = LanGuideDialog(self)
        self._guide_dialog.show()
        self._guide_dialog.raise_()
        self._guide_dialog.activateWindow()

    # ── 收尾 ────────────────────────────────────
    def _on_destroy(self):
        self._stop_server()
