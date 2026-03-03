"""
crypto_helper.py
================
Fix #6: Symmetric encryption helper for sensitive values at rest.

Uses Fernet (AES-128-CBC + HMAC-SHA256) via the `cryptography` library.

Setup:
  Generate a key once and add to your .env file:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # → Add to .env: OIPRO_ENCRYPT_KEY=<generated key>

Usage:
  from lib.utils.crypto_helper import encrypt_value, decrypt_value
  encrypted = encrypt_value("my-api-key")      # returns encrypted string
  plaintext = decrypt_value(encrypted)          # returns original string
"""
import os
import logging

logger = logging.getLogger("OIPRO")

# --- Key Setup ---
_raw_key = os.getenv("OIPRO_ENCRYPT_KEY")
_fernet = None

if _raw_key:
    try:
        from cryptography.fernet import Fernet
        _fernet = Fernet(_raw_key.encode() if isinstance(_raw_key, str) else _raw_key)
        logger.info("[CORE] [Crypto] Fernet encryption initialized for broker credentials.")
    except Exception as _e:
        logger.warning(
            f"[CORE] [Crypto] Invalid OIPRO_ENCRYPT_KEY — broker credentials will NOT be encrypted at rest! "
            f"Error: {_e}"
        )
else:
    logger.warning(
        "[CORE] [Crypto] OIPRO_ENCRYPT_KEY is not set. "
        "Broker API keys and access tokens will be stored in plaintext. "
        "Generate a key and add to .env: "
        "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
    )


# Prefix to identify encrypted values stored in DB
_ENCRYPTED_PREFIX = "enc::"


def encrypt_value(plaintext: str) -> str:
    """
    Encrypts a plaintext string using Fernet symmetric encryption.
    Returns the encrypted string with an 'enc::' prefix.
    If OIPRO_ENCRYPT_KEY is not set or invalid, returns plaintext unchanged (with a warning log).
    """
    if not plaintext:
        return plaintext
    # Don't double-encrypt already encrypted values
    if plaintext.startswith(_ENCRYPTED_PREFIX):
        return plaintext
    if _fernet is None:
        logger.debug("[CORE] [Crypto] No encryption key — skipping encryption.")
        return plaintext
    try:
        encrypted = _fernet.encrypt(plaintext.encode("utf-8"))
        return _ENCRYPTED_PREFIX + encrypted.decode("utf-8")
    except Exception as e:
        logger.error(f"[CORE] [Crypto] Encryption failed: {e}")
        return plaintext


def decrypt_value(ciphertext: str) -> str:
    """
    Decrypts a Fernet-encrypted string produced by encrypt_value().
    If the value does not have the 'enc::' prefix (legacy plaintext), returns it unchanged.
    If decryption fails, logs an error and returns the original value.
    """
    if not ciphertext:
        return ciphertext
    if not ciphertext.startswith(_ENCRYPTED_PREFIX):
        # Legacy plaintext value — return as-is (backward compatible)
        return ciphertext
    if _fernet is None:
        logger.error(
            "[CORE] [Crypto] Cannot decrypt — OIPRO_ENCRYPT_KEY is not set. "
            "Encrypted broker credential cannot be used."
        )
        return ""
    try:
        raw = ciphertext[len(_ENCRYPTED_PREFIX):]
        decrypted = _fernet.decrypt(raw.encode("utf-8"))
        return decrypted.decode("utf-8")
    except Exception as e:
        logger.error(f"[CORE] [Crypto] Decryption failed: {e}")
        return ""


def is_encrypted(value: str) -> bool:
    """Returns True if the value was encrypted by encrypt_value()."""
    return bool(value and value.startswith(_ENCRYPTED_PREFIX))
