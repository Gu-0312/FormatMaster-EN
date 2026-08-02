"""Base panel — 面板基类与生命周期协议。

定义所有面板共有的外部协议：build / collect_params / apply_prefs / collect_prefs。
具体面板继承 BasePanel，实现自己的 build() 与状态收集逻辑。

依赖方向：gui/panels/base_panel.py -> app/context.py（向下）。
"""
import tkinter as tk
from typing import Optional

from app.context import AppContext, PanelContext


class BasePanel:
    """所有面板的抽象基类。

    子类约定：
      - 类属性 panel_key：面板唯一标识，与 FormatMaster.PANEL_META 中的 key 一致
      - 类属性 context_cls：该面板的 PanelContext 子类（dataclass）
      - 实现 build()：构建 UI，实例化 self.context，并 ctx.register_panel(key, context)
      - 实现 collect_params()：导出供调度层 _go 使用的参数 dict
      - 实现 apply_prefs(prefs)：从持久化 prefs 恢复控件状态
    """

    panel_key: str = ""
    context_cls = None  # type: type

    def __init__(self, app_ctx: AppContext, parent: tk.Widget):
        self.ctx: AppContext = app_ctx
        self.parent: tk.Widget = parent
        self.context: Optional[PanelContext] = None
        self.frame: Optional[tk.Widget] = None
        # panel_data 兼容：原 FormatMaster.panel_data[key] = {"files":..., "listbox":...}
        self.panel_data: dict = {"files": [], "listbox": None}

    def build(self) -> tk.Widget:
        raise NotImplementedError

    def collect_params(self) -> dict:
        raise NotImplementedError

    def apply_prefs(self, prefs: dict) -> None:
        raise NotImplementedError

    def collect_prefs(self) -> dict:
        """导出可持久化的偏好。默认等价于 collect_params()，子类可覆盖以过滤运行态字段。"""
        return self.collect_params()
