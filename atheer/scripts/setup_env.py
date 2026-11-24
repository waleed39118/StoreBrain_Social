"""Create .env from .env.example on first install and generate a staff key.

Safe to run again: an existing .env is never overwritten, and an existing staff
key is kept. Prints the key so the installer can show it to the user.
"""

from __future__ import annotations

import re
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
env, example = root / ".env", root / ".env.example"

if not env.exists():
    env.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    print("Created .env from .env.example")

text = env.read_text(encoding="utf-8")
match = re.search(r"^ATHEER_STAFF_API_KEY=(.+)$", text, flags=re.M)
if match and match.group(1).strip():
    key = match.group(1).strip()
else:
    key = secrets.token_urlsafe(24)
    text = re.sub(r"^#\s*ATHEER_STAFF_API_KEY=.*$", "", text, flags=re.M).rstrip() + f"\nATHEER_STAFF_API_KEY={key}\n"
    env.write_text(text, encoding="utf-8")

print()
print("Staff key for the reception panel / مفتاح لوحة الاستقبال:")
print(f"    {key}")
print("It is saved in the .env file next to Atheer.")
