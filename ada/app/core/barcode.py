"""Barcode normalisation and GTIN (EAN-8/UPC-A/EAN-13/GTIN-14) check-digit validation.

Validating the check digit catches scanner misreads and typing mistakes before they
reach the catalog. Non-numeric codes (Code128, QR payloads, internal labels) are accepted
as-is after normalisation.
"""
import re

_ALLOWED = re.compile(r"^[0-9A-Za-z\-_.]{1,64}$")
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
GTIN_LENGTHS = {8, 12, 13, 14}


class BarcodeError(ValueError):
    pass


def gtin_check_digit_ok(code: str) -> bool:
    digits = [int(c) for c in code]
    body, check = digits[:-1], digits[-1]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def normalize_barcode(raw: str | int | float | None) -> str | None:
    """Return a clean barcode, None for empty input, or raise BarcodeError."""
    if raw is None:
        return None
    if isinstance(raw, float):           # Excel turns long numbers into floats
        if raw != raw:                   # NaN
            return None
        raw = f"{raw:.0f}"
    code = str(raw).translate(_AR_DIGITS).strip().replace(" ", "")
    if not code:
        return None
    if not _ALLOWED.match(code):
        raise BarcodeError(f"Invalid barcode characters: {code!r}")
    if code.isdigit() and len(code) in GTIN_LENGTHS and not gtin_check_digit_ok(code):
        raise BarcodeError(f"Barcode {code} has an invalid check digit")
    return code
