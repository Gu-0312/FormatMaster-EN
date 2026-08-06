"""pdf_panel — PDF 工具面板（阶段2 迁移自 gui/panels/pdf_panel.py）。

9 种操作模式：合并/拆分/按页提取/加密/解密/压缩/添加水印/添加页码/转为图片。
各模式独立子区，随模式切换显隐；任务经 TaskManager 通用链路执行
core.tools / core.pdf_extract / core.pdf_to_image（不依赖 FFmpeg）。
顶部入口按钮可跳转到 PDF编辑（pdf_editor_panel）可视化编辑页。
"""
import os

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (FluentIcon, CaptionLabel, CheckBox, ComboBox,
                            LineEdit, PasswordLineEdit, PushButton,
                            SegmentedWidget)

from core.tools import (pdf_add_page_numbers, pdf_add_watermark, pdf_compress,
                        pdf_decrypt, pdf_encrypt, pdf_merge, pdf_split)
from gui_qt import task_manager as tm
from gui_qt.components import toast
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt.panels.task_mixin import TaskPanelMixin
from gui_qt.widgets import ActionBar, FileListCard, OutputDirRow

MODE_VALUES = [
    "合并（多个→一个）",
    "拆分（一个→多个）",
    "按页提取",
    "加密（设置密码）",
    "解密（移除密码）",
    "压缩",
    "添加水印",
    "添加页码",
    "转为图片",
    "填写表单",
]

# 模式分段选择器：routeKey(完整模式名) → 短标签（SegmentedWidget 展示）
MODE_SHORT_LABELS = [
    ("合并（多个→一个）", "合并"),
    ("拆分（一个→多个）", "拆分"),
    ("按页提取", "按页提取"),
    ("压缩", "压缩"),
    ("转为图片", "转图片"),
    ("加密（设置密码）", "加密"),
    ("解密（移除密码）", "解密"),
    ("添加水印", "水印"),
    ("添加页码", "页码"),
    ("填写表单", "填写表单"),
]


