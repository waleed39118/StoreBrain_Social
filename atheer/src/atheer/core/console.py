"""Console output that is safe for Arabic text and emoji on every platform."""

from __future__ import annotations

import sys


def configure_console() -> None:
    """Read and write UTF-8, and never crash on characters a stream can't represent.

    Older Windows consoles and redirected input/output default to a legacy code
    page (e.g. cp1252): printing Arabic or emoji raises UnicodeEncodeError, and
    typed or piped Arabic is decoded as gibberish. Must run before any input is read.
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # stream already detached or not reconfigurable
                pass
