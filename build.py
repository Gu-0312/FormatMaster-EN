"""打包脚本 - 将格式大师打包为exe（新版 PySide6 / Fluent Widgets）

风险规避：
1. 默认使用文件夹模式（--onedir），测试 PyMuPDF 等 C 扩展库能否正常加载；
   验证通过后可加 --onefile 参数切换为单文件模式。
2. 显式添加 --collect-all fitz，确保 PyMuPDF 的二进制资源被正确收集。
3. 添加 --collect-submodules PIL，避免 Pillow 子模块丢失。
"""
import subprocess
import sys
import os


def _check_env():
    """解释器依赖自检：build.py 由 sys.executable 调 PyInstaller，若用
    非 venv 解释器（如系统 python），可能缺 rapid_table/opencc/cryptography
    等打包关键依赖 → PyInstaller 分析阶段 ModuleNotFoundError 打包失败。
    启动前检查，缺失时给出明确指引而非裸报错。"""
    import importlib.util
    critical = ["PySide6", "qfluentwidgets", "rapid_table", "opencc",
                "cryptography", "rapidocr_onnxruntime", "onnxruntime",
                "pdf2docx", "reportlab", "fitz", "PIL"]
    missing = [m for m in critical if importlib.util.find_spec(m) is None]
    if missing:
        print("✗ 当前解释器缺少打包关键依赖：" + ", ".join(missing))
        print("  请改用项目虚拟环境解释器运行：venv\\Scripts\\python.exe build.py")
        sys.exit(1)


