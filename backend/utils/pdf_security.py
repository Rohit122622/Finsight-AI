"""
FinSentry AI — Locked PDF security utilities.

Provides:
  * generate_pdf_password()   -> cryptographically-random report password (FS-XXXX-XXXX-XXXX)
  * encrypt_pdf_bytes()       -> AES-256 encrypted PDF bytes (via pypdf)
  * encrypt_password_at_rest()/decrypt_password_at_rest() -> Fernet at-rest protection

SECURITY INVARIANTS:
  - Passwords are generated with the `secrets` module (CSPRNG), never predictable data.
  - The plaintext password is NEVER logged and NEVER persisted in plaintext.
  - The at-rest key is a dedicated PDF_SECRET_KEY, or derived from JWT_SECRET_KEY if unset.
  - Encryption happens on in-memory bytes; the unlocked PDF is never written to disk/DB.
"""

from __future__ import annotations

import base64
import hashlib
import io
import secrets
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from pypdf import PdfReader, PdfWriter

from core.config import get_settings

# Unambiguous alphabet (no 0/O/1/I/L) for human-typeable passwords.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_GROUP_LEN = 4
_GROUP_COUNT = 3  # FS-XXXX-XXXX-XXXX


def generate_pdf_password() -> str:
    """
    Return a cryptographically-random report-specific password.

    Format: FS-XXXX-XXXX-XXXX using an unambiguous uppercase/digit alphabet.
    ~14.6 bits per group * 3 = ~44 bits of entropy from a CSPRNG.
    """
    groups = [
        "".join(secrets.choice(_ALPHABET) for _ in range(_GROUP_LEN))
        for _ in range(_GROUP_COUNT)
    ]
    return "FS-" + "-".join(groups)


def encrypt_pdf_bytes(pdf_bytes: bytes, password: str) -> bytes:
    """
    Return AES-256 encrypted PDF bytes protected by `password`.

    The input unlocked bytes exist only in memory; the returned bytes are the
    only artifact that should ever be persisted/downloaded/emailed.
    """
    if not pdf_bytes:
        raise ValueError("Cannot encrypt empty PDF bytes.")
    if not password:
        raise ValueError("A non-empty password is required to encrypt the PDF.")

    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter(clone_from=reader)

    # AES-256 is the strongest algorithm pypdf supports reliably.
    writer.encrypt(user_password=password, owner_password=None, algorithm="AES-256")

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def decrypt_pdf_bytes(encrypted_bytes: bytes, password: str) -> bytes:
    """
    Return UNLOCKED PDF bytes by decrypting `encrypted_bytes` with `password`.

    Used ONLY to stream an unlocked copy to the authenticated owner on demand.
    The unlocked bytes exist only in memory and are NEVER persisted. Raises
    ValueError if the password does not open the document.
    """
    if not encrypted_bytes:
        raise ValueError("Cannot decrypt empty PDF bytes.")
    if not password:
        raise ValueError("A password is required to decrypt the PDF.")

    reader = PdfReader(io.BytesIO(encrypted_bytes))
    if reader.is_encrypted:
        result = reader.decrypt(password)
        if result == 0 or result is False:
            raise ValueError("Incorrect password for PDF decryption.")

    # Re-serialize without encryption -> unlocked PDF (in memory only).
    writer = PdfWriter(clone_from=reader)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def is_pdf_encrypted(pdf_bytes: bytes) -> bool:
    """Return True if the given PDF bytes are encrypted."""
    try:
        return bool(PdfReader(io.BytesIO(pdf_bytes)).is_encrypted)
    except Exception:
        return False


def can_open_with_password(pdf_bytes: bytes, password: str) -> bool:
    """
    Return True if `password` successfully decrypts the PDF. Used by tests to
    verify wrong/right password behavior. Never logs the password.
    """
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        if not reader.is_encrypted:
            return False
        result = reader.decrypt(password)
        # pypdf returns PasswordType (0 == failed) or truthy on success
        if result == 0 or result is False:
            return False
        # Touch a page to confirm decryption really worked
        _ = len(reader.pages)
        return True
    except Exception:
        return False


def _derive_fernet_key() -> bytes:
    """
    Build a valid Fernet key from PDF_SECRET_KEY (preferred) or JWT_SECRET_KEY.

    Fernet requires 32 url-safe base64-encoded bytes; we derive them via SHA-256
    so any-length secret works.
    """
    settings = get_settings()
    secret = (settings.PDF_SECRET_KEY or settings.JWT_SECRET_KEY or "finsentry-fallback").encode("utf-8")
    digest = hashlib.sha256(secret).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_password_at_rest(plaintext_password: str) -> str:
    """Return a Fernet token for storing the PDF password securely at rest."""
    f = Fernet(_derive_fernet_key())
    return f.encrypt(plaintext_password.encode("utf-8")).decode("utf-8")


def decrypt_password_at_rest(token: str) -> Optional[str]:
    """Return the plaintext PDF password from a stored Fernet token, or None if invalid."""
    if not token:
        return None
    try:
        f = Fernet(_derive_fernet_key())
        return f.decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):
        return None
