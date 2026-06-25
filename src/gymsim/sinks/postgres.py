"""Sink a Supabase/Postgres (SQLAlchemy 2.0). Inserción idempotente.

Crea los esquemas/tablas (create_all), siembra las dimensiones (dim_device, dim_member) y
escribe los eventos en raw.access_event_raw con ON CONFLICT DO NOTHING.
"""
from __future__ import annotations

from sqlalchemy import create_engine, text

from ..config import DeviceConfig
from ..domain.events import AccessEvent
from ..domain.member import Member
from ..db.models import SCHEMAS, Base


class PostgresSink:
    def __init__(
        self,
        dsn: str,
        devices: list[DeviceConfig] | None = None,
        site_id: str = "gym-01",
        batch_size: int = 1000,
    ) -> None:
        # normaliza el driver a psycopg v3
        if dsn.startswith("postgresql://"):
            dsn = dsn.replace("postgresql://", "postgresql+psycopg://", 1)
        self._engine = create_engine(dsn, future=True)
        self._devices = devices or []
        self._site_id = site_id
        self.batch_size = batch_size
        self._buffer: list[dict] = []

    def open(self) -> None:
        # crea los esquemas (raw/staging/curated) y las tablas
        with self._engine.begin() as conn:
            for sch in SCHEMAS:
                conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {sch}"))
        Base.metadata.create_all(self._engine)
        self._write_devices()

    def _write_devices(self) -> None:
        """Siembra curated.dim_device (las tablas de hechos referencian esta dimensión)."""
        if not self._devices:
            return
        rows = [
            {
                "device_id": d.device_id,
                "site_id": self._site_id,
                "door": d.door,
                "direction_mode": d.direction_mode,
                "antipassback": d.antipassback,
            }
            for d in self._devices
        ]
        stmt = text(
            """
            INSERT INTO curated.dim_device (device_id, site_id, door, direction_mode, antipassback)
            VALUES (:device_id, :site_id, :door, :direction_mode, :antipassback)
            ON CONFLICT (device_id) DO NOTHING
            """
        )
        with self._engine.begin() as conn:
            conn.execute(stmt, rows)

    def write_members(self, members: list[Member]) -> None:
        rows = [
            {
                "external_id": m.external_id,
                "email": m.email,
                "phone": m.phone,
                "archetype_hint": m.archetype.value,
            }
            for m in members
        ]
        stmt = text(
            """
            INSERT INTO curated.dim_member (external_id, email, phone, archetype_hint)
            VALUES (:external_id, :email, :phone, :archetype_hint)
            ON CONFLICT (external_id) DO NOTHING
            """
        )
        with self._engine.begin() as conn:
            conn.execute(stmt, rows)

    def emit(self, event: AccessEvent) -> None:
        msg = event.to_message()
        self._buffer.append(msg)
        if len(self._buffer) >= self.batch_size:
            self._flush()

    def _flush(self) -> None:
        if not self._buffer:
            return
        stmt = text(
            """
            INSERT INTO raw.access_event_raw
                (event_uuid, device_id, raw_seq, credential_id, direction,
                 result, reason, device_ts, ingested_at)
            VALUES
                (:event_uuid, :device_id, :raw_seq, :credential_id, :direction,
                 :result, :reason, :device_ts, :ingested_at)
            ON CONFLICT (event_uuid) DO NOTHING
            """
        )
        with self._engine.begin() as conn:
            conn.execute(stmt, self._buffer)
        self._buffer.clear()

    def close(self) -> None:
        self._flush()
        self._engine.dispose()
