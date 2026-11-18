"""Security primitives (stdlib only): phone normalisation, PIN hashing, tokens, OTPs."""
import hashlib
import hmac
import re
import secrets

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_SCRYPT = dict(n=2**14, r=8, p=1, dklen=32)   # ~16 MB, OWASP-recommended scrypt baseline


class PhoneError(ValueError):
    pass


def normalize_phone(raw: str, default_cc: str) -> str:
    """Return E.164 (``+9665XXXXXXXX``). Accepts +CC, 00CC, local 0-prefixed, Arabic digits."""
    s = re.sub(r"[\s\-().]", "", str(raw).translate(_AR_DIGITS))
    if s.startswith("+"):
        digits = s[1:]
    elif s.startswith("00"):
        digits = s[2:]
    elif s.startswith("0"):
        digits = default_cc + s[1:]
    else:
        digits = s
    if not digits.isdigit() or not 8 <= len(digits) <= 15 or digits.startswith("0"):
        raise PhoneError("Invalid phone number")
    return "+" + digits


def mask_phone(e164: str) -> str:
    return e164[:4] + "•" * max(len(e164) - 7, 0) + e164[-3:]


# ---------- PIN (staff) ----------
def hash_pin(pin: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(pin.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_pin(pin: str, stored: str | None) -> bool:
    if not stored:
        hashlib.scrypt(b"x", salt=b"0" * 16, **_SCRYPT)   # equalise timing for unknown users
        return False
    _, salt_hex, dk_hex = stored.split("$")
    dk = hashlib.scrypt(pin.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT)
    return hmac.compare_digest(dk.hex(), dk_hex)


def validate_pin_format(pin: str) -> None:
    if not (pin.isdigit() and 4 <= len(pin) <= 8):
        raise ValueError("PIN must be 4–8 digits")
    if len(set(pin)) == 1 or pin in "0123456789" or pin in "9876543210":
        raise ValueError("PIN is too easy to guess")


# ---------- tokens & OTP (keyed hashes; DB leak alone cannot reveal them) ----------
def new_token() -> str:
    return secrets.token_urlsafe(32)


def keyed_hash(secret: str, value: str) -> str:
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def new_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"
