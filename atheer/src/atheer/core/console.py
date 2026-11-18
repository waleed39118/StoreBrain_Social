"""Console output that is safe for Arabic text and emoji on every platform."""

from __future__ import annotations

import sys


def configure_console() -> None:
    """Write UTF-8 and never crash on unencodable characters.

    Older Windows consoles and redirected output default to a legacy code page
    (e.g. cp1252), where printing Arabic or emoji raises UnicodeEncodeError.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # stream already detached or not reconfigurable
                pass
