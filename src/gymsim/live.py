"""Llenado incremental autónomo: cada `tick` inserta los eventos ocurridos desde el último
checkpoint, anclando el tiempo simulado al reloj real. Pensado para correr en un cron
gratuito (GitHub Actions). Idempotente y robusto a retrasos. Ver memoria self-living-free-fill.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from .config import SimConfig
from .simulation.engine import build_population_stable, make_calendar
from .simulation.windowed import events_between
from .sinks.postgres import PostgresSink

# Horizonte largo por defecto para el modo vivo: altas escalonadas por ~10 años.
LIVE_HORIZON_DAYS = 3650
# Máximo de días simulados que un solo tick puede volcar (cota ante pausas largas / accel alto).
MAX_CATCHUP_DAYS = 30
# Clave del advisory lock que serializa los ticks (el checkpoint es un recurso compartido).
# Dos ticks en paralelo (p. ej. cron + ejecución manual) no deben pisar raw.sim_state.
_TICK_LOCK_KEY = 911001


def _start_dt(config: SimConfig) -> datetime:
    return datetime.combine(config.time.start_date, datetime.min.time(), tzinfo=timezone.utc)


def run_tick(config: SimConfig, dsn: str, accel: float, now_real: datetime | None = None) -> dict:
    """Ejecuta un tick: calcula la ventana simulada hasta 'ahora' y vuelca sus eventos.

    accel: factor de aceleración (1.0 = a ritmo real; >1 comprime el tiempo y llena más rápido).
    """
    if config.time.horizon_days < LIVE_HORIZON_DAYS:
        config.time.horizon_days = LIVE_HORIZON_DAYS

    now_real = now_real or datetime.now(timezone.utc)
    start_dt = _start_dt(config)

    sink = PostgresSink(dsn, devices=config.devices, site_id=config.site_id, batch_size=500)
    sink.open()  # crea esquemas y tablas (incl. raw.sim_state) y siembra dim_device
    engine = sink._engine

    # Serializa los ticks: un advisory lock de sesión (no bloqueante). Si otro tick ya lo tiene,
    # este sale sin tocar el checkpoint. AUTOCOMMIT para que el lock viva mientras dure la conexión.
    lock_conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    got_lock = lock_conn.execute(
        text("SELECT pg_try_advisory_lock(:k)"), {"k": _TICK_LOCK_KEY}
    ).scalar()
    if not got_lock:
        lock_conn.close()
        sink.close()
        return {"skipped": "otro tick en curso (advisory lock no adquirido)",
                "events_inserted": 0, "accel": accel}

    try:
        return _run_tick_locked(config, sink, engine, accel, now_real, start_dt)
    finally:
        lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _TICK_LOCK_KEY})
        lock_conn.close()
        sink.close()


def _run_tick_locked(config, sink, engine, accel, now_real, start_dt) -> dict:
    """Cuerpo del tick, ya con el advisory lock adquirido (un solo tick a la vez)."""
    members = build_population_stable(config)

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT real_anchor, sim_checkpoint FROM raw.sim_state WHERE id = 1")
        ).first()

    if row is None:
        # primer tick: ancla el reloj y carga el catálogo de socios (contacto para campañas)
        sink.write_members(members)
        real_anchor, sim_checkpoint = now_real, start_dt
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO raw.sim_state (id, real_anchor, sim_checkpoint) "
                    "VALUES (1, :a, :s)"
                ),
                {"a": real_anchor, "s": sim_checkpoint},
            )
    else:
        real_anchor, sim_checkpoint = row

    # tiempo simulado "ahora" = inicio + (tiempo real transcurrido) * aceleración
    sim_now = start_dt + (now_real - real_anchor) * accel
    # cota de avance por tick: el siguiente tick sigue rellenando si quedó atrás
    sim_now = min(sim_now, sim_checkpoint + timedelta(days=MAX_CATCHUP_DAYS))

    events_generated = 0
    if sim_now > sim_checkpoint:
        calendar = make_calendar(config)
        events = events_between(config, members, calendar, sim_checkpoint, sim_now)
        for ev in events:
            sink.emit(ev)
        sink._flush()
        events_generated = len(events)
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE raw.sim_state SET sim_checkpoint = :s WHERE id = 1"),
                {"s": sim_now},
            )

    with engine.begin() as conn:
        total_rows = conn.execute(
            text("SELECT count(*) FROM raw.access_event_raw")
        ).scalar_one()

    return {
        "sim_from": sim_checkpoint.isoformat(),
        "sim_to": sim_now.isoformat(),
        "events_generated": events_generated,   # eventos generados en la ventana simulada
        "rows_inserted": sink.inserted_count,    # filas NUEVAS reales en la BD (tras dedup)
        "total_rows": total_rows,                # total en raw.access_event_raw tras el tick
        "accel": accel,
    }
