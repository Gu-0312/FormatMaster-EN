"""monitor_panel — 文件夹监视 + 剪贴板监视自动转换面板。

- 文件夹监视：QTimer 轮询监视目录，发现新文件自动提交转换任务
- 剪贴板监视：监听系统剪贴板，复制图片或文件自动转换（与文件夹监视
  共用目标类型/格式选择）
"""
import hashlib
import os

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout,
                               QLabel)
from qfluentwidgets import (CaptionLabel, ComboBox, FluentIcon, LineEdit,
                            PrimaryPushButton, PushButton)

from gui_qt.components import toast
from gui_qt.i18n import tr
from gui_qt.components.form_widgets import FormSection
from gui_qt.panels.base_panel import BaseQtPanel

# 剪贴板图片动作：仅保存 / OCR 识别 / 保存并 OCR
CLIP_ACTIONS = [
    (tr("仅保存图片", "Save image"), "save"),
    (tr("OCR 识别文字", "OCR text"), "ocr"),
    (tr("保存并 OCR", "Save + OCR"), "save_ocr"),
]


class _OcrWorker(QThread):
    """后台 OCR：RapidOCR 推理耗时，不能阻塞 UI 线程。"""

    sig_done = Signal(str, bool)   # (输出 txt 路径, 是否成功)

    def __init__(self, img_path, out_path, parent=None):
        super().__init__(parent)
        self._img = img_path
        self._out = out_path

    def run(self):
        from core.ocr_tool import ocr_to_file
        try:
            ok = ocr_to_file(self._img, self._out)
        except Exception:  # noqa: BLE001
            ok = False
        self.sig_done.emit(self._out, ok)

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"}
AUDIO_EXTS = {".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".webp"}
DOC_EXTS = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv", ".txt",
            ".pptx", ".ppt", ".md", ".html", ".epub", ".rtf", ".odt", ".ofd"}

# 输入扩展名按类型分组（监视时只转换匹配新文件）
INPUT_EXTS = {"video": VIDEO_EXTS, "audio": AUDIO_EXTS,
              "image": IMAGE_EXTS, "doc": DOC_EXTS}

# 目标格式：类型 → [(显示名, 输出扩展名, 音频/视频编码器或 None), ...]
KIND_LABELS = {"video": tr("视频", "Video"),
               "audio": tr("音频", "Audio"),
               "image": tr("图片", "Image"),
               "doc": tr("文档", "Docs")}
FORMAT_OPTIONS = {
    "video": [
        ("MP4", "mp4", None),
        ("MKV", "mkv", None),
        ("AVI", "avi", None),
        ("MOV", "mov", None),
        ("WebM", "webm", "libvpx-vp9"),   # WebM 不支持 H.264，需显式 VP9
    ],
    "audio": [
        ("MP3", "mp3", "mp3"),
        ("WAV", "wav", "pcm_s16le"),
        ("AAC", "aac", "aac"),
        ("FLAC", "flac", "flac"),
        ("OGG", "ogg", "libvorbis"),
        ("M4A", "m4a", "aac"),
    ],
    "image": [
        ("PNG", "png", None),
        ("JPG", "jpg", None),
        ("WebP", "webp", None),
        ("BMP", "bmp", None),
    ],
    "doc": [
        ("PDF", "pdf", None),
        ("DOCX", "docx", None),
        ("TXT", "txt", None),
        ("MD", "md", None),
    ],
}


