"""Tests del dominio sin infraestructura: reproducibilidad, calendario, ruido y realismo."""
from __future__ import annotations

import datetime as dt


from gymsim.config import SimConfig
from gymsim.domain.calendar import GymCalendar
from gymsim.simulation.engine import build_simulation
from gymsim.sinks.memory import MemorySink
from gymsim.simulation.engine import run


def _small_config() -> SimConfig:
    c = SimConfig()
    c.population.size = 120
    c.population.monthly_new_members = 5
    c.time.horizon_days = 45
    return c


def test_reproducible_given_seed():
    c = _small_config()
    r1 = build_simulation(c)
    r2 = build_simulation(c)
    assert len(r1.events) == len(r2.events)
    assert r1.events[0].event_uuid == r2.events[0].event_uuid


def test_calendar_full_closures():
    cal = GymCalendar(years=[2025])
    assert cal.plan(dt.date(2025, 1, 1)).is_open is False   # Año Nuevo
    assert cal.plan(dt.date(2025, 12, 25)).is_open is False  # Navidad
    assert cal.plan(dt.date(2025, 4, 18)).is_open is False   # Viernes Santo


def test_operating_hours_by_daytype():
    cal = GymCalendar(years=[2025])
    # 2025-01-02 es jueves (L-V) → 5-22
    wd = cal.plan(dt.date(2025, 1, 2))
    assert (wd.open_hour, wd.close_hour) == (5, 22)
    # 2025-01-04 es sábado → 7-15
    we = cal.plan(dt.date(2025, 1, 4))
    assert (we.open_hour, we.close_hour) == (7, 15)


def test_no_events_on_closed_days():
    c = _small_config()
    sink = MemorySink()
    run(c, sink)
    closed = {dt.date(2025, 1, 1)}
    days_with_events = {
        (e.true_ts or e.device_ts).date() for e in sink.events
    }
    assert closed.isdisjoint(days_with_events)


def test_noise_layer_present():
    c = _small_config()
    r = build_simulation(c)
    kinds = {e.noise_kind for e in r.events}
    # debe haber eventos limpios y al menos algún tipo de ruido
    assert None in kinds  # limpios (noise_kind None)
    assert kinds & {"duplicate", "reentry", "denied"}


def test_events_within_open_hours_on_weekends():
    c = _small_config()
    r = build_simulation(c)
    # en fines de semana las visitas reales (true_ts) caen dentro de 7-15
    for e in r.events:
        t = e.true_ts or e.device_ts
        if t.weekday() >= 5 and e.noise_kind != "denied":
            assert 7 <= t.hour <= 15
