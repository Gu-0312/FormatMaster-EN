"""crypto_advanced — 高级加密工具（RSA/ECC 非对称 · 数字签名 · AES-GCM · X.509 证书）。

- generate_keypair(): RSA/ECC 密钥对生成
- encrypt/decrypt_asymmetric(): 混合加密（AES-GCM 会话密钥 + RSA-OAEP / ECDH）
- sign_file()/verify_signature(): 数字签名（RSA-PSS / ECDSA）
- encrypt/decrypt_file_gcm(): 纯 AES-GCM 认证加密（比 Fernet 更快）
- generate_self_signed_cert(): X.509 自签名证书

依赖 cryptography；缺失时 _CRYPTO_OK=False，各函数给出明确提示。
"""
import base64
import os
import secrets

try:
    import cryptography  # noqa: F401
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, ec, padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    import datetime
    _CRYPTO_OK = True
except Exception:  # noqa: BLE001
    _CRYPTO_OK = False

_MISSING_MSG = ("缺少 cryptography 模块：请执行 pip install cryptography")
MAGIC = b"FMCRY01\0"          # 高级加密格式魔数
_BLOCK = 16 * 1024 * 1024     # 分块 16MB


# ── 密钥对生成 ──────────────────────────────────

def generate_keypair(algorithm="rsa", key_size=2048, curve="SECP256R1"):
    """生成密钥对，返回 (private_pem, public_pem) 字节。

    algorithm: "rsa"（默认 2048） / "ecc"（默认 SECP256R1）。
    """
    if not _CRYPTO_OK:
        return None, None
    try:
        if algorithm == "ecc":
            cname = getattr(ec, curve, ec.SECP256R1)
            private = ec.generate_private_key(cname())
        else:
            private = rsa.generate_private_key(
                public_exponent=65537, key_size=int(key_size))
        private_pem = private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption())
        public_pem = private.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo)
        return private_pem, public_pem
    except Exception:  # noqa: BLE001
        return None, None


def _load_private(pem: bytes):
    return serialization.load_pem_private_key(pem, password=None)


def _load_public(pem: bytes):
    return serialization.load_pem_public_key(pem)


# ── 混合加密（非对称 + AES-GCM 会话密钥）────────

def encrypt_asymmetric(input_path, output_path, public_key_pem, progress_cb=None):
    """公钥加密文件（混合加密）。

    输出格式：魔数 + 1字节算法(0=RSA/1=ECC) + 4字节会话密钥长度 +
    会话密钥密文 + 12字节 nonce + 密文分块（块长 4 字节前缀）。
    """
    if not _CRYPTO_OK:
        if progress_cb: progress_cb(-1, _MISSING_MSG)
        return False
    try:
        pub = _load_public(public_key_pem)
        # 生成 AES-256 会话密钥
        session_key = secrets.token_bytes(32)
        if isinstance(pub, rsa.RSAPublicKey):
            algo = b"\x00"
            enc_key = pub.encrypt(
                session_key,
                padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),
                             algorithm=hashes.SHA256(), label=None))
        else:
            algo = b"\x01"
            # ECC: ECDH 派生共享密钥
            eph = ec.generate_private_key(pub.curve)
            shared = eph.exchange(ec.ECDH(), pub)
            _h = hashes.Hash(hashes.SHA256())
            _h.update(shared)
            session_key = _h.finalize()
            enc_key = eph.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo)
        nonce = secrets.token_bytes(12)
        aes = AESGCM(session_key)
        size = os.path.getsize(input_path)
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        done = 0
        with open(input_path, "rb") as fin, open(output_path, "wb") as fout:
            fout.write(MAGIC + algo)
            fout.write(len(enc_key).to_bytes(4, "big") + enc_key)
            fout.write(nonce)
            while True:
                chunk = fin.read(_BLOCK)
                if not chunk:
                    break
                ct = aes.encrypt(nonce, chunk, None)
                fout.write(len(ct).to_bytes(4, "big") + ct)
                done += len(chunk)
                if progress_cb and size:
                    progress_cb(int(done * 90 / size), f"加密中 {done // 1048576}MB…")
        if progress_cb:
            progress_cb(100, "完成")
        return True
    except Exception as e:  # noqa: BLE001
        if progress_cb: progress_cb(-1, f"加密失败：{e}")
        return False


