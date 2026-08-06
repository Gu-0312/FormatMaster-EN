"""m3u8_panel — M3U8 视频下载面板（阶段2 迁移自 gui/panels/m3u8_panel.py + main.py 下载逻辑）。

URL 队列式 M3U8 下载（core.m3u8_downloader）：解析画质/字幕、批量添加、
多线程并发下载、断点续传、字幕下载，任务经 TaskManager 通用链路串行执行。
"""
import hashlib
import os
from urllib.parse import unquote, urlparse

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout,
                               QVBoxLayout, QWidget)
from qfluentwidgets import (FluentIcon, CaptionLabel, CheckBox, ComboBox,
                            LineEdit, ListWidget, PrimaryPushButton, PushButton,
                            TextEdit)

from gui_qt.i18n import tr
from gui_qt.components import toast
from gui_qt.components.form_widgets import FormSection, FormGrid
from gui_qt.panels.base_panel import BaseQtPanel
from gui_qt import task_manager as tm
from gui_qt.widgets import ActionBar

# 预置值（与 tkinter 版 m3u8_panel 一致）
THREADS_VALUES = ["4", "8", "16", "24", "32", "48", "64"]
FORMAT_VALUES = ["mp4", "mkv", "avi", "mov", "ts"]
SPEED_VALUES = ["不限", "2", "5", "10", "20", "50"]


def _parse_headers(text):
    headers = {}
    if text:
        for pair in text.split(","):
            if ":" in pair:
                k, v = pair.split(":", 1)
                headers[k.strip()] = v.strip()
    return headers


class _QualityWorker(QThread):
    """后台解析 M3U8 画质与字幕轨道（联网请求）。"""

    sig_done = Signal(list, list)   # (qualities, subs)
    sig_fail = Signal(str)

    def __init__(self, dl, url, headers, cookie, proxy, parent=None):
        super().__init__(parent)
        self._dl, self._url = dl, url
        self._headers, self._cookie, self._proxy = headers, cookie, proxy

    def run(self):
        try:
            qualities = self._dl.get_qualities(
                self._url, headers=self._headers,
                cookie=self._cookie, proxy=self._proxy)
            subs = self._dl.get_subtitles(
                self._url, headers=self._headers,
                cookie=self._cookie, proxy=self._proxy)
            self.sig_done.emit(qualities or [], subs or [])
        except Exception as e:  # noqa: BLE001
            self.sig_fail.emit(str(e))


