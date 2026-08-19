# -*- coding: utf-8 -*-
"""code_editor — 类 VSCode 代码编辑器（行号 + 语法高亮）。

说明：QScintilla 的 pip 包仅提供 PyQt5 绑定（会污染 PySide6 环境），
改用 Qt 自带 QSyntaxHighlighter + 自绘行号区实现等效效果：
零依赖、深浅主题自适应、JSON/Python/JS 高亮。
"""
import os

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import (QColor, QFont, QPainter, QSyntaxHighlighter,
                           QTextCharFormat)
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPlainTextEdit,
                               QVBoxLayout)
from qfluentwidgets import FluentIcon, PushButton

from gui_qt.i18n import tr


# ── 语法高亮（QSyntaxHighlighter）────────────────
class _BaseHighlighter(QSyntaxHighlighter):
    """通用高亮基类：注册 (regex, format) 规则。"""

    def __init__(self, doc, rules=None):
        super().__init__(doc)
        self._rules = rules or []

    def highlightBlock(self, text):
        for pattern, fmt in self._rules:
            idx = 0
            while True:
                m = pattern.search(text, idx)
                if m is None:
                    break
                start, end = m.start(), m.end()
                self.setFormat(start, end - start, fmt)
                idx = end
                if start == end:
                    break


def _fmt(color, bold=False, italic=False):
    f = QTextCharFormat()
    f.setForeground(QColor(color))
    if bold:
        f.setFontWeight(QFont.Weight.Bold)
    if italic:
        f.setFontItalic(True)
    return f


