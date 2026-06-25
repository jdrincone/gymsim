"""Puerto: la interfaz que implementan los sinks (a dónde van los eventos)."""
from __future__ import annotations

from typing import Protocol

from .domain.events import AccessEvent
from .domain.member import Member


class EventSink(Protocol):
    """Destino de los eventos generados (memoria, archivo JSONL o Postgres)."""

    def open(self) -> None: ...

    def write_members(self, members: list[Member]) -> None:
        """Persiste el catálogo de socios (dim_member) y sus datos de contacto."""

    def emit(self, event: AccessEvent) -> None:
        """Emite un evento de paso."""

    def close(self) -> None: ...
