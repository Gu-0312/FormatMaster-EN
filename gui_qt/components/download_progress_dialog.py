"""download_progress_dialog — 工具下载进度弹窗。

用于「工具状态」检查更新后，点击「立即更新」时弹出一个带进度条的模态
对话框，实时显示下载/解压进度，替代原先的纯后台静默下载。

设计要点：
- 下载/解压均在后台线程执行，进度与完成结果通过 Qt Signal 从后台线程
  队列调度到主线程更新 UI（本项目约定：后台线程回主线程一律用 Signal，
  禁止 QTimer.singleShot —— 后者在 daemon 线程无事件循环、回调永不触发）。
- update(pct, msg) / finish(ok, msg) 是线程安全入口，供后台回调调用。
- 模态 + 下载完成自动关闭；用户可在下载中「取消」（仅关闭窗口，下载在
  后台继续完成），避免下载卡住时无法关闭窗口。
"""
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout,
)

from gui_qt.components import design_system as ds
from gui_qt.components import toast
from gui_qt.components.dialog import FluentDialogBase
from gui_qt.i18n import tr


class DownloadProgressDialog(FluentDialogBase):
    """带进度条的模态下载对话框。

    用法（在 UI 线程）：
        dlg = DownloadProgressDialog("FFmpeg", parent)
        dlg.show()
        mgr.download_async(callback=dlg.finish, force=True,
                           progress_cb=dlg.update)
        dlg.exec()
        # 之后读 dlg.ok / dlg.msg 判断结果（或直接依赖对话框内的 toast）
    """

    _progress = Signal(int, str)   # (pct 0-100, 阶段描述)
    _finished = Signal(bool, str)  # (ok, 结果消息)
    retry_requested = Signal()     # 失败态点「重试」（retryable=True 时）

    def __init__(self, tool_label, parent=None, retryable=False,
                 manual_url=None):
        """manual_url：更新失败时额外显示「前往 GitHub 下载」按钮（打开该链接）。"""
        title = tr("正在更新 {}", "Updating {}").format(tool_label)
        super().__init__(title, parent)
        self.tool_label = tool_label
        self.ok = False
        self.msg = ""
        self.cancelled = False
        self.retryable = retryable
        self.manual_url = manual_url
        self._close_btn = None
        self._manual_btn = None

        self.setFixedSize(440, 190)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(0)

        # 标题
        self.title_lbl = QLabel(
            tr("正在下载 {}", "Downloading {}").format(tool_label), self)
        self.title_lbl.setObjectName("dlTitle")
        root.addWidget(self.title_lbl)

        root.addSpacing(14)

        # 进度条
        self.bar = QProgressBar(self)
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        root.addWidget(self.bar)

        root.addSpacing(10)

        # 状态文字
        self.status_lbl = QLabel(tr("准备下载…", "Preparing..."), self)
        self.status_lbl.setObjectName("dlStatus")
        self.status_lbl.setWordWrap(True)
        root.addWidget(self.status_lbl)

        root.addStretch(1)

        # 按钮行：下载中「取消」；失败时变「关闭」或「重试 + 关闭」
        btn_lay = QHBoxLayout()
        btn_lay.addStretch(1)
        self.btn = QPushButton(tr("取消", "Cancel"), self)
        self.btn.setObjectName("dlBtn")
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.clicked.connect(self._on_btn)
        btn_lay.addWidget(self.btn)
        root.addLayout(btn_lay)
        self._btn_lay = btn_lay

        # 后台线程信号 → 主线程槽
        self._progress.connect(self._on_progress)
        self._finished.connect(self._on_finished)

        # 基类 __init__ 已调用 bind_theme(self, self._theme_qss)，
        # 故 _theme_qss 必须返回完整样式；这里无需再手动 setStyleSheet。
        self.setStyleSheet(self._theme_qss())

    # ── 线程安全入口（后台线程调用）──
    def update(self, pct, msg):
        """更新进度（后台线程可调用）。"""
        try:
            self._progress.emit(int(pct), str(msg or ""))
        except Exception:  # noqa: BLE001 - 对话框可能已销毁
            pass

    def finish(self, ok, msg):
        """下载完成/失败（后台线程可调用）。"""
        try:
            self._finished.emit(bool(ok), str(msg or ""))
        except Exception:  # noqa: BLE001
            pass

    # ── 主线程槽 ──
    def _on_progress(self, pct, msg):
        if self.cancelled:
            return
        if pct < 0:
            # 不确定进度（如服务器未返回 Content-Length）：忙碌条 + 已下载量
            self.bar.setRange(0, 0)
        else:
            self.bar.setRange(0, 100)
            self.bar.setValue(max(0, min(100, pct)))
        self.status_lbl.setText(msg or "")

    def _on_finished(self, ok, msg):
        self.ok = ok
        self.msg = msg
        if ok:
            self.bar.setValue(100)
            toast.show_success(
                self.parent(), tr("{} 更新完成", "{} updated").format(self.tool_label))
            self.accept()
        else:
            self.bar.setValue(0)
            self.status_lbl.setText(
                tr("下载失败：{}\n\n若多次失败，可能是网络受限（需代理/梯子）。"
                   "\n可前往 GitHub Release 页面手动下载。",
                   "Download failed: {}\n\nIf it keeps failing, your network "
                   "may be restricted (VPN/proxy needed).\nGet the package "
                   "manually from the GitHub Release page.").format(msg))
            if self.retryable:
                # 失败态：主按钮变「重试」，左侧追加「关闭」；可选「前往 GitHub」
                self.btn.setText(tr("重试", "Retry"))
                if self._close_btn is None:
                    self._close_btn = QPushButton(tr("关闭", "Close"), self)
                    self._close_btn.setObjectName("dlBtnSec")
                    self._close_btn.setCursor(Qt.PointingHandCursor)
                    self._close_btn.clicked.connect(self._on_close)
                    # 插到主按钮左侧：[stretch, 关闭, 重试]
                    self._btn_lay.insertWidget(self._btn_lay.count() - 1,
                                               self._close_btn)
                if self.manual_url and self._manual_btn is None:
                    self._manual_btn = QPushButton(
                        tr("前往 GitHub 下载", "Get from GitHub"), self)
                    self._manual_btn.setObjectName("dlBtnSec")
                    self._manual_btn.setCursor(Qt.PointingHandCursor)
                    self._manual_btn.clicked.connect(self._open_manual)
                    # [stretch, 前往GitHub, 关闭, 重试]
                    self._btn_lay.insertWidget(self._btn_lay.count() - 1,
                                               self._manual_btn)
            else:
                self.btn.setText(tr("关闭", "Close"))
            toast.show_error(
                self.parent(),
                tr("{} 更新失败：{}", "{} update failed: {}").format(self.tool_label, msg))

    def reset(self):
        """重试前重置为下载中状态（主线程调用）。"""
        self.ok = False
        self.msg = ""
        self.cancelled = False
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.status_lbl.setText(tr("准备下载…", "Preparing..."))
        self.btn.setText(tr("取消", "Cancel"))
        if self._close_btn is not None:
            self._close_btn.hide()
        if self._manual_btn is not None:
            self._manual_btn.hide()
        self.setStyleSheet(self._theme_qss())

    def _open_manual(self):
        """打开 GitHub Release 页面让用户手动下载（失败引导）。"""
        try:
            QDesktopServices.openUrl(QUrl(self.manual_url or ""))
        except Exception:  # noqa: BLE001 - 打开失败不影响关闭
            pass
        toast.show_info(self.parent(),
                        tr("已打开 GitHub Release 页面", "GitHub Release page opened"))

    def _on_close(self):
        self.reject()

    def _on_btn(self):
        if self.retryable and self.btn.text() == tr("重试", "Retry"):
            # 失败态：通知调用方重新下载（对话框保持打开，继续显示进度）
            self.retry_requested.emit()
            return
        if self.btn.text() == tr("关闭", "Close"):
            # 失败态：用户看到错误后手动关闭
            self.reject()
            return
        # 下载中：取消仅关闭窗口（retryable 场景下载线程会真正停止，
        # 由调用方传入 should_stop 感知 cancelled；工具更新场景后台继续）
        self.cancelled = True
        self.reject()
        if self.retryable:
            toast.show_info(
                self.parent(), tr("已取消更新", "Update cancelled"))
        else:
            toast.show_info(
                self.parent(),
                tr("已取消显示，下载将在后台继续完成",
                   "Window closed, download continues in background"))

    # ── 主题样式 ──
    def _theme_qss(self):
        """返回当前主题的完整 QSS（覆盖基类；供 bind_theme 在主题切换时刷新）。"""
        t = ds.tokens()
        return (
            f"QDialog {{ background: {t['card_bg']}; border-radius: 12px; }}"
            f"QLabel {{ background: transparent; }}"
            f"QLabel#dlTitle {{ color: {t['ink']}; font-size: 15px;"
            f" font-weight: 600; }}"
            f"QLabel#dlStatus {{ color: {t['ink_sec']}; font-size: 13px; }}"
            f"QProgressBar {{ background: {t['prog_trough']}; border: none;"
            f" border-radius: 4px; }}"
            f"QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0,"
            f" x2:1, y2:0, stop:0 {t['accent']}, stop:1 {t['accent_soft']});"
            f" border-radius: 4px; }}"
            f"QPushButton#dlBtn {{ background: {t['accent']}; color: #FFFFFF;"
            f" border: none; border-radius: 8px; padding: 8px 24px;"
            f" font-size: 13px; }}"
            f"QPushButton#dlBtn:hover {{ background: {t['accent_hover']}; }}"
            f"QPushButton#dlBtn:pressed {{ background: {t['accent_deep']}; }}"
            f"QPushButton#dlBtnSec {{ background: transparent; color: {t['accent']};"
            f" border: none; border-radius: 8px; padding: 8px 24px;"
            f" font-size: 13px; }}"
            f"QPushButton#dlBtnSec:hover {{ background: {t['accent_soft']}; }}"
        )
