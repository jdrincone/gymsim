"""Capa de ruido: convierte visitas limpias en eventos de hardware con errores reales.

Se aplica DESPUÉS de generar la verdad (visitas), preservando el ground-truth para validar
la analítica. Modos de ruido: re-entradas, marcajes faltantes, doble lectura, drift de
reloj, accesos denegados y entrega tardía. Ver docs/03-modelo-comportamental.md.
"""
from __future__ import annotations

import hashlib
from datetime import timedelta

import numpy as np

from ..config import SimConfig
from ..domain.events import DENIED, GRANTED, IN, OUT, AccessEvent
from .behavior import Visit


def _pick(devices, rng) -> str:
    return devices[int(rng.integers(0, len(devices)))].device_id


def _seed_from(s: str) -> int:
    return int(hashlib.sha1(s.encode()).hexdigest()[:8], 16)


def device_drift(config: SimConfig) -> dict[str, float]:
    """Drift de reloj por dispositivo, **determinista** y estable entre corridas/días.

    No consume el RNG del día (depende solo de config.seed y del device_id), de modo que
    regenerar una ventana produce el mismo device_ts → idempotencia total con `gymsim tick`.
    """
    return {
        d.device_id: float(
            np.random.default_rng([config.seed, _seed_from(d.device_id)]).normal(
                0, config.noise.clock_drift_sec
            )
        )
        for d in config.devices
    }


def visits_to_events(
    visits: list[Visit],
    config: SimConfig,
    rng: np.random.Generator,
) -> list[AccessEvent]:
    """Expande cada visita a eventos IN/OUT e inyecta ruido de medición."""
    noise = config.noise
    in_devs = config.in_devices()
    out_devs = config.out_devices() or in_devs
    events: list[AccessEvent] = []

    # drift de reloj por dispositivo: determinista (no consume el RNG del día)
    drift = device_drift(config)

    def add(dev_id, cred, direction, true_ts, member_id, visit_id, result=GRANTED,
            reason="OK", kind=None):
        device_ts = true_ts + timedelta(seconds=drift.get(dev_id, 0.0))
        ingested = device_ts
        if rng.random() < noise.late_delivery_prob:
            ingested = device_ts + timedelta(seconds=float(rng.exponential(120)))
        events.append(
            AccessEvent(
                device_id=dev_id,
                credential_id=cred,
                direction=direction,
                device_ts=device_ts,
                result=result,
                reason=reason,
                ingested_at=ingested,
                member_external_id=member_id,
                true_ts=true_ts,
                visit_id=visit_id,
                noise_kind=kind,
            )
        )

    for v in visits:
        cred = v.member.credential_id
        mid = v.member.external_id
        dev_in = _pick(in_devs, rng)
        dev_out = _pick(out_devs, rng)

        # acceso denegado previo (tarjeta vencida/no reconocida) y reintento exitoso
        if rng.random() < noise.denied_rate:
            reason = str(rng.choice(["EXPIRED", "UNKNOWN_CARD"]))
            add(dev_in, cred, IN, v.ts_in - timedelta(seconds=8), mid, v.visit_id,
                result=DENIED, reason=reason, kind="denied")

        has_in = rng.random() >= noise.missing_mark_prob   # a veces falta el IN (tailgating)
        has_out = rng.random() >= noise.missing_mark_prob  # a veces falta el OUT

        if has_in:
            _maybe_duplicate(add, rng, noise, dev_in, cred, IN, v.ts_in, mid, v.visit_id)

        # re-entradas legítimas (salió a una llamada / a comprar agua y volvió)
        if rng.random() < noise.reentry_prob and v.duration_min > 20:
            n_re = 1 + int(rng.poisson(0.3))
            for _ in range(n_re):
                t_out = v.ts_in + timedelta(
                    minutes=float(rng.uniform(5, max(6, v.duration_min - 5)))
                )
                gap = float(rng.exponential(noise.reentry_gap_min_mean))
                t_back = t_out + timedelta(minutes=min(gap, 14))
                if t_back < v.ts_out:
                    add(dev_out, cred, OUT, t_out, mid, v.visit_id, kind="reentry")
                    add(dev_in, cred, IN, t_back, mid, v.visit_id, kind="reentry")

        if has_out:
            _maybe_duplicate(add, rng, noise, dev_out, cred, OUT, v.ts_out, mid, v.visit_id)

    _assign_raw_seq(events)
    return events


def _maybe_duplicate(add, rng, noise, dev, cred, direction, ts, mid, vid) -> None:
    """Emite el evento y, con prob duplicate_rate, una doble lectura (rebote) casi idéntica."""
    add(dev, cred, direction, ts, mid, vid)
    if rng.random() < noise.duplicate_rate:
        offset = timedelta(seconds=float(rng.exponential(1.2)))
        add(dev, cred, direction, ts + offset, mid, vid, kind="duplicate")


def _assign_raw_seq(events: list[AccessEvent]) -> None:
    """Asigna un contador monotónico por dispositivo (clave de idempotencia con device_id)."""
    counters: dict[str, int] = {}
    for ev in sorted(events, key=lambda e: (e.device_id, e.device_ts)):
        counters[ev.device_id] = counters.get(ev.device_id, 0) + 1
        ev.raw_seq = counters[ev.device_id]
