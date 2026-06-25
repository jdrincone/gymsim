"""Orquestador de la simulación: población → visitas → ruido → emisión al sink."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import numpy as np

from ..config import SimConfig
from ..domain.calendar import GymCalendar
from ..domain.events import AccessEvent
from ..domain.member import Member
from ..ports import EventSink
from .behavior import Visit
from .population import build_population
from .windowed import events_for_day


@dataclass
class SimResult:
    members: list[Member]
    visits: list[Visit]
    events: list[AccessEvent]

    def summary(self) -> dict:
        kinds: dict[str, int] = {}
        for e in self.events:
            k = e.noise_kind or "clean"
            kinds[k] = kinds.get(k, 0) + 1
        return {
            "members": len(self.members),
            "visits": len(self.visits),
            "events": len(self.events),
            "events_by_kind": kinds,
        }


def _years_spanned(config: SimConfig) -> list[int]:
    start = config.time.start_date
    end = start + timedelta(days=config.time.horizon_days)
    return list(range(start.year, end.year + 1))


def make_calendar(config: SimConfig) -> GymCalendar:
    return GymCalendar(
        years=_years_spanned(config),
        country=config.time.country,
        weekday_hours=tuple(config.time.weekday_hours),
        weekend_hours=tuple(config.time.weekend_hours),
    )


def build_population_stable(config: SimConfig) -> list[Member]:
    """Población determinista y estable entre corridas (depende solo de config.seed)."""
    return build_population(config, np.random.default_rng(config.seed))


def build_simulation(config: SimConfig) -> SimResult:
    """Genera todo el horizonte en memoria, día a día (mismo camino que el modo ventana)."""
    calendar = make_calendar(config)
    members = build_population_stable(config)
    visits: list[Visit] = []
    events: list[AccessEvent] = []
    for day_index in range(config.time.horizon_days):
        d = config.time.start_date + timedelta(days=day_index)
        vs, evs = events_for_day(config, members, calendar, d)
        visits.extend(vs)
        events.extend(evs)
    return SimResult(members=members, visits=visits, events=events)


def run(config: SimConfig, sink: EventSink) -> SimResult:
    """Genera el horizonte completo y lo vuelca al sink (en orden temporal)."""
    result = build_simulation(config)
    sink.open()
    try:
        sink.write_members(result.members)
        for ev in sorted(result.events, key=lambda e: e.device_ts):
            sink.emit(ev)
    finally:
        sink.close()
    return result
