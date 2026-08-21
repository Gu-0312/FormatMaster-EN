"""app_update_checker — 程序自身自动更新（GUI 协调层）。

- AppUpdateChecker：后台线程查 GitHub Releases 最新版，发现更新发 found 信号；
- prompt_app_update：确认框 → 进度条弹窗下载（国内镜像）→ 解压并生成
  更新器脚本 → 启动脚本 → 退出主程序（脚本完成文件替换后拉起新版本）。

与 core.app_updater 分离：本模块只管 UI/线程协调，网络与文件逻辑在 core 层。
"""
import os
import sys
import threading

from PySide6.QtCore import QObject, QProcess, Signal
from PySide6.QtWidgets import QApplication

from core import app_updater
from core.tool_updater import version_gt
from gui_qt.i18n import tr


class AppUpdateChecker(QObject):
    """后台检查程序新版本（GitHub Releases），发现更新发 found 信号。"""

    found = Signal(str)          # 最新版本号（如 "1.3.8"）
    up_to_date = Signal()        # 已是最新（供手动检查「已是最新」反馈）
    failed = Signal()            # 检查失败（网络/无 release；启动检查可忽略）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False

    def is_running(self):
        return self._running

    def check_async(self):
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self):
        try:
            latest = app_updater.fetch_latest_tag()
            if not latest:
                # 检查失败 / 无 release：不发「已是最新」避免误导
                self.failed.emit()
                return
            from utils.config import APP_VERSION
            if version_gt(latest, APP_VERSION):
                self.found.emit(latest)
            else:
                self.up_to_date.emit()
        except Exception:  # noqa: BLE001 - 检查失败静默
            self.failed.emit()
        finally:
            self._running = False


def prompt_app_update(parent, latest):
    """发现新版本：确认 → 进度条下载（镜像）→ 替换 → 自动重启。

    latest: 已确认比当前版本新的版本号字符串。

    失败处理（本函数为「更新失败绝不影响旧版」设计）：
    - 下载源多级回退（ghproxy.net → gh-proxy.com → 原始），全失败/校验失败
      → 弹窗红色报错 + 「重试 / 关闭」按钮，程序继续用旧版，绝不重启；
    - 用户点「取消」→ 下载线程真正停止（should_stop），不替换、不重启；
    - 替换阶段由 update.bat 回滚式执行：新版起不来自动恢复旧版。
    """
    from gui_qt.components.download_progress_dialog import DownloadProgressDialog
    try:
        from qfluentwidgets import MessageBox
    except Exception:  # noqa: BLE001
        return

    if getattr(sys, "frozen", False) is False:
        # 开发模式（python main_qt.py）下不更新自身
        try:
            from gui_qt.components import toast
            toast.show_info(
                parent, tr("开发模式下不支持自动更新，请使用打包版",
                           "Auto-update disabled in dev mode"))
        except Exception:  # noqa: BLE001
            pass
        return

    box = MessageBox(
        tr("发现新版本 v{}", "New version v{}").format(latest),
        tr("格式大师 v{} 已发布。\n\n是否立即下载并更新？更新完成后将自动重启。",
           "FormatMaster v{} is available.\n\nDownload and update now? "
           "The app will restart automatically.").format(latest),
        parent)
    box.yesButton.setText(tr("立即更新", "Update now"))
    box.cancelButton.setText(tr("稍后", "Later"))
    if not box.exec():
        return

    dlg = DownloadProgressDialog(tr("格式大师", "FormatMaster"), parent,
                                 retryable=True)
    _thread = {"t": None}  # 防止重试时旧线程引用问题（旧线程失败后已结束）

    def _run():
        zip_path = None
        try:
            asset_names = app_updater.fetch_asset_names(latest)
            asset = app_updater.find_portable_asset(asset_names)
            if not asset:
                dlg.finish(False, tr("未找到免安装更新包（zip）",
                                     "No portable package found"))
                return
            url = app_updater.asset_download_url(asset, latest)
            urls = app_updater.build_download_urls(url)

            def _prog(done, total):
                if total > 0:
                    pct = int(done * 100 / total)
                    msg = tr("下载中 {:.1f} / {:.1f} MB",
                             "Downloading {:.1f} / {:.1f} MB").format(
                        done / 1048576, total / 1048576)
                else:
                    pct = 0
                    msg = tr("已下载 {:.1f} MB", "Downloaded {:.1f} MB").format(
                        done / 1048576)
                dlg.update(pct, msg)

            # 用户取消 → 真正停止下载（不替换、不重启）
            zip_path = app_updater.download_update(
                urls, _prog, should_stop=lambda: dlg.cancelled)
            if dlg.cancelled:
                return
            app_dir = os.path.dirname(sys.executable)
            app_exe = os.path.basename(sys.executable)
            bat = app_updater.prepare_update(zip_path, app_dir, app_exe)
            # 更新包已解压完成，立即删除临时 zip——原逻辑只在失败/取消时
            # 清理，成功路径会在 %TEMP% 遗留几十 MB（进程崩溃/强杀后永不清）。
            try:
                if zip_path and os.path.isfile(zip_path):
                    os.remove(zip_path)
            except OSError:
                pass
            if dlg.cancelled:
                # 解压期间被取消：不替换、不重启
                return
            dlg.finish(True, tr("更新完成，正在重启…", "Updated, restarting…"))
            _launch_updater(bat, parent)
        except app_updater.UpdateCancelled:
            # 用户取消：静默收尾（download_update 已清理临时文件）
            return
        except Exception as e:  # noqa: BLE001
            try:
                if zip_path and os.path.isfile(zip_path):
                    os.remove(zip_path)
            except OSError:
                pass
            dlg.finish(False, str(e))

    def _start():
        # 首次启动与失败后重试共用；重试前重置弹窗状态
        dlg.reset()
        _thread["t"] = threading.Thread(target=_run, daemon=True)
        _thread["t"].start()

    dlg.retry_requested.connect(_start)
    _start()
    dlg.exec()


def _launch_updater(bat, parent):
    """主线程：启动更新器脚本（替换文件并拉起新版本），然后退出当前实例。

    2026-08-21 彻底修复：原先直接 QApplication.quit() 跳过 closeEvent（只
    补 prefs.flush()，且不落物理盘）。现在 close() 触发 _force_quit 分支的
    _finalize_shutdown() 统一收尾——面板偏好/任务快照/临时清理 + prefs
    durable（os.fsync）落盘，断电/强杀不丢。
    """
    try:
        QProcess.startDetached("cmd", ["/c", bat])
    except Exception:  # noqa: BLE001
        pass
    # 标记强制退出，跳过关闭确认对话框
    try:
        parent._force_quit = True
    except Exception:  # noqa: BLE001
        pass
    # 统一收尾并关闭（closeEvent → _force_quit → _finalize_shutdown）
    try:
        parent.close()
    except Exception:  # noqa: BLE001
        pass
    QApplication.quit()
