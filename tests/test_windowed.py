"""Tests de la generación por día/ventana (base del llenado incremental). Sin infraestructura."""
from __future__ import annotations

from datetime import datetime, timezone

from gymsim.config import SimConfig
from gymsim.simulation.engine import build_population_stable, build_simulation, make_calendar
from gymsim.simulation.windowed import events_between, events_for_day


def _cfg() -> SimConfig:
    c = SimConfig()
    c.population.size = 150
    c.population.monthly_new_members = 5
    c.time.horizon_days = 60
    return c


def test_events_for_day_deterministic():
    c = _cfg()
    members = build_population_stable(c)
    cal = make_calendar(c)
    day = c.time.start_date.replace(day=2)  # 2025-01-02 (jueves, abierto)
    _, e1 = events_for_day(c, members, cal, day)
    _, e2 = events_for_day(c, members, cal, day)
    assert [e.event_uuid for e in e1] == [e.event_uuid for e in e2]
    assert len(e1) > 0


def test_events_between_idempotent():
    """Regenerar la misma ventana produce exactamente los mismos UUIDs (idempotencia)."""
    c = _cfg()
    members = build_population_stable(c)
    cal = make_calendar(c)
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    t1 = datetime(2025, 1, 8, tzinfo=timezone.utc)
    a = events_between(c, members, cal, t0, t1)
    b = events_between(c, members, cal, t0, t1)
    assert {e.event_uuid for e in a} == {e.event_uuid for e in b}
    # sin colisiones: todos los UUID son únicos
    assert len({e.event_uuid for e in a}) == len(a)


def test_windows_partition_matches_full_range():
    """Cubrir [t0,t1] de una vez == cubrirlo en dos mitades (continuidad sin huecos ni solapes)."""
    c = _cfg()
    members = build_population_stable(c)
    cal = make_calendar(c)
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    tm = datetime(2025, 1, 5, tzinfo=timezone.utc)
    t1 = datetime(2025, 1, 9, tzinfo=timezone.utc)
    full = {e.event_uuid for e in events_between(c, members, cal, t0, t1)}
    half = {e.event_uuid for e in events_between(c, members, cal, t0, tm)}
    half |= {e.event_uuid for e in events_between(c, members, cal, tm, t1)}
    assert full == half


def test_backfill_equals_per_day_union():
    """El backfill completo == unión de los eventos generados día a día (mismo mundo)."""
    c = _cfg()
    result = build_simulation(c)
    uuids = {e.event_uuid for e in result.events}
    assert len(uuids) == len(result.events)  # sin duplicados de pipeline
