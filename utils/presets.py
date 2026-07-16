import json
import os
from typing import Dict, List, Optional

from .config import get_presets_path

DEFAULT_PRESETS = {
    "video": [
        {
            "name": "高清MP4",
            "ext": ".mp4",
            "codec": "libx264",
            "preset": "high",
            "resolution": None,
        },
        {
            "name": "手机视频",
            "ext": ".mp4",
            "codec": "libx264",
            "preset": "medium",
            "resolution": "720p (1280x720)",
        },
        {
            "name": "网络分享",
            "ext": ".mp4",
            "codec": "libx264",
            "preset": "medium",
            "resolution": "1080p (1920x1080)",
        },
        {
            "name": "小文件",
            "ext": ".mp4",
            "codec": "libx264",
            "preset": "low",
            "resolution": "480p (854x480)",
        },
    ],
    "audio": [
        {
            "name": "高质量MP3",
            "ext": ".mp3",
            "codec": "libmp3lame",
        },
        {
            "name": "无损FLAC",
            "ext": ".flac",
            "codec": "flac",
        },
        {
            "name": "小体积AAC",
            "ext": ".aac",
            "codec": "aac",
        },
    ],
    "image": [
        {
            "name": "网页图片",
            "ext": ".webp",
            "quality": 80,
            "max_size": "1920x1080",
        },
        {
            "name": "高清PNG",
            "ext": ".png",
            "quality": 95,
            "max_size": None,
        },
        {
            "name": "小图JPG",
            "ext": ".jpg",
            "quality": 70,
            "max_size": "800x800",
        },
    ],
}

def _load_presets() -> Dict:
    path = get_presets_path()
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return DEFAULT_PRESETS

def _save_presets(presets: Dict):
    path = get_presets_path()
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(presets, f, ensure_ascii=False, indent=2)
    except IOError:
        pass

def get_presets(type: str) -> List[Dict]:
    presets = _load_presets()
    return presets.get(type, [])

def get_preset_names(type: str) -> List[str]:
    presets = get_presets(type)
    return [p["name"] for p in presets]

def get_preset_by_name(type: str, name: str) -> Optional[Dict]:
    presets = get_presets(type)
    for p in presets:
        if p.get("name") == name:
            return p
    return None

def add_preset(type: str, preset: Dict):
    presets = _load_presets()
    if type not in presets:
        presets[type] = []
    presets[type].append(preset)
    _save_presets(presets)

def update_preset(type: str, name: str, preset: Dict):
    presets = _load_presets()
    if type in presets:
        for i, p in enumerate(presets[type]):
            if p.get("name") == name:
                presets[type][i] = preset
                _save_presets(presets)
                return True
    return False

def delete_preset(type: str, name: str) -> bool:
    presets = _load_presets()
    if type in presets:
        for i, p in enumerate(presets[type]):
            if p.get("name") == name:
                del presets[type][i]
                _save_presets(presets)
                return True
    return False

def reset_presets():
    _save_presets(DEFAULT_PRESETS)
