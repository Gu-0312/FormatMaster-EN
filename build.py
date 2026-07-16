"""打包脚本 - 将格式大师打包为exe"""
import subprocess
import sys
import os

def main():
    project_dir = os.path.dirname(os.path.abspath(__file__))
    main_script = os.path.join(project_dir, "main.py")

    icon_path = os.path.join(project_dir, "assets", "icon.ico")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
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
        "--hidden-import", "PIL",
        "--hidden-import", "PIL._tkinter_finder",
        # 拖拽
        "--hidden-import", "windnd",
        # tkinter
        "--hidden-import", "tkinter",
        "--hidden-import", "tkinter.ttk",
        "--hidden-import", "tkinter.filedialog",
        "--hidden-import", "tkinter.messagebox",
        "--hidden-import", "json",
        "--hidden-import", "threading",
        "--hidden-import", "subprocess",
        "--hidden-import", "re",
        "--hidden-import", "csv",
        "--hidden-import", "shutil",
        "--noconfirm",
        "--clean",
        main_script,
    ]

    print("正在打包格式大师...")
    result = subprocess.run(cmd, cwd=project_dir)
    if result.returncode == 0:
        dist_dir = os.path.join(project_dir, "dist")
        exe_path = os.path.join(dist_dir, "格式大师.exe")
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"\n打包成功！输出: {exe_path} ({size_mb:.1f} MB)")
        else:
            print("打包完成，请检查dist目录")
    else:
        print("打包失败")
        sys.exit(1)

if __name__ == "__main__":
    main()
