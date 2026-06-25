"""Socio (member) con sus parámetros individuales latentes (ground-truth)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .archetypes import Archetype


@dataclass
class Member:
    external_id: str
    credential_id: str           # normalmente == external_id; difiere si la credencial se comparte
    archetype: Archetype
    base_freq: float             # visitas/semana base
    hour_weights: np.ndarray     # preferencia horaria (24,)
    weekday_weights: np.ndarray  # preferencia por día de semana (7,) media 1
    duration_median_min: float
    join_week: int               # semana del horizonte en que se inscribe
    group_id: int | None = None
    # contacto (PII) para campañas proactivas
    email: str = ""
    phone: str = ""


def _hour_weights(rng: np.random.Generator, global_profile: np.ndarray) -> np.ndarray:
    """Preferencia horaria *propia* del socio: 1-2 modas (madrugador/vespertino...).

    Las modas se centran en horas realistas (muestreadas del perfil global), pero NO se
    multiplica por el perfil global: la combinación con el perfil del día concreto
    (L-V vs fin de semana) se hace al muestrear, en behavior.py. Así el perfil del día
    aporta el horario de apertura y este vector aporta la preferencia individual.
    """
    pref = np.full(24, 1e-6)  # piso pequeño para evitar ceros totales
    n_modes = int(rng.choice([1, 2], p=[0.6, 0.4]))
    p = global_profile / global_profile.sum()
    for _ in range(n_modes):
        center = int(rng.choice(24, p=p))
        spread = rng.uniform(1.0, 2.5)
        for h in range(24):
            d = min(abs(h - center), 24 - abs(h - center))
            pref[h] += np.exp(-0.5 * (d / spread) ** 2)
    return pref / pref.sum()


def _weekday_weights(rng: np.random.Generator, global_profile: np.ndarray) -> np.ndarray:
    """Preferencia por día de semana: perfil global perturbado por el socio (media 1)."""
    w = global_profile * rng.uniform(0.7, 1.3, size=7)
    return w / w.mean()
