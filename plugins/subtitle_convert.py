"""插件：字幕格式互转（SRT ↔ ASS ↔ VTT，自动识别格式）。

纯函数实现解析/生成，无第三方依赖；文件编码自动检测（utf-8/gbk/big5）。
"""

import os
from plugins._i18n import t
import re

from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLineEdit,
                               QPlainTextEdit, QVBoxLayout, QWidget)
from qfluentwidgets import (CaptionLabel, ComboBox, PrimaryPushButton)

PLUGIN_INFO = {
    "name": "字幕格式互转",
    "description": "SRT / ASS / VTT 三向转换，自动识别源格式",
    "version": "1.0.0",
}

_SRT_TIME = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*"
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})")
_VTT_TIME = re.compile(
    r"(?:(\d{1,2}):)?(\d{2}):(\d{2})[.](\d{3})\s*-->\s*"
    r"(?:(\d{1,2}):)?(\d{2}):(\d{2})[.](\d{3})")
_ASS_DIALOGUE = re.compile(
    r"Dialogue:\s*([^,]*),(\d+):(\d{2}):(\d{2})[.](\d{2}),"
    r"(\d+):(\d{2}):(\d{2})[.](\d{2}),([^,]*),([^,]*),([^,]*),"
    r"([^,]*),([^,]*),([^,]*),(.*)")


# ── 解析 ────────────────────────────────────────
def parse_subtitles(path):
    """自动识别格式 → [(start_ms, end_ms, text), ...]。"""
    text = _read_text(path)
    stripped = text.lstrip()
    if stripped.startswith("WEBVTT"):
        return _parse_vtt(text)
    if "[Events]" in text and "Dialogue:" in text:
        return _parse_ass(text)
    return _parse_srt(text)


def _parse_srt(text):
    subs = []
    for line in text.splitlines():
        m = _SRT_TIME.search(line)
        if not m:
            continue
        start = _hms_to_ms(*[int(x) for x in m.groups()[:4]])
        end = _hms_to_ms(*[int(x) for x in m.groups()[4:]])
        subs.append({"start": start, "end": end, "text": ""})
    # 填充分组文本（时间行之后的非空行）
    lines = text.splitlines()
    idx = 0
    for s in subs:
        while idx < len(lines) and _SRT_TIME.search(lines[idx]) is None:
            idx += 1
        idx += 1
        parts = []
        while idx < len(lines) and lines[idx].strip():
            parts.append(lines[idx])
            idx += 1
        s["text"] = "\n".join(parts)
    return subs


def _parse_vtt(text):
    subs = []
    cur = None
    for line in text.splitlines():
        if line.startswith("NOTE") or line.strip() == "WEBVTT" or not line.strip():
            continue
        m = _VTT_TIME.search(line)
        if m:
            g = m.groups()
            h1, m1, s1, ms1 = (int(g[0] or 0), int(g[1]), int(g[2]), int(g[3]))
            h2, m2, s2, ms2 = (int(g[4] or 0), int(g[5]), int(g[6]), int(g[7]))
            cur = {"start": h1 * 3600000 + m1 * 60000 + s1 * 1000 + ms1,
                   "end": h2 * 3600000 + m2 * 60000 + s2 * 1000 + ms2,
                   "text": ""}
            subs.append(cur)
        elif cur is not None:
            cur["text"] = (cur["text"] + "\n" + line.strip()).strip()
    return subs


def _parse_ass(text):
    subs = []
    for line in text.splitlines():
        m = _ASS_DIALOGUE.match(line.strip())
        if not m:
            continue
        g = m.groups()
        start = (int(g[1]) * 3600000 + int(g[2]) * 60000
                 + int(g[3]) * 1000 + int(g[4]) * 10)
        end = (int(g[5]) * 3600000 + int(g[6]) * 60000
               + int(g[7]) * 1000 + int(g[8]) * 10)
        subs.append({"start": start, "end": end,
                     "text": g[15].replace("\\N", "\n")})
    return subs


