"""download_panel — 视频下载面板（阶段2 迁移自 gui/panels/download_panel.py + main.py 下载逻辑）。

URL 队列式下载（yt-dlp，core.video_downloader）：解析格式、添加/批量导入链接、
Cookie/代理/限速/仅音频等设置，任务经 TaskManager 通用链路串行执行。
"""
import os
import re

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QWidget,
                               QVBoxLayout)
from qfluentwidgets import (FluentIcon, CaptionLabel, CheckBox, ComboBox,
                            LineEdit, ListWidget, PrimaryPushButton, PushButton,
                            TextEdit)

from gui_qt.i18n import tr
from gui_qt.components import toast
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt import task_manager as tm
from gui_qt.widgets import ActionBar

# 预置值（与 tkinter 版 download_panel 一致）
SPEED_VALUES = [tr("不限", "Unlimited"), "2", "5", "10", "20", "50"]
AUDIO_FMT_VALUES = ["mp3", "m4a", "flac", "wav", "opus"]


def _clean_url(raw):
    """提取文本中的首个有效 URL（与 main.py:_clean_url 一致）。"""
    raw = raw.strip()
    m = re.search(r"https?://[^\s\u4e00-\u9fff\u3000-\u303f\uff00-\uffef<>\"']+", raw)
    if m:
        return m.group(0).rstrip(".,;:!?)")
    return re.sub(r"[^\x00-\x7f]", "", raw).strip()


class _ParseWorker(QThread):
    """后台解析视频格式（yt-dlp 联网，可能耗时）。"""

    sig_done = Signal(list, str, object)   # (formats, title, playlist)
    sig_fail = Signal(str)

    def __init__(self, url, cookie, proxy, parent=None):
        super().__init__(parent)
        self._url, self._cookie, self._proxy = url, cookie, proxy

    def run(self):
        try:
            from core.video_downloader import VideoDownloader
            dl = VideoDownloader()
            fmts, title, _thumb, playlist = dl.get_formats(self._url)
            self.sig_done.emit(fmts or [], title or "", playlist)
        except Exception as e:  # noqa: BLE001
            self.sig_fail.emit(str(e))


