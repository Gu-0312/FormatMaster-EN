"""打包脚本 - 将格式大师打包为exe

风险规避：
1. 默认使用文件夹模式（--onedir），测试 PyMuPDF 等 C 扩展库能否正常加载；
   验证通过后可加 --onefile 参数切换为单文件模式。
2. 显式添加 --collect-all fitz，确保 PyMuPDF 的二进制资源被正确收集。
3. 添加 --collect-submodules PIL，避免 Pillow 子模块丢失。
"""
import subprocess
import sys
import os


def _add_data(cmd, src, dst):
    """添加数据文件（如果存在）"""
    if os.path.exists(src):
        cmd.extend(["--add-data", f"{src}{os.pathsep}{dst}"])


def main(onefile=False):
    project_dir = os.path.dirname(os.path.abspath(__file__))
    main_script = os.path.join(project_dir, "main.py")

    icon_path = os.path.join(project_dir, "assets", "icon.ico")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile" if onefile else "--onedir",
        "--windowed",
        "--name", "格式大师",
        "--icon", icon_path,
        "--paths", project_dir,
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
        "--hidden-import", "utils.ytdlp_manager",
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
        "--hidden-import", "PIL._tkinter_finder",
        "--collect-submodules", "PIL",
        # 拖拽
        "--hidden-import", "windnd",
        # tkinter
        "--hidden-import", "tkinter",
        "--hidden-import", "tkinter.ttk",
        "--hidden-import", "tkinter.filedialog",
        "--hidden-import", "tkinter.messagebox",
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
    ]

    # 预先下载的二进制（如果存在则打包，不存在则运行时下载）
    _add_data(cmd, os.path.join(project_dir, "bin", "yt-dlp.exe"), "bin")
    _add_data(cmd, os.path.join(project_dir, "bin", "ffmpeg.exe"), "bin")
    _add_data(cmd, os.path.join(project_dir, "bin", "ffprobe.exe"), "bin")

    cmd.append(main_script)

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

