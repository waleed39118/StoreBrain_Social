"""Medical terminology loaded from the current content release (``terminology/*.json``).

Each file maps a term to its entry, e.g. ``{"BP": {"ar": "ضغط الدم", "en": "Blood pressure"}}``.
Later files override earlier ones (alphabetical order). Reloads swap the whole
table at once, so lookups never see a half-loaded state.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TerminologyStore:
    def __init__(self) -> None:
        self._terms: Mapping[str, Any] = {}

    def __len__(self) -> int:
        return len(self._terms)

    def load(self, release_dir: Path) -> int:
        table: dict[str, Any] = {}
        for path in sorted((Path(release_dir) / "terminology").glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError(f"{path.name} must contain a JSON object")
            table.update({_key(k): v for k, v in data.items()})
        self._terms = table  # atomic swap
        logger.info("Terminology loaded: %d terms", len(table))
        return len(table)

    def lookup(self, term: str) -> Any | None:
        return self._terms.get(_key(term))


def _key(term: str) -> str:
    return " ".join(term.casefold().split())
