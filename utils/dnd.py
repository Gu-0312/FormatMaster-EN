"""Windows文件拖拽支持 - 使用windnd"""
import windnd


def enable_drop(tk_root, callback):
    """让tkinter窗口接受文件拖拽。callback(files: list[str])"""
    try:
        def _on_drop(raw_files):
            files = []
            for f in raw_files:
                if isinstance(f, bytes):
                    f = f.decode('gbk', errors='replace')
                files.append(f)
            if files:
                callback(files)

        windnd.hook_dropfiles(tk_root, func=_on_drop)
    except Exception as e:
        print(f"拖拽初始化失败: {e}")
