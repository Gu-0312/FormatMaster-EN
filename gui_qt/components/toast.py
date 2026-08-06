"""toast — InfoBar 轻提示统一封装。

所有页面/面板通过 show_* 发出轻提示，避免直接散落 InfoBar 调用。
页面切换时会自动清理当前窗口的 InfoBar，避免长时间滞留。
"""
from gui_qt.i18n import tr
from qfluentwidgets import InfoBar, InfoBarPosition

# 活跃 InfoBar 实例池
_active_toasts = []


def _track(info_bar):
    """跟踪 InfoBar 生命周期，关闭时从池中移除。"""
    _active_toasts.append(info_bar)
    info_bar.closedSignal.connect(lambda: _remove(info_bar))


def _remove(info_bar):
    try:
        _active_toasts.remove(info_bar)
    except ValueError:
        pass


def close_all(parent=None):
    """关闭所有活跃 InfoBar，或仅关闭指定父窗口子树下的 InfoBar。"""
    for info_bar in list(_active_toasts):
        if parent is None or info_bar.window() is parent:
            try:
                info_bar.close()
            except Exception:
                pass


def _show(parent, level, content, duration=3000):
    kw = dict(parent=parent, content=content,
              position=InfoBarPosition.TOP, duration=duration)
    if level == "success":
        ib = InfoBar.success(title=tr("成功", "Success"), **kw)
    elif level == "warning":
        ib = InfoBar.warning(title=tr("注意", "Notice"), **kw)
    elif level == "error":
        ib = InfoBar.error(title=tr("错误", "Error"), **kw)
    else:
        ib = InfoBar.info(title=tr("提示", "Info"), **kw)
    _track(ib)


def show_success(parent, content, duration=3000):
    _show(parent, "success", content, duration)


def show_warning(parent, content, duration=3000):
    _show(parent, "warning", content, duration)


def show_error(parent, content, duration=5000):
    _show(parent, "error", content, duration)


def show_info(parent, content, duration=3000):
    _show(parent, "info", content, duration)


def show_by_level(parent, level, content):
    """按 TaskManager.sig_log 的 level 分发。"""
    _show(parent, level, content)
