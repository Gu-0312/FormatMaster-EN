"""utils/temp_cleanup — 转换/下载产生的临时文件清理。

清理范围（仅系统临时目录下、明确属于本程序的前缀/后缀模式，绝不碰
用户文件），按分类可单独启用（设置页「高级 → 退出清理」分项勾选）：
- concat：formatmaster_concat_*.txt   （视频拼接列表）
- update：formatmaster_update_*.zip   （程序自更新下载包残留）
- share ：fm_share_*                  （局域网分享临时目录）
- m3u8  ：*_m3u8                      （M3U8 下载临时目录）

安全策略：只删除模式匹配的**文件或空目录**；带完整内容的临时目录
（如正在使用的 _m3u8 目录）若非空则保留，避免误删进行中的任务。
"""
import glob
import os
import shutil
import tempfile

# 分类 → (匹配模式, 类型) —— 类型 "file" 直接删文件；"dir" 仅删空目录
_CATEGORIES = {
    "concat": ("formatmaster_concat_*.txt", "file"),
    "update": ("formatmaster_update_*.zip", "file"),
    "share": ("fm_share_*", "dir"),
    "m3u8": ("*_m3u8", "dir"),
}
_PATTERNS = list(_CATEGORIES.values())  # 兼容旧引用


def _matches_dir(name):
    return name.startswith("fm_share_") or name.endswith("_m3u8")


def cleanup_temp_files(categories=None):
    """清理本程序遗留的临时文件/空目录；返回清理项数。幂等、绝不抛异常。

    categories: 要清理的分类列表（None=全部）。设置页「退出清理」按分类
    勾选，未勾选的分类不清理。
    """
    cats = categories or list(_CATEGORIES)
    patterns = [_CATEGORIES[c] for c in cats if c in _CATEGORIES]
    cleaned = 0
    try:
        tmp = tempfile.gettempdir()
        # 文件模式
        for pat, _ in patterns:
            for p in glob.glob(os.path.join(tmp, pat)):
                try:
                    if os.path.isfile(p):
                        os.remove(p)
                        cleaned += 1
                except OSError:
                    pass
        # 目录模式（仅删空目录；非空=可能正在使用，跳过）
        for name in os.listdir(tmp):
            if not _matches_dir(name):
                continue
            # 按分类过滤：share 类只清 fm_share_*，m3u8 类只清 *_m3u8
            if name.startswith("fm_share_") and "share" not in cats:
                continue
            if name.endswith("_m3u8") and "m3u8" not in cats:
                continue
            p = os.path.join(tmp, name)
            try:
                if os.path.isdir(p) and not os.listdir(p):
                    os.rmdir(p)
                    cleaned += 1
            except OSError:
                pass
    except Exception:  # noqa: BLE001 - 清理失败静默
        pass
    return cleaned
