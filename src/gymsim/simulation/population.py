"""Construcción de la población de socios con heterogeneidad, grupos sociales y credenciales."""
from __future__ import annotations

import numpy as np

from ..config import SimConfig
from ..domain.archetypes import FREQ_RANGE, Archetype
from ..domain.member import Member, _hour_weights, _weekday_weights


def _assign_archetypes(config: SimConfig, n: int, rng: np.random.Generator) -> list[Archetype]:
    mix = config.population.archetype_mix
    kinds = [Archetype(k) for k in mix]
    probs = np.array([mix[k.value] for k in kinds], dtype=float)
    probs /= probs.sum()
    idx = rng.choice(len(kinds), size=n, p=probs)
    return [kinds[i] for i in idx]


def build_population(config: SimConfig, rng: np.random.Generator) -> list[Member]:
    """Genera la población: cohorte inicial + altas mensuales, con grupos y credenciales."""
    total_weeks = max(1, config.time.horizon_days // 7)
    weekday_hourly = config.weekday_hourly
    weekday_profile = config.weekday

    # cohorte inicial (join_week=0) + altas a lo largo del horizonte
    n_initial = config.population.size
    months = max(1, config.time.horizon_days // 30)
    n_new = config.population.monthly_new_members * months
    join_weeks = [0] * n_initial + [
        int(rng.integers(1, total_weeks + 1)) for _ in range(n_new)
    ]
    n_total = len(join_weeks)
    archetypes = _assign_archetypes(config, n_total, rng)

    members: list[Member] = []
    for i in range(n_total):
        arch = archetypes[i]
        low, high = FREQ_RANGE[arch]
        base_freq = rng.uniform(low, high)
        ext_id = f"M{i:06d}"
        members.append(
            Member(
                external_id=ext_id,
                credential_id=ext_id,
                archetype=arch,
                base_freq=base_freq,
                hour_weights=_hour_weights(rng, weekday_hourly),
                weekday_weights=_weekday_weights(rng, weekday_profile),
                duration_median_min=float(
                    rng.normal(config.session.duration_median_min, 8)
                ),
                join_week=join_weeks[i],
                email=f"{ext_id.lower()}@example.com",
                phone=f"+57 3{rng.integers(0, 10**9):09d}",
            )
        )

    _assign_groups(members, config, rng)
    _assign_shared_credentials(members, config, rng)
    return members


def _assign_groups(members: list[Member], config: SimConfig, rng: np.random.Generator) -> None:
    """Forma grupos (parejas/amigos) que comparten preferencias → co-asistencia real."""
    n_in_groups = int(len(members) * config.social.group_fraction)
    if n_in_groups < 2:
        return
    candidates = list(rng.permutation(len(members))[:n_in_groups])
    gid = 0
    while len(candidates) >= 2:
        size = int(min(rng.integers(2, config.social.max_group_size + 1), len(candidates)))
        idxs = [candidates.pop() for _ in range(size)]
        anchor = members[idxs[0]]
        for j in idxs:
            m = members[j]
            m.group_id = gid
            # comparten franja/días con el ancla según co_attendance_prob
            if rng.random() < config.social.co_attendance_prob:
                m.hour_weights = anchor.hour_weights.copy()
                m.weekday_weights = anchor.weekday_weights.copy()
        gid += 1


def _assign_shared_credentials(
    members: list[Member], config: SimConfig, rng: np.random.Generator
) -> None:
    """Una fracción de socios comparte credencial (ruido/fraude: misma tarjeta, dos patrones)."""
    n_pairs = int(len(members) * config.noise.shared_credential_fraction)
    for _ in range(n_pairs):
        a, b = rng.integers(0, len(members), size=2)
        if a != b:
            members[int(b)].credential_id = members[int(a)].credential_id
