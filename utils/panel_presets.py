"""panel_presets — 通用面板转换预设存储。

把各面板的当前参数组合（collect_prefs 快照）保存为命名预设，
可一键应用到所有面板（apply_prefs），用于批量生产的参数复用。
JSON 存储于用户数据目录 panel_presets.json。
"""
import json
import os
import tempfile
import time

from utils.config import get_user_data_dir


class PanelPresetStore:
    """面板预设存取（JSON 文件，原子写）。"""

    def __init__(self, path=None):
        self.path = path or os.path.join(get_user_data_dir(), "panel_presets.json")

    # ── 底层读写 ────────────────────────────────
    def _read(self):
        if not os.path.isfile(self.path):
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def _write(self, data):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path),
                                   suffix=".tmp", prefix="presets_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    # ── 公开接口 ────────────────────────────────
    def list(self):
        """返回全部预设名（按创建时间排序）。"""
        return [p["name"] for p in self._read()]

    def save(self, name, panels):
        """保存预设：panels 为 {panel_key: prefs} 字典。"""
        data = self._read()
        for p in data:
            if p["name"] == name:
                p["panels"] = panels
                p["updated"] = time.strftime("%Y-%m-%d %H:%M")
                self._write(data)
                return True
        data.append({
            "name": name,
            "panels": panels,
            "created": time.strftime("%Y-%m-%d %H:%M"),
        })
        self._write(data)
        return True

    def load(self, name):
        """按名称取回 {panel_key: prefs}，不存在返回 None。"""
        for p in self._read():
            if p["name"] == name:
                return p.get("panels", {})
        return None

    def delete(self, name):
        """删除预设，返回是否存在。"""
        data = self._read()
        kept = [p for p in data if p["name"] != name]
        if len(kept) == len(data):
            return False
        self._write(kept)
        return True
