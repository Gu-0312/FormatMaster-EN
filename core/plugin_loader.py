"""plugin_loader — 轻量插件系统。

约定：`plugins/` 目录下的每个 .py 文件是一个插件，可声明：
    PLUGIN_INFO = {"name", "description", "author", "version"}   # 元数据（必填 name）
    PANEL_CLASS = <QWidget 子类>                                  # 可选：提供界面
    def on_load(ctx): ...                                         # 可选：加载回调（ctx 为 dict）
    def on_unload(): ...                                          # 可选：卸载回调

扫描顺序：先用户数据目录 %APPDATA%/FormatMaster/plugins，再项目 plugins/。
纯逻辑，无 UI 依赖。
"""

import importlib.util
import os
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass

from utils.config import get_user_data_dir


@dataclass
class PluginInfo:
    name: str
    description: str = ""
    author: str = ""
    version: str = ""
    module: object = None       # 加载后的模块
    panel_class: object = None  # PANEL_CLASS
    source: str = ""            # 插件文件路径


def plugin_dirs():
    """返回待扫描目录（用户数据目录优先，内置 plugins/ 其次）。

    内置插件目录用 get_resource_path 解析：打包后指向
    _MEIPASS/plugins（对应 build.py 的 --add-data plugins;plugins，
    onedir 下位于 _internal/plugins）；开发环境即项目根 plugins/。
    用 __file__ 推导在打包后指向 exe 旁目录，会找不到插件。
    """
    dirs = [os.path.join(get_user_data_dir(), "plugins")]
    try:
        from utils.config import get_resource_path
        rp = get_resource_path("plugins")
        if os.path.isdir(rp):
            dirs.append(rp)
    except Exception:  # noqa: BLE001 - 资源路径不可用时回退旧逻辑
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dirs.append(os.path.join(root, "plugins"))
    return dirs


def _load_module(path):
    """importlib 加载单文件模块，失败返回 None。"""
    try:
        name = f"fm_plugin_{os.path.splitext(os.path.basename(path))[0]}"
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod
    except Exception:  # noqa: BLE001 - 单个插件失败不影响其他
        return None


def scan_plugins():
    """扫描全部插件目录，返回 PluginInfo 列表（含加载失败的标记为 None 的跳过）。"""
    found = []
    seen = set()
    for d in plugin_dirs():
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".py") or fn.startswith("_"):
                continue
            path = os.path.join(d, fn)
            key = os.path.abspath(path)
            if key in seen:
                continue
            seen.add(key)
            info = _load_plugin_file(path)
            if info:
                found.append(info)
    return found


def _load_plugin_file(path):
    """加载单个插件文件 → PluginInfo；失败返回 None。"""
    mod = _load_module(path)
    if mod is None:
        return None
    meta = getattr(mod, "PLUGIN_INFO", None) or {}
    name = str(meta.get("name") or os.path.splitext(os.path.basename(path))[0])
    return PluginInfo(
        name=name,
        description=str(meta.get("description", "")),
        author=str(meta.get("author", "")),
        version=str(meta.get("version", "")),
        module=mod,
        panel_class=getattr(mod, "PANEL_CLASS", None),
        source=path,
    )


def activate(info: PluginInfo, ctx: dict):
    """调用插件 on_load(ctx)；失败返回 False。"""
    if info.module is None:
        return False
    on_load = getattr(info.module, "on_load", None)
    if callable(on_load):
        try:
            on_load(ctx)
        except Exception:  # noqa: BLE001
            return False
    return True


def deactivate(info: PluginInfo):
    """调用插件 on_unload()（若提供）。"""
    if info.module is None:
        return
    on_unload = getattr(info.module, "on_unload", None)
    if callable(on_unload):
        try:
            on_unload()
        except Exception:  # noqa: BLE001
            pass


def validate_plugin_file(path):
    """校验单个插件文件是否有效。返回 (ok, 插件名或错误原因)。"""
    try:
        mod = _load_module(path)
    except Exception as e:  # noqa: BLE001
        return False, f"加载失败：{e}"
    if mod is None:
        return False, "无法加载（语法错误或依赖缺失）"
    meta = getattr(mod, "PLUGIN_INFO", None) or {}
    name = str(meta.get("name") or "").strip()
    if not name:
        return False, "缺少 PLUGIN_INFO（需含 name）"
    return True, name


def import_plugin(source, target_dir):
    """导入插件源（.py / .zip / 文件夹）到 target_dir。

    全部校验通过才复制落地；有任何一个无效则整体拒绝（不留残件）。
    返回 (ok, 成功导入的插件名列表或错误原因)。
    """
    tmp_dir = None
    try:
        if os.path.isdir(source):
            files = [os.path.join(source, f) for f in sorted(os.listdir(source))
                     if f.endswith(".py") and not f.startswith("_")]
            if not files:
                return False, "文件夹里没有 .py 插件文件"
        elif source.lower().endswith(".zip"):
            with zipfile.ZipFile(source) as zf:
                names = [n for n in zf.namelist() if n.endswith(".py")
                         and not os.path.basename(n).startswith("_")]
                if not names:
                    return False, "压缩包里没有 .py 插件文件"
                tmp_dir = tempfile.mkdtemp(prefix="fm_imp_")
                for n in names:
                    # 只取文件名落盘，忽略压缩包内目录结构（防路径穿越）
                    base = os.path.basename(n)
                    with open(os.path.join(tmp_dir, base), "wb") as fh:
                        fh.write(zf.read(n))
            files = [os.path.join(tmp_dir, f) for f in os.listdir(tmp_dir)]
        elif source.lower().endswith(".py"):
            files = [source]
        else:
            return False, "不支持的格式（支持 .py / .zip / 文件夹）"

        # 逐个校验；先全部校验通过再落地，避免半途残留
        valid = []
        for f in files:
            ok, info = validate_plugin_file(f)
            if not ok:
                return False, f"{os.path.basename(f)}：{info}（已取消导入，未写入任何文件）"
            valid.append((f, info))

        os.makedirs(target_dir, exist_ok=True)
        imported = []
        for f, name in valid:
            dst = os.path.join(target_dir, os.path.basename(f))
            shutil.copy2(f, dst)
            imported.append(name)
        return True, imported
    except Exception as e:  # noqa: BLE001
        return False, f"导入失败：{e}"
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)