class DownloadPanelPage(BaseQtPanel):
    """视频下载页。"""

    panel_key = "download"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(self.make_title(tr("视频下载", "Video download")))
        head.addWidget(CaptionLabel(tr("支持 B站 / YouTube / 微博 / Instagram 等数百个平台", "Supports Bilibili / YouTube / Weibo / Instagram and hundreds of sites")))
        head.addStretch(1)
        lay.addLayout(head)

        # URL 输入区
        from gui_qt.components.form_widgets import FormSection, FormGrid
        card = FormSection(tr("链接与格式", "Link & format"), FluentIcon.EDIT)
        url_body = QWidget()
        vl = QVBoxLayout(url_body)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(8)
        self.txt_url = TextEdit()
        self.txt_url.setFixedHeight(64)
        self.txt_url.setPlaceholderText(tr("粘贴视频链接，每行一个，支持批量", "Paste video links, one per line"))
        self.txt_url.setAcceptRichText(False)
        from gui_qt.components import design_system as _ds
        _ds.apply_text_edit_style(self.txt_url)
        self._url_cleaning = False
        self.txt_url.textChanged.connect(self._check_douyin_tip)
        self.txt_url.installEventFilter(self)
        vl.addWidget(self.txt_url)
        brow = QHBoxLayout()
        brow.setSpacing(8)
        btn_parse = PushButton(tr("解析格式", "Parse formats"))
        btn_parse.clicked.connect(self._parse_url)
        btn_add = PrimaryPushButton(tr("添加链接", "Add link"))
        btn_add.clicked.connect(self._add_url)
        btn_import = PushButton(tr("📁 批量导入", "📁 Import batch"))
        btn_import.clicked.connect(self._batch_import)
        btn_fav = PushButton(tr("⭐ 收藏", "⭐ Favorite"))
        btn_fav.clicked.connect(self._add_favorite)
        btn_favs = PushButton(tr("⭐ 收藏夹", "⭐ Favorites"))
        btn_favs.clicked.connect(self._show_favorites)
        btn_hist = PushButton(tr("📋 历史", "📋 History"))
        btn_hist.clicked.connect(self._show_history)
        for b in (btn_parse, btn_add, btn_import):
            brow.addWidget(b)
        brow.addStretch(1)
        for b in (btn_hist, btn_favs, btn_fav):
            brow.addWidget(b)
        vl.addLayout(brow)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(CaptionLabel(tr("选择格式", "Format")))
        self.lst_formats = ListWidget()
        self.lst_formats.setFixedHeight(140)
        row.addWidget(self.lst_formats, 1)
        vl.addLayout(row)
        self.lb_fmt_info = CaptionLabel("")
        vl.addWidget(self.lb_fmt_info)
        card.add_widget(url_body)
        lay.addWidget(card)

        # 设置区
        set_card = FormSection(tr("下载设置", "Download settings"), FluentIcon.DOWNLOAD)
        grid = FormGrid(columns=3)

        self.ed_cookie = grid.add_field(
            "Cookie", self._line_edit(200, ""),
            hint=tr("登录 Cookie，用于访问受限资源", "Login cookie for restricted content"))
        self.ed_proxy = grid.add_field(
            tr("代理", "Proxy"), self._line_edit(150, ""),
            hint=tr("HTTP/HTTPS 代理地址", "HTTP/HTTPS proxy"))
        self.cb_speed = grid.add_field(
            tr("限速 MB/s", "Speed limit MB/s"), self._combo(SPEED_VALUES, tr("不限", "Unlimited")),
            hint=tr("下载速度上限，不限为 0", "Download speed limit, 0 = unlimited"))
        self.ed_headers = grid.add_field(
            "Header", self._line_edit(0, "Key:Val,Key:Val"),
            hint=tr("自定义请求头，逗号分隔", "Custom headers, comma separated"))
        self.ed_template = grid.add_field(
            tr("文件名模板", "Filename template"), self._line_edit(200, "留空=默认"),
            hint=tr("输出文件名模板，留空使用默认", "Output name template, blank = default"))
        r3 = QHBoxLayout()
        r3.setSpacing(8)
        self.cb_audio_only = CheckBox(tr("仅音频", "Audio only"))
        self.cb_audio_only.toggled.connect(self._toggle_audio)
        r3.addWidget(self.cb_audio_only)
        self.cb_audio_fmt = ComboBox()
        self.cb_audio_fmt.addItems(AUDIO_FMT_VALUES)
        self.cb_audio_fmt.setCurrentText("mp3")
        self.cb_audio_fmt.setEnabled(False)
        r3.addWidget(self.cb_audio_fmt)
        self.cb_subtitles = CheckBox(tr("下载字幕", "Download subtitles"))
        r3.addWidget(self.cb_subtitles)
        r3.addStretch(1)
        r3_box = QWidget()
        r3_box.setLayout(r3)
        grid.add_field("", r3_box, colspan=1)
        set_card.add_form(grid)
        lay.addWidget(set_card)

        # 保存目录
        drow = QHBoxLayout()
        drow.setSpacing(8)
        drow.addWidget(CaptionLabel(tr("保存到", "Save to")))
        self.ed_dir = LineEdit()
        self.ed_dir.setText(os.path.expanduser("~/Downloads"))
        drow.addWidget(self.ed_dir, 1)
        btn_browse = PushButton(tr("浏览", "Browse"))
        btn_browse.clicked.connect(self._browse_dir)
        drow.addWidget(btn_browse)
        btn_open_dir = PushButton(tr("打开文件夹", "Open folder"))
        btn_open_dir.clicked.connect(self._open_output_folder)
        drow.addWidget(btn_open_dir)
        lay.addLayout(drow)

        # 下载队列
        q_card = FormSection(tr("下载队列", "Download queue"), FluentIcon.MENU)
        q_body = QWidget()
        ql = QVBoxLayout(q_body)
        ql.setContentsMargins(0, 0, 0, 0)
        ql.setSpacing(8)
        qhead = QHBoxLayout()
        qhead.setSpacing(8)
        self.lb_count = CaptionLabel(tr("0 个任务", "0 tasks"))
        qhead.addStretch(1)
        qhead.addWidget(self.lb_count)
        ql.addLayout(qhead)
        self.lst_queue = ListWidget()
        self.lst_queue.setMinimumHeight(110)
        ql.addWidget(self.lst_queue)
        qbtn = QHBoxLayout()
        qbtn.setSpacing(8)
        b_up = PushButton(tr("▲ 上移", "▲ Up"))
        b_up.clicked.connect(lambda: self._move(-1))
        b_down = PushButton(tr("▼ 下移", "▼ Down"))
        b_down.clicked.connect(lambda: self._move(1))
        b_del = PushButton(tr("✕ 移除选中", "✕ Remove selected"))
        b_del.clicked.connect(self._remove_selected)
        b_clear = PushButton(tr("清空队列", "Clear queue"))
        b_clear.clicked.connect(self._clear_queue)
        for b in (b_up, b_down, b_del, b_clear):
            qbtn.addWidget(b)
        qbtn.addStretch(1)
        ql.addLayout(qbtn)
        q_card.add_widget(q_body)
        lay.addWidget(q_card)

        self.action_bar = ActionBar(tr("开始下载", "Download"))
        lay.addWidget(self.action_bar)

        # 运行态
        self._queue = []            # [{"url","name","fmt_id"}]
        self._formats = []
        self._title = ""
        self._dl_obj = None
        self._task_rows = {}        # task_id -> queue 行号
        self._worker = None
        mgr = self.services.task_manager
        mgr.sig_progress.connect(self._on_progress)
        mgr.sig_state.connect(self._on_state)
        self.action_bar.btn_go.clicked.connect(self._start)
        self.action_bar.btn_go.setEnabled(False)
        self.action_bar.btn_cancel.clicked.connect(self._cancel_all)

    # ── 表单辅助 ─────────────────────────────────
    def _combo(self, items, default):
        cb = ComboBox()
        cb.addItems(items)
        cb.setCurrentText(default)
        return cb

    def _line_edit(self, width, placeholder):
        ed = LineEdit()
        if width > 0:
            ed.setFixedWidth(width)
        if placeholder:
            ed.setPlaceholderText(placeholder)
        return ed

    # ── 事件过滤：粘贴时自动清理并提取 URL ──────────
    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication
        if (hasattr(self, 'txt_url') and obj is self.txt_url
                and event.type() == QEvent.KeyPress):
            from PySide6.QtCore import Qt
            if (event.key() == Qt.Key_V
                    and event.modifiers() & Qt.ControlModifier):
                clip = QApplication.clipboard()
                text = clip.text()
                if text:
                    import re
                    # 1. 清理不可见控制字符
                    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
                    # 2. 提取 URL（去除分享描述文本）
                    lines = cleaned.split("\n")
                    urls = []
                    for line in lines:
                        url = _clean_url(line)
                        if url:
                            urls.append(url)
                    if urls:
                        clip.setText("\n".join(urls))
                return False
        return super().eventFilter(obj, event)

    # ── URL 操作 ─────────────────────────────────
    def _check_douyin_tip(self):
        """检测到抖音/TikTok 链接时显示 Cookie 必填提示（仅首次）；内容清空/切换后自动复位。"""
        if not hasattr(self, '_douyin_tip_shown'):
            self._douyin_tip_shown = False
        text = self.txt_url.toPlainText()
        has_douyin = any(d in text.lower() for d in ("douyin.com", "tiktok.com", "v.douyin.com", "vt.tiktok.com"))
        # 无抖音链接时复位，允许下一次输入再次触发
        if not has_douyin:
            self._douyin_tip_shown = False
            return
        if self._douyin_tip_shown:
            return
        self._douyin_tip_shown = True
        from gui_qt.components import toast
        toast.show_warning(
            self,
            tr("检测到抖音/TikTok 链接\n", "Douyin/TikTok link detected\n")
 +
            tr("⚠ 平台强制要求有效 Cookie 才能解析\n", "⚠ The platform requires a valid cookie to parse\n")
 +
            tr("请在上方「Cookie」框粘贴浏览器完整 Cookie，\n", "Paste your full browser cookie in the \"Cookie\" field above,\n")
 +
            tr("或命令行启动：python main_qt.py --cookies-from-browser chrome", "or launch: python main_qt.py --cookies-from-browser chrome"),
            duration=8000
        )

    def _parse_url(self):
        url = _clean_url(self.txt_url.toPlainText())
        if not url:
            toast.show_warning(self, tr("未检测到有效URL", "No valid URL detected"))
            return
        self.txt_url.setPlainText(url)
        self.lst_formats.clear()
        self.lb_fmt_info.setText(tr("正在获取格式信息...", "Fetching format info…"))
        self._worker = _ParseWorker(url, self.ed_cookie.text().strip() or None,
                                    self.ed_proxy.text().strip() or None, self)
        self._worker.sig_done.connect(self._on_formats)
        self._worker.sig_fail.connect(self._on_parse_fail)
        self._worker.start()

    def _on_formats(self, fmts, title, playlist):
        self._formats = fmts
        self._title = title
        self.lst_formats.clear()
        for f in fmts:
            sz = f"{f['filesize'] / 1024 / 1024:.0f}MB" if f.get("filesize") else "?"
            self.lst_formats.addItem(
                f"[{f.get('format_id')}] {f.get('ext')}  " +
                f"{f.get('resolution', '')}  {sz}")
        info = tr("已识别：{}", "Recognized: {}").format((title or '')[:60])
        if playlist:
            info += (tr("  |  播放列表: {} ", "  |  Playlist: {} ").format(playlist.get('title', '')) +
                     tr("({}个视频)", "({} videos)").format(playlist.get('count', 0)))
        self.lb_fmt_info.setText(info)
        # 有格式才允许下载
        if fmts:
            self.action_bar.btn_go.setEnabled(True)
        else:
            self.action_bar.btn_go.setEnabled(False)
            self.lb_fmt_info.setText(tr("未找到可用格式", "No format available"))

    def _on_parse_fail(self, err):
        self.lb_fmt_info.setText(tr("获取失败：{}", "Fetch failed: {}").format(err[:80]))
        self.action_bar.btn_go.setEnabled(False)

    def _add_url(self):
        raw = self.txt_url.toPlainText()
        urls = [_clean_url(u) for u in raw.split("\n") if _clean_url(u)]
        if not urls:
            toast.show_warning(self, tr("请输入有效URL", "Enter a valid URL"))
            return
        # 先解析第一个URL的格式
        self._parse_url()
        added = 0
        for url in urls:
            if any(q["url"] == url for q in self._queue):
                continue
            name = self._title or "video"
            fmt_id = None
            row = self.lst_formats.currentRow()
            if 0 <= row < len(self._formats):
                fmt_id = self._formats[row].get("format_id")
            display = f"  {name[:30]}  —  {url[:50]}"
            self._queue.append({"url": url, "name": name,
                                "fmt_id": fmt_id, "display": display})
            self.lst_queue.addItem(display)
            added += 1
        self._update_count()
        self.txt_url.clear()
        self._douyin_tip_shown = False  # 重置提示，允许新链接再次触发
        if added:
            toast.show_success(self, tr("已添加 {} 个链接到队列", "Added {} links to queue").format(added))

    def _batch_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("选择链接文件", "Pick link file"), "", tr("文本文件 (*.txt);;所有文件 (*.*)", "Text files (*.txt);;All files (*.*)"))
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            with open(path, "r", encoding="gbk") as f:
                lines = f.readlines()
        added = 0
        for line in lines:
            url = _clean_url(line)
            if not url or any(q["url"] == url for q in self._queue):
                continue
            display = f"  {url[:60]}"
            self._queue.append({"url": url, "name": tr("批量导入", "Import batch"),
                                "fmt_id": None, "display": display})
            self.lst_queue.addItem(display)
            added += 1
        self._update_count()
        if added:
            toast.show_success(self, tr("成功导入 {} 个链接", "Imported {} links").format(added))
        else:
            toast.show_warning(self, tr("未找到有效链接", "No valid links found"))

    def _add_favorite(self):
        url = _clean_url(self.txt_url.toPlainText())
        if not url:
            toast.show_warning(self, tr("请先输入链接", "Enter links first"))
            return
        from core.m3u8_downloader import M3U8Store
        M3U8Store().add_favorite(url, name=self._title or url[:40], note="")
        toast.show_success(self, tr("已收藏", "Saved"))

    def _show_favorites(self):
        from core.m3u8_downloader import M3U8Store
        from gui_qt.panels.url_list_dialog import UrlListDialog

        def use(url, name):
            if url and not any(q["url"] == url for q in self._queue):
                display = f"  {name[:30]}  —  {url[:50]}"
                self._queue.append({"url": url, "name": name,
                                    "fmt_id": None, "display": display})
                self.lst_queue.addItem(display)
                self._update_count()

        dlg = UrlListDialog(tr("收藏链接", "Saved links"), M3U8Store().get_favorites(), use, self)
        dlg.exec()

    def _show_history(self):
        from core.m3u8_downloader import M3U8Store
        from gui_qt.panels.url_list_dialog import UrlListDialog

        def use(url, name):
            if url:
                self._title = name
                self.txt_url.setPlainText(url)

        dlg = UrlListDialog(tr("下载历史", "Download history"), M3U8Store().get_history(), use, self)
        dlg.exec()

    # ── 队列操作 ─────────────────────────────────
    def _update_count(self):
        self.lb_count.setText(tr("{} 个任务", "{} tasks").format(len(self._queue)))

    def _move(self, delta):
        row = self.lst_queue.currentRow()
        j = row + delta
        if row < 0 or j < 0 or j >= len(self._queue):
            return
        self._queue[row], self._queue[j] = self._queue[j], self._queue[row]
        item = self.lst_queue.takeItem(row)
        self.lst_queue.insertItem(j, item)
        self.lst_queue.setCurrentRow(j)

    def _remove_selected(self):
        for row in sorted(
                {i.row() for i in self.lst_queue.selectedIndexes()},
                reverse=True):
            self.lst_queue.takeItem(row)
            if row < len(self._queue):
                self._queue.pop(row)
        self._update_count()

    def _clear_queue(self):
        self.lst_queue.clear()
        self._queue.clear()
        self._update_count()
        self.action_bar.btn_go.setEnabled(False)
        self._douyin_tip_shown = False  # 重置提示

    # ── 设置辅助 ─────────────────────────────────
    def _toggle_audio(self, checked):
        self.cb_audio_fmt.setEnabled(checked)

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, tr("选择下载目录", "Pick download folder"),
                                             self.ed_dir.text() or "")
        if d:
            self.ed_dir.setText(d)

    def _open_output_folder(self):
        d = self.ed_dir.text().strip()
        if d and os.path.isdir(d):
            os.startfile(d)
        else:
            toast.show_warning(self, tr("输出目录不存在", "Output folder does not exist"))

    # ── 提交下载 ─────────────────────────────────
    def _start(self):
        if not self._queue:
            toast.show_warning(self, tr("请先添加下载链接", "Add download links first"))
            return
        out_dir = self.ed_dir.text().strip()
        if not out_dir:
            toast.show_warning(self, tr("请选择保存目录", "Choose a save folder"))
            return
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError as e:
            toast.show_error(self, tr("无法创建输出目录：{}", "Cannot create output folder: {}").format(e))
            return
        self.save_prefs()

        from core.video_downloader import VideoDownloader
        if self._dl_obj is None:
            self._dl_obj = VideoDownloader()

        speed_str = self.cb_speed.currentText()
        params = {
            "cookie": self.ed_cookie.text().strip() or None,
            "proxy": self.ed_proxy.text().strip() or None,
            "speed_limit": 0 if speed_str == tr("不限", "Unlimited") else int(speed_str),
            "audio_only": self.cb_audio_only.isChecked(),
            "audio_format": self.cb_audio_fmt.currentText(),
            "subtitles": self.cb_subtitles.isChecked(),
            "output_template": self.ed_template.text().strip() or None,
            "headers": self._parse_headers(),
            "out_dir": out_dir,
        }
        mgr = self.services.task_manager
        added = 0
        for i, item in enumerate(self._queue):
            url, name = item["url"], item["name"]
            ext = params["audio_format"] if params["audio_only"] else "mp4"
            output_path = os.path.join(out_dir, f"{name}.{ext}")
            if os.path.exists(output_path):
                base, ext2 = os.path.splitext(output_path)
                c = 1
                while os.path.exists(f"{base}_{c}{ext2}"):
                    c += 1
                output_path = f"{base}_{c}{ext2}"
            p = dict(params)
            p["url"] = url
            p["format_id"] = item.get("fmt_id")
            tid = mgr.add_task(
                name=f"{tr('下载', 'Download')} - {name}", task_type="download",
                file_path="", output_path=output_path, params=p,
                runner=self._runner, canceller=self._dl_obj.cancel,
                history_type=tr("视频下载", "Video Download"), history_target=tr("视频下载", "Video Download"),
                need_ffmpeg=False)
            if tid is not None:
                self._task_rows[tid] = i
                added += 1
        if added:
            self.action_bar.set_running(True)
            self.action_bar.set_status(tr("已提交 {} 个下载任务", "Submitted {} download tasks").format(added))
        else:
            toast.show_error(self, tr("任务提交失败", "Submit failed"))

    @staticmethod
    def _parse_headers_from(text):
        headers = {}
        if text:
            for pair in text.split(","):
                if ":" in pair:
                    k, v = pair.split(":", 1)
                    headers[k.strip()] = v.strip()
        return headers

    def _parse_headers(self):
        return self._parse_headers_from(self.ed_headers.text().strip())

    def _runner(self, task, prog):
        p = task.params
        return self._dl_obj.download(
            p.get("url", ""), task.output_path,
            format_id=p.get("format_id"), progress_callback=prog,
            cookie=p.get("cookie"), headers=p.get("headers"),
            proxy=p.get("proxy"), speed_limit=p.get("speed_limit", 0),
            audio_only=p.get("audio_only", False),
            audio_format=p.get("audio_format", "mp3"),
            subtitles=p.get("subtitles", False),
            output_template=p.get("output_template"))

    def _cancel_all(self):
        mgr = self.services.task_manager
        for tid in list(self._task_rows):
            mgr.cancel_task(tid)
        self.action_bar.btn_cancel.setEnabled(False)

    # ── 进度/状态联动 ────────────────────────────
    def _on_progress(self, task_id, pct, msg, speed):
        if task_id not in self._task_rows:
            return
        self.action_bar.set_status(msg)
        if pct >= 0:
            self.action_bar.set_total(pct)

    def _on_state(self, task_id, state):
        if task_id not in self._task_rows:
            return
        row = self._task_rows[task_id]
        if (0 <= row < self.lst_queue.count()
                and row < len(self._queue)):
            self.lst_queue.item(row).setText(
                f"{self._queue[row]['display']}  [{tm.state_text(state)}]")
        if state in (tm.SUCCESS, tm.FAILED, tm.CANCELLED):
            self._task_rows.pop(task_id, None)
        active = [self.services.task_manager.get_task(t)
                  for t in self._task_rows]
        if not any(t and t.state in (tm.WAITING, tm.RUNNING, tm.PAUSED)
                   for t in active):
            self.action_bar.set_running(False)

    # ── 参数/偏好 ────────────────────────────────
    def collect_params(self) -> dict:
        return {
            "url": self.txt_url.toPlainText().strip(),
            "cookie": self.ed_cookie.text(),
            "proxy": self.ed_proxy.text(),
            "speed": self.cb_speed.currentText(),
            "headers": self.ed_headers.text(),
            "audio_only": self.cb_audio_only.isChecked(),
            "audio_fmt": self.cb_audio_fmt.currentText(),
            "subtitles": self.cb_subtitles.isChecked(),
            "template": self.ed_template.text(),
            "dir": self.ed_dir.text(),
        }

    def collect_prefs(self) -> dict:
        return {"dl_dir": self.ed_dir.text()}

    def apply_prefs(self, prefs: dict):
        if prefs and prefs.get("dl_dir"):
            self.ed_dir.setText(prefs["dl_dir"])
