"""Versioned salted scrypt hashes; plaintext passwords are never stored."""
import hashlib
import hmac
import secrets


def hash_password(password: str, *, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode('utf-8'), salt=bytes.fromhex(salt),
                            n=32768, r=8, p=3, maxmem=64 * 1024 * 1024, dklen=32)
    return f'scrypt-v1${salt}${digest.hex()}'


def verify_password(password: str, encoded: str) -> bool:
    try:
        version, salt, digest = encoded.split('$')
        if version != 'scrypt-v1' or len(salt) != 32 or len(digest) != 64:
            return False
        actual = hash_password(password, salt=salt).split('$')[-1]
        return hmac.compare_digest(actual, digest)
    except (ValueError, TypeError):
        return False

# Matches real account verification work for unknown users; not a usable account.
DUMMY_HASH = hash_password('dummy-account-not-a-login', salt='00' * 16)
