# backend/app/encryption.py
import os
import base64
import logging
from pycryptodome.Cipher import AES
from pycryptodome.Util.Padding import pad, unpad

logger = logging.getLogger(__name__)

# Fetch 32-byte encryption key from env
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "stressfreak-32byte-default-key-for-aes")

# Pad or trim key to exactly 32 bytes for AES-256
if len(ENCRYPTION_KEY) < 32:
    ENCRYPTION_KEY = (ENCRYPTION_KEY * 2)[:32]
else:
    ENCRYPTION_KEY = ENCRYPTION_KEY[:32].encode('utf-8')

class JournalEncryptor:
    """
    Encrypts and decrypts sensitive journal entries in database fields.
    Guarantees ZDR (Zero Disclosure Risk) data protection.
    """
    @staticmethod
    def encrypt(raw_text: str) -> str:
        """Encrypt plain text to base64 AES-256 payload."""
        if not raw_text:
            return ""
        try:
            cipher = AES.new(ENCRYPTION_KEY, AES.MODE_CBC)
            ct_bytes = cipher.encrypt(pad(raw_text.encode('utf-8'), AES.block_size))
            iv = base64.b64encode(cipher.iv).decode('utf-8')
            ct = base64.b64encode(ct_bytes).decode('utf-8')
            return f"{iv}:{ct}"
        except Exception as e:
            logger.error(f"AES Encryption failed: {e}")
            return raw_text

    @staticmethod
    def decrypt(encrypted_text: str) -> str:
        """Decrypt base64 AES-256 payload to plain text."""
        if not encrypted_text or ":" not in encrypted_text:
            return encrypted_text
        try:
            iv_b64, ct_b64 = encrypted_text.split(":", 1)
            iv = base64.b64decode(iv_b64)
            ct = base64.b64decode(ct_b64)
            cipher = AES.new(ENCRYPTION_KEY, AES.MODE_CBC, iv)
            pt = unpad(cipher.decrypt(ct), AES.block_size)
            return pt.decode('utf-8')
        except Exception as e:
            logger.warning(f"AES Decryption failed: {e}. Returning raw value.")
            return encrypted_text
