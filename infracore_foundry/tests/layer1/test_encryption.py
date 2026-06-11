"""Tests for the encryption module."""

import os
import pytest
from layer1_ingestion.core.encryption import encrypt_value, decrypt_value, generate_encryption_key


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        os.environ["ENCRYPTION_KEY"] = generate_encryption_key()
        plaintext = "my_secret_password_123"
        encrypted = encrypt_value(plaintext)
        assert encrypted != plaintext
        decrypted = decrypt_value(encrypted)
        assert decrypted == plaintext

    def test_encrypted_value_format(self):
        os.environ["ENCRYPTION_KEY"] = generate_encryption_key()
        encrypted = encrypt_value("test")
        # Should be base64 encoded
        import base64
        decoded = base64.b64decode(encrypted)
        assert len(decoded) > 0

    def test_generate_key_length(self):
        key = generate_encryption_key()
        import base64
        raw = base64.b64decode(key)
        assert len(raw) == 32  # 256 bits
