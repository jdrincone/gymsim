"""Carga y validación de la configuración del simulador (pydantic). Una config = un negocio."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import yaml
from pydantic import BaseModel, Field

# Perfil horario LUN-VIE (24 pesos): bimodal, pico mañana (~6-9) y tarde (~17-21).
# Ceros fuera de 5-22 (horario L-V).
DEFAULT_WEEKDAY_HOURLY = [
    0, 0, 0, 0, 0, 3, 7, 9, 7, 4, 3, 3,        # 0-11h  (abre 5)
    4, 3, 3, 4, 6, 9, 10, 8, 5, 3, 0, 0,       # 12-23h (cierra 22)
]
# Perfil horario FIN DE SEMANA / FESTIVO (24 pesos): 7-15, pico de media mañana.
DEFAULT_WEEKEND_HOURLY = [
    0, 0, 0, 0, 0, 0, 0, 5, 8, 10, 9, 7,       # 0-11h (abre 7)
    5, 3, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0,        # 12-23h (cierra 15)
]
# Preferencia por día de semana (lun..dom): lun-jue alto, vie medio, sáb mañana, dom bajo.
DEFAULT_WEEKDAY_PROFILE = [1.15, 1.15, 1.15, 1.10, 0.95, 0.85, 0.65]
# Índice estacional por mes (ene..dic): pico de año nuevo, bajón vacacional.
DEFAULT_MONTHLY = [1.35, 1.10, 1.00, 1.00, 1.00, 0.90, 0.80, 0.80, 1.10, 1.05, 1.00, 0.85]


class TimeConfig(BaseModel):
    start_date: date = date(2025, 1, 1)
    horizon_days: int = 180
    weekday_hours: tuple[int, int] = (5, 22)   # L-V: 5:00–22:00
    weekend_hours: tuple[int, int] = (7, 15)   # sáb/dom/festivo: 7:00–15:00
    country: str = "CO"                        # festivos de Colombia
    daily_noise_sigma: float = 0.18            # azar diario (ε log-normal de λ)


class PopulationConfig(BaseModel):
    size: int = 1200
    monthly_new_members: int = 40
    archetype_mix: dict[str, float] = Field(
        default_factory=lambda: {
            "constante": 0.30,
            "casual": 0.25,
            "esporadico": 0.15,
            "ramp_up": 0.08,
            "decadente": 0.12,
            "fantasma": 0.05,
            "nuevo": 0.05,
        }
    )


class ArrivalsConfig(BaseModel):
    weekday_hourly: list[float] = Field(default_factory=lambda: list(DEFAULT_WEEKDAY_HOURLY))
    weekend_hourly: list[float] = Field(default_factory=lambda: list(DEFAULT_WEEKEND_HOURLY))
    weekday_profile: list[float] = Field(default_factory=lambda: list(DEFAULT_WEEKDAY_PROFILE))
    monthly_profile: list[float] = Field(default_factory=lambda: list(DEFAULT_MONTHLY))


class SocialConfig(BaseModel):
    group_fraction: float = 0.25     # fracción de socios en algún grupo
    co_attendance_prob: float = 0.6  # afinidad de horarios dentro del grupo
    max_group_size: int = 4


class SessionConfig(BaseModel):
    duration_median_min: float = 60.0
    duration_sigma: float = 0.4      # sigma log-normal


class NoiseConfig(BaseModel):
    duplicate_rate: float = 0.03        # rebote de lector
    reentry_prob: float = 0.12          # salir y volver (llamada/agua)
    reentry_gap_min_mean: float = 6.0   # media del gap de re-entrada (min)
    clock_drift_sec: float = 30.0       # desv. del drift de reloj por dispositivo
    missing_mark_prob: float = 0.04     # marcaje faltante (tailgating)
    denied_rate: float = 0.02           # accesos denegados (no son visita)
    shared_credential_fraction: float = 0.01  # credenciales compartidas
    late_delivery_prob: float = 0.05    # eventos tardíos / fuera de orden


class DeviceConfig(BaseModel):
    device_id: str
    door: str = "entrada_principal"
    direction_mode: str = "BIDI"   # BIDI / IN_ONLY / OUT_ONLY
    antipassback: bool = False


class SimConfig(BaseModel):
    site_id: str = "gym-01"
    seed: int = 42
    time: TimeConfig = Field(default_factory=TimeConfig)
    population: PopulationConfig = Field(default_factory=PopulationConfig)
    arrivals: ArrivalsConfig = Field(default_factory=ArrivalsConfig)
    social: SocialConfig = Field(default_factory=SocialConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    noise: NoiseConfig = Field(default_factory=NoiseConfig)
    devices: list[DeviceConfig] = Field(
        default_factory=lambda: [
            DeviceConfig(device_id="reg-entrada-1", door="entrada_principal", antipassback=True),
            DeviceConfig(device_id="reg-entrada-2", door="entrada_principal"),
            DeviceConfig(device_id="reg-salida-1", door="salida", direction_mode="OUT_ONLY"),
        ]
    )

    # ── helpers numéricos ──
    @property
    def weekday_hourly(self) -> np.ndarray:
        return np.asarray(self.arrivals.weekday_hourly, dtype=float)

    @property
    def weekend_hourly(self) -> np.ndarray:
        return np.asarray(self.arrivals.weekend_hourly, dtype=float)

    @property
    def weekday(self) -> np.ndarray:
        w = np.asarray(self.arrivals.weekday_profile, dtype=float)
        return w / w.mean()

    @property
    def monthly(self) -> np.ndarray:
        return np.asarray(self.arrivals.monthly_profile, dtype=float)

    def in_devices(self) -> list[DeviceConfig]:
        return [d for d in self.devices if d.direction_mode in ("BIDI", "IN_ONLY")]

    def out_devices(self) -> list[DeviceConfig]:
        return [d for d in self.devices if d.direction_mode in ("BIDI", "OUT_ONLY")]


def load_config(path: str | Path) -> SimConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return SimConfig(**data)