# ── 生成 ────────────────────────────────────────
def to_srt(subs):
    out = []
    for i, s in enumerate(subs, 1):
        out.append(str(i))
        out.append(f"{_ms_fmt(s['start'], ',')} --> {_ms_fmt(s['end'], ',')}")
        out.append(s["text"])
        out.append("")
    return "\n".join(out)


def to_vtt(subs):
    out = ["WEBVTT", ""]
    for s in subs:
        out.append(f"{_ms_fmt(s['start'], '.')} --> {_ms_fmt(s['end'], '.')}")
        out.append(s["text"])
        out.append("")
    return "\n".join(out)


def to_ass(subs):
    head = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 384\n"
            "PlayResY: 288\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, "
            "SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
            "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
            "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, "
            "MarginV, Encoding\n"
            "Style: Default, Arial, 20, &H00FFFFFF, &H000000FF, "
            "&H00000000, &H00000000, 0, 0, 0, 0, 100, 100, 0, 0, 1, 2, 0, "
            "2, 10, 10, 10, 1\n\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text\n")
    body = []
    for s in subs:
        text = s["text"].replace("\n", r"\N")
        body.append(
            f"Dialogue: 0,{_ass_time(s['start'])},{_ass_time(s['end'])},"
            f"Default,,0,0,0,,{text}")
    return head + "\n".join(body)


# ── 工具 ────────────────────────────────────────
def _hms_to_ms(h, m, s, ms):
    return h * 3600000 + m * 60000 + s * 1000 + ms


