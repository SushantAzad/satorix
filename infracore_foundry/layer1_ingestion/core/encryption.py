"""
AES-256-GCM encryption for storing connector credentials securely.
Key is loaded from ENCRYPTION_KEY environment variable only.
Never logs decrypted values. Never stores key in database.
"""

import base64
import logging
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

_NONCE_SIZE = 12  # 96-bit nonce for AES-GCM
_KEY_SIZE = 32  # 256-bit key


def _get_key() -> bytes:
    """
    Retrieve the encryption key from the ENCRYPTION_KEY environment variable.
    The key must be base64-encoded 32 bytes.
    """
    key_b64 = os.environ.get("ENCRYPTION_KEY", "")
    if not key_b64:
        raise ValueError(
            "ENCRYPTION_KEY environment variable is not set. "
            "Generate one with generate_key() and set it in .env"
        )
    try:
        key_bytes = base64.b64decode(key_b64)
    except Exception as exc:
        raise ValueError(
            "ENCRYPTION_KEY is not valid base64. "
            "Generate a valid key with generate_key()"
        ) from exc

    if len(key_bytes) != _KEY_SIZE:
        raise ValueError(
            f"ENCRYPTION_KEY must be exactly {_KEY_SIZE} bytes when decoded. "
            f"Got {len(key_bytes)} bytes. Generate a new key with generate_key()"
        )
    return key_bytes


def generate_key() -> str:
    """
    Generate a new AES-256-GCM encryption key.
    Returns a base64-encoded 32-byte key suitable for the ENCRYPTION_KEY env var.
    """
    raw_key = secrets.token_bytes(_KEY_SIZE)
    encoded = base64.b64encode(raw_key).decode("utf-8")
    logger.info("New encryption key generated (store this securely in .env)")
    return encoded


def encrypt_credential(plaintext: str) -> str:
    """
    Encrypt a credential string using AES-256-GCM.

    Args:
        plaintext: The credential value to encrypt.

    Returns:
        Base64-encoded string containing nonce + ciphertext + tag.
    """
    if not plaintext:
        raise ValueError("Cannot encrypt empty credential")

    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(_NONCE_SIZE)
    plaintext_bytes = plaintext.encode("utf-8")
    ciphertext = aesgcm.encrypt(nonce, plaintext_bytes, None)
    # Combine nonce + ciphertext (which includes the 16-byte GCM tag)
    combined = nonce + ciphertext
    encoded = base64.b64encode(combined).decode("utf-8")
    logger.debug("Credential encrypted successfully (length=%d)", len(encoded))
    return encoded


def decrypt_credential(ciphertext: str) -> str:
    """
    Decrypt a credential string encrypted with AES-256-GCM.

    Args:
        ciphertext: Base64-encoded string containing nonce + ciphertext + tag.

    Returns:
        The decrypted plaintext credential.
    """
    if not ciphertext:
        raise ValueError("Cannot decrypt empty ciphertext")

    key = _get_key()
    try:
        combined = base64.b64decode(ciphertext)
    except Exception as exc:
        raise ValueError("Ciphertext is not valid base64") from exc

    if len(combined) < _NONCE_SIZE + 16:
        raise ValueError(
            "Ciphertext too short: must contain at least nonce + GCM tag"
        )

    nonce = combined[:_NONCE_SIZE]
    encrypted_data = combined[_NONCE_SIZE:]
    aesgcm = AESGCM(key)
    try:
        plaintext_bytes = aesgcm.decrypt(nonce, encrypted_data, None)
    except Exception as exc:
        raise ValueError(
            "Decryption failed: invalid key or corrupted ciphertext"
        ) from exc

    return plaintext_bytes.decode("utf-8")