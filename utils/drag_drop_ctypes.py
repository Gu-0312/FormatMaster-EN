import ctypes
import ctypes.wintypes
import os
import queue
import weakref

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32

WM_DROPFILES = 0x0233
GWL_WNDPROC = -4

if ctypes.sizeof(ctypes.c_void_p) == 8:
    LRESULT = ctypes.c_int64
    WPARAM = ctypes.c_uint64
    LPARAM = ctypes.c_int64
else:
    LRESULT = ctypes.c_long
    WPARAM = ctypes.c_uint
    LPARAM = ctypes.c_long

WNDPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.wintypes.HWND, ctypes.c_uint, WPARAM, LPARAM)

_old_wndprocs = {}
_callbacks = {}
_proc_refs = {}
_drop_queues = {}


user32.GetWindowLongPtrW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_void_p

user32.SetWindowLongPtrW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
user32.SetWindowLongPtrW.restype = ctypes.c_void_p

user32.CallWindowProcW.argtypes = [ctypes.c_void_p, ctypes.wintypes.HWND, ctypes.c_uint, WPARAM, LPARAM]
user32.CallWindowProcW.restype = LRESULT

shell32.DragAcceptFiles.argtypes = [ctypes.wintypes.HWND, ctypes.c_bool]
shell32.DragAcceptFiles.restype = None

shell32.DragQueryFileW.argtypes = [ctypes.wintypes.HWND, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint]
shell32.DragQueryFileW.restype = ctypes.c_uint

shell32.DragFinish.argtypes = [ctypes.wintypes.HWND]
shell32.DragFinish.restype = None


def _window_proc(hwnd, msg, wp, lp):
    if msg == WM_DROPFILES:
        try:
            callback = _callbacks.get(hwnd)
            if callback:
                count = shell32.DragQueryFileW(wp, -1, None, 0)
                if count > 0:
                    files = []
                    buf = ctypes.create_unicode_buffer(260)
                    for i in range(count):
                        try:
                            shell32.DragQueryFileW(wp, i, buf, ctypes.sizeof(buf) // 2)
                            path = buf.value.strip()
                            if path and os.path.exists(path):
                                files.append(path)
                        except Exception:
                            continue
                    if files:
                        try:
                            callback(files)
                        except Exception:
                            pass
        except Exception:
            pass
        finally:
            try:
                shell32.DragFinish(wp)
            except Exception:
                pass
        return 0
    return user32.CallWindowProcW(_old_wndprocs[hwnd], hwnd, msg, wp, lp)


def register_drop(hwnd, callback):
    if not isinstance(hwnd, int) or hwnd <= 0:
        print(f"✗ 无效的窗口句柄: {hwnd}")
        return False
    
    if hwnd in _callbacks:
        print(f"✗ 窗口句柄 {hwnd} 已注册拖拽")
        return False
    
    try:
        if not user32.IsWindow(hwnd):
            print(f"✗ 窗口句柄 {hwnd} 对应的窗口不存在")
            return False
        
        shell32.DragAcceptFiles(hwnd, True)
        
        old_proc = user32.GetWindowLongPtrW(hwnd, GWL_WNDPROC)
        if not old_proc:
            print(f"✗ 获取原始窗口过程失败")
            return False
        
        _old_wndprocs[hwnd] = old_proc
        _callbacks[hwnd] = callback
        _drop_queues[hwnd] = queue.Queue()
        
        new_proc = WNDPROC(_window_proc)
        user32.SetWindowLongPtrW(hwnd, GWL_WNDPROC, ctypes.cast(new_proc, ctypes.c_void_p))
        _proc_refs[hwnd] = new_proc
        
        print(f"✓ 纯 ctypes 拖拽已注册 (hwnd: {hwnd})")
        return True
    except Exception as e:
        print(f"✗ 纯 ctypes 拖拽注册失败: {e}")
        if hwnd in _old_wndprocs:
            del _old_wndprocs[hwnd]
        if hwnd in _callbacks:
            del _callbacks[hwnd]
        if hwnd in _drop_queues:
            del _drop_queues[hwnd]
        return False


def unregister_drop(hwnd):
    if not isinstance(hwnd, int) or hwnd <= 0:
        return False
    
    try:
        if hwnd not in _old_wndprocs:
            return False
        
        if user32.IsWindow(hwnd):
            user32.SetWindowLongPtrW(hwnd, GWL_WNDPROC, _old_wndprocs[hwnd])
            shell32.DragAcceptFiles(hwnd, False)
        
        del _old_wndprocs[hwnd]
        del _callbacks[hwnd]
        if hwnd in _drop_queues:
            del _drop_queues[hwnd]
        if hwnd in _proc_refs:
            del _proc_refs[hwnd]
        
        print(f"✓ 拖拽已注销 (hwnd: {hwnd})")
        return True
    except Exception as e:
        print(f"✗ 拖拽注销失败: {e}")
        return False


class SafeDropHandler:
    """
    安全的拖拽事件处理器 - 使用队列+after模式避免GIL崩溃
    
    使用方式:
        handler = SafeDropHandler(root)
        handler.register_callback(on_drop)
        
    回调函数签名:
        def on_drop(files):
            # files 是文件路径列表
            pass
    """
    
    def __init__(self, root_widget):
        self._root_ref = weakref.ref(root_widget)
        self._queue = queue.Queue()
        self._callback = None
        self._is_running = True
        self._hwnd = None
    
    def register_callback(self, callback):
        self._callback = callback
    
    def get_queue(self):
        return self._queue
    
    def set_hwnd(self, hwnd):
        self._hwnd = hwnd
    
    def _enqueue_files(self, files):
        """将文件放入队列（可在任意线程调用）"""
        if self._is_running:
            self._queue.put(files)
    
    def _process_queue(self):
        """在主线程中处理队列"""
        root = self._root_ref()
        if not root or not self._is_running:
            return
        
        while not self._queue.empty():
            try:
                files = self._queue.get_nowait()
                if self._callback:
                    try:
                        self._callback(files)
                    except Exception:
                        pass
            except queue.Empty:
                break
            except Exception:
                continue
        
        try:
            root.after(100, self._process_queue)
        except Exception:
            pass
    
    def start(self):
        """启动队列处理循环"""
        root = self._root_ref()
        if root:
            root.after(0, self._process_queue)
    
    def stop(self):
        """停止队列处理"""
        self._is_running = False


def create_safe_drop_handler(root_widget):
    """创建安全的拖拽处理器"""
    return SafeDropHandler(root_widget)


def parse_dropped_files(files):
    """
    安全解析拖拽的文件列表
    
    Args:
        files: 原始文件列表（可能是列表、元组、字节或字符串）
    
    Returns:
        清理后的有效文件路径列表
    """
    result = []
    
    if not files:
        return result
    
    try:
        if isinstance(files, (list, tuple)):
            for item in files:
                try:
                    if isinstance(item, bytes):
                        path = item.decode("utf-8").strip()
                    elif isinstance(item, str):
                        path = item.strip()
                    else:
                        path = str(item).strip()
                    
                    if path and os.path.isfile(path):
                        result.append(path)
                except Exception:
                    continue
        elif isinstance(files, bytes):
            path = files.decode("utf-8").strip()
            if path and os.path.isfile(path):
                result.append(path)
        elif isinstance(files, str):
            path = files.strip()
            if path and os.path.isfile(path):
                result.append(path)
    except Exception:
        pass
    
    return result
