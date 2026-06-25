"""Modelos SQLAlchemy 2.0 (esquema en capas: raw / staging / curated)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMAS = ("raw", "staging", "curated")


class Base(DeclarativeBase):
    pass


# ── Dimensiones (curated) ────────────────────────────────────────────────────
class DimMember(Base):
    __tablename__ = "dim_member"
    __table_args__ = {"schema": "curated"}

    member_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String)        # PII (contacto para campañas)
    phone: Mapped[str | None] = mapped_column(String)        # PII
    join_date: Mapped["datetime | None"] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String, default="active", server_default=text("'active'"))
    archetype_hint: Mapped[str | None] = mapped_column(String)  # solo ground-truth/validación


class DimDevice(Base):
    __tablename__ = "dim_device"
    __table_args__ = {"schema": "curated"}

    device_id: Mapped[str] = mapped_column(String, primary_key=True)
    site_id: Mapped[str] = mapped_column(String, default="gym-01", server_default=text("'gym-01'"))
    door: Mapped[str | None] = mapped_column(String)
    direction_mode: Mapped[str] = mapped_column(
        String, default="BIDI", server_default=text("'BIDI'")
    )
    antipassback: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )


# ── RAW (bronze): eventos crudos, sin deduplicar, con ruido ──────────────────
class AccessEventRaw(Base):
    __tablename__ = "access_event_raw"
    __table_args__ = (
        Index("ix_raw_device_ts", "device_id", "device_ts"),
        Index("ix_raw_credential", "credential_id"),
        {"schema": "raw"},
    )

    event_uuid: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    device_id: Mapped[str] = mapped_column(String, nullable=False)
    raw_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    credential_id: Mapped[str] = mapped_column(String, nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)
    result: Mapped[str] = mapped_column(String, default="GRANTED", server_default=text("'GRANTED'"))
    reason: Mapped[str] = mapped_column(String, default="OK", server_default=text("'OK'"))
    device_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


# ── STAGING (silver): tipado, idempotente, marcado (no borrado) ──────────────
class StagingAccessEvent(Base):
    __tablename__ = "access_event"
    __table_args__ = (
        Index("ix_stg_member_ts", "member_id", "event_ts"),
        {"schema": "staging"},
    )

    event_uuid: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("raw.access_event_raw.event_uuid"), primary_key=True
    )
    member_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("curated.dim_member.member_id")
    )
    device_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("curated.dim_device.device_id")
    )
    direction: Mapped[str] = mapped_column(String, nullable=False)
    event_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    is_denied: Mapped[bool] = mapped_column(Boolean, default=False)
    is_suspect: Mapped[bool] = mapped_column(Boolean, default=False)
    dedup_group_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))


# ── CURATED (gold): hechos y sesiones ────────────────────────────────────────
class FactAccessEvent(Base):
    __tablename__ = "fact_access_event"
    __table_args__ = (
        Index("ix_fact_member_ts", "member_id", "event_ts"),
        Index("ix_fact_device_ts", "device_id", "event_ts"),
        Index("ix_fact_date", "date_key"),
        {"schema": "curated"},
    )

    event_uuid: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    member_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("curated.dim_member.member_id")
    )
    device_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("curated.dim_device.device_id")
    )
    event_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)
    date_key: Mapped[int] = mapped_column(Integer, nullable=False)
    time_key: Mapped[int] = mapped_column(Integer, nullable=False)


class SimState(Base):
    """Checkpoint del llenado incremental: ancla del reloj real ↔ simulado y avance.

    Una sola fila (id=1). real_anchor = instante real del primer tick; sim_checkpoint =
    último instante simulado ya volcado. Ver memoria self-living-free-fill.
    """

    __tablename__ = "sim_state"
    __table_args__ = {"schema": "raw"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, server_default=text("1"))
    real_anchor: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sim_checkpoint: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FactSession(Base):
    __tablename__ = "fact_session"
    __table_args__ = (
        Index("ix_session_member_ts", "member_id", "ts_in"),
        {"schema": "curated"},
    )

    session_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    member_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("curated.dim_member.member_id")
    )
    device_in: Mapped[str | None] = mapped_column(String)
    device_out: Mapped[str | None] = mapped_column(String)
    ts_in: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ts_out: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_min: Mapped[float | None] = mapped_column(Numeric)
    n_reentries: Mapped[int] = mapped_column(Integer, default=0)
    imputed_out: Mapped[bool] = mapped_column(Boolean, default=False)
    is_double_visit: Mapped[bool] = mapped_column(Boolean, default=False)
    date_key: Mapped[int] = mapped_column(Integer, nullable=False)