def decrypt_asymmetric(input_path, output_path, private_key_pem, progress_cb=None):
    """私钥解密文件（encrypt_asymmetric 的逆过程）。"""
    if not _CRYPTO_OK:
        if progress_cb: progress_cb(-1, _MISSING_MSG)
        return False
    try:
        priv = _load_private(private_key_pem)
        with open(input_path, "rb") as fh:
            head = fh.read(len(MAGIC))
            if head != MAGIC:
                if progress_cb: progress_cb(-1, "不是本工具非对称加密的文件")
                return False
            algo = fh.read(1)
            n = int.from_bytes(fh.read(4), "big")
            enc_key = fh.read(n)
            nonce = fh.read(12)
            rest = fh.read()
        if algo == b"\x00":
            session_key = priv.decrypt(
                enc_key,
                padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),
                             algorithm=hashes.SHA256(), label=None))
        else:
            eph_pub = _load_public(enc_key)
            shared = priv.exchange(ec.ECDH(), eph_pub)
            _h = hashes.Hash(hashes.SHA256())
            _h.update(shared)
            session_key = _h.finalize()
        aes = AESGCM(session_key)
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        done = 0
        with open(output_path, "wb") as fout:
            pos = 0
            while pos + 4 <= len(rest):
                ln = int.from_bytes(rest[pos:pos + 4], "big")
                tok = rest[pos + 4:pos + 4 + ln]
                fout.write(aes.decrypt(nonce, tok, None))
                pos += 4 + ln
                done = pos
                if progress_cb:
                    progress_cb(min(int(done * 90 / max(len(rest), 1)), 95), "解密中…")
        if progress_cb:
            progress_cb(100, "完成")
        return True
    except Exception as e:  # noqa: BLE001
        if progress_cb: progress_cb(-1, f"解密失败：{e}")
        return False


# ── 数字签名 ────────────────────────────────────

def sign_file(input_path, private_key_pem, signature_path=None, progress_cb=None):
    """私钥签名文件，返回签名字节（RSA-PSS / ECDSA 自动适配）。"""
    if not _CRYPTO_OK:
        if progress_cb: progress_cb(-1, _MISSING_MSG)
        return None
    try:
        priv = _load_private(private_key_pem)
        with open(input_path, "rb") as fh:
            data = fh.read()
        _h = hashes.Hash(hashes.SHA256())
        _h.update(data)
        h = _h.finalize()
        if isinstance(priv, rsa.RSAPrivateKey):
            sig = priv.sign(
                h, padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                               salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256())
        else:
            sig = priv.sign(h, ec.ECDSA(hashes.SHA256()))
        if signature_path:
            os.makedirs(os.path.dirname(os.path.abspath(signature_path)),
                        exist_ok=True)
            with open(signature_path, "wb") as f:
                f.write(sig)
        if progress_cb:
            progress_cb(100, "签名完成")
        return sig
    except Exception as e:  # noqa: BLE001
        if progress_cb: progress_cb(-1, f"签名失败：{e}")
        return None


def verify_signature(input_path, public_key_pem, signature, progress_cb=None):
    """公钥验签，返回 (ok, msg)。signature 为字节或签名文件路径。"""
    if not _CRYPTO_OK:
        if progress_cb: progress_cb(-1, _MISSING_MSG)
        return False, _MISSING_MSG
    try:
        if isinstance(signature, (bytes, bytearray)):
            sig = bytes(signature)
        else:
            with open(signature, "rb") as f:
                sig = f.read()
        pub = _load_public(public_key_pem)
        with open(input_path, "rb") as fh:
            data = fh.read()
        _h = hashes.Hash(hashes.SHA256())
        _h.update(data)
        h = _h.finalize()
        if isinstance(pub, rsa.RSAPublicKey):
            pub.verify(
                sig, h,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                            salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256())
        else:
            pub.verify(sig, h, ec.ECDSA(hashes.SHA256()))
        if progress_cb:
            progress_cb(100, "验签通过")
        return True, "签名有效"
    except Exception:  # noqa: BLE001 - 验签失败统一返回 False
        if progress_cb:
            progress_cb(100, "验签失败")
        return False, "签名无效或文件被篡改"


# ── 纯 AES-GCM 认证加密（比 Fernet 快）──────────

