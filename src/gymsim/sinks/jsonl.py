"""Sink a archivos JSONL: inspección local sin BD. Escribe eventos y catálogo de socios."""
from __future__ import annotations

import json
from pathlib import Path

from ..domain.events import AccessEvent
from ..domain.member import Member


class JsonlSink:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.members_path = self.path.with_name(self.path.stem + "_members.jsonl")
        self._fh = None

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("w", encoding="utf-8")

    def write_members(self, members: list[Member]) -> None:
        with self.members_path.open("w", encoding="utf-8") as f:
            for m in members:
                f.write(
                    json.dumps(
                        {
                            "external_id": m.external_id,
                            "credential_id": m.credential_id,
                            "email": m.email,
                            "phone": m.phone,
                            "join_week": m.join_week,
                            "group_id": m.group_id,
                            "archetype_hint": m.archetype.value,  # ground-truth
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    def emit(self, event: AccessEvent) -> None:
        assert self._fh is not None
        self._fh.write(json.dumps(event.to_record(), ensure_ascii=False) + "\n")

    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None
