"""Modelo de evento de paso por la registradora (entrada/salida)."""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime

IN = "IN"
OUT = "OUT"
GRANTED = "GRANTED"
DENIED = "DENIED"


def content_uuid(
    device_id: str,
    member_external_id: str | None,
    credential_id: str,
    direction: str,
    true_ts: datetime,
    noise_kind: str | None,
) -> str:
    """UUID determinístico **basado en el contenido lógico** del evento.

    No depende del orden de generación ni de un contador global, así que regenerar
    una ventana temporal produce exactamente los mismos UUIDs → idempotencia real
    (clave para el llenado incremental con `gymsim tick`). Ver memoria
    self-living-free-fill.
    """
    key = "|".join(
        [
            device_id,
            member_external_id or "",
            credential_id,
            direction,
            true_ts.isoformat(),
            noise_kind or "",
        ]
    )
    h = hashlib.sha1(key.encode()).hexdigest()
    return str(uuid.UUID(h[:32]))


@dataclass
class AccessEvent:
    """Un evento de hardware. Incluye campos de ground-truth (no se persisten a producción)."""

    device_id: str
    credential_id: str
    direction: str
    device_ts: datetime           # reloj del dispositivo (puede traer drift)
    raw_seq: int = -1             # se asigna al ordenar por dispositivo
    result: str = GRANTED
    reason: str = "OK"
    ingested_at: datetime | None = None

    # ── Ground-truth (validación de la analítica) ──
    member_external_id: str | None = None
    true_ts: datetime | None = None        # timestamp real sin drift
    visit_id: int | None = None            # visita real a la que pertenece
    noise_kind: str | None = None          # None=limpio / duplicate / reentry / denied

    @property
    def event_uuid(self) -> str:
        return content_uuid(
            self.device_id,
            self.member_external_id,
            self.credential_id,
            self.direction,
            self.true_ts or self.device_ts,
            self.noise_kind,
        )

    def to_message(self) -> dict:
        """Mensaje del contrato de datos enviado al topic / fila raw (sin ground-truth)."""
        return {
            "event_uuid": self.event_uuid,
            "device_id": self.device_id,
            "raw_seq": self.raw_seq,
            "credential_id": self.credential_id,
            "direction": self.direction,
            "result": self.result,
            "reason": self.reason,
            "device_ts": self.device_ts.isoformat(),
            "ingested_at": (self.ingested_at or self.device_ts).isoformat(),
        }

    def to_record(self) -> dict:
        """Registro completo (mensaje + ground-truth) para modo seco/validación."""
        rec = self.to_message()
        rec.update(
            {
                "member_external_id": self.member_external_id,
                "true_ts": self.true_ts.isoformat() if self.true_ts else None,
                "visit_id": self.visit_id,
                "noise_kind": self.noise_kind,
            }
        )
        return rec
