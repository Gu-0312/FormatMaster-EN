"""文件哈希计算 — MD5/SHA1/SHA256/SHA512

支持单文件/批量计算、哈希比对验证、导出 CSV/TXT。
纯标准库实现，无额外依赖。
"""
import hashlib
import os
from typing import List, Dict, Tuple, Optional

ALGORITHMS = {
    "MD5": hashlib.md5,
    "SHA1": hashlib.sha1,
    "SHA256": hashlib.sha256,
    "SHA512": hashlib.sha512,
}

# 大文件分块读取缓冲（8MB）
_BUF_SIZE = 8 * 1024 * 1024


def compute_hash(filepath: str, algo: str = "SHA256", progress_cb=None) -> Optional[str]:
    """计算单个文件的哈希值，返回十六进制字符串。失败返回 None。"""
    if algo not in ALGORITHMS:
        if progress_cb:
            progress_cb(-1, f"错误：不支持的算法 {algo}")
        return None

    if not os.path.isfile(filepath):
        if progress_cb:
            progress_cb(-1, f"错误：找不到文件 {os.path.basename(filepath)}")
        return None

    try:
        file_size = os.path.getsize(filepath)
        h = ALGORITHMS[algo]()
        with open(filepath, "rb") as f:
            read = 0
            while True:
                chunk = f.read(_BUF_SIZE)
                if not chunk:
                    break
                h.update(chunk)
                read += len(chunk)
                if progress_cb and file_size > 0:
                    pct = int(read * 90 / file_size)
                    progress_cb(pct, f"计算中... {read // 1024 // 1024}MB / {file_size // 1024 // 1024}MB")
        if progress_cb:
            progress_cb(100, "计算完成")
        return h.hexdigest()
    except PermissionError:
        if progress_cb:
            progress_cb(-1, "错误：没有读取权限")
        return None
    except Exception as e:
        if progress_cb:
            progress_cb(-1, f"错误：{e}")
        return None


def batch_compute(files: List[str], algo: str = "SHA256", progress_cb=None) -> List[Dict]:
    """批量计算多个文件的哈希值。

    返回 [{"file": path, "hash": hex_str, "algo": algo, "size": bytes}, ...]
    """
    results = []
    total = len(files)
    for i, fp in enumerate(files):
        if progress_cb:
            progress_cb(int(i * 90 / max(total, 1)), f"计算 {i+1}/{total}...")
        h = compute_hash(fp, algo)
        if h:
            results.append({
                "file": fp,
                "hash": h,
                "algo": algo,
                "size": os.path.getsize(fp) if os.path.exists(fp) else 0,
            })
    if progress_cb:
        progress_cb(100, f"完成 {len(results)}/{total}")
    return results


def verify_hash(filepath: str, expected_hash: str, algo: str = "SHA256") -> Tuple[bool, str]:
    """验证文件哈希是否匹配。返回 (ok, computed_hash)"""
    h = compute_hash(filepath, algo)
    if h is None:
        return False, ""
    return (h.lower() == expected_hash.lower().strip()), h


def export_csv(results: List[Dict], output_path: str) -> bool:
    """导出哈希列表为 CSV 文件（UTF-8 BOM，Excel 兼容）"""
    try:
        import csv
        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["文件名", "算法", "哈希值", "文件大小(bytes)"])
            for r in results:
                w.writerow([
                    os.path.basename(r["file"]),
                    r["algo"],
                    r["hash"],
                    r.get("size", 0),
                ])
        return True
    except Exception:
        return False


def export_txt(results: List[Dict], output_path: str) -> bool:
    """导出哈希列表为 TXT 文件"""
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            for r in results:
                f.write(f"{r['hash']}  {os.path.basename(r['file'])}\n")
        return True
    except Exception:
        return False
