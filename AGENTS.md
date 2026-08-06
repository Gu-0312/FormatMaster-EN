# AGENTS.md — 格式大师（FormatMaster）项目级代理指令

本文件是本项目对 AI 编码代理的权威约定。修改代码前请先阅读本文件，并遵循其中的分层、约定与测试规范。

## 项目概览

- **产品**：Windows 桌面全能格式转换工具（视频/音频/图片/文档转换、PDF 处理、OCR、下载、哈希校验等 20+ 功能）
- **技术栈**：Python 3.11+、PySide6 + qfluentwidgets（Fluent Widgets，Prism 设计系统）、FFmpeg（外部二进制，bin/ 或自动下载）、yt-dlp、RapidOCR
- **入口**：`main_qt.py`（引导高 DPI 后进入 `gui_qt/app.py` 的 `MainWindow`）；打包使用 PyInstaller（见 `build.py`，onedir 模式）
- **运行**：`python main_qt.py`（注意：旧 tkinter 入口 `main.py` 已删除，不要再引用）

## 分层架构

依赖方向严格单向：`gui_qt/ → core/ → utils/`；`app/` 为全局基础层（主题/异常），供上层引用。**禁止反向依赖**（如 `core/` 不得 import `gui_qt/`，`utils/` 不得 import `core/`、`gui_qt/`）。

| 层 | 目录 | 职责 | 关键模块 |
|---|---|---|---|
| UI 层 | `gui_qt/` | PySide6 界面（FluentWindow + Mica） | `app.py`（MainWindow 引导）、`nav_registry.py`（导航真源）、`services.py`（QtServices 容器）、`task_manager.py`（TaskManager）、`pages/`、`panels/`、`components/` |
| 业务层 | `core/` | 转换/处理逻辑，无 UI 依赖 | `video_converter.py`、`audio_converter.py`、`doc_converter.py`、`ffmpeg_executor.py`、`pdf_editor.py`、`ocr_tool.py` 等 20 模块 |
| 工具层 | `utils/` | 配置、路径、纯函数工具 | `config.py`、`ffmpeg_manager.py`、`hardware_accel.py`、`format_helpers.py`、`presets.py` |
| 基础层 | `app/` | 主题、异常映射 | `theme.py`（D 可变字典）、`exceptions.py`（EX_HINT + _debug_log） |

注意：`main_qt.py` 只做入口引导（高 DPI 策略 + 调用 `run()`），所有窗口逻辑在 `gui_qt/app.py`。新功能应放入 `gui_qt/panels/`、`gui_qt/pages/` 与 `core/`，避免膨胀 `gui_qt/app.py`。

## 关键约定

### 1. FFmpeg 封装

- **路径获取**：一律通过 `utils.config.get_ffmpeg_path()` / `get_ffprobe_path()`，按「用户可写 bin 目录 → 项目 bin/ → PATH」优先级查找。**禁止硬编码路径或直接写 `"ffmpeg"`**。
- **元数据读取**：统一走 `core/ffmpeg_executor.py` 的 `get_ffprobe_info()`（强制 3 秒超时，失败返回 `None`，绝不阻塞 UI 线程）。
- **错误翻译**：FFmpeg stderr 错误用 `utils.config.translate_ffmpeg_error()` 转中文。
- **自动下载**：缺失 FFmpeg 时由 `utils/ffmpeg_manager.py` 的 `FFmpegManager` 异步下载。
- **subprocess 规范**：Windows 下必须带 `creationflags=subprocess.CREATE_NO_WINDOW`；文本模式用 `encoding='utf-8', errors='ignore'`；短命令带 `timeout`；长转换用 `Popen` 并解析进度。

### 2. 页面/面板注册模式（gui_qt）

每个功能面板遵循 `gui_qt/panels/` 的标准结构（参考 `base_panel.py` 与 `video_panel.py`）：

