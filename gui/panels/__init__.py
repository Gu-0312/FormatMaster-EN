"""UI panel package — 面板类（DI 化）。

每个面板一个独立模块，定义自己的 PanelContext dataclass 与 Panel(BasePanel) 类。
通过 AppContext 注入获取服务，不再直接挂载到 FormatMaster 的 self 命名空间。
"""