def _parse_ranges(range_str):
    """「1-3,5,7-10」→ [(1,3),(5,5),(7,10)]（与 tkinter 版 _go 一致）。"""
    ranges = []
    for part in (range_str or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            s, e = part.split("-", 1)
            ranges.append((int(s.strip()), int(e.strip())))
        else:
            ranges.append((int(part), int(part)))
    return ranges


class PdfPanelPage(BaseQtPanel, TaskPanelMixin):
    """PDF 工具页。"""

    panel_key = "pdf"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title("PDF处理"))
        lay.addWidget(CaptionLabel("合并、拆分、提取、加密、解密、压缩、水印、页码、转图片"))

        # 编辑器入口：跳转 PDF编辑 导航页（对应 tkinter 版「编辑器」按钮）
        entry_row = QHBoxLayout()
        entry_row.setSpacing(8)
        self.btn_editor = PushButton("📝 PDF可视化编辑")
        self.btn_editor.clicked.connect(self._open_editor_page)
        entry_row.addWidget(self.btn_editor)
        entry_row.addStretch(1)
        lay.addLayout(entry_row)

        self.file_card = FileListCard("文件列表", file_exts={".pdf"})
        lay.addWidget(self.file_card)
        self.file_card.set_target_fmt("PDF")

        lay.addWidget(self._build_settings_card())

        from gui_qt.components.form_widgets import FormSection
        out_card = FormSection("输出目录", FluentIcon.FOLDER)
        self.out_row = OutputDirRow()
        self.out_row.bind_file_list(self.file_card)
        out_card.add_widget(self.out_row)
        lay.addWidget(out_card)

        self.action_bar = ActionBar("开始处理")
        lay.addWidget(self.action_bar)

        self._mode_changed()
        self._wire_tasks()

    def _build_settings_card(self):
        from gui_qt.components.form_widgets import FormSection

        sec = FormSection("操作设置", FluentIcon.SETTING)

        # 模式行：分段选择器（10 个短标签，routeKey 为完整模式名）
        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        mode_row.addWidget(CaptionLabel("操作模式"))
        self.cb_mode = SegmentedWidget()
        for full, label in MODE_SHORT_LABELS:
            self.cb_mode.addItem(full, label)
        self.cb_mode.setCurrentItem("合并（多个→一个）")
        self.cb_mode.currentItemChanged.connect(
            lambda _key: self._mode_changed())
        mode_row.addWidget(self.cb_mode, 1)
        sec.add_layout(mode_row)

        # 各模式子区（随模式显隐）
        # 主选项直接展示；高级选项（加密/解密/水印/页码/表单）默认折叠
        self.sec_split = self._build_split_section()
        self.sec_encrypt = self._build_encrypt_section()
        self.sec_decrypt = self._build_decrypt_section()
        self.sec_compress = self._build_compress_section()
        self.sec_wm = self._build_watermark_section()
        self.sec_pn = self._build_page_number_section()
        self.sec_img = self._build_to_image_section()
        self.sec_form = self._build_form_section()
        for w in (self.sec_split, self.sec_compress, self.sec_img):
            sec.add_widget(w)

        # 高级选项折叠区
        self.adv_toggle = CheckBox("高级选项（加密 / 解密 / 水印 / 页码 / 填写表单）")
        self.adv_toggle.toggled.connect(self._toggle_advanced)
        sec.add_widget(self.adv_toggle)
        self.adv_box = QWidget()
        self.adv_box.setVisible(False)
        _adv = QVBoxLayout(self.adv_box)
        _adv.setContentsMargins(0, 0, 0, 0)
        _adv.setSpacing(10)
        for w in (self.sec_encrypt, self.sec_decrypt, self.sec_wm,
                  self.sec_pn, self.sec_form):
            _adv.addWidget(w)
        sec.add_widget(self.adv_box)
        return sec

    def _toggle_advanced(self, checked):
        """展开/收起高级选项区。"""
        self.adv_box.setVisible(checked)
        if checked:
            # 展开时按当前模式显示对应子区
            self._mode_changed()
        else:
            # 收起时隐藏全部高级子区
            for w in (self.sec_encrypt, self.sec_decrypt, self.sec_wm,
                      self.sec_pn, self.sec_form):
                w.setVisible(False)

    def _row_widget(self, builder):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        builder(h)
        h.addStretch(1)
        return w

    def _build_split_section(self):
        def build(h):
            h.addWidget(CaptionLabel("页码范围"))
            self.ed_range = LineEdit()
            self.ed_range.setText("1-3,5,7-10")
            self.ed_range.setFixedWidth(180)
            h.addWidget(self.ed_range)
            h.addWidget(CaptionLabel("示例: 1-3,5,7-10"))
            self.cb_extract_mode = ComboBox()
            self.cb_extract_mode.addItems(["按范围提取", "每页一个文件", "指定页码"])
            self.cb_extract_mode.setCurrentIndex(0)
            h.addWidget(self.cb_extract_mode)
        return self._row_widget(build)

    def _build_encrypt_section(self):
        def build(h):
            h.addWidget(CaptionLabel("打开密码"))
            self.ed_open_pwd = PasswordLineEdit()
            self.ed_open_pwd.setFixedWidth(160)
            h.addWidget(self.ed_open_pwd)
            h.addWidget(CaptionLabel("权限密码"))
            self.ed_owner_pwd = PasswordLineEdit()
            self.ed_owner_pwd.setFixedWidth(160)
            h.addWidget(self.ed_owner_pwd)
            h.addWidget(CaptionLabel("加密方式"))
            self.cb_encrypt_method = ComboBox()
            self.cb_encrypt_method.addItems(["AES-256", "AES-128"])
            self.cb_encrypt_method.setCurrentIndex(0)
            h.addWidget(self.cb_encrypt_method)
        return self._row_widget(build)

    def _build_decrypt_section(self):
        def build(h):
            h.addWidget(CaptionLabel("输入密码"))
            self.ed_decrypt_pwd = PasswordLineEdit()
            self.ed_decrypt_pwd.setFixedWidth(240)
            h.addWidget(self.ed_decrypt_pwd)
        return self._row_widget(build)

    def _build_compress_section(self):
        def build(h):
            h.addWidget(CaptionLabel("目标分辨率"))
            self.cb_compress_dpi = ComboBox()
            self.cb_compress_dpi.addItems(["72dpi", "100dpi", "150dpi", "200dpi"])
            self.cb_compress_dpi.setCurrentText("150dpi")
            h.addWidget(self.cb_compress_dpi)
            h.addWidget(CaptionLabel("图片质量"))
            self.cb_compress_quality = ComboBox()
            self.cb_compress_quality.addItems(["60", "70", "80", "90"])
            self.cb_compress_quality.setCurrentText("80")
            h.addWidget(self.cb_compress_quality)
        return self._row_widget(build)

    def _build_watermark_section(self):
        def build(h):
            h.addWidget(CaptionLabel("水印文字"))
            self.ed_wm_text = LineEdit()
            self.ed_wm_text.setText("机密")
            self.ed_wm_text.setFixedWidth(140)
            h.addWidget(self.ed_wm_text)
            h.addWidget(CaptionLabel("位置"))
            self.cb_wm_pos = ComboBox()
            self.cb_wm_pos.addItems(["左上角", "右上角", "左下角", "右下角", "居中"])
            self.cb_wm_pos.setCurrentText("居中")
            h.addWidget(self.cb_wm_pos)
            h.addWidget(CaptionLabel("透明度"))
            self.cb_wm_opacity = ComboBox()
            self.cb_wm_opacity.addItems(["0.1", "0.2", "0.3", "0.5", "0.7", "0.9"])
            self.cb_wm_opacity.setCurrentText("0.3")
            h.addWidget(self.cb_wm_opacity)
            h.addWidget(CaptionLabel("旋转"))
            self.cb_wm_rotate = ComboBox()
            self.cb_wm_rotate.addItems(["0°", "45°", "90°"])
            self.cb_wm_rotate.setCurrentIndex(0)
            h.addWidget(self.cb_wm_rotate)
        return self._row_widget(build)

    def _build_page_number_section(self):
        def build(h):
            h.addWidget(CaptionLabel("起始页码"))
            self.ed_pn_start = LineEdit()
            self.ed_pn_start.setText("1")
            self.ed_pn_start.setFixedWidth(60)
            h.addWidget(self.ed_pn_start)
            h.addWidget(CaptionLabel("位置"))
            self.cb_pn_pos = ComboBox()
            self.cb_pn_pos.addItems(["底部居中", "底部左对齐", "底部右对齐", "顶部居中"])
            self.cb_pn_pos.setCurrentIndex(0)
            h.addWidget(self.cb_pn_pos)
            h.addWidget(CaptionLabel("格式"))
            self.ed_pn_fmt = LineEdit()
            self.ed_pn_fmt.setText("第{n}页")
            self.ed_pn_fmt.setFixedWidth(110)
            h.addWidget(self.ed_pn_fmt)
            h.addWidget(CaptionLabel("{n}=页码"))
        return self._row_widget(build)

    def _build_to_image_section(self):
        def build(h):
            h.addWidget(CaptionLabel("图片格式"))
            self.cb_img_fmt = ComboBox()
            self.cb_img_fmt.addItems(["PNG", "JPG"])
            self.cb_img_fmt.setCurrentIndex(0)
            h.addWidget(self.cb_img_fmt)
            h.addWidget(CaptionLabel("输出 DPI"))
            self.cb_img_dpi = ComboBox()
            self.cb_img_dpi.addItems(["72", "100", "150", "200", "300", "400", "600"])
            self.cb_img_dpi.setCurrentText("200")
            h.addWidget(self.cb_img_dpi)
            h.addWidget(CaptionLabel("页码范围"))
            self.ed_img_pages = LineEdit()
            self.ed_img_pages.setPlaceholderText("留空=全部  示例: 1-3,5,7")
            self.ed_img_pages.setFixedWidth(160)
            h.addWidget(self.ed_img_pages)
        return self._row_widget(build)

    def _build_form_section(self):
        """表单填写子区：检测字段 → 动态生成输入框。"""
        from PySide6.QtWidgets import QScrollArea, QVBoxLayout as VLAY
        from PySide6.QtWidgets import QWidget as QW

        w = QW()
        v = VLAY(w)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(4)

        self._lbl_form = CaptionLabel("点击「检测表单」读取 PDF 中的可填写字段")
        v.addWidget(self._lbl_form)

        self.btn_detect_form = PushButton(FluentIcon.SEARCH, "检测表单")
        self.btn_detect_form.clicked.connect(self._detect_form_fields)
        v.addWidget(self.btn_detect_form)

        # 字段容器（滚动区域）
        self._form_scroll = QScrollArea()
        self._form_scroll.setWidgetResizable(True)
        self._form_scroll.setMaximumHeight(200)
        self._form_scroll.setStyleSheet("background: transparent; border: none;")
        self._form_container = QW()
        self._form_layout = VLAY(self._form_container)
        self._form_layout.setContentsMargins(0, 0, 0, 0)
        self._form_layout.setSpacing(4)
        self._form_scroll.setWidget(self._form_container)
        v.addWidget(self._form_scroll, 1)

        self._form_fields = {}  # field_name -> LineEdit/ComboBox
        return w

    def _detect_form_fields(self):
        """检测当前文件的 PDF 表单字段。"""
        files = self.file_card.files()
        if not files:
            toast.show_warning(self, "请先添加 PDF 文件")
            return
        from core import pdf_form
        if not pdf_form.is_available():
            toast.show_error(self, "PyMuPDF 未安装，无法检测表单")
            return

        # 清空旧字段
        self._form_fields.clear()
        while self._form_layout.count():
            child = self._form_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        all_fields = []
        for f in files:
            fields = pdf_form.get_form_fields(f)
            for fd in fields:
                fd["_file"] = f
                all_fields.append(fd)

        if not all_fields:
            self._lbl_form.setText("未检测到可填写的表单字段")
            return

        self._lbl_form.setText(f"检测到 {len(all_fields)} 个字段：")
        for fd in all_fields:
            key = f"{fd['_file']}::{fd['name']}"
            row = QHBoxLayout()
            row.setSpacing(6)
            lbl = CaptionLabel(fd["name"])
            lbl.setFixedWidth(120)
            lbl.setToolTip(f"类型: {fd['type']}  页: {fd['page']}")
            row.addWidget(lbl)

            if fd["type"] == "checkbox":
                from qfluentwidgets import CheckBox
                cb = CheckBox()
                cb.setChecked(bool(fd["value"]))
                row.addWidget(cb)
                self._form_fields[key] = cb
            elif fd["type"] in ("combo", "list") and fd["options"]:
                cb = ComboBox()
                cb.addItems(fd["options"])
                if fd["value"] in fd["options"]:
                    cb.setCurrentText(fd["value"])
                cb.setFixedWidth(180)
                row.addWidget(cb)
                self._form_fields[key] = cb
            else:
                le = LineEdit()
                le.setText(str(fd["value"]))
                le.setFixedWidth(240)
                row.addWidget(le)
                self._form_fields[key] = le

            row.addStretch(1)
            w = QWidget()
            w.setLayout(row)
            self._form_layout.addWidget(w)

        self._form_layout.addStretch(1)
        self._detected_form_files = [f for f in files
                                     if any(fd["_file"] == f for fd in all_fields)]

    # ── 模式切换 ─────────────────────────────────
    _ADV_MODES = ("加密", "解密", "水印", "页码", "表单")

    def _mode_changed(self):
        mode = self.cb_mode.currentRouteKey()
        # 高级模式自动展开折叠区；主模式自动收起（blockSignals 防递归）
        is_adv = any(k in mode for k in self._ADV_MODES)
        if is_adv and not self.adv_toggle.isChecked():
            self.adv_toggle.blockSignals(True)
            self.adv_toggle.setChecked(True)
            self.adv_toggle.blockSignals(False)
            self.adv_box.setVisible(True)
        elif not is_adv and self.adv_toggle.isChecked():
            self.adv_toggle.blockSignals(True)
            self.adv_toggle.setChecked(False)
            self.adv_toggle.blockSignals(False)
            self.adv_box.setVisible(False)

        secs = (self.sec_split, self.sec_encrypt, self.sec_decrypt,
                self.sec_compress, self.sec_wm, self.sec_pn, self.sec_img,
                self.sec_form)
        for w in secs:
            w.setVisible(False)
        if "拆分" in mode or "提取" in mode:
            self.sec_split.setVisible(True)
        elif "加密" in mode:
            self.sec_encrypt.setVisible(True)
        elif "解密" in mode:
            self.sec_decrypt.setVisible(True)
        elif "压缩" in mode:
            self.sec_compress.setVisible(True)
        elif "水印" in mode:
            self.sec_wm.setVisible(True)
        elif "页码" in mode:
            self.sec_pn.setVisible(True)
        elif "转为图片" in mode:
            self.sec_img.setVisible(True)
        elif "表单" in mode:
            self.sec_form.setVisible(True)

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        return {
            "mode": self.cb_mode.currentRouteKey(),
            "range": self.ed_range.text().strip(),
            "extract_mode": self.cb_extract_mode.currentText(),
            "open_pwd": self.ed_open_pwd.text(),
            "owner_pwd": self.ed_owner_pwd.text(),
            "encrypt_method": self.cb_encrypt_method.currentText(),
            "decrypt_pwd": self.ed_decrypt_pwd.text(),
            "compress_dpi": self.cb_compress_dpi.currentText(),
            "compress_quality": self.cb_compress_quality.currentText(),
            "wm_text": self.ed_wm_text.text().strip(),
            "wm_pos": self.cb_wm_pos.currentText(),
            "wm_opacity": float(self.cb_wm_opacity.currentText()),
            "wm_rotate": int(self.cb_wm_rotate.currentText().replace("°", "")),
            "pn_start": int(self.ed_pn_start.text())
            if self.ed_pn_start.text().isdigit() else 1,
            "pn_pos": self.cb_pn_pos.currentText(),
            "pn_fmt": self.ed_pn_fmt.text(),
            "to_image_fmt": self.cb_img_fmt.currentText(),
            "to_image_dpi": int(self.cb_img_dpi.currentText()),
            "to_image_pages": self.ed_img_pages.text().strip(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
            "form_values": self._collect_form_values(),
        }

    def collect_prefs(self) -> dict:
        # 与 tkinter 版一致：仅持久化 mode + 输出目录
        return {
            "mode": self.cb_mode.currentRouteKey(),
            "out_dir_combo": self.out_row.mode(),
            "out_dir_path": self.out_row.path(),
        }

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        if prefs.get("mode") in MODE_VALUES:
            self.cb_mode.setCurrentItem(prefs["mode"])
            self._mode_changed()
        if prefs.get("out_dir_combo") == OutputDirRow.MODE_CUSTOM:
            self.out_row.set_state(OutputDirRow.MODE_CUSTOM,
                                   prefs.get("out_dir_path", ""))

    # ── 任务执行器 ───────────────────────────────
    def _runner(self, task, prog):
        p = task.params
        mode = p.get("mode", "")
        files_list = p.get("files") or [task.file_path]

        if "合并" in mode:
            return pdf_merge(files_list, task.output_path, prog)
        if "拆分" in mode:
            ranges = _parse_ranges(p.get("range", ""))
            if not ranges:
                task.error = "页码范围无效"
                return False
            return pdf_split(task.file_path, task.output_path, ranges, prog)
        if "提取" in mode:
            from core.pdf_extract import pdf_extract_pages
            em = p.get("extract_mode", "按范围提取")
            ex_mode = "each" if "每页" in em else ("selected" if "指定" in em else "range")
            return pdf_extract_pages(task.file_path, task.output_path, ex_mode,
                                     p.get("range", ""), prog)
        if "加密" in mode:
            if not p.get("open_pwd") and not p.get("owner_pwd"):
                task.error = "请至少设置一个密码"
                return False
            return pdf_encrypt(task.file_path, task.output_path,
                               p.get("open_pwd", ""), p.get("owner_pwd", ""),
                               p.get("encrypt_method", "AES-256"), prog)
        if "解密" in mode:
            return pdf_decrypt(task.file_path, task.output_path,
                               p.get("decrypt_pwd", ""), prog)
        if "压缩" in mode:
            dpi = int(p.get("compress_dpi", "150dpi").replace("dpi", ""))
            quality = int(p.get("compress_quality", "80"))
            return pdf_compress(task.file_path, task.output_path, dpi, quality, prog)
        if "水印" in mode:
            if not p.get("wm_text"):
                task.error = "水印文字不能为空"
                return False
            return pdf_add_watermark(task.file_path, task.output_path,
                                     text=p["wm_text"],
                                     pos=p.get("wm_pos", "居中"),
                                     opacity=p.get("wm_opacity", 0.3),
                                     rotation=p.get("wm_rotate", 0),
                                     progress_cb=prog)
        if "页码" in mode:
            return pdf_add_page_numbers(task.file_path, task.output_path,
                                        start=p.get("pn_start", 1),
                                        pos=p.get("pn_pos", "底部居中"),
                                        fmt=p.get("pn_fmt", "{n}"),
                                        progress_cb=prog)
        if "转为图片" in mode:
            from core.pdf_to_image import pdf_to_images
            ok, _saved = pdf_to_images(task.file_path, task.output_path,
                                       fmt=p.get("to_image_fmt", "PNG"),
                                       dpi=p.get("to_image_dpi", 200),
                                       pages=p.get("to_image_pages", ""),
                                       progress_cb=prog)
            return ok
        if "表单" in mode:
            from core.pdf_form import fill_form
            field_values = p.get("form_values", {})
            prog(10, "正在填写表单…")
            ok, msg = fill_form(task.file_path, task.output_path, field_values)
            if ok:
                prog(100, msg)
            else:
                task.error = msg
            return ok
        task.error = "未知操作模式"
        return False

    # ── 任务提交（合并为整批单任务）────────────────
    def _start(self):
        files = self.file_card.files()
        if not files:
            toast.show_warning(self, "请先添加 PDF 文件")
            return
        if self.out_row.mode() == OutputDirRow.MODE_CUSTOM and not self.out_row.path():
            toast.show_warning(self, "请先选择自定义输出目录")
            return

        mode = self.cb_mode.currentText()
        params = self.collect_params()
        if "水印" in mode and not params["wm_text"]:
            toast.show_warning(self, "水印文字不能为空")
            return
        self.save_prefs()
        mgr = self.services.task_manager

        if "合并" in mode:
            out_dir = self.out_row.resolve_dir(files[0])
            out_path = self._unique_path(os.path.join(out_dir, "merged.pdf"))
            params["files"] = list(files)
            tid = mgr.add_task(
                name=f"PDF合并 - {len(files)}个文件",
                task_type="pdf", file_path=files[0], output_path=out_path,
                params=params, runner=self._runner,
                history_type="PDF 处理", history_target="合并",
                need_ffmpeg=False)
            if tid is not None:
                self._task_rows[tid] = (files[0], -1)
                self.action_bar.set_running(True)
                self.action_bar.set_status("已提交合并任务")
            return

        # 其余模式：逐文件入队
        added = 0
        for f in files:
            kwargs = self._make_task(f)
            if kwargs is None:
                continue
            tid = mgr.add_task(**kwargs)
            if tid is not None:
                self._task_rows[tid] = (f, self.file_card.row_of_file(f))
                added += 1
        if added:
            self.action_bar.set_running(True)
            self.action_bar.set_status(f"已提交 {added} 个任务")
        else:
            toast.show_error(self, "任务提交失败")

    def _unique_path(self, path):
        """已存在时追加 _N 计数（与 make_output_path 行为一致）。"""
        if not os.path.exists(path):
            return path
        base, ext = os.path.splitext(path)
        counter = 1
        while os.path.exists(f"{base}_{counter}{ext}"):
            counter += 1
        return f"{base}_{counter}{ext}"

    def _make_task(self, f):
        params = self.collect_params()
        mode = params["mode"]
        nm = os.path.splitext(os.path.basename(f))[0]
        out_dir = self.out_row.resolve_dir(f)
        if "拆分" in mode:
            out_path = os.path.join(out_dir, nm + "_split")
            try:
                os.makedirs(out_path, exist_ok=True)
            except OSError:
                toast.show_error(self, f"无法创建输出目录：{out_path}")
                return None
        elif "提取" in mode:
            out_path = os.path.join(out_dir, nm + "_extract")
            try:
                os.makedirs(out_path, exist_ok=True)
            except OSError:
                toast.show_error(self, f"无法创建输出目录：{out_path}")
                return None
        elif "转为图片" in mode:
            out_path = os.path.join(out_dir, nm + "_images")
            try:
                os.makedirs(out_path, exist_ok=True)
            except OSError:
                toast.show_error(self, f"无法创建输出目录：{out_path}")
                return None
        elif "加密" in mode:
            out_path = self._unique_path(os.path.join(out_dir, nm + "_encrypted.pdf"))
        elif "解密" in mode:
            out_path = self._unique_path(os.path.join(out_dir, nm + "_decrypted.pdf"))
        elif "压缩" in mode:
            out_path = self._unique_path(os.path.join(out_dir, nm + "_compressed.pdf"))
        elif "表单" in mode:
            out_path = self._unique_path(os.path.join(out_dir, nm + "_filled.pdf"))
        else:
            out_path = self._unique_path(os.path.join(out_dir, nm + "_numbered.pdf"
                                                      if "页码" in mode
                                                      else nm + "_watermarked.pdf"))
        return dict(
            name=f"PDF处理 - {os.path.basename(f)}",
            task_type="pdf", file_path=f, output_path=out_path,
            params=params, runner=self._runner,
            history_type="PDF 处理", history_target=mode.split("（")[0],
            need_ffmpeg=False)

    def _open_editor_page(self):
        """跳转到 PDF编辑 导航页（对应 tkinter 版 _open_pdf_editor 弹窗）。"""
        # 优先用 MainWindow 挂载的 _switch_to(key)，回退到标准 switchTo
        page = getattr(self.window, "pages", {}).get("pdf_editor")
        if page is None:
            return
        switcher = getattr(self.window, "_switch_to", None)
        if callable(switcher):
            switcher("pdf_editor")
        else:
            self.window.switchTo(page)

    def _empty_hint(self):
        return "请先添加 PDF 文件"

    def _collect_form_values(self):
        """从 UI 控件中收集表单字段值。"""
        from qfluentwidgets import CheckBox as CB, ComboBox as Cb
        values = {}
        for key, widget in self._form_fields.items():
            field_name = key.split("::", 1)[1] if "::" in key else key
            if isinstance(widget, CB):
                values[field_name] = widget.isChecked()
            elif isinstance(widget, Cb):
                values[field_name] = widget.currentText()
            else:
                values[field_name] = widget.text()
        return values
