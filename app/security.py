from __future__ import annotations

import hashlib
import hmac
import secrets

PBKDF2_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 210_000
SALT_BYTES = 16


def legacy_sha256_hash(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def api_key_lookup_hash(raw_key: str) -> str:
    return f"sha256:{legacy_sha256_hash(raw_key)}"


def hash_api_key(raw_key: str, *, salt: str | None = None) -> str:
    key_salt = salt or secrets.token_hex(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        raw_key.encode("utf-8"),
        key_salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    ).hex()
    return f"{PBKDF2_ALGORITHM}${PBKDF2_ITERATIONS}${key_salt}${digest}"


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    if stored_hash.startswith(f"{PBKDF2_ALGORITHM}$"):
        try:
            algorithm, iterations_text, salt, expected = stored_hash.split("$", 3)
            iterations = int(iterations_text)
        except ValueError:
            return False
        if algorithm != PBKDF2_ALGORITHM or iterations <= 0:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            raw_key.encode("utf-8"),
            salt.encode("utf-8"),
            iterations,
        ).hex()
        return hmac.compare_digest(digest, expected)
    return hmac.compare_digest(legacy_sha256_hash(raw_key), stored_hash)


def api_key_hash_needs_migration(stored_hash: str) -> bool:
    return not stored_hash.startswith(f"{PBKDF2_ALGORITHM}$")
