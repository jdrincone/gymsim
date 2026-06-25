"""Sink en memoria: para tests y validación sin infraestructura."""
from __future__ import annotations

from ..domain.events import AccessEvent
from ..domain.member import Member


class MemorySink:
    def __init__(self) -> None:
        self.members: list[Member] = []
        self.events: list[AccessEvent] = []

    def open(self) -> None:
        self.members.clear()
        self.events.clear()

    def write_members(self, members: list[Member]) -> None:
        self.members.extend(members)

    def emit(self, event: AccessEvent) -> None:
        self.events.append(event)

    def close(self) -> None:
        pass
