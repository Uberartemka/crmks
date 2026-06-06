from __future__ import annotations

import hashlib
import secrets


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    phash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
    return f"{salt}${phash}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, phash = stored.split('$', 1)
        check = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
        return check == phash
    except Exception:
        return False
