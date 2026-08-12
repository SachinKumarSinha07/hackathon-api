"""Password hashing utilities"""

import hashlib
import bcrypt


def _pre_hash_password(password: str) -> bytes:
    """
    Pre-hash password with SHA256 to handle any length passwords.
    bcrypt has a 72-byte limit, so we pre-hash to ensure compatibility.

    Args:
        password: Plain text password

    Returns:
        SHA256 digest (hex-encoded) of the password as bytes
    """
    return hashlib.sha256(password.encode("utf-8")).hexdigest().encode("utf-8")


def hash_password(password: str) -> str:
    """
    Hash a plain text password using bcrypt.
    Uses SHA256 pre-hashing to handle passwords of any length.

    Args:
        password: Plain text password

    Returns:
        Hashed password
    """
    pre_hashed = _pre_hash_password(password)
    hashed = bcrypt.hashpw(pre_hashed, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain text password against a hashed password.

    Args:
        plain_password: Plain text password to verify
        hashed_password: Hashed password from database

    Returns:
        True if password matches, False otherwise
    """
    pre_hashed = _pre_hash_password(plain_password)
    return bcrypt.checkpw(pre_hashed, hashed_password.encode("utf-8"))