class MonitorPanelPage(BaseQtPanel):
    """文件夹监视页。"""

    panel_key = "monitor"

    def __init__(self, window, services, parent=None):
        self._timer = QTimer()
        self._seen = set()
        self._converted = 0
        self._running = False
        self._clip_running = False
        self._seen_clip_files = set()   # 剪贴板已处理文件
        self._seen_img_keys = []        # 剪贴板已处理图片 hash（最近 200）
        super().__init__(window, services, parent)

    def build(self):
        lay = self.content_layout
        lay.addWidget(self.make_title(tr("文件夹监视", "Folder Watch")))
        lay.addWidget(CaptionLabel(
            tr("监视指定文件夹，新放入的文件自动转换为目标格式", "Watch a folder and auto-convert new files")))

        # 监视目录 + 目标格式
        sec = FormSection(tr("监视设置", "Watch Settings"), FluentIcon.FOLDER_ADD)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(CaptionLabel(tr("监视目录", "Watch folder")))
        self.ed_dir = LineEdit()
        self.ed_dir.setPlaceholderText(tr("选择要监视的文件夹…", "Pick a folder to watch…"))
        self.ed_dir.setReadOnly(True)
        self.btn_browse = PushButton(FluentIcon.FOLDER, tr("浏览", "Browse"))
        self.btn_browse.clicked.connect(self._pick_dir)
        row.addWidget(self.ed_dir, 1)
        row.addWidget(self.btn_browse)
        sec.add_layout(row)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(CaptionLabel(tr("目标类型", "Target type")))
        self.cb_kind = ComboBox()
        self.cb_kind.addItems([KIND_LABELS[k] for k in FORMAT_OPTIONS])
        row2.addWidget(self.cb_kind)
        row2.addWidget(CaptionLabel(tr("目标格式", "Target format")))
        self.cb_fmt = ComboBox()
        row2.addWidget(self.cb_fmt)
        row2.addStretch(1)
        sec.add_layout(row2)
        lay.addWidget(sec)

        # 开始/停止 + 状态
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)
        self.btn_toggle = PrimaryPushButton(FluentIcon.PLAY, tr("开始监视", "Start"))
        self.btn_toggle.clicked.connect(self._toggle)
        ctrl.addWidget(self.btn_toggle)
        self.status_label = CaptionLabel(tr("未监视", "Not watching"))
        self.status_label.setStyleSheet(
            f"color: {self._ink_sec()};")
        ctrl.addWidget(self.status_label)
        ctrl.addStretch(1)
        lay.addLayout(ctrl)

        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._scan)
        self.cb_kind.currentIndexChanged.connect(self._kind_changed)
        self._kind_changed()

        # ── 剪贴板监视（同页，共用目标类型/格式）──
        clip_sec = FormSection(
            tr("剪贴板监视", "Clipboard Watch"), FluentIcon.PASTE)
        clip_hint = CaptionLabel(
            tr("复制图片或文件后自动转换为所选格式（输出到下方目录）",
               "Copy an image or file, it auto-converts to the target format"))
        clip_hint.setWordWrap(True)
        clip_hint.setStyleSheet(
            f"font-size: 12px; color: {self._ink_sec()};")
        clip_sec.add_widget(clip_hint)

        clip_row = QHBoxLayout()
        clip_row.setSpacing(8)
        clip_row.addWidget(CaptionLabel(tr("输出目录", "Output folder")))
        self.ed_clip_dir = LineEdit()
        self.ed_clip_dir.setText(os.path.join(
            os.path.expanduser("~"), "Desktop"))
        self.ed_clip_dir.setPlaceholderText(
            tr("选择或输入剪贴板输出目录…", "Pick or type the output folder…"))
        self.btn_clip_browse = PushButton(
            FluentIcon.FOLDER, tr("浏览", "Browse"))
        self.btn_clip_browse.clicked.connect(self._pick_clip_dir)
        clip_row.addWidget(self.ed_clip_dir, 1)
        clip_row.addWidget(self.btn_clip_browse)
        clip_sec.add_layout(clip_row)

        # 剪贴板独立的「目标类型 + 目标格式」（不跟文件夹监视共用）
        clip_fmt = QHBoxLayout()
        clip_fmt.setSpacing(8)
        clip_fmt.addWidget(CaptionLabel(tr("目标类型", "Target type")))
        self.cb_clip_kind = ComboBox()
        self.cb_clip_kind.addItems([KIND_LABELS[k] for k in FORMAT_OPTIONS])
        clip_fmt.addWidget(self.cb_clip_kind)
        clip_fmt.addWidget(CaptionLabel(tr("目标格式", "Target format")))
        self.cb_clip_fmt = ComboBox()
        clip_fmt.addWidget(self.cb_clip_fmt)
        clip_fmt.addStretch(1)
        clip_sec.add_layout(clip_fmt)
        self.cb_clip_kind.currentIndexChanged.connect(self._clip_kind_changed)
        self._clip_kind_changed()

        clip_act = QHBoxLayout()
        clip_act.setSpacing(8)
        clip_act.addWidget(CaptionLabel(tr("截图动作", "Image action")))
        self.cb_clip_act = ComboBox()
        self.cb_clip_act.addItems([a[0] for a in CLIP_ACTIONS])
        self.cb_clip_act.setToolTip(
            tr("复制截图后自动执行的动作", "Action after copying an image"))
        clip_act.addWidget(self.cb_clip_act)
        clip_act.addStretch(1)
        clip_sec.add_layout(clip_act)

        clip_ctrl = QHBoxLayout()
        clip_ctrl.setSpacing(8)
        self.btn_clip_toggle = PrimaryPushButton(
            FluentIcon.PLAY, tr("开始剪贴板监视", "Start Clipboard Watch"))
        self.btn_clip_toggle.clicked.connect(self._toggle_clip)
        clip_ctrl.addWidget(self.btn_clip_toggle)
        self.clip_status = CaptionLabel(tr("未监视剪贴板", "Clipboard idle"))
        self.clip_status.setStyleSheet(
            f"color: {self._ink_sec()};")
        clip_ctrl.addWidget(self.clip_status)
        clip_ctrl.addStretch(1)
        clip_sec.add_layout(clip_ctrl)
        lay.addWidget(clip_sec)

    def _kind_changed(self):
        """大类切换 → 更新目标格式下拉选项。"""
        kind = list(FORMAT_OPTIONS)[self.cb_kind.currentIndex()]
        self.cb_fmt.clear()
        self.cb_fmt.addItems([opt[0] for opt in FORMAT_OPTIONS[kind]])

    def _clip_kind_changed(self):
        """剪贴板监视独立的目标类型切换 → 联动格式下拉。"""
        kind = list(FORMAT_OPTIONS)[self.cb_clip_kind.currentIndex()]
        self.cb_clip_fmt.clear()
        self.cb_clip_fmt.addItems([opt[0] for opt in FORMAT_OPTIONS[kind]])

    def _clip_target(self):
        """剪贴板监视独立的目标 (kind, ext, codec)。"""
        kind = list(FORMAT_OPTIONS)[self.cb_clip_kind.currentIndex()]
        _label, ext, codec = FORMAT_OPTIONS[kind][self.cb_clip_fmt.currentIndex()]
        return kind, ext, codec

    def _ink_sec(self):
        from gui_qt.components import design_system as ds
        return ds.ink_sec()

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, tr("选择监视目录", "Pick watch folder"))
        if d:
            self.ed_dir.setText(d)

    def _toggle(self):
        d = self.ed_dir.text().strip()
        if not d or not os.path.isdir(d):
            toast.show_warning(self, tr("请先选择有效的监视目录", "Pick a valid folder first"))
            return
        if self._running:
            self._stop()
        else:
            self._start(d)

    def _start(self, d):
        self._running = True
        self._dir = d
        # 初始快照：已存在的文件不转换
        kind, _ext, _codec = self._target()
        exts = INPUT_EXTS[kind]
        self._seen = {f for f in self._list_files(d) if f.lower().endswith(tuple(exts))}
        self._timer.start()
        self.btn_toggle.setText(tr("停止监视", "Stop watch"))
        self.btn_toggle.setIcon(FluentIcon.CANCEL)
        self.status_label.setText(tr("监视中：{}", "Watching: {}").format(os.path.basename(d)))
        toast.show_success(self, tr("开始监视文件夹", "Now watching folder"))

    def _stop(self):
        self._running = False
        self._timer.stop()
        self.btn_toggle.setText(tr("开始监视", "Start watch"))
        self.btn_toggle.setIcon(FluentIcon.PLAY)
        self.status_label.setText(tr("已停止（本次转换 {} 个文件）", "Stopped (converted {} files)").format(self._converted))

    def _target(self):
        kind = list(FORMAT_OPTIONS)[self.cb_kind.currentIndex()]
        _label, ext, codec = FORMAT_OPTIONS[kind][self.cb_fmt.currentIndex()]
        return kind, ext, codec

    def _list_files(self, d):
        try:
            return [os.path.join(d, f) for f in os.listdir(d)
                    if os.path.isfile(os.path.join(d, f))]
        except OSError:
            return []

    def _scan(self):
        if not self._running:
            return
        kind, _ext, _codec = self._target()
        exts = INPUT_EXTS[kind]
        now = {f for f in self._list_files(self._dir)
               if f.lower().endswith(tuple(exts))}
        new = now - self._seen
        for f in sorted(new):
            self._convert(f)
        self._seen = now

    def _convert(self, path):
        kind, ext, codec = self._target()
        self._submit_conversion(kind, ext, codec, path, self._dir)

    def _submit_conversion(self, kind, ext, codec, path, out_dir):
        """把单个文件提交为转换任务（文件夹/剪贴板监视共用）。"""
        mgr = self.services.task_manager
        out = os.path.join(out_dir,
                           os.path.splitext(os.path.basename(path))[0]
                           + f".{ext}")
        label = ext.upper()
        if kind == "video":
            # WebM 等需要特定编码器（选项里已配置，如 libvpx-vp9）
            vcodec = codec

            def runner(task, prog):
                return self.services.video_conv.convert(
                    task.file_path, task.output_path, ext, codec=vcodec,
                    progress_callback=prog)
            mgr.add_task(name=tr("监视转换", "Watch & convert"), task_type="monitor",
                         file_path=path, output_path=out, params={},
                         runner=runner, need_ffmpeg=True,
                         history_type=tr("文件夹监视", "Folder Watch"),
                         history_target=label)
        elif kind == "audio":

            def runner(task, prog):
                return self.services.audio_conv.convert(
                    task.file_path, task.output_path, codec,
                    progress_callback=prog)
            mgr.add_task(name=tr("监视转换", "Watch & convert"), task_type="monitor",
                         file_path=path, output_path=out, params={},
                         runner=runner, need_ffmpeg=True,
                         history_type=tr("文件夹监视", "Folder Watch"),
                         history_target=label)
        elif kind == "doc":

            def runner(task, prog):
                return self.services.doc_conv.convert(
                    task.file_path, task.output_path, progress_callback=prog)
            mgr.add_task(name=tr("监视转换", "Watch & convert"), task_type="monitor",
                         file_path=path, output_path=out, params={},
                         runner=runner, need_ffmpeg=False,
                         history_type=tr("文件夹监视", "Folder Watch"),
                         history_target=label)
        else:

            def runner(task, prog):
                return self.services.image_conv.convert(
                    task.file_path, task.output_path, progress_callback=prog)
            mgr.add_task(name=tr("监视转换", "Watch & convert"), task_type="monitor",
                         file_path=path, output_path=out, params={},
                         runner=runner, need_ffmpeg=False,
                         history_type=tr("文件夹监视", "Folder Watch"),
                         history_target=label)
        self._converted += 1

    # ── 剪贴板监视 ──────────────────────────────
    def _pick_clip_dir(self):
        d = QFileDialog.getExistingDirectory(
            self, tr("选择剪贴板输出目录", "Pick clipboard output folder"))
        if d:
            self.ed_clip_dir.setText(d)

    def _toggle_clip(self):
        if self._clip_running:
            self._stop_clip()
        else:
            self._start_clip()

    def _start_clip(self):
        d = self.ed_clip_dir.text().strip()
        if not d or not os.path.isdir(d):
            toast.show_warning(self, tr("请先选择有效的剪贴板输出目录",
                                        "Pick a valid output folder first"))
            return
        self._clip_running = True
        self._clip = QApplication.clipboard()
        self._clip.dataChanged.connect(self._on_clip_changed)
        self.btn_clip_toggle.setText(tr("停止剪贴板监视", "Stop Clipboard Watch"))
        self.btn_clip_toggle.setIcon(FluentIcon.CANCEL)
        self.clip_status.setText(tr("监视剪贴板中：复制即转", "Watching clipboard"))
        toast.show_success(self, tr("开始剪贴板监视", "Now watching clipboard"))

    def _stop_clip(self):
        self._clip_running = False
        try:
            self._clip.dataChanged.disconnect(self._on_clip_changed)
        except (RuntimeError, TypeError):
            pass
        self.btn_clip_toggle.setText(tr("开始剪贴板监视", "Start Clipboard Watch"))
        self.btn_clip_toggle.setIcon(FluentIcon.PLAY)
        self.clip_status.setText(tr("已停止剪贴板监视", "Clipboard idle"))

    def _on_clip_changed(self):
        if not self._clip_running:
            return
        try:
            mime = self._clip.mimeData()
        except RuntimeError:
            return
        if mime is None:
            return
        out_dir = self.ed_clip_dir.text().strip()
        if not os.path.isdir(out_dir):
            return
        kind, ext, codec = self._clip_target()
        # ① 剪贴板图片 → 按所选动作处理
        if kind == "image" and mime.hasImage():
            img = self._clip.image()
            if not img.isNull() and self._clip_img_new(img):
                self._save_clip_image(img, ext, out_dir)
            return
        # ② 剪贴板文件 → 匹配类型则转换
        if mime.hasUrls():
            for url in mime.urls():
                if not url.isLocalFile():
                    continue
                fp = url.toLocalFile()
                if not os.path.isfile(fp):
                    continue
                if not fp.lower().endswith(tuple(INPUT_EXTS[kind])):
                    continue
                if fp in self._seen_clip_files:
                    continue
                self._seen_clip_files.add(fp)
                self._submit_conversion(kind, ext, codec, fp, out_dir)
                toast.show_success(
                    self, tr("剪贴板文件已加入转换", "Clipboard file converting")
                    + f"  {os.path.basename(fp)}")

    def _clip_img_new(self, img):
        """按缩小图 hash 去重剪贴板图片。"""
        small = img.scaled(32, 32, Qt.KeepAspectRatio)
        small = small.convertToFormat(QImage.Format_RGBA8888)
        try:
            key = hashlib.md5(bytes(small.bits())).hexdigest()
        except Exception:  # noqa: BLE001
            return False
        if key in self._seen_img_keys:
            return False
        self._seen_img_keys.append(key)
        if len(self._seen_img_keys) > 200:
            self._seen_img_keys = self._seen_img_keys[-200:]
        return True

    def _save_clip_image(self, img, ext, out_dir):
        """按「截图动作」处理剪贴板图片：保存 / OCR / 保存并 OCR。"""
        name = tr("剪贴板", "clipboard")
        seq = self._converted + 1
        action = CLIP_ACTIONS[self.cb_clip_act.currentIndex()][1]
        need_save = action in ("save", "save_ocr")
        img_path = ""
        if need_save:
            path = os.path.join(out_dir, f"{name}_{seq}.{ext}")
            fmt = "jpg" if ext == "jpg" else ext
            if img.save(path, fmt):
                self._converted += 1
                img_path = path
                toast.show_success(
                    self, tr("剪贴板图片已转换", "Clipboard image converted")
                    + f"  {os.path.basename(path)}")
        if action in ("ocr", "save_ocr"):
            if not img_path:
                img_path = os.path.join(out_dir, f"{name}_{seq}.png")
                img.save(img_path, "png")
            out_txt = os.path.splitext(img_path)[0] + ".txt"
            self.clip_status.setText(tr("正在识别截图文字…", "OCR in progress…"))
            self._ocr_worker = _OcrWorker(img_path, out_txt, self)
            self._ocr_worker.sig_done.connect(self._on_ocr_done)
            self._ocr_worker.start()

    def _on_ocr_done(self, out_txt, ok):
        if not self._clip_running:
            return
        if ok and os.path.isfile(out_txt):
            self.clip_status.setText(tr("OCR 完成", "OCR done"))
            toast.show_success(
                self, tr("截图文字已识别", "Clipboard text recognized")
                + f"  {os.path.basename(out_txt)}")
        else:
            self.clip_status.setText(tr("OCR 未识别到文字", "OCR no text"))
            toast.show_warning(self, tr("OCR 未识别到文字", "No text recognized"))
