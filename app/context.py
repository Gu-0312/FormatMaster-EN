"""Context layer for panel Dependency Injection.

提供 PanelContext（面板状态基类）与 AppContext（全局服务容器）。
让 Panel 不必直接挂载到 FormatMaster 的 self 命名空间上，而是独立维护自己的状态，
并通过构造注入获取 root / prefs / history / converters / task_queue 等服务。

依赖方向：app/context.py 不依赖 gui/，避免环依赖。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import tkinter as tk

# 延迟导入 USER_PREFS / CONV_HISTORY，避免在模块加载期触发文件 IO
# （在 AppContext.__init__ 中按需从 utils.config 取最新引用）
from utils.config import USER_PREFS, CONV_HISTORY


@dataclass
class PanelContext:
    """所有面板上下文的基类。

    子类用 @dataclass 声明自己的状态字段与控件引用，替代原先散落在
    FormatMaster 实例上的 self.v_xxx / self.a_xxx 等动态属性。
    """
    panel_key: str = ""


class AppContext:
    """全局上下文容器。

    由 FormatMaster 在 __init__ 中创建一次，注入到每个 Panel。
    只暴露 Panel 需要的服务接口；不暴露业务调度方法（_go / _run_task_*），
    保证依赖方向单向：Panel -> Context -> Services，不反向依赖 FormatMaster。
    """

    def __init__(self, app):
        # 内部反向引用，仅用于 root.after 调度与 converting 状态同步。
        # Panel 不应直接使用 _app 调用业务方法。
        self._app = app
        self.root: tk.Tk = app.root
        self.prefs = USER_PREFS
        self.history = CONV_HISTORY
        self.ffmpeg_mgr = app.ffmpeg_mgr
        self.converters: Dict[str, Any] = {
            "video": app.video_conv,
            "audio": app.audio_conv,
            "image": app.image_conv,
            "doc":   app.doc_conv,
            "m3u8":  app.m3u8_dl,
        }
        self.task_queue = app.task_queue
        # panel_key -> PanelContext 注册表
        self.panels: Dict[str, PanelContext] = {}

    # ── 面板注册 ──────────────────────────────────
    def register_panel(self, key: str, ctx: PanelContext) -> None:
        self.panels[key] = ctx

    def get_panel(self, key: str) -> Optional[PanelContext]:
        return self.panels.get(key)

    # ── 线程安全的 UI 调度入口 ────────────────────
    def after_main(self, ms: int, fn, *args) -> str:
        """在工作线程中安全地把回调投递到 Tk 主线程。"""
        return self.root.after(ms, lambda: fn(*args))

    # ── 转换状态（与 FormatMaster.converting 同步）──
    @property
    def converting(self) -> bool:
        return self._app.converting

    @converting.setter
    def converting(self, value: bool) -> None:
        self._app.converting = value

    @property
    def panels_disabled(self) -> bool:
        return getattr(self._app, "panels_disabled", False)