class M3u8PanelPage(BaseQtPanel):
    """M3U8 下载页。"""

    panel_key = "m3u8"

    # ── UI 构建 ──────────────────────────────────
    def build(self):
        lay = self.content_layout
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(self.make_title(tr("M3U8 视频下载", "M3U8 download")))
        head.addWidget(CaptionLabel("添加多个链接，支持画质选择，批量队列下载"))
        head.addStretch(1)
        lay.addLayout(head)

        # URL 输入区
        card = FormSection(tr("M3U8 链接", "M3U8 link"), FluentIcon.DOWNLOAD)
        body = QWidget()
        vl = QVBoxLayout(body)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(8)
        self.txt_url = TextEdit()
        self.txt_url.setFixedHeight(64)
        self.txt_url.setPlaceholderText("每行一个 M3U8 链接，支持批量粘贴")
        self.txt_url.setAcceptRichText(False)
        from gui_qt.components import design_system as _ds
        _ds.apply_text_edit_style(self.txt_url)
        vl.addWidget(self.txt_url)
        brow = QHBoxLayout()
        brow.setSpacing(8)
        btn_add = PrimaryPushButton(tr("批量添加", "Add batch"))
        btn_add.clicked.connect(self._batch_add)
        btn_fav = PushButton("⭐ 收藏")
        btn_fav.clicked.connect(self._add_favorite)
        btn_parse = PushButton("解析画质")
        btn_parse.clicked.connect(self._parse_url)
        brow.addWidget(btn_add)
        brow.addWidget(btn_fav)
        brow.addWidget(btn_parse)
        brow.addStretch(1)
        vl.addLayout(brow)
        qrow = QHBoxLayout()
        qrow.setSpacing(8)
        qrow.addWidget(CaptionLabel("画质"))
        self.cb_quality = ComboBox()
        self.cb_quality.addItem("")
        self.cb_quality.currentIndexChanged.connect(self._quality_changed)
        qrow.addWidget(self.cb_quality, 1)
        self.lb_quality_hint = CaptionLabel("点击「解析画质」获取可选项")
        qrow.addWidget(self.lb_quality_hint)
        vl.addLayout(qrow)
        card.add_widget(body)
        lay.addWidget(card)

        # 文件名 + 保存目录
        nrow = QHBoxLayout()
        nrow.setSpacing(8)
        nrow.addWidget(CaptionLabel(tr("文件名", "File name")))
        self.ed_name = LineEdit()
        self.ed_name.setPlaceholderText("留空=自动命名")
        nrow.addWidget(self.ed_name, 1)
        nrow.addWidget(CaptionLabel("保存到"))
        self.ed_dir = LineEdit()
        self.ed_dir.setText(os.path.expanduser("~/Downloads"))
        nrow.addWidget(self.ed_dir, 1)
        btn_browse = PushButton(tr("浏览", "Browse"))
        btn_browse.clicked.connect(self._browse_dir)
        nrow.addWidget(btn_browse)
        lay.addLayout(nrow)

        # 下载设置
        set_card = FormSection(tr("下载设置", "Download settings"), FluentIcon.SETTING)
        grid = FormGrid(columns=3)

        self.cb_threads = grid.add_field(
            "并发线程", self._combo(THREADS_VALUES, "16"),
            hint="并发下载的线程数")
        self.cb_format = grid.add_field(
            "输出格式", self._combo(FORMAT_VALUES, "mp4"),
            hint="输出视频容器格式")
        self.cb_speed = grid.add_field(
            "限速 MB/s", self._combo(SPEED_VALUES, "不限"),
            hint="下载速度上限，不限为 0")
        self.ed_cookie = grid.add_field(
            "Cookie", self._line_edit(180, ""),
            hint="登录 Cookie，用于访问受限资源")
        self.ed_proxy = grid.add_field(
            "代理", self._line_edit(180, "如 http://127.0.0.1:7890"),
            hint="HTTP/HTTPS 代理地址")
        self.ed_headers = grid.add_field(
            "自定义Header", self._line_edit(0, "Key:Value,Key:Value"),
            hint="自定义请求头，逗号分隔")
        sec_grid_box = QWidget()
        chk_lay = QHBoxLayout(sec_grid_box)
        chk_lay.setContentsMargins(0, 0, 0, 0)
        self.cb_resume = CheckBox("断点续传")
        self.cb_resume.setChecked(True)
        chk_lay.addWidget(self.cb_resume)
        chk_lay.addStretch(1)
        grid.add_field("", sec_grid_box, colspan=1)
        set_card.add_form(grid)
        lay.addWidget(set_card)

        # 下载队列
        q_card = FormSection(tr("下载队列", "Download queue"), FluentIcon.MENU)
        qhead = QHBoxLayout()
        qhead.setSpacing(8)
        qhead.addStretch(1)
        self.lb_count = CaptionLabel("0 个任务")
        qhead.addWidget(self.lb_count)
        q_body = QWidget()
        ql = QVBoxLayout(q_body)
        ql.setContentsMargins(0, 0, 0, 0)
        ql.setSpacing(8)
        ql.addLayout(qhead)
        self.lst_queue = ListWidget()
        self.lst_queue.setMinimumHeight(120)
        ql.addWidget(self.lst_queue)
        qbtn = QHBoxLayout()
        qbtn.setSpacing(8)
        b_up = PushButton("▲ 上移")
        b_up.clicked.connect(lambda: self._move(-1))
        b_down = PushButton("▼ 下移")
        b_down.clicked.connect(lambda: self._move(1))
        b_del = PushButton("✕ 移除选中")
        b_del.clicked.connect(self._remove_selected)
        b_clear = PushButton("清空队列")
        b_clear.clicked.connect(self._clear_queue)
        b_import = PushButton("📁 批量导入")
        b_import.clicked.connect(self._batch_import)
        b_favs = PushButton("⭐ 收藏链接")
        b_favs.clicked.connect(self._show_favorites)
        b_hist = PushButton("📋 历史记录")
        b_hist.clicked.connect(self._show_history)
        for b in (b_up, b_down, b_del, b_clear, b_import, b_favs, b_hist):
            qbtn.addWidget(b)
        qbtn.addStretch(1)
        ql.addLayout(qbtn)
        q_card.add_widget(q_body)
        lay.addWidget(q_card)

        # 选项
        orow = QHBoxLayout()
        orow.setSpacing(16)
        self.cb_download_sub = CheckBox("同时下载字幕")
        self.cb_notify = CheckBox("完成通知")
        self.cb_notify.setChecked(True)
        orow.addWidget(self.cb_download_sub)
        orow.addWidget(self.cb_notify)
        orow.addStretch(1)
        lay.addLayout(orow)

        # 底部操作栏（ActionBar + 打开输出文件夹）
        bar_row = QHBoxLayout()
        bar_row.setSpacing(8)
        self.action_bar = ActionBar(tr("开始下载", "Download"))
        bar_row.addWidget(self.action_bar, 1)
        btn_open = PushButton("📁 打开输出文件夹")
        btn_open.clicked.connect(self._open_output_folder)
        bar_row.addWidget(btn_open)
        lay.addLayout(bar_row)

        # 运行态
        from core.m3u8_downloader import M3U8Downloader
        self._m3u8_dl = M3U8Downloader()
        self._queue = []            # [{"url","master_url","name"}]
        self._qualities = []
        self._task_rows = {}        # task_id -> queue 行号
        self._worker = None
        mgr = self.services.task_manager
        mgr.sig_progress.connect(self._on_progress)
        mgr.sig_state.connect(self._on_state)
        self.action_bar.btn_go.clicked.connect(self._start)
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

    # ── 画质解析 ─────────────────────────────────
    def _parse_url(self):
        from utils.format_helpers import extract_urls
        urls = extract_urls(self.txt_url.toPlainText())
        if not urls:
            toast.show_warning(self, "请先输入M3U8链接")
            return
        url = urls[0]
        self.lb_quality_hint.setText("正在解析画质...")
        self._worker = _QualityWorker(
            self._m3u8_dl, url,
            _parse_headers(self.ed_headers.text().strip()),
            self.ed_cookie.text().strip() or None,
            self.ed_proxy.text().strip() or None, self)
        self._worker.sig_done.connect(self._on_qualities)
        self._worker.sig_fail.connect(self._on_parse_fail)
        self._worker.start()

    def _on_qualities(self, qualities, subs):
        self._qualities = qualities
        self.cb_quality.blockSignals(True)
        self.cb_quality.clear()
        if not qualities:
            self.cb_quality.addItem("仅有一个画质")
            hint = "该链接没有多码率选项，将使用默认画质"
        else:
            self.cb_quality.addItems([q["display"] for q in qualities])
            hint = f"找到 {len(qualities)} 个画质，最高: {qualities[0]['label']}"
        if subs:
            names = ", ".join(s["name"] for s in subs)
            hint += f"  |  字幕: {len(subs)}个 ({names})"
        else:
            hint += "  |  字幕: 无"
        self.cb_quality.blockSignals(False)
        self.lb_quality_hint.setText(hint)

    def _on_parse_fail(self, err):
        self._qualities = []
        self.cb_quality.clear()
        self.cb_quality.addItem("解析失败")
        self.lb_quality_hint.setText(f"解析失败：{err[:50]}")

    def _quality_changed(self, idx):
        if 0 <= idx < len(self._qualities):
            q = self._qualities[idx]
            hint = f"已选: {q['label']}"
            if q.get("resolution"):
                hint += f"  {q['resolution']}"
            if q.get("bandwidth_str"):
                hint += f"  {q['bandwidth_str']}"
            self.lb_quality_hint.setText(hint)

    # ── 队列操作 ─────────────────────────────────
    def _gen_name(self, url):
        name = self.ed_name.text().strip()
        if name:
            return name
        base = unquote(os.path.basename(urlparse(url).path.rstrip("/")))
        if "." in base:
            base = os.path.splitext(base)[0]
        if base and 2 <= len(base) <= 30:
            return base
        return hashlib.md5(url.encode()).hexdigest()[:12]

    def _batch_add(self):
        from utils.format_helpers import extract_urls
        urls = extract_urls(self.txt_url.toPlainText())
        if not urls:
            toast.show_warning(self, "请先输入有效的M3U8链接")
            return
        added = 0
        sel = self.cb_quality.currentIndex()
        for url in urls:
            name = self._gen_name(url)
            quality_url = url
            label = ""
            if self._qualities and 0 <= sel < len(self._qualities):
                quality_url = self._qualities[sel]["url"]
                label = f"  [{self._qualities[sel]['label']}]"
            display = f"  {name}{label}  —  {url[:50]}"
            self._queue.append({"url": quality_url, "master_url": url,
                                "name": name, "display": display})
            self.lst_queue.addItem(display)
            added += 1
        self._update_count()
        self.txt_url.clear()
        self.ed_name.clear()
        if added:
            toast.show_success(self, f"已添加 {added} 个链接到队列")

    def _batch_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择链接文件", "", "文本文件 (*.txt);;所有文件 (*.*)")
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
            url = line.strip()
            if (not url or url.startswith("#")
                    or not url.lower().startswith(("http://", "https://"))):
                continue
            if any(q["url"] == url for q in self._queue):
                continue
            base = unquote(os.path.basename(urlparse(url).path.rstrip("/")))
            if "." in base:
                base = os.path.splitext(base)[0]
            name = (base if base and 2 <= len(base) <= 30 and base.isalnum()
                    else hashlib.md5(url.encode()).hexdigest()[:12])
            display = f"  {name}  —  {url[:50]}"
            self._queue.append({"url": url, "master_url": url,
                                "name": name, "display": display})
            self.lst_queue.addItem(display)
            added += 1
        self._update_count()
        if added:
            toast.show_success(self, f"成功导入 {added} 个链接")
        else:
            toast.show_warning(self, "未找到有效链接")

    def _add_favorite(self):
        from utils.format_helpers import extract_urls
        urls = extract_urls(self.txt_url.toPlainText())
        if not urls:
            toast.show_warning(self, "请先输入链接")
            return
        url = urls[0]
        path_parts = urlparse(url).path
        name = unquote(path_parts.split("/")[-1].split("?")[0])
        if not name or name.endswith(".m3u8"):
            name = self.ed_name.text().strip() or url[:40]
        self._m3u8_dl.store.add_favorite(url, name, "")
        toast.show_success(self, f"已收藏: {name}")

    def _show_favorites(self):
        from gui_qt.panels.url_list_dialog import UrlListDialog

        def use(url, name):
            if url and not any(q["url"] == url for q in self._queue):
                display = f"  {name[:30]}  —  {url[:50]}"
                self._queue.append({"url": url, "master_url": url,
                                    "name": name or url[:40],
                                    "display": display})
                self.lst_queue.addItem(display)
                self._update_count()

        dlg = UrlListDialog("收藏链接", self._m3u8_dl.store.get_favorites(),
                            use, self)
        dlg.exec()

    def _show_history(self):
        from gui_qt.panels.url_list_dialog import UrlListDialog

        def use(url, name):
            if url:
                self.txt_url.setPlainText(url)
                self.ed_name.setText(name or "")

        dlg = UrlListDialog("下载历史", self._m3u8_dl.store.get_history(),
                            use, self)
        dlg.exec()

    def _update_count(self):
        self.lb_count.setText(f"{len(self._queue)} 个任务")

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

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择保存目录",
                                             self.ed_dir.text() or "")
        if d:
            self.ed_dir.setText(d)

    def _open_output_folder(self):
        d = self.ed_dir.text().strip()
        if d and os.path.isdir(d):
            os.startfile(d)  # noqa: S606 Windows 资源管理器
        else:
            toast.show_warning(self, "输出目录不存在")

    # ── 提交下载 ─────────────────────────────────
    def _start(self):
        if not self._queue:
            toast.show_warning(self, "请先添加下载链接")
            return
        if not self.services.ffmpeg_ready():
            toast.show_error(self, tr("FFmpeg 未就绪，请稍后重试", "FFmpeg not ready"))
            return
        out_dir = self.ed_dir.text().strip()
        if not out_dir:
            toast.show_warning(self, "请选择保存目录")
            return
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError as e:
            toast.show_error(self, f"无法创建输出目录：{e}")
            return
        self.save_prefs()

        speed_str = self.cb_speed.currentText()
        base_params = {
            "threads": int(self.cb_threads.currentText()),
            "output_format": self.cb_format.currentText(),
            "speed_limit": 0 if speed_str == "不限" else int(speed_str),
            "cookie": self.ed_cookie.text().strip() or None,
            "proxy": self.ed_proxy.text().strip() or None,
            "headers": _parse_headers(self.ed_headers.text().strip()),
            "resume": self.cb_resume.isChecked(),
            "download_sub": self.cb_download_sub.isChecked(),
            "notify": self.cb_notify.isChecked(),
        }
        mgr = self.services.task_manager
        added = 0
        for i, item in enumerate(self._queue):
            name = item["name"]
            output_path = os.path.join(
                out_dir, f"{name}.{base_params['output_format']}")
            if os.path.exists(output_path):
                base, ext = os.path.splitext(output_path)
                counter = 1
                while os.path.exists(f"{base}_{counter}{ext}"):
                    counter += 1
                output_path = f"{base}_{counter}{ext}"
            p = dict(base_params)
            p["url"] = item["url"]
            p["master_url"] = item.get("master_url", item["url"])
            p["name"] = name
            p["index"] = i
            tid = mgr.add_task(
                name=f"M3U8下载 - {name}", task_type="m3u8",
                file_path="", output_path=output_path, params=p,
                runner=self._runner, canceller=self._m3u8_dl.cancel,
                history_type="M3U8 下载", history_target="M3U8下载",
                need_ffmpeg=True)
            if tid is not None:
                self._task_rows[tid] = i
                added += 1
        if added:
            self.action_bar.set_running(True)
            self.action_bar.set_status(f"已提交 {added} 个下载任务")
        else:
            toast.show_error(self, "任务提交失败：FFmpeg 未就绪")

    def _runner(self, task, prog):
        p = task.params
        ok = self._m3u8_dl.download(
            p.get("url", ""), task.output_path, prog,
            threads=p.get("threads", 16), cookie=p.get("cookie"),
            headers=p.get("headers"), proxy=p.get("proxy"),
            speed_limit=p.get("speed_limit", 0),
            resume=p.get("resume", True),
            output_format=p.get("output_format", "mp4"))
        # 字幕下载（对齐 tkinter 版 _run_task 的 m3u8 分支）
        if ok and p.get("download_sub"):
            try:
                subs = self._m3u8_dl.get_subtitles(
                    p.get("master_url", p.get("url", "")),
                    headers=p.get("headers"), cookie=p.get("cookie"),
                    proxy=p.get("proxy"))
                if subs:
                    for sub in subs:
                        sub_url = sub["url"]
                        lang = sub.get("lang", "und")
                        ext = ".vtt" if ".vtt" in sub_url.lower() else ".srt"
                        sub_out = (os.path.splitext(task.output_path)[0]
                                   + f".{lang}{ext}")
                        sub_ok = self._m3u8_dl.download_subtitle(
                            sub_url, sub_out, cookie=p.get("cookie"),
                            headers=p.get("headers"), proxy=p.get("proxy"))
                        prog(-1, f"字幕{'已保存' if sub_ok else '下载失败'}: "
                                 f"{os.path.basename(sub_out)}")
                else:
                    prog(-1, "未找到字幕轨道（该视频可能没有字幕）")
            except Exception as e:  # noqa: BLE001
                prog(-1, f"字幕下载出错: {e}")
        if ok and p.get("notify"):
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_OK)
            except (ImportError, OSError):
                pass
        return ok

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

    # ── 参数/偏好（10 键与 tkinter 版一致）────────
    def collect_params(self) -> dict:
        return {
            "url": self.txt_url.toPlainText().strip(),
            "quality": self.cb_quality.currentText(),
            "name": self.ed_name.text(),
            "out_dir": self.ed_dir.text(),
            "threads": self.cb_threads.currentText(),
            "format": self.cb_format.currentText(),
            "speed": self.cb_speed.currentText(),
            "cookie": self.ed_cookie.text(),
            "proxy": self.ed_proxy.text(),
            "headers": self.ed_headers.text(),
            "resume": self.cb_resume.isChecked(),
            "download_sub": self.cb_download_sub.isChecked(),
            "notify": self.cb_notify.isChecked(),
        }

    def collect_prefs(self) -> dict:
        return {
            "out_dir": self.ed_dir.text(),
            "threads": self.cb_threads.currentText(),
            "format": self.cb_format.currentText(),
            "speed": self.cb_speed.currentText(),
            "cookie": self.ed_cookie.text(),
            "proxy": self.ed_proxy.text(),
            "headers": self.ed_headers.text(),
            "resume": self.cb_resume.isChecked(),
            "notify": self.cb_notify.isChecked(),
            "download_sub": self.cb_download_sub.isChecked(),
        }

    def apply_prefs(self, prefs: dict):
        if not prefs:
            return
        if prefs.get("out_dir"):
            self.ed_dir.setText(prefs["out_dir"])
        if prefs.get("threads") in THREADS_VALUES:
            self.cb_threads.setCurrentText(prefs["threads"])
        if prefs.get("format") in FORMAT_VALUES:
            self.cb_format.setCurrentText(prefs["format"])
        if prefs.get("speed") in SPEED_VALUES:
            self.cb_speed.setCurrentText(prefs["speed"])
        if prefs.get("cookie"):
            self.ed_cookie.setText(prefs["cookie"])
        if prefs.get("proxy"):
            self.ed_proxy.setText(prefs["proxy"])
        if prefs.get("headers"):
            self.ed_headers.setText(prefs["headers"])
        if "resume" in prefs:
            self.cb_resume.setChecked(bool(prefs["resume"]))
        if "notify" in prefs:
            self.cb_notify.setChecked(bool(prefs["notify"]))
        if "download_sub" in prefs:
            self.cb_download_sub.setChecked(bool(prefs["download_sub"]))