def main(onefile=False):
    _check_env()
    project_dir = os.path.dirname(os.path.abspath(__file__))
    main_script = os.path.join(project_dir, "main_qt.py")

    # 输出目录：默认项目外同盘上级（避免项目内 build/dist 被清理/污染）
    out_root = os.environ.get("FORMATMASTER_DIST",
                              os.path.join(os.path.dirname(project_dir), "FormatMaster_dist"))
    dist_path = os.path.join(out_root, "dist")
    work_path = os.path.join(out_root, "build")
    os.makedirs(out_root, exist_ok=True)

    icon_path = os.path.join(project_dir, "assets", "icon.ico")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--distpath", dist_path,
        "--workpath", work_path,
        "--specpath", out_root,
        # 风险规避：默认 onedir，确认 fitz 加载正常后再切 --onefile
        "--onefile" if onefile else "--onedir",
        "--windowed",
        "--name", "格式大师",
        "--icon", icon_path,
        "--paths", project_dir,
        # 打包bin目录（FFmpeg、FFprobe、yt-dlp）
        "--add-data", f"{os.path.join(project_dir, 'bin')};bin",
        # 打包assets目录
        "--add-data", f"{os.path.join(project_dir, 'assets')};assets",
        # 插件中心：plugin_loader 用 spec_from_file_location 从文件系统加载
        # plugins/*.py（动态扫描），必须 add-data 带真实文件，否则打包后插件全丢
        "--add-data", f"{os.path.join(project_dir, 'plugins')};plugins",
        # 证件照 AI 抠图模型（MODNet onnx，core.id_photo._model_path 经
        # get_resource_path 从 _MEIPASS/data/models 读取；25.9MB）
        "--add-data", f"{os.path.join(project_dir, 'data', 'models')};data/models",
        # 核心模块（collect-submodules core 全量收集：函数内延迟 import 的
        # crypto_advanced/auto_recover/file_repair/doc_excel 等模块均防丢）
        "--hidden-import", "core",
        "--collect-submodules", "core",
        "--hidden-import", "core.video_converter",
        "--hidden-import", "core.audio_converter",
        "--hidden-import", "core.image_converter",
        "--hidden-import", "core.doc_converter",
        "--hidden-import", "core.ffmpeg_executor",
        "--hidden-import", "core.tools",
        "--hidden-import", "utils",
        "--hidden-import", "utils.config",
        "--hidden-import", "utils.ffmpeg_manager",
        # 文档转换依赖
        "--hidden-import", "docx",
        "--hidden-import", "openpyxl",
        "--hidden-import", "pptx",
        "--hidden-import", "pypdf",
        "--hidden-import", "pdf2docx",
        "--hidden-import", "reportlab",
        "--hidden-import", "fitz",
        # 文档转换补充依赖（函数内延迟导入，显式收集防丢）
        "--hidden-import", "striprtf",
        "--hidden-import", "odf",
        "--hidden-import", "xlrd",
        "--hidden-import", "chardet",
        "--hidden-import", "psutil",
        # 风险规避：完整收集 PyMuPDF 的二进制与资源（代码已改用 import pymupdf；
        # fitz 兼容层与新包名都收集，避免二进制资源缺失）
        "--collect-all", "fitz",
        "--collect-all", "pymupdf",
        "--hidden-import", "PIL",
        "--collect-submodules", "PIL",
        # COM自动化（Word/PPT转PDF）
        "--hidden-import", "win32com",
        "--hidden-import", "win32com.client",
        "--hidden-import", "pythoncom",
        # 二维码
        "--hidden-import", "qrcode",
        # 工具模块
        "--hidden-import", "utils.presets",
        "--hidden-import", "utils.format_helpers",
        "--hidden-import", "utils.hardware_accel",
        # 应用层
        "--hidden-import", "app",
        "--hidden-import", "app.exceptions",
        # 新版 GUI（PySide6）
        "--hidden-import", "gui_qt",
        "--hidden-import", "gui_qt.app",
        "--hidden-import", "gui_qt.services",
        "--hidden-import", "gui_qt.task_manager",
        "--hidden-import", "gui_qt.nav_registry",
        "--hidden-import", "gui_qt.update_checker",
        "--hidden-import", "gui_qt.widgets",
        "--hidden-import", "gui_qt.i18n",
        "--hidden-import", "gui_qt.context_menu",
        "--hidden-import", "gui_qt.components",
        "--hidden-import", "gui_qt.pages",
        "--hidden-import", "gui_qt.panels",
        # 风险规避：nav_registry 用 importlib 动态加载面板/页面/组件，
        # PyInstaller 静态分析无法发现，必须 collect-submodules 全量收集
        "--collect-submodules", "gui_qt.panels",
        "--collect-submodules", "gui_qt.pages",
        "--collect-submodules", "gui_qt.components",
        # PySide6 / qfluentwidgets
        "--collect-submodules", "qfluentwidgets",
        "--hidden-import", "qfluentwidgets",
        # 核心模块
        "--hidden-import", "core.image_cropper",
        "--hidden-import", "core.m3u8_downloader",
        "--hidden-import", "core.ocr_tool",
        "--hidden-import", "core.audio_trimmer",
        "--hidden-import", "core.hash_tool",
        "--hidden-import", "core.watermark_tool",
        "--hidden-import", "core.thumbnail_sheet",
        "--hidden-import", "core.pdf_extract",
        "--hidden-import", "core.pdf_to_image",
        "--hidden-import", "core.video_tools",
        "--hidden-import", "core.video_downloader",
        # 视频/M3U8 下载 Python 引擎（函数内延迟 import，静态分析发现不了；
        # bin/yt-dlp.exe 已随 bin 目录打入，此 hidden-import 保证
        # Python API 路径（格式解析等）在打包后也可用）
        "--hidden-import", "yt_dlp",
        "--hidden-import", "core.table_recognizer",
        # 表格识别：rapid_table 由 core/ocr_table 函数内延迟导入（PyInstaller
        # 静态分析发现不了），且模型 slanet-plus.onnx 在包内，必须 collect-all
        "--collect-all", "rapid_table",
        # 插件运行时依赖（插件经 importlib 动态加载，PyInstaller 分析不到，
        # 不显式收集则打包后对应插件功能缺失）：
        # 简繁转换（opencc C 扩展）+ YAML 插件（pyyaml）
        "--hidden-import", "opencc",
        "--collect-binaries", "opencc",
        "--hidden-import", "yaml",
        # 网页转 PDF 插件 / ECharts 大屏：QtWebEngine 延迟 import，
        # 显式 hidden-import 触发 PyInstaller 官方 PySide6 hook 收集
        # QtWebEngineProcess.exe / resources 等全部资源
        "--hidden-import", "PySide6.QtWebEngineWidgets",
        "--hidden-import", "PySide6.QtWebEngineCore",
        "--hidden-import", "PySide6.QtWebChannel",
        # 文档→PDF 多级降级引擎（doc_word/doc_misc 函数内延迟导入，显式收集防丢）
        "--hidden-import", "core.doc_office_pdf",
        "--hidden-import", "pillow_avif",
        "--hidden-import", "pillow_heif",
        "--hidden-import", "core.id_photo",
        "--hidden-import", "core.image_album",
        "--hidden-import", "core.audio_tools",
        "--hidden-import", "core.subtitle_extract",
        "--hidden-import", "utils.panel_presets",
        "--hidden-import", "gui_qt.panels.id_photo_panel",
        "--hidden-import", "core.video_compress",
        "--hidden-import", "gui_qt.panels.video_compress_panel",
        "--hidden-import", "gui_qt.panels.image_merge_panel",
        "--hidden-import", "gui_qt.panels.audio_enhance_panel",
        "--hidden-import", "gui_qt.panels.subtitle_panel",
        # 局域网服务（lan_transfer_panel 函数内 import，运行时延迟加载；内部还有
        # lan_transfer↔lan_receiver/lan_sender 循环延迟导入，显式收集防丢）
        "--hidden-import", "core.lan_service",
        "--hidden-import", "core.lan_transfer",
        "--hidden-import", "core.lan_receiver",
        "--hidden-import", "core.lan_sender",
        "--hidden-import", "rapidocr_onnxruntime",
        "--hidden-import", "rapidocr_onnxruntime.onnxruntime",
        "--hidden-import", "onnxruntime",
        "--collect-all", "rapidocr_onnxruntime",
        # 体积瘦身：onnxruntime 只收二进制与核心包（OCR 推理不需要 transformers/
        # quantization/tools 等可选工具子包，可省 100+ MB）
        "--collect-binaries", "onnxruntime",
        "--exclude-module", "onnxruntime.transformers",
        "--exclude-module", "onnxruntime.quantization",
        "--exclude-module", "onnxruntime.tools",
        # 文件安全工具：cryptography（含 C 扩展 _rust，必须 collect-binaries）
        "--hidden-import", "cryptography",
        "--hidden-import", "cryptography.hazmat.backends.openssl",
        "--collect-binaries", "cryptography",
        "--collect-submodules", "cryptography",
        # 标准库
        "--hidden-import", "json",
        "--hidden-import", "threading",
        "--hidden-import", "subprocess",
        "--hidden-import", "re",
        "--hidden-import", "csv",
        "--hidden-import", "shutil",
        "--hidden-import", "urllib.request",
        "--hidden-import", "urllib.error",
        "--hidden-import", "socket",
        "--noconfirm",
        "--clean",
        main_script,
    ]

    mode = "单文件" if onefile else "文件夹"
    print(f"正在打包格式大师（{mode}模式）...")
    result = subprocess.run(cmd, cwd=project_dir)
    if result.returncode == 0:
        dist_dir = dist_path
        if onefile:
            exe_path = os.path.join(dist_dir, "格式大师.exe")
            if os.path.exists(exe_path):
                size_mb = os.path.getsize(exe_path) / (1024 * 1024)
                print(f"\n打包成功！输出: {exe_path} ({size_mb:.1f} MB)")
            else:
                print("打包完成，请检查dist目录")
        else:
            exe_path = os.path.join(dist_dir, "格式大师", "格式大师.exe")
            if os.path.exists(exe_path):
                print(f"\n打包成功！输出: {exe_path}")
                print("提示：测试通过后可用 'python build.py --onefile' 重新打包为单文件")
            else:
                print("打包完成，请检查dist目录")
    else:
        print("打包失败")
        sys.exit(1)


if __name__ == "__main__":
    # 支持命令行参数 --onefile 切换为单文件模式
    use_onefile = "--onefile" in sys.argv
    main(onefile=use_onefile)
