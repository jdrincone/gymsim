# 02 — Arquitectura

Objetivo: una solución **simple, legible y enfocada** en llenar la BD con eventos realistas de la
registradora del gimnasio. Producido con el agente `software-architect`.

## Flujo
```
configs/gym.yaml
      │
      ▼
  Población (arquetipos) ──► Visitas reales por día ──► Capa de ruido ──► Eventos
      │                         (behavior.py)            (noise.py)       (AccessEvent)
      │                                                                       │
      └── determinista dado (config, seed); cada día con su propia semilla    │
                                                                              ▼
                                                                     Sink (a dónde van)
                                                          memory · jsonl · postgres(Supabase)
```

Dos formas de llenar la BD:
- **`gymsim simulate`** — genera un horizonte fijo de una vez (backfill / inspección a JSONL).
- **`gymsim tick`** — incremental: inserta los eventos desde el último checkpoint, anclando el
  tiempo simulado al reloj real. Es lo que corre en el cron de GitHub Actions (gratis).

## Piezas
- **Dominio** (`domain/`): `calendar` (horarios y festivos de Colombia), `archetypes`, `member`,
  `events`. Sin dependencias de infraestructura.
- **Simulación** (`simulation/`): `population` (socios + grupos), `behavior` (visitas reales por
  día), `noise` (errores del hardware), `windowed` (un día / una ventana), `engine` (orquesta).
- **Sinks** (`sinks/`): `memory` (tests), `jsonl` (inspección sin BD), `postgres` (destino real).
- **Persistencia** (`db/`): modelos SQLAlchemy 2.0 en capas `raw/staging/curated` (las tablas se
  crean solas con `metadata.create_all`); el SQL de analítica vive en `sql/transforms/`.
- **`live.py`**: el comando `tick` y el checkpoint (`raw.sim_state`).

## Decisiones clave
- **Generación determinista por día** (semilla por día) + **`event_uuid` por contenido**:
  regenerar una ventana temporal produce exactamente los mismos eventos → `tick` es **idempotente**
  (`ON CONFLICT DO NOTHING`). Esto es lo que hace seguro el llenado incremental.
- **Verdad → ruido → persistencia**: el ground-truth se exporta aparte para validar la analítica.
- **Tiempo anclado al reloj real** (no un reloj virtual aparte): el `tick` calcula la ventana
  `(checkpoint, ahora]` con un factor `SIM_ACCEL`. Si el cron se retrasa, el siguiente tick rellena.
- **Generalizable**: el gimnasio es la primera config (`configs/gym.yaml`). Otro negocio = otra
  config (perfiles, arquetipos, dispositivos), mismo motor.

## Infraestructura (mínima, gratis)
- **BD:** Supabase (vía `DATABASE_URL`).
- **Ejecución autónoma:** GitHub Actions (`schedule: cron`) corriendo `gymsim tick`. Sin servidor.
- **Tooling:** `uv` para entorno y dependencias.

## Roadmap
1. ✅ Simulador realista + llenado autónomo e idempotente de la BD.
2. ✅ Transforms automáticos (`gymsim transform`) tras cada tick: la capa `curated` queda al día
   sola. Ticks serializados con un advisory lock de Postgres; alerta por issue si el workflow falla.
3. ⏳ Analítica batch sobre `curated` (RFM, segmentación, churn, cohortes, grafo social) y
   validación contra el ground-truth.
4. ⏳ Transforms **incrementales** (hoy son full-refresh `TRUNCATE + INSERT`): materializar por
   `date_key`/watermark cuando el volumen lo exija. Correcto y suficiente al volumen actual.
