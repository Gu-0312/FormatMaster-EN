"""backup — 用户数据导出/导入（设置页「数据备份」）。

打包 get_user_data_dir() 下的核心 JSON（偏好/历史/m3u8/预设等）
为单个 .zip；导入时覆盖同名文件。不涉及大文件与临时数据。
"""
import json
import os
import zipfile

from utils.config import get_user_data_dir


def _data_files():
    """用户数据目录下参与备份的 .json 文件名列表。"""
    d = get_user_data_dir()
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d)
                  if f.endswith(".json") and os.path.isfile(os.path.join(d, f)))


def export_backup(dest_path):
    """导出用户数据到 dest_path（zip）。返回写入的文件数；失败抛异常。"""
    files = _data_files()
    with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name in files:
            z.write(os.path.join(get_user_data_dir(), name), name)
    return len(files)


def import_backup(src_path):
    """从备份 zip 恢复，覆盖同名 json。返回恢复的文件数；失败抛异常。"""
    d = get_user_data_dir()
    os.makedirs(d, exist_ok=True)
    restored = 0
    with zipfile.ZipFile(src_path, "r") as z:
        for name in z.namelist():
            if not name.endswith(".json"):
                continue
            base = os.path.basename(name)
            data = z.read(name)
            # 校验是合法 JSON，避免导入损坏文件
            json.loads(data.decode("utf-8"))
            with open(os.path.join(d, base), "wb") as f:
                f.write(data)
            restored += 1
    return restored
