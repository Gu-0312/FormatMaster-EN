"""file_security_panel — 文件安全工具面板。

模式：加密 / 解密 / 粉碎删除 / 数字签名 / 验签 / 生成证书。
加密支持算法：Fernet（AES-CBC，兼容旧版）、AES-GCM（更快）、
RSA 混合、ECC 混合（公钥加密 / 私钥解密）。走任务队列。
"""

import os

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (CaptionLabel, ComboBox, FluentIcon, LineEdit,
                            PushButton, SegmentedWidget, ToolButton)

from gui_qt.components import toast
from gui_qt.i18n import tr
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow

SEC_EXTS = {".fmsec", ".fmgcm", ".fmpub", ".sig", ".pem", ".crt", ".key"}
ALL_EXTS = None   # 不限

ALGO_VALUES = [
    ("fernet", tr("AES-CBC (Fernet, 兼容旧版)", "AES-CBC (Fernet, legacy)")),
    ("gcm", tr("AES-GCM (更快)", "AES-GCM (faster)")),
    ("rsa", tr("RSA 混合加密 (需公钥)", "RSA hybrid (needs public key)")),
    ("ecc", tr("ECC 混合加密 (需公钥)", "ECC hybrid (needs public key)")),
]


class FileSecurityPanelPage(BaseQtPanel, TaskPanelMixin):
    """文件安全工具页。"""

    panel_key = "file_security"
    need_ffmpeg = False   # 加密/解密/粉碎不依赖 FFmpeg

    # ── UI ──────────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("文件安全工具", "File Security")))
        lay.addWidget(CaptionLabel(
            tr("加密 / 解密 / 粉碎 / 数字签名 / 验签 / 证书",
               "Encrypt / decrypt / shred / sign / verify / cert")))

        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        mode_row.addWidget(CaptionLabel(tr("模式", "Mode")))
        self.sg_mode = SegmentedWidget()
        self.sg_mode.addItem("encrypt", tr("加密", "Encrypt"))
        self.sg_mode.addItem("decrypt", tr("解密", "Decrypt"))
        self.sg_mode.addItem("shred", tr("粉碎删除", "Shred"))
        self.sg_mode.addItem("sign", tr("数字签名", "Sign"))
        self.sg_mode.addItem("verify", tr("验签", "Verify"))
        self.sg_mode.addItem("cert", tr("生成证书", "Certificate"))
        self.sg_mode.setCurrentItem("encrypt")
        self.sg_mode.currentItemChanged.connect(lambda _k: self._mode_changed())
        mode_row.addWidget(self.sg_mode)
        mode_row.addStretch(1)
        lay.addLayout(mode_row)

        self.file_card = FileListCard(tr("文件列表", "Files"),
                                      file_exts=ALL_EXTS)
        lay.addWidget(self.file_card)

        # 加密算法（加密/解密模式显示）
        algo_row = QHBoxLayout()
        algo_row.setSpacing(8)
        algo_row.addWidget(CaptionLabel(tr("算法", "Algorithm")))
        self.cb_algo = ComboBox()
        for _k, label in ALGO_VALUES:
            self.cb_algo.addItem(label)
        self.cb_algo.currentIndexChanged.connect(lambda _i: self._mode_changed())
        algo_row.addWidget(self.cb_algo, 1)
        self.w_algo = QWidget()
        self.w_algo.setLayout(algo_row)
        lay.addWidget(self.w_algo)

        # 密钥/签名文件选择（非对称/签名/验签模式显示）
        key_row = QHBoxLayout()
        key_row.setSpacing(8)
        key_row.addWidget(CaptionLabel(tr("密钥文件", "Key file")))
        self.ed_key = LineEdit()
        self.ed_key.setReadOnly(True)
        self.ed_key.setPlaceholderText(tr("选择 .pem 公钥/私钥…", "Pick a .pem key…"))
        key_row.addWidget(self.ed_key, 1)
        self.btn_key = PushButton(FluentIcon.DOCUMENT, tr("选择", "Pick"))
        self.btn_key.clicked.connect(self._pick_key)
        key_row.addWidget(self.btn_key)
        self.w_key = QWidget()
        self.w_key.setLayout(key_row)
        lay.addWidget(self.w_key)

        pw_row = QHBoxLayout()
        pw_row.setSpacing(8)
        pw_row.addWidget(CaptionLabel(tr("密码", "Password")))
        self.ed_pw = LineEdit()
        self.ed_pw.setEchoMode(LineEdit.EchoMode.Password)
        self.ed_pw.setPlaceholderText(tr("输入密码…", "Type password…"))
        pw_row.addWidget(self.ed_pw, 1)
        # 小眼睛：显示/隐藏密码
        self.btn_eye = ToolButton(FluentIcon.VIEW)
        self.btn_eye.setFixedSize(32, 32)
        self.btn_eye.setToolTip(tr("显示 / 隐藏密码", "Show / hide password"))
        self.btn_eye.clicked.connect(self._toggle_password)
        pw_row.addWidget(self.btn_eye)
        pw_row.addWidget(CaptionLabel(tr("确认", "Confirm")))
        self.ed_pw2 = LineEdit()
        self.ed_pw2.setEchoMode(LineEdit.EchoMode.Password)
        self.ed_pw2.setPlaceholderText(tr("再次输入…", "Confirm…"))
        pw_row.addWidget(self.ed_pw2, 1)
        self.w_pw = QWidget()
        self.w_pw.setLayout(pw_row)
        lay.addWidget(self.w_pw)

        # 证书参数（证书模式显示）
        cert_row = QHBoxLayout()
        cert_row.setSpacing(8)
        cert_row.addWidget(CaptionLabel(tr("证书名称(CN)", "Common name")))
        self.ed_cn = LineEdit()
        self.ed_cn.setPlaceholderText(tr("如 myapp.local", "e.g. myapp.local"))
        cert_row.addWidget(self.ed_cn, 1)
        cert_row.addWidget(CaptionLabel(tr("有效期(天)", "Days")))
        self.ed_days = LineEdit()
        self.ed_days.setText("365")
        self.ed_days.setFixedWidth(60)
        cert_row.addWidget(self.ed_days)
        self.w_cert = QWidget()
        self.w_cert.setLayout(cert_row)
        lay.addWidget(self.w_cert)

        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        lay.addWidget(self.out_row)

        self.action_bar = ActionBar(tr("开始处理", "Start"))
        lay.addWidget(self.action_bar)
        # 打开输出目录（解密/加密后方便直接找到文件）
        self.btn_open_dir = PushButton(
            FluentIcon.FOLDER, tr("打开输出目录", "Open Output Folder"))
        self.btn_open_dir.clicked.connect(self._open_output_dir)
        lay.addWidget(self.btn_open_dir)

        self.services.task_manager.register_runner(
            "file_security", lambda task: self._runner)
        self._wire_tasks()
        self._mode_changed()

    def _mode(self):
        return self.sg_mode.currentRouteKey()

    def _algo_key(self):
        return ALGO_VALUES[self.cb_algo.currentIndex()][0]

    def _mode_changed(self):
        # 切换模式时清空文件列表与密码（各模式文件不复用）
        self.file_card.clear_files()
        self.ed_pw.clear()
        self.ed_pw2.clear()
        self.ed_key.clear()
        mode = self._mode()
        self.out_row.setVisible(mode != "shred")
        # 密码行：加密/解密需要
        self.w_pw.setVisible(mode in ("encrypt", "decrypt"))
        # 算法行：加密/解密需要
        self.w_algo.setVisible(mode in ("encrypt", "decrypt"))
        # 密钥文件行：RSA/ECC 加密、解密、签名、验签需要
        need_key = mode in ("sign", "verify") or (
            mode in ("encrypt", "decrypt") and self._algo_key() in ("rsa", "ecc"))
        self.w_key.setVisible(need_key)
        # 证书行：证书模式
        self.w_cert.setVisible(mode == "cert")
        # 非对称加密时不需要密码（改用密钥）
        self.w_pw.setVisible(
            mode in ("encrypt", "decrypt") and self._algo_key() not in ("rsa", "ecc"))
        # 验签需第二个文件（签名文件）
        self.btn_key.setText(tr("选择", "Pick"))

    def _pick_key(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("选择密钥文件", "Pick key file"), "",
            tr("PEM 密钥 (*.pem *.key);;所有文件 (*)", "PEM keys (*.pem *.key);;All (*)"))
        if path:
            self.ed_key.setText(path)

    def _toggle_password(self):
        """小眼睛：切换密码显示/隐藏（两个密码框同步）。"""
        mode = (LineEdit.EchoMode.Normal
                if self.ed_pw.echoMode() == LineEdit.EchoMode.Password
                else LineEdit.EchoMode.Password)
        self.ed_pw.setEchoMode(mode)
        self.ed_pw2.setEchoMode(mode)

    def _open_output_dir(self):
        """打开当前输出目录（加密/解密结果所在处）。"""
        import subprocess
        out_dir = self.out_row.resolve_dir("") if self._mode() != "shred" \
            else os.path.dirname(self.file_card.files()[0]) \
            if self.file_card.files() else ""
        if out_dir and os.path.isdir(out_dir):
            try:
                os.startfile(out_dir)   # noqa: S606 - Windows 打开目录
            except Exception:  # noqa: BLE001
                subprocess.Popen(["explorer", out_dir])
        else:
            toast.show_warning(self, tr("输出目录不可用，请检查设置",
                                        "Output folder unavailable"))

    # ── 任务 ────────────────────────────────────
    def collect_params(self) -> dict:
        return {
            "mode": self._mode(),
            "algo": self._algo_key(),
            "password": self.ed_pw.text(),
            "key_path": self.ed_key.text().strip(),
            "cn": self.ed_cn.text().strip(),
            "days": self.ed_days.text().strip(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def _runner(self, task, prog):
        p = task.params
        mode = p.get("mode", "encrypt")
        algo = p.get("algo", "fernet")
        # 粉碎
        if mode == "shred":
            from core.file_security import shred_paths
            ok, failed = shred_paths([task.file_path], progress_cb=prog)
            return ok == 1 and not failed
        # 数字签名
        if mode == "sign":
            from core.crypto_advanced import sign_file
            key = p.get("key_path", "")
            if not key or not os.path.isfile(key):
                if prog: prog(-1, "错误: 请选择私钥文件")
                return False
            with open(key, "rb") as f:
                priv = f.read()
            sig = sign_file(task.file_path, priv, task.output_path + ".sig", prog)
            return sig is not None
        # 验签
        if mode == "verify":
            from core.crypto_advanced import verify_signature
            key = p.get("key_path", "")
            if not key or not os.path.isfile(key):
                if prog: prog(-1, "错误: 请选择公钥文件")
                return False
            sig_path = task.file_path + ".sig"
            if not os.path.isfile(sig_path):
                if prog: prog(-1, "错误: 未找到同名 .sig 签名文件")
                return False
            with open(key, "rb") as f:
                pub = f.read()
            ok, msg = verify_signature(task.file_path, pub, sig_path, prog)
            if not ok and prog:
                prog(-1, msg)
            return ok
        # 生成证书
        if mode == "cert":
            from core.crypto_advanced import generate_self_signed_cert
            cn = p.get("cn", "") or "FormatMaster"
            days = int(p.get("days", "365") or "365")
            out_dir = self.out_row.resolve_dir(task.file_path)
            cert_path = os.path.join(out_dir, cn.replace(" ", "_") + ".crt")
            c, _k = generate_self_signed_cert(cn, cert_path, days=days,
                                              progress_cb=prog)
            return c is not None
        # 加密/解密
        password = p.get("password", "")
        if algo in ("rsa", "ecc"):
            key_path = p.get("key_path", "")
            if not key_path or not os.path.isfile(key_path):
                if prog: prog(-1, "错误: 请选择 PEM 密钥文件")
                return False
            with open(key_path, "rb") as f:
                pem = f.read()
            from core.crypto_advanced import (decrypt_asymmetric,
                                              encrypt_asymmetric)
            fn = (encrypt_asymmetric if mode == "encrypt"
                  else decrypt_asymmetric)
            return fn(task.file_path, task.output_path,
                      pem if mode == "encrypt" else pem,
                      progress_cb=prog)
        if algo == "gcm":
            from core.crypto_advanced import (decrypt_file_gcm,
                                              encrypt_file_gcm)
            fn = (encrypt_file_gcm if mode == "encrypt" else decrypt_file_gcm)
            return fn(task.file_path, task.output_path, password,
                      progress_cb=prog)
        from core.file_security import decrypt_file, encrypt_file
        fn = (encrypt_file if mode == "encrypt" else decrypt_file)
        return fn(task.file_path, task.output_path, password,
                  progress_cb=prog)

    def _make_task(self, f):
        params = self.collect_params()
        mode = params["mode"]
        if mode == "shred":
            if not params["password"]:
                pass  # 粉碎不需要密码
            out = f   # 粉碎无输出文件，output_path 占位为源路径
            target = tr("粉碎", "Shred")
        elif mode in ("sign", "verify"):
            out = f   # 输出由 runner 决定（.sig / 校验结果）
            target = tr("签名", "Sign") if mode == "sign" else tr("验签", "Verify")
        elif mode == "cert":
            out = f   # 证书输出由 runner 生成到输出目录
            target = tr("证书", "Certificate")
        else:
            if not params["password"] and params["algo"] not in ("rsa", "ecc"):
                toast.show_warning(self, tr("请先输入密码", "Enter a password first"))
                return None
            if params["algo"] not in ("rsa", "ecc") and params["password"] != self.ed_pw2.text():
                toast.show_warning(self, tr("两次输入的密码不一致",
                                            "Passwords do not match"))
                return None
            src = os.path.basename(f)
            if mode == "encrypt":
                ext_map = {"fernet": ".fmsec", "gcm": ".fmgcm",
                           "rsa": ".fmpub", "ecc": ".fmpub"}
                out = os.path.join(self.out_row.resolve_dir(f),
                                   src + ext_map.get(params["algo"], ".fmsec"))
                target = tr("加密", "Encrypt")
            else:
                # 解密：去掉加密扩展名恢复原名
                for ext in (".fmsec", ".fmgcm", ".fmpub"):
                    if src.lower().endswith(ext):
                        out = os.path.join(self.out_row.resolve_dir(f),
                                           src[:-len(ext)])
                        break
                else:
                    out = os.path.join(self.out_row.resolve_dir(f), src)
                target = tr("解密", "Decrypt")
        return dict(
            name=f"{target} - {os.path.basename(f)}",
            task_type="file_security", file_path=f, output_path=out,
            params=params, runner=self._runner,
            history_type=tr("文件安全", "File Security"),
            history_target=target, need_ffmpeg=False)

    def _start(self):
        self._submit_files()

    def _empty_hint(self):
        return tr("请先添加要处理的文件", "Add files first")

    def collect_prefs(self) -> dict:
        """记忆模式/算法选择，重进面板自动恢复（密码等敏感项不记忆）。"""
        return {"mode": self.sg_mode.currentRouteKey(),
                "algo": self.cb_algo.currentIndex()}

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        mode = prefs.get("mode")
        if mode in self.sg_mode.items:
            self.sg_mode.setCurrentItem(mode)
        idx = prefs.get("algo")
        if isinstance(idx, int) and 0 <= idx < self.cb_algo.count():
            self.cb_algo.setCurrentIndex(idx)