def _ms_fmt(ms, sep):
    h, rem = divmod(max(0, ms), 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _ass_time(ms):
    h, rem = divmod(max(0, ms), 3600000)
    m, rem = divmod(rem, 60000)
    s, cs = divmod(rem, 1000)
    return f"{h}:{m:02d}:{s:02d}.{cs // 10:02d}"


def _read_text(path):
    with open(path, "rb") as fh:
        data = fh.read()
    for enc in ("utf-8-sig", "utf-8", "gbk", "big5", "shift_jis", "latin-1"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def detect_format(path):
    """返回 'SRT' / 'ASS' / 'VTT'（按内容判断，非扩展名）。"""
    text = _read_text(path)
    if text.lstrip().startswith("WEBVTT"):
        return "VTT"
    if "[Events]" in text and "Dialogue:" in text:
        return "ASS"
    return "SRT"


class SubtitlePanel(QWidget):
    """字幕格式互转面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.ed_path = QLineEdit()
        self.ed_path.setPlaceholderText(t("选择字幕文件（自动识别 SRT/ASS/VTT）…"))
        row.addWidget(self.ed_path, 1)
        btn_pick = PrimaryPushButton(t("浏览"))
        btn_pick.clicked.connect(self._pick)
        row.addWidget(btn_pick)
        v.addLayout(row)

        # 输出目录（自定义 + 打开）
        out_row = QHBoxLayout()
        out_row.setSpacing(8)
        out_row.addWidget(CaptionLabel(t("输出目录")))
        self.ed_out_dir = QLineEdit()
        self.ed_out_dir.setPlaceholderText(t("默认与源文件同目录"))
        out_row.addWidget(self.ed_out_dir, 1)
        btn_out = PrimaryPushButton(t("选择目录"))
        btn_out.clicked.connect(self._pick_out)
        out_row.addWidget(btn_out)
        self.btn_open_dir = PrimaryPushButton(t("打开输出文件夹"))
        self.btn_open_dir.clicked.connect(self._open_out)
        self.btn_open_dir.setEnabled(False)
        out_row.addWidget(self.btn_open_dir)
        v.addLayout(out_row)

        cfg = QHBoxLayout()
        cfg.setSpacing(8)
        cfg.addWidget(CaptionLabel(t("转换为")))
        self.cb_fmt = ComboBox()
        self.cb_fmt.addItems(["SRT", "ASS", "VTT"])
        cfg.addWidget(self.cb_fmt)
        self.btn_run = PrimaryPushButton(t("转换"))
        self.btn_run.clicked.connect(self._convert)
        cfg.addWidget(self.btn_run)
        cfg.addStretch(1)
        v.addLayout(cfg)

        self.lb_info = CaptionLabel("")
        v.addWidget(self.lb_info)

        # 字幕内容预览（前 8 条，可视化）
        self.ed_preview = QPlainTextEdit()
        self.ed_preview.setReadOnly(True)
        self.ed_preview.setMaximumHeight(140)
        v.addWidget(self.ed_preview, 1)

        self._path = ""
        self._last_out = ""
        self._apply_theme()
        from gui_qt.components import design_system as ds
        ds.bind_theme(self, self._apply_theme)

    def _apply_theme(self):
        from gui_qt.components import design_system as ds
        t = ds.tokens()
        self.setStyleSheet(
            f"QLineEdit, QPlainTextEdit {{ background: {t['card_bg']};"
            f" color: {t['ink']}; border: 1px solid {t['border']};"
            f" border-radius: 6px; padding: 4px; font-size: 13px; }}")

    def _pick(self):
        path, _ = QFileDialog.getOpenFileName(
            self, t("选择字幕文件"), "", "字幕文件 (*.srt *.ass *.vtt);;所有文件 (*)")
        if not path:
            return
        self._path = path
        self.ed_path.setText(path)
        if not self.ed_out_dir.text().strip():
            self.ed_out_dir.setText(os.path.dirname(path))
        try:
            fmt = detect_format(path)
            subs = parse_subtitles(path)
            self.lb_info.setText(
                f"检测到 {fmt} 格式 · {len(subs)} 条字幕 · "
                f"{os.path.basename(path)}")
            self._show_preview(subs)
        except Exception as e:  # noqa: BLE001
            self.lb_info.setText(t("读取失败：{e}").format(e=e))

    def _show_preview(self, subs):
        """预览前 8 条字幕。"""
        lines = []
        for i, s in enumerate(subs[:8], 1):
            lines.append(
                f"{i}. {_ms_fmt(s['start'], ',')} → {_ms_fmt(s['end'], ',')}"
                f"  {s['text'].splitlines()[0][:24]}")
        if len(subs) > 8:
            lines.append(f"… 共 {len(subs)} 条")
        self.ed_preview.setPlainText("\n".join(lines))

    def _pick_out(self):
        path = QFileDialog.getExistingDirectory(self, t("选择输出目录"))
        if path:
            self.ed_out_dir.setText(path)

    def _open_out(self):
        if self._last_out and os.path.isdir(self._last_out):
            try:
                os.startfile(self._last_out)   # noqa: S606
                return
            except Exception:  # noqa: BLE001
                import subprocess
                try:
                    subprocess.Popen(["explorer", self._last_out])
                    return
                except Exception:  # noqa: BLE001
                    pass
        self.lb_info.setText(t("输出目录不存在"))

    def _convert(self):
        if not self._path:
            self.lb_info.setText(t("请先选择字幕文件"))
            return
        dst = self.cb_fmt.currentText()
        out_dir = self.ed_out_dir.text().strip() or os.path.dirname(self._path)
        if not os.path.isdir(out_dir):
            self.lb_info.setText(t("输出目录不存在，请重新选择"))
            return
        base = os.path.splitext(os.path.basename(self._path))[0]
        out_path = os.path.join(out_dir, base + "." + dst.lower())
        out_path = _unique_out(out_path)
        try:
            subs = parse_subtitles(self._path)
            if dst == "SRT":
                content = to_srt(subs)
            elif dst == "ASS":
                content = to_ass(subs)
            else:
                content = to_vtt(subs)
            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write(content)
            self._last_out = os.path.dirname(out_path)
            self.btn_open_dir.setEnabled(True)
            self.lb_info.setText(
                f"已转换 {len(subs)} 条字幕 → {os.path.basename(out_path)}")
        except Exception as e:  # noqa: BLE001
            self.lb_info.setText(t("转换失败：{e}").format(e=e))


def _unique_out(path):
    """同名已存在则自动加 _1/_2 后缀（不覆盖）。"""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while os.path.exists(f"{base}_{i}{ext}"):
        i += 1
    return f"{base}_{i}{ext}"


PANEL_CLASS = SubtitlePanel


def on_load(ctx):
    pass


def on_unload():
    pass
