"""Arquetipos de socio y sus trayectorias de frecuencia a lo largo del tiempo.

Ver docs/03-modelo-comportamental.md. La trayectoria devuelve la frecuencia objetivo
(visitas/semana) de un socio en una semana dada, lo que produce churn, ramp-up, etc.
"""
from __future__ import annotations

from enum import Enum

import numpy as np


class Archetype(str, Enum):
    CONSTANTE = "constante"      # estable, 3-5 visitas/sem
    CASUAL = "casual"           # estable bajo, 1-2/sem
    ESPORADICO = "esporadico"   # intermitente, ráfagas
    RAMP_UP = "ramp_up"         # creciente (motivación / pre-evento)
    DECADENTE = "decadente"     # decreciente hasta abandonar (churn)
    FANTASMA = "fantasma"       # paga y casi no asiste
    NUEVO = "nuevo"             # onboarding con alta varianza


# Frecuencia base objetivo (visitas/semana): rango (low, high) de muestreo inicial.
FREQ_RANGE: dict[Archetype, tuple[float, float]] = {
    Archetype.CONSTANTE: (3.0, 5.0),
    Archetype.CASUAL: (1.0, 2.0),
    Archetype.ESPORADICO: (0.3, 1.0),
    Archetype.RAMP_UP: (1.0, 2.0),
    Archetype.DECADENTE: (3.0, 4.5),
    Archetype.FANTASMA: (0.0, 0.25),
    Archetype.NUEVO: (2.0, 4.0),
}


def weekly_frequency(
    archetype: Archetype,
    base_freq: float,
    week: int,
    rng: np.random.Generator,
) -> float:
    """Frecuencia objetivo (visitas/semana) del socio en su semana ``week`` desde que se inscribió.

    Las trayectorias usan **escalas de tiempo absolutas en semanas** (no relativas al horizonte),
    para que el ramp-up y el churn se vean en cualquier ventana de observación. El churn se expresa
    como una caída sostenida a ~0 (no una fecha fija).
    """
    if archetype == Archetype.CONSTANTE:
        freq = base_freq
    elif archetype == Archetype.CASUAL:
        freq = base_freq
    elif archetype == Archetype.ESPORADICO:
        # ráfagas: alterna semanas activas/inactivas
        freq = base_freq * (1.6 if rng.random() < 0.4 else 0.2)
    elif archetype == Archetype.RAMP_UP:
        # crece de base_freq hasta ~5 visitas/sem en ~10 semanas
        freq = base_freq + (5.0 - base_freq) * min(1.0, week / 10.0)
    elif archetype == Archetype.DECADENTE:
        # decae y se apaga (churn) en ~10 semanas
        freq = base_freq * max(0.0, 1.0 - week / 10.0)
    elif archetype == Archetype.FANTASMA:
        freq = base_freq
    elif archetype == Archetype.NUEVO:
        # primeras semanas altas y con mucha varianza, luego se estabiliza (~4 semanas)
        early = np.exp(-week / 4.0)
        freq = base_freq * (0.6 + 0.8 * early) * rng.uniform(0.5, 1.5)
    else:  # pragma: no cover
        freq = base_freq

    # ruido multiplicativo leve por semana
    freq *= rng.uniform(0.85, 1.15)
    return max(0.0, freq)
