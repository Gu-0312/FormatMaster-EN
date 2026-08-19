"""phantom_panel — 幻影坦克图片（制作 / 解密）面板。

- 制作：选「白底图」+「黑底图」→ 生成一张 PNG，浅色主题下显示白底图，
  深色主题下显示黑底图
- 解密：选一张幻影坦克 PNG → 拆出白底图与黑底图两张

核心逻辑在 core/phantom_tank.py（numpy 逐像素合成）。
"""

import os

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (CaptionLabel, FluentIcon, LineEdit,
                            PrimaryPushButton, PushButton, SegmentedWidget)

from gui_qt.components import toast
from gui_qt.components.form_widgets import FormSection
from gui_qt.i18n import tr
from gui_qt.panels.base_panel import BaseQtPanel

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif"}


class PhantomPanelPage(BaseQtPanel):
    """幻影坦克图片页。"""

    panel_key = "phantom"

    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("幻影坦克", "Phantom Tank")))
        lay.addWidget(CaptionLabel(
            tr("一张图片：浅色背景显示一张图，深色背景显示另一张图",
               "One image: shows one picture on light background, another on dark")))

        # 模式切换
        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        mode_row.addWidget(CaptionLabel(tr("模式", "Mode")))
        self.sg_mode = SegmentedWidget()
        self.sg_mode.addItem("make", tr("制作", "Make"))
        self.sg_mode.addItem("decode", tr("解密", "Decode"))
        self.sg_mode.setCurrentItem("make")
        self.sg_mode.currentItemChanged.connect(lambda _k: self._mode_changed())
        mode_row.addWidget(self.sg_mode)
        mode_row.addStretch(1)
        lay.addLayout(mode_row)

        sec = FormSection(tr("图片设置", "Images"), FluentIcon.PHOTO)

        # 制作：白底图 + 黑底图
        self.w_make = QWidget()
        mv = QVBoxLayout(self.w_make)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(8)
        mv.addLayout(self._file_row(
            tr("白底图（浅色下显示）", "Light image"),
            "ed_white", "btn_white"))
        mv.addLayout(self._file_row(
            tr("黑底图（深色下显示）", "Dark image"),
            "ed_black", "btn_black"))
        sec.add_widget(self.w_make)

        # 解密：幻影坦克 PNG
        self.w_decode = QWidget()
        dv = QVBoxLayout(self.w_decode)
        dv.setContentsMargins(0, 0, 0, 0)
        dv.setSpacing(8)
        dv.addLayout(self._file_row(
            tr("幻影坦克 PNG", "Phantom tank PNG"),
            "ed_src", "btn_src"))
        sec.add_widget(self.w_decode)

        lay.addWidget(sec)

        # 输出目录
        out_sec = FormSection(tr("输出目录", "Output folder"), FluentIcon.FOLDER)
        out_row = QHBoxLayout()
        out_row.setSpacing(8)
        out_row.addWidget(CaptionLabel(tr("输出目录", "Output folder")))
        self.ed_out = LineEdit()
        self.ed_out.setText(os.path.join(os.path.expanduser("~"), "Desktop"))
        self.ed_out.setPlaceholderText(
            tr("选择或输入输出目录…", "Pick or type the output folder…"))
        self.btn_out = PushButton(FluentIcon.FOLDER, tr("浏览", "Browse"))
        self.btn_out.clicked.connect(self._pick_out)
        out_row.addWidget(self.ed_out, 1)
        out_row.addWidget(self.btn_out)
        out_sec.add_layout(out_row)
        lay.addWidget(out_sec)

        # 开始
        ctrl = QHBoxLayout()
        self.btn_go = PrimaryPushButton(FluentIcon.PLAY, tr("开始", "Start"))
        self.btn_go.clicked.connect(self._run)
        ctrl.addWidget(self.btn_go)
        self.btn_open_out = PushButton(
            FluentIcon.FOLDER, tr("打开输出文件夹", "Open Output Folder"))
        self.btn_open_out.setToolTip(
            tr("在文件管理器中打开输出目录", "Open the output folder in Explorer"))
        self.btn_open_out.clicked.connect(self._open_out_dir)
        ctrl.addWidget(self.btn_open_out)
        self.lb_status = CaptionLabel("")
        self.lb_status.setStyleSheet(
            f"font-size: 12px; color: {self._ink_sec()};")
        ctrl.addWidget(self.lb_status)
        ctrl.addStretch(1)
        lay.addLayout(ctrl)

        self._mode_changed()

    def _file_row(self, label, ed_attr, btn_attr):
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(CaptionLabel(label))
        ed = LineEdit()
        ed.setPlaceholderText(tr("选择图片文件…", "Pick an image…"))
        btn = PushButton(FluentIcon.FOLDER, tr("浏览", "Browse"))
        setattr(self, ed_attr, ed)
        setattr(self, btn_attr, btn)
        btn.clicked.connect(
            lambda _c, e=ed: self._pick_image(e))
        row.addWidget(ed, 1)
        row.addWidget(btn)
        return row

    def _ink_sec(self):
        from gui_qt.components import design_system as ds
        return ds.ink_sec()

    def _mode_changed(self):
        mode = self.sg_mode.currentRouteKey()
        self.w_make.setVisible(mode == "make")
        self.w_decode.setVisible(mode == "decode")
        self.btn_go.setText(
            tr("开始制作", "Make") if mode == "make" else tr("开始解密", "Decode"))

    def _pick_image(self, ed):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("选择图片", "Pick image"), "",
            tr("图片文件 (*.png *.jpg *.jpeg *.bmp *.webp *.gif)",
               "Images (*.png *.jpg *.jpeg *.bmp *.webp *.gif)"))
        if path:
            ed.setText(path)

    def _pick_out(self):
        d = QFileDialog.getExistingDirectory(self, tr("选择输出目录", "Pick output folder"))
        if d:
            self.ed_out.setText(d)

    def _open_out_dir(self):
        """在系统文件管理器中打开输出目录。"""
        d = self.ed_out.text().strip()
        if not d or not os.path.isdir(d):
            toast.show_warning(self, tr("输出目录不存在，请先选择有效目录",
                                        "Output folder does not exist"))
            return
        try:
            if os.name == "nt":
                os.startfile(d)  # noqa: S606 - Windows 专用
            else:
                import subprocess
                subprocess.Popen(["xdg-open", d])
        except OSError as exc:
            toast.show_error(self, tr("无法打开输出目录", "Cannot open folder")
                             + f": {exc}")

    def _run(self):
        out_dir = self.ed_out.text().strip()
        if not out_dir or not os.path.isdir(out_dir):
            toast.show_warning(self, tr("请先选择有效的输出目录",
                                        "Pick a valid output folder first"))
            return
        from core.phantom_tank import decode_phantom, make_phantom
        mode = self.sg_mode.currentRouteKey()
        try:
            if mode == "make":
                w = self.ed_white.text().strip()
                b = self.ed_black.text().strip()
                if not w or not os.path.isfile(w):
                    toast.show_warning(self, tr("请选择白底图", "Pick the light image"))
                    return
                if not b or not os.path.isfile(b):
                    toast.show_warning(self, tr("请选择黑底图", "Pick the dark image"))
                    return
                out = os.path.join(out_dir, "幻影坦克.png")
                make_phantom(w, b, out)
                self.lb_status.setText(tr("已生成", "Made") + f"  {out}")
                toast.show_success(self, tr("幻影坦克已生成", "Phantom tank created")
                                   + f"  {os.path.basename(out)}")
            else:
                s = self.ed_src.text().strip()
                if not s or not os.path.isfile(s):
                    toast.show_warning(self, tr("请选择幻影坦克 PNG",
                                                "Pick the phantom tank PNG"))
                    return
                base = os.path.splitext(os.path.basename(s))[0]
                wo = os.path.join(out_dir, f"{base}_白底.png")
                bo = os.path.join(out_dir, f"{base}_黑底.png")
                decode_phantom(s, wo, bo)
                self.lb_status.setText(
                    tr("已解密", "Decoded") + f"  {wo} / {os.path.basename(bo)}")
                toast.show_success(self, tr("幻影坦克已解密", "Phantom tank decoded"))
        except Exception as exc:  # noqa: BLE001
            toast.show_error(self, tr("处理失败", "Failed") + f": {exc}")

    def collect_prefs(self) -> dict:
        """记忆模式/颜色/源图/输出目录，重进面板自动恢复。"""
        return {"mode": self.sg_mode.currentRouteKey(),
                "white": self.ed_white.text().strip(),
                "black": self.ed_black.text().strip(),
                "src": self.ed_src.text().strip(),
                "out": self.ed_out.text().strip()}

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        mode = prefs.get("mode")
        if mode in self.sg_mode.items:
            self.sg_mode.setCurrentItem(mode)
        for k in ("white", "black", "src", "out"):
            v = prefs.get(k)
            if v:
                getattr(self, f"ed_{k}").setText(v)