def _build_highlighter(lang, doc):
    """按语言构建高亮器；返回 None 表示不支持。"""
    import re
    try:
        from gui_qt.components import design_system as ds
        t = ds.tokens()
        kw_c = t.get("accent", "#5B5BD6")
        str_c = "#2FC99A" if not ds.isDarkTheme() else "#7EE2B8"
        com_c = t.get("ink_tertiary", "#9AA0AE")
        num_c = t.get("success", "#3B6D11")
        fn_c = t.get("ink_sec", "#5F6472")
    except Exception:  # noqa: BLE001
        kw_c, str_c, com_c, num_c, fn_c = "#5B5BD6", "#2FC99A", "#9AA0AE", "#639922", "#5F6472"

    rules = []
    if lang == "python":
        rules = [
            (re.compile(r"\b(def|class|return|import|from|if|elif|else|for|while|try|except|finally|with|as|pass|break|continue|lambda|yield|global|nonlocal|raise|assert|del|in|is|not|and|or|None|True|False|self)\b"), _fmt(kw_c, bold=True)),
            (re.compile(r"#[^\n]*"), _fmt(com_c, italic=True)),
            (re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|'''[^']*'''"), _fmt(str_c)),
            (re.compile(r"\b\d+(\.\d+)?\b"), _fmt(num_c)),
        ]
    elif lang == "json":
        rules = [
            (re.compile(r"\"(?:[^\"\\]|\\.)*\"(?=\s*:)"), _fmt(kw_c, bold=True)),   # 键
            (re.compile(r"\"(?:[^\"\\]|\\.)*\""), _fmt(str_c)),                      # 字符串
            (re.compile(r"\b(true|false|null)\b"), _fmt(kw_c, bold=True)),
            (re.compile(r"-?\d+(\.\d+)?([eE][+-]?\d+)?"), _fmt(num_c)),
        ]
    elif lang == "js":
        rules = [
            (re.compile(r"\b(var|let|const|function|return|if|else|for|while|new|class|extends|import|export|from|try|catch|finally|throw|async|await|typeof|instanceof|this|undefined|null|true|false)\b"), _fmt(kw_c, bold=True)),
            (re.compile(r"//[^\n]*|/\*[\s\S]*?\*/"), _fmt(com_c, italic=True)),
            (re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|`(?:[^`\\]|\\.)*`"), _fmt(str_c)),
            (re.compile(r"\b\d+(\.\d+)?\b"), _fmt(num_c)),
        ]
    else:
        return None
    return _BaseHighlighter(doc, rules)


# ── 行号区 ──────────────────────────────────────
class _LineNumberArea(QPlainTextEdit):
    def __init__(self, editor):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self):
        return self._editor._line_number_width()

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
        block = self._editor.firstVisibleBlock()
        num = block.blockNumber()
        top = self._editor.blockBoundingGeometry(block).translated(
            self._editor.contentOffset()).top()
        bottom = top + self._editor.blockBoundingRect(block).height()
        while block.isValid() and top <= e.rect().bottom():
            if block.isVisible() and bottom >= e.rect().top():
                painter.setPen(QColor(150, 150, 150))
                painter.drawText(0, int(top), self.width() - 6,
                                 int(self._editor.fontMetrics().height()),
                                 Qt.AlignmentFlag.AlignRight, str(num + 1))
            block = block.next()
            top = bottom
            bottom = top + self._editor.blockBoundingRect(block).height()
            num += 1


class CodeEditorWidget(QPlainTextEdit):
    """代码编辑器：行号 + 语法高亮 + 主题自适应。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lang = None
        self._highlighter = None
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(' '))
        self._line_area = _LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_area_width)
        self.updateRequest.connect(self._update_line_area)
        self._update_line_area_width()

    # ── 行号区 ────────────────────────────────
    def _line_number_width(self):
        digits = len(str(max(1, self.blockCount())))
        return 18 + self.fontMetrics().horizontalAdvance('9') * digits

    def _update_line_area_width(self, *args):
        self.setViewportMargins(self._line_number_width(), 0, 0, 0)

    def _update_line_area(self, rect, dy):
        if dy:
            self._line_area.scroll(0, dy)
        else:
            self._line_area.update(0, rect.y(), self._line_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_area_width()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        cr = self.contentsRect()
        self._line_area.setGeometry(
            QRect(cr.left(), cr.top(), self._line_number_width(), cr.height()))

    # ── 语言/内容 ──────────────────────────────
    def set_language(self, lang):
        """lang: python / json / js / None。"""
        self._lang = lang
        self._highlighter = _build_highlighter(lang, self.document())

    def set_text(self, text):
        self.setPlainText(text or "")

    def language(self):
        return self._lang


class CodeEditorDialog(QDialog):
    """代码查看/编辑对话框：打开文件 → 高亮显示 → 可保存。"""

    def __init__(self, path="", parent=None, editable=True):
        super().__init__(parent)
        self._path = path
        self.setWindowTitle(tr("代码编辑器", "Code editor"))
        self.resize(760, 560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        self.editor = CodeEditorWidget(self)
        lay.addWidget(self.editor, 1)

        bar = QHBoxLayout()
        bar.addStretch(1)
        self.lb_info = QLabel("")
        bar.addWidget(self.lb_info)
        self.btn_save = PushButton(FluentIcon.SAVE, tr("保存", "Save"))
        self.btn_save.clicked.connect(self.save)
        bar.addWidget(self.btn_save)
        self.btn_close = PushButton(tr("关闭", "Close"))
        self.btn_close.clicked.connect(self.close)
        bar.addWidget(self.btn_close)
        lay.addLayout(bar)

        self.editor.setReadOnly(not editable)
        self.btn_save.setEnabled(editable)
        if path:
            self.open_file(path)

    def open_file(self, path):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            self.lb_info.setText(tr("读取失败：{}", "Read failed: {}").format(e))
            return
        ext = os.path.splitext(path)[1].lower()
        lang = {".py": "python", ".json": "json", ".js": "js",
                ".mjs": "js", ".cjs": "js"}.get(ext)
        self.editor.set_language(lang)
        self.editor.set_text(text)
        self.lb_info.setText(os.path.basename(path))

    def save(self):
        if not self._path:
            return
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                f.write(self.editor.toPlainText())
            self.lb_info.setText(tr("已保存：{}", "Saved: {}").format(os.path.basename(self._path)))
        except OSError as e:
            self.lb_info.setText(tr("保存失败：{}", "Save failed: {}").format(e))
