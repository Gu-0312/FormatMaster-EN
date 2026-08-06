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


def main(onefile=False):
    project_dir = os.path.dirname(os.path.abspath(__file__))
    main_script = os.path.join(project_dir, "main_qt.py")

    icon_path = os.path.join(project_dir, "assets", "icon.ico")
    cmd = [
        sys.executable, "-m", "PyInstaller",
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
        # 核心模块
        "--hidden-import", "core",
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
        # 风险规避：完整收集 PyMuPDF 的二进制与资源
        "--collect-all", "fitz",
        "--hidden-import", "PIL",
        "--collect-submodules", "PIL",
        # COM自动化（Word/PPT转PDF）
        "--hidden-import", "win32com",
        "--hidden-import", "win32com.client",
        "--hidden-import", "pythoncom",
        # 二维码
        "--hidden-import", "qrcode",
        # 工具模块
        "--hidden-import", "utils.tool_downloader",
        "--hidden-import", "utils.presets",
        "--hidden-import", "utils.drag_drop_ctypes",
        "--hidden-import", "utils.format_helpers",
        "--hidden-import", "utils.hardware_accel",
        # 应用层
        "--hidden-import", "app",
        "--hidden-import", "app.theme",
        "--hidden-import", "app.exceptions",
        # 新版 GUI（PySide6）
        "--hidden-import", "gui_qt",
        "--hidden-import", "gui_qt.app",
        "--hidden-import", "gui_qt.services",
        "--hidden-import", "gui_qt.task_manager",
        "--hidden-import", "gui_qt.nav_registry",
        "--hidden-import", "gui_qt.update_checker",
        "--hidden-import", "gui_qt.widgets",
        "--hidden-import", "gui_qt.components",
        "--hidden-import", "gui_qt.pages",
        "--hidden-import", "gui_qt.panels",
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
        "--hidden-import", "rapidocr_onnxruntime",
        "--hidden-import", "rapidocr_onnxruntime.onnxruntime",
        "--hidden-import", "onnxruntime",
        "--collect-all", "rapidocr_onnxruntime",
        "--collect-all", "onnxruntime",
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
        dist_dir = os.path.join(project_dir, "dist")
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
