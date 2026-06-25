"""Generación de la VERDAD LIMPIA: las visitas reales de cada socio (sin ruido de medición).

Modelo jerárquico: cada socio genera sus propias llegadas (NHPP a nivel individual). La
intensidad agregada λ(t) del gimnasio emerge de la suma de todos los socios.

Generación **determinista por día**: cada día usa su propia semilla derivada de
(config.seed, día). Así un día cualquiera puede regenerarse de forma idéntica y aislada,
lo que habilita el llenado incremental por ventana (`gymsim tick`). Ver windowed.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import numpy as np

from ..config import SimConfig
from ..domain.archetypes import weekly_frequency
from ..domain.calendar import GymCalendar
from ..domain.member import Member


@dataclass
class Visit:
    """Una visita real (ground-truth) antes de aplicar ruido."""

    visit_id: int
    member: Member
    ts_in: datetime
    ts_out: datetime

    @property
    def duration_min(self) -> float:
        return (self.ts_out - self.ts_in).total_seconds() / 60.0


def day_rng(seed: int, day: date) -> np.random.Generator:
    """RNG independiente y reproducible para un día concreto."""
    return np.random.default_rng([seed, day.toordinal()])


def visits_for_day(
    config: SimConfig,
    members: list[Member],
    calendar: GymCalendar,
    day: date,
    rng: np.random.Generator,
) -> list[Visit]:
    """Genera las visitas reales de TODOS los socios para un día concreto (aislado)."""
    plan = calendar.plan(day)
    if not plan.is_open:
        return []  # gimnasio cerrado

    base_dt = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    weekday_prof = config.weekday
    monthly = config.monthly
    sigma = config.session.duration_sigma

    day_profile = config.weekend_hourly if plan.day_type != "WEEKDAY" else config.weekday_hourly
    mask = np.zeros(24)
    mask[list(plan.open_hours)] = 1.0
    day_profile = day_profile * mask

    wd = day.weekday()
    season = monthly[day.month - 1]
    day_index = (day - config.time.start_date).days
    week = day_index // 7
    eps = float(np.exp(rng.normal(0, config.time.daily_noise_sigma)))  # azar diario

    # visit_id determinista y único por día (no es un contador global)
    vid = day.toordinal() * 100_000
    visits: list[Visit] = []

    for m in members:
        if week < m.join_week:
            continue
        freq = weekly_frequency(m.archetype, m.base_freq, week - m.join_week, rng)
        if freq <= 0:
            continue
        daily = (freq / 7.0) * weekday_prof[wd] * m.weekday_weights[wd] * season * eps
        n = min(int(rng.poisson(min(daily, 3.0))), 3)  # tope de visitas/día
        if n == 0:
            continue

        eff = m.hour_weights * day_profile
        if eff.sum() <= 0:
            eff = day_profile.copy()  # socio fuera de horario → usa perfil del día
        if eff.sum() <= 0:
            continue
        eff = eff / eff.sum()

        close_dt = base_dt.replace(hour=min(plan.close_hour, 23), minute=59)
        for _ in range(n):
            hour = int(rng.choice(24, p=eff))
            minute = int(rng.integers(0, 60))
            second = int(rng.integers(0, 60))
            micro = int(rng.integers(0, 1_000_000))  # resolución real → evita colisiones de UUID
            ts_in = base_dt.replace(hour=hour, minute=minute, second=second, microsecond=micro)
            dur = float(np.exp(rng.normal(np.log(max(m.duration_median_min, 15)), sigma)))
            dur = float(np.clip(dur, 10, 180))
            ts_out = ts_in + timedelta(minutes=dur)
            if ts_out > close_dt:
                ts_out = close_dt
            if ts_out <= ts_in:
                ts_out = ts_in + timedelta(minutes=10)
            visits.append(Visit(vid, m, ts_in, ts_out))
            vid += 1

    return visits