1. **导航真源**：`gui_qt/nav_registry.py` 的 `NAV_GROUPS`（6 组：首页/转换中心/编辑处理/智能工具/网络下载/管理中心）。每个条目含 `key`、`text`、`icon`、`factory(window, services)`；`_page(mod, cls)` 工厂延迟导入页面类，避免循环依赖。**新增功能必须在此注册**。
2. **面板类**：`gui_qt/panels/<key>_panel.py` 中定义页面类，继承 `BaseQtPanel(ScrollArea)`（`gui_qt/panels/base_panel.py`），约定：
   - 类属性 `panel_key`：与 `NAV_GROUPS` 中的 key 一致（唯一导航真源）；
   - `build()`：构建 UI（构造时自动调用）；
   - `collect_params()`：导出供任务调度使用的参数 dict；
   - `apply_prefs(prefs)` / `collect_prefs()`：偏好持久化恢复/导出（构造时自动 `apply_prefs`）。
3. 面板只通过 `services`（`QtServices`，见 `gui_qt/services.py`）获取业务能力（config、task_manager、history 等），**不得直接操作主窗口内部逻辑**；耗时任务提交 `services.task_manager`（`TaskManager`，信号驱动 `sig_state`/`sig_batch_done`，FIFO 串行）。
4. 页面（首页/任务中心/转换历史/设置/关于）位于 `gui_qt/pages/`，与面板同属 UI 层。

### 3. 其他通用约定

- **异常处理**：用户可见错误经 `app/exceptions.py` 的 `EX_HINT` 映射为中文提示；调试日志统一用 `_debug_log()`（写入 %APPDATA%/FormatMaster/debug.log，自动截断 2MB）。
- **主题**：颜色走 `app/theme.py` 的 `D` 可变字典（暗色主题运行时改写 `D[k]`）；亮/暗/跟随系统由 `gui_qt/components/theme_manager.py` 管理，样式在 `gui_qt/components/design_system.py`（Prism 设计系统）。
- **数据文件**：用户数据（config/history/user_prefs/m3u8 记录等）经 `utils.config.get_user_data_dir()` 定位；打包后写入 `%APPDATA%/FormatMaster`，**禁止写安装目录**。本项目 `data/` 目录为运行时数据（.gitignore 已忽略）。只读资源用 `get_resource_path()`。
- **注释与提示**：项目为中文产品，用户可见文案一律中文；代码注释使用中文（与现有代码一致）。

## 测试规范

- **框架**：pytest，配置见 `pytest.ini`（`pythonpath = .`、`testpaths = tests`、`addopts = -q --tb=short`）。
- **运行命令**：项目根目录执行 `pytest`（或 `venv\Scripts\python -m pytest`）。
- **测试范围**：`tests/` 只放**纯逻辑单元测试**（如 `utils/format_helpers.py`、`app/exceptions.py`、`utils/hardware_accel.py`、`core/video_converter.py` 的辅助函数）。**不启动 GUI、不依赖真实 FFmpeg 二进制、不访问网络**；需要时 mock。
- **命名**：文件 `test_*.py`，类 `Test*`，函数 `test_*`。
- **路径**：`tests/conftest.py` 已将项目根加入 `sys.path`，测试中直接 `from utils.xxx import ...` 即可。
- **要求**：为 `core/`、`utils/`、`app/` 中的纯函数新增/修改逻辑时，应补充对应单元测试；修改后必须全量跑 `pytest` 确认通过。

## 修改代码的检查清单

1. 是否违反分层依赖方向？（`core/` 不 import `gui_qt/`；`utils/` 不 import `core/`、`gui_qt/`）
2. FFmpeg 调用是否走 `get_ffmpeg_path()` 且 subprocess 参数合规（CREATE_NO_WINDOW / timeout / encoding）？
3. 新面板是否遵循 `nav_registry.py` 注册 + `BaseQtPanel` 模式（panel_key 能被 NAV_GROUPS 解析）？
4. 是否避免向 `gui_qt/app.py` 或 `main_qt.py` 堆砌新逻辑？
5. `pytest` 是否全部通过？