def _gcm_derive_key(password: str, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    kdf = Scrypt(salt=salt, length=32, n=2 ** 14, r=8, p=1)
    return kdf.derive(password.encode("utf-8"))


def encrypt_file_gcm(input_path, output_path, password, progress_cb=None):
    """AES-GCM 加密（scrypt 派生密钥，认证加密，比 Fernet 快）。
    输出：魔数 + salt(16) + nonce(12) + 密文块（块长 4 字节前缀）。
    """
    if not _CRYPTO_OK:
        if progress_cb: progress_cb(-1, _MISSING_MSG)
        return False
    try:
        salt = secrets.token_bytes(16)
        nonce = secrets.token_bytes(12)
        key = _gcm_derive_key(password, salt)
        aes = AESGCM(key)
        size = os.path.getsize(input_path)
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        done = 0
        with open(input_path, "rb") as fin, open(output_path, "wb") as fout:
            fout.write(MAGIC + b"G" + salt + nonce)
            while True:
                chunk = fin.read(_BLOCK)
                if not chunk:
                    break
                ct = aes.encrypt(nonce, chunk, None)
                fout.write(len(ct).to_bytes(4, "big") + ct)
                done += len(chunk)
                if progress_cb and size:
                    progress_cb(int(done * 90 / size), f"加密中 {done // 1048576}MB…")
        if progress_cb:
            progress_cb(100, "完成")
        return True
    except Exception as e:  # noqa: BLE001
        if progress_cb: progress_cb(-1, f"加密失败：{e}")
        return False


def decrypt_file_gcm(input_path, output_path, password, progress_cb=None):
    """AES-GCM 解密（encrypt_file_gcm 逆过程）。"""
    if not _CRYPTO_OK:
        if progress_cb: progress_cb(-1, _MISSING_MSG)
        return False
    try:
        with open(input_path, "rb") as fh:
            head = fh.read(len(MAGIC) + 1)
            if head[:len(MAGIC)] != MAGIC or head[-1:] != b"G":
                if progress_cb: progress_cb(-1, "不是本工具 GCM 加密的文件")
                return False
            salt = fh.read(16)
            nonce = fh.read(12)
            rest = fh.read()
        key = _gcm_derive_key(password, salt)
        aes = AESGCM(key)
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        done = 0
        with open(output_path, "wb") as fout:
            pos = 0
            while pos + 4 <= len(rest):
                ln = int.from_bytes(rest[pos:pos + 4], "big")
                tok = rest[pos + 4:pos + 4 + ln]
                fout.write(aes.decrypt(nonce, tok, None))
                pos += 4 + ln
                done = pos
                if progress_cb:
                    progress_cb(min(int(done * 90 / max(len(rest), 1)), 95), "解密中…")
        if progress_cb:
            progress_cb(100, "完成")
        return True
    except Exception as e:  # noqa: BLE001
        if progress_cb: progress_cb(-1, f"解密失败：{e}")
        return False


# ── X.509 自签名证书 ────────────────────────────

def generate_self_signed_cert(common_name, output_path, private_key_path=None,
                              days=365, key_size=2048, progress_cb=None):
    """生成 X.509 自签名证书。

    返回 (cert_path, private_key_path)；密钥未指定时生成 RSA 密钥对并
    一并保存（证书与私钥分离，私钥供服务器/签名使用）。
    """
    if not _CRYPTO_OK:
        if progress_cb: progress_cb(-1, _MISSING_MSG)
        return None, None
    try:
        if private_key_path and os.path.isfile(private_key_path):
            with open(private_key_path, "rb") as f:
                private = _load_private(f.read())
        else:
            private = rsa.generate_private_key(
                public_exponent=65537, key_size=int(key_size))
            private_key_path = private_key_path or (output_path + ".key")
            os.makedirs(os.path.dirname(os.path.abspath(private_key_path)),
                        exist_ok=True)
            with open(private_key_path, "wb") as f:
                f.write(private.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()))
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=int(days)))
            .sign(private, hashes.SHA256())
        )
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        if progress_cb:
            progress_cb(100, "证书已生成")
        return output_path, private_key_path
    except Exception as e:  # noqa: BLE001
        if progress_cb: progress_cb(-1, f"证书生成失败：{e}")
        return None, None
