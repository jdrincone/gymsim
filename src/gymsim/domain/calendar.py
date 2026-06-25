"""Calendario operativo del gimnasio: festivos de Colombia, cierres y horarios por tipo de día.

Reglas (ver memoria gym-operating-rules):
- Lunes a viernes: 5:00–22:00.
- Sábados, domingos y festivos: 7:00–15:00.
- Cerrado totalmente: 1 de enero, 25 de diciembre y Viernes Santo.
- Festivos de Colombia vía el paquete `holidays` (Ley Emiliani incluida).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

try:
    import holidays as _holidays
except ImportError:  # pragma: no cover - fallback sin la librería
    _holidays = None


WEEKDAY = "WEEKDAY"
WEEKEND = "WEEKEND"
HOLIDAY = "HOLIDAY"
CLOSED = "CLOSED"


@dataclass(frozen=True)
class DayPlan:
    day_type: str          # WEEKDAY / WEEKEND / HOLIDAY / CLOSED
    open_hour: int         # inclusive
    close_hour: int        # exclusive
    is_open: bool

    @property
    def open_hours(self) -> range:
        return range(self.open_hour, self.close_hour) if self.is_open else range(0)


class GymCalendar:
    """Resuelve, para cada fecha, el tipo de día, si abre y su ventana horaria."""

    def __init__(
        self,
        years: list[int],
        country: str = "CO",
        weekday_hours: tuple[int, int] = (5, 22),
        weekend_hours: tuple[int, int] = (7, 15),
    ) -> None:
        self.weekday_hours = weekday_hours
        self.weekend_hours = weekend_hours
        if _holidays is not None:
            self.holidays = _holidays.country_holidays(country, years=years)
        else:  # fallback mínimo si no está la librería
            self.holidays = {}

    def _is_full_closure(self, d: date) -> bool:
        """Cierres totales: 1-ene, 25-dic y Viernes Santo."""
        if (d.month, d.day) in ((1, 1), (12, 25)):
            return True
        name = self.holidays.get(d, "") if self.holidays else ""
        return "Good Friday" in name or "Viernes Santo" in name

    def plan(self, d: date) -> DayPlan:
        if self._is_full_closure(d):
            return DayPlan(CLOSED, 0, 0, is_open=False)

        is_holiday = bool(self.holidays.get(d)) if self.holidays else False
        is_weekend = d.weekday() >= 5  # 5=sáb, 6=dom

        if is_holiday:
            o, c = self.weekend_hours
            return DayPlan(HOLIDAY, o, c, is_open=True)
        if is_weekend:
            o, c = self.weekend_hours
            return DayPlan(WEEKEND, o, c, is_open=True)
        o, c = self.weekday_hours
        return DayPlan(WEEKDAY, o, c, is_open=True)
