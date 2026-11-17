"""Minimal in-process domain event bus.

Services publish events *after* their transaction commits. Subscribers (the
receptionist layer, notifiers, the memory store) react without the services
knowing about them. A failing subscriber is logged and isolated so it can never
break a booking.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any

logger = logging.getLogger(__name__)

WILDCARD = "*"


@dataclass(frozen=True, slots=True)
class DomainEvent:
    name: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


Handler = Callable[[DomainEvent], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._lock = RLock()

    def subscribe(self, name: str, handler: Handler) -> Callable[[], None]:
        """Register ``handler`` for ``name`` (or ``"*"`` for all). Returns an unsubscribe function."""
        with self._lock:
            self._handlers[name].append(handler)

        def _unsubscribe() -> None:
            with self._lock:
                if handler in self._handlers[name]:
                    self._handlers[name].remove(handler)

        return _unsubscribe

    def publish(self, event: DomainEvent) -> None:
        with self._lock:
            handlers = [*self._handlers.get(event.name, ()), *self._handlers.get(WILDCARD, ())]
        for handler in handlers:
            try:
                handler(event)
            except Exception:  # noqa: BLE001 - subscriber faults must not propagate
                logger.exception("Event handler %r failed for event %s", handler, event.name)
