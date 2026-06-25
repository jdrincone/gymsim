---
name: run-gym-simulation
description: Cómo configurar y ejecutar el simulador de la registradora del gimnasio. Dos modos — `gymsim tick` (llenado autónomo e incremental de la BD, pensado para correr en un cron gratuito de GitHub Actions) y `gymsim simulate` (backfill de un horizonte fijo a Postgres, o a un JSONL para inspección sin BD). Úsala cuando el usuario quiera generar datos, llenar la BD, ajustar la población/arquetipos, el ritmo (SIM_ACCEL) o el nivel de ruido.
---

# Ejecutar la simulación del gimnasio

El simulador vive en `src/gymsim/`. Genera eventos de paso (entrada/salida) realistas con ruido y
los guarda en Postgres/Supabase. Se gestiona con `uv`.

## Preparar
```bash
uv sync
cp .env.example .env          # DATABASE_URL de Supabase (Session pooler, puerto 5432)
```

## Modo 1 — Llenado autónomo: `gymsim tick`
Inserta los eventos ocurridos desde el último checkpoint (tabla `raw.sim_state`), anclando el
tiempo simulado al reloj real. Idempotente y robusto a retrasos. Es lo que dispara el cron.
```bash
uv run gymsim tick --accel 24     # SIM_ACCEL: 1=ritmo real; 24=1 día por hora real
```
En producción lo ejecuta solo el workflow `.github/workflows/fill-db.yml` (gratis). Para activarlo:
subir el repo a GitHub y crear el secret `DATABASE_URL`.

## Modo 2 — Backfill / inspección: `gymsim simulate`
```bash
# A Postgres (histórico de una vez, crea tablas e inserta idempotente)
uv run gymsim simulate --sink postgres --days 180

# A un JSONL para inspeccionar sin BD (+ ground-truth de visitas reales)
uv run gymsim simulate --sink jsonl --out data/events.jsonl --days 60 --ground-truth data/truth.jsonl
```

## Parámetros clave (`configs/gym.yaml`)
- `population.size`, `population.archetype_mix` — tamaño y mezcla de arquetipos.
- `time.weekday_hours`, `time.weekend_hours`, `time.country` — horarios y festivos.
- `arrivals.weekday_hourly`, `arrivals.weekend_hourly`, `arrivals.weekday_profile`,
  `arrivals.monthly_profile` — perfiles de llegada (hora, día de semana, estación).
- `noise.*` — tasas de ruido (duplicados, re-entradas, drift, marcajes faltantes, denegados…).
- `devices` — registradoras (id, puerta, dirección, antipassback).

## Reglas
- La **verdad limpia** se genera primero; el **ruido** se aplica encima (capa separada). El
  ground-truth se exporta para validar la analítica.
- Generación **determinista por día** + `event_uuid` por contenido → `tick` es idempotente.
- Reproducible dado `(config, seed)`. Para otro negocio: copia `configs/gym.yaml` y cambia perfiles,
  arquetipos y dispositivos; no toques el motor.
