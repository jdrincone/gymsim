"""Generación por día y por ventana temporal (base del llenado incremental `gymsim tick`).

Como cada día es determinista (semilla propia) y los UUID son por contenido, regenerar
una ventana produce exactamente los mismos eventos → idempotencia total. Ver memoria
self-living-free-fill y docs/02-arquitectura.md.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from ..config import SimConfig
from ..domain.calendar import GymCalendar
from ..domain.events import AccessEvent
from ..domain.member import Member
from .behavior import Visit, day_rng, visits_for_day
from .noise import visits_to_events


def events_for_day(
    config: SimConfig,
    members: list[Member],
    calendar: GymCalendar,
    day: date,
) -> tuple[list[Visit], list[AccessEvent]]:
    """Visitas + eventos (con ruido) de un día concreto, de forma aislada y reproducible."""
    rng = day_rng(config.seed, day)
    visits = visits_for_day(config, members, calendar, day, rng)
    events = visits_to_events(visits, config, rng)
    return visits, events


def events_between(
    config: SimConfig,
    members: list[Member],
    calendar: GymCalendar,
    t0: datetime,
    t1: datetime,
) -> list[AccessEvent]:
    """Eventos cuyo ``device_ts`` cae en la ventana (t0, t1].

    Recorre los días que tocan el rango (con 1 día de margen por el drift de reloj) y filtra.
    """
    out: list[AccessEvent] = []
    d = t0.date() - timedelta(days=1)
    end = t1.date()
    while d <= end:
        _, evs = events_for_day(config, members, calendar, d)
        out.extend(e for e in evs if t0 < e.device_ts <= t1)
        d += timedelta(days=1)
    out.sort(key=lambda e: e.device_ts)
    return out
