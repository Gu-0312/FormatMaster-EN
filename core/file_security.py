"""file_security — 文件安全工具。

- 加密/解密：密码经 scrypt 派生密钥，Fernet（AES-128-CBC + HMAC-SHA256）加密。
  输出格式：8 字节魔数 `FMSEC01\\0` + 16 字节 salt +
  若干块 [4 字节块长 + Fernet token]，分块流式处理支持大文件。
- 粉碎：多次随机数据覆写 + fsync 落盘后删除，防止数据恢复。
纯函数，无 UI 依赖。
"""

import os
import secrets

try:
    import cryptography  # noqa: F401 - 启动即检查，缺失时给出明确提示
    from cryptography.fernet import Fernet, InvalidToken
    _CRYPTO_OK = True
except Exception:  # noqa: BLE001
    _CRYPTO_OK = False
    Fernet = None          # type: ignore[assignment]
    InvalidToken = Exception

_MISSING_MSG = ("缺少 cryptography 模块：打包运行请重新打包（build.py 已含收集配置）；"
                "源码运行请执行 pip install cryptography")

MAGIC = b"FMSEC01\0"
_SALT_LEN = 16
_DEFAULT_PASSES = 3
_BLOCK = 16 * 1024 * 1024   # 分块大小 16MB，避免大文件整读入内存

# Fernet token 首字节必是 url-safe base64 字符（用于区分新旧格式）
_B64URL_CHARS = frozenset(
    b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


def _derive_key(password: str, salt: bytes) -> bytes:
    """scrypt 派生 Fernet key（base64 编码，拖慢暴力破解）。"""
    import base64
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    kdf = Scrypt(salt=salt, length=32, n=2 ** 14, r=8, p=1)
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def encrypt_file(input_path, output_path, password, progress_cb=None):
    """加密文件 → 输出加密文件（含魔数+salt，分块流式）。成功返回 True。"""
    if not _CRYPTO_OK:
        if progress_cb:
            progress_cb(-1, _MISSING_MSG)
        return False
    try:
        salt = secrets.token_bytes(_SALT_LEN)
        key = _derive_key(password, salt)
        f = Fernet(key)
        size = os.path.getsize(input_path)
        os.makedirs(os.path.dirname(os.path.abspath(output_path)),
                    exist_ok=True)
        if progress_cb:
            progress_cb(5, "读取文件…")
        done = 0
        with open(input_path, "rb") as fin, open(output_path, "wb") as fout:
            fout.write(MAGIC + salt)
            while True:
                chunk = fin.read(_BLOCK)
                if not chunk:
                    break
                tok = f.encrypt(chunk)
                fout.write(len(tok).to_bytes(4, "big") + tok)
                done += len(chunk)
                if progress_cb:
                    pct = int(done * 90 / size) if size else 90
                    progress_cb(pct, f"加密中 {done // 1048576}/{size // 1048576} MB…")
        if progress_cb:
            progress_cb(100, "完成")
        return True
    except OSError as e:
        if progress_cb:
            progress_cb(-1, f"错误：{e}")
        return False
    except Exception as e:  # noqa: BLE001
        if progress_cb:
            progress_cb(-1, f"加密失败：{e}")
        return False


def decrypt_file(input_path, output_path, password, progress_cb=None):
    """解密文件。兼容两种格式：
    - 新格式（分块流式）：salt 后是 [4 字节块长 + token] × N
    - 旧格式（整体 token）：salt 后直接是单个 Fernet token
    密码错误/文件损坏返回 False。
    """
    if not _CRYPTO_OK:
        if progress_cb:
            progress_cb(-1, _MISSING_MSG)
        return False
    try:
        with open(input_path, "rb") as fh:
            head = fh.read(len(MAGIC))
            if head != MAGIC:
                if progress_cb:
                    progress_cb(-1, "错误：不是本工具加密的文件")
                return False
            salt = fh.read(_SALT_LEN)
            rest = fh.read()
        key = _derive_key(password, salt)
        f = Fernet(key)
        size = os.path.getsize(input_path)
        os.makedirs(os.path.dirname(os.path.abspath(output_path)),
                    exist_ok=True)
        # 格式判定：新格式首字节是块长度高位（0x00/0x01 等，非 base64url 字符）；
        # 旧格式首字节必是 Fernet token 的 base64url 字符（rest[0] 为 int 值）
        if rest and rest[0] in _B64URL_CHARS:
            # 旧格式：整体 token 一次解密
            data = f.decrypt(rest)
            with open(output_path, "wb") as fout:
                fout.write(data)
        else:
            # 新格式：分块解密
            done = 0
            with open(output_path, "wb") as fout:
                pos = 0
                while pos + 4 <= len(rest):
                    n = int.from_bytes(rest[pos:pos + 4], "big")
                    tok = rest[pos + 4:pos + 4 + n]
                    fout.write(f.decrypt(tok))
                    pos += 4 + n
                    done = pos
                    if progress_cb:
                        pct = int(done * 90 / size) if size else 90
                        progress_cb(pct, "解密中…")
        if progress_cb:
            progress_cb(100, "完成")
        return True
    except InvalidToken:
        if progress_cb:
            progress_cb(-1, "错误：密码不正确")
        return False
    except OSError as e:
        if progress_cb:
            progress_cb(-1, f"错误：{e}")
        return False
    except Exception as e:  # noqa: BLE001
        if progress_cb:
            progress_cb(-1, f"解密失败：{e}")
        return False


def _is_encrypted(path):
    """判断文件是否为本工具加密产物（读魔数）。"""
    try:
        with open(path, "rb") as fh:
            return fh.read(len(MAGIC)) == MAGIC
    except OSError:
        return False


def shred_file(path, passes=_DEFAULT_PASSES, progress_cb=None):
    """粉碎单个文件：随机覆写 N 遍 + fsync 后删除。"""
    try:
        size = os.path.getsize(path)
        with open(path, "r+b") as fh:
            chunk = 1 << 20
            for i in range(passes):
                fh.seek(0)
                remaining = size
                while remaining > 0:
                    n = min(chunk, remaining)
                    fh.write(secrets.token_bytes(n))
                    remaining -= n
                fh.flush()
                os.fsync(fh.fileno())
                if progress_cb:
                    progress_cb(int((i + 1) * 90 / passes), f"覆写第 {i + 1}/{passes} 遍…")
        os.remove(path)
        if progress_cb:
            progress_cb(100, "已粉碎删除")
        return True
    except OSError as e:
        if progress_cb:
            progress_cb(-1, f"粉碎失败：{e}")
        return False


def shred_paths(paths, passes=_DEFAULT_PASSES, progress_cb=None):
    """批量粉碎文件。返回 (成功数, 失败列表)。"""
    total = len(paths)
    ok = 0
    failed = []
    for i, p in enumerate(paths):
        if progress_cb:
            progress_cb(int(i * 100 / max(total, 1)),
                        f"粉碎 {os.path.basename(p)} ({i + 1}/{total})…")
        if shred_file(p, passes):
            ok += 1
        else:
            failed.append(p)
    return ok, failed
