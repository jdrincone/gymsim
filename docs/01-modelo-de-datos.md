# 01 — Modelo de datos

Diseño en capas (medallion) sobre Postgres. Producido con el agente `data-engineer`. DDL ejecutable en `db/schema.sql`.

## Capas
- **raw (bronze)** — eventos crudos del dispositivo tal cual llegan, **sin deduplicar**, con metadatos de ingesta. Fuente de verdad inmutable; **incluye el ruido a propósito**.
- **staging (silver)** — eventos tipados/validados, con clave de idempotencia; se **marca** (no se borra) lo duplicado/denegado/sospechoso.
- **curated (gold)** — sesiones reconstruidas y agregados; dimensiones. Alimenta la analítica.

## Tablas

### raw.access_event_raw  (grano: un evento de hardware)
| Columna | Tipo | Notas |
|---|---|---|
| event_uuid | uuid PK | **determinístico por contenido** del evento (idempotencia) |
| device_id | text | registradora |
| raw_seq | bigint | contador del dispositivo (orden, informativo) |
| credential_id | text | id de la tarjeta/credencial (puede compartirse) |
| direction | text | IN / OUT |
| result | text | GRANTED / DENIED |
| reason | text | OK / UNKNOWN_CARD / ANTIPASSBACK / EXPIRED |
| device_ts | timestamptz | reloj del dispositivo (con posible drift) |
| ingested_at | timestamptz | hora de inserción |

Idempotencia: `INSERT ... ON CONFLICT (event_uuid) DO NOTHING`. Como el `event_uuid` se deriva del
**contenido** del evento, regenerar una ventana (al re-ejecutar un tick) no duplica; los duplicados
de **hardware** (rebote) sí se conservan porque su contenido difiere (otro `device_ts`/tipo).

### dim_member  (persona + contacto, PII separada)
`member_id (PK surrogate)`, `external_id`, `full_name`, `email`, `phone`, `join_date`, `status`, `archetype_hint (nullable)`.
> Contacto solo aquí; los hechos no llevan PII. `archetype_hint` se llena solo en datasets de validación (ground-truth), no en producción.

### dim_device  (registradora)
`device_id (PK)`, `door` (entrada_principal, torniquete_2, salida, clases), `direction_mode` (BIDI/IN_ONLY/OUT_ONLY), `antipassback (bool)`, `site_id`.

### dim_date / dim_time  — calendario y franja horaria (para slicing temporal).

### staging.access_event  (grano: evento tipado y deduplicado a nivel pipeline)
Columnas de raw + `member_id` (resuelto desde credential_id) + flags: `is_duplicate`, `is_denied`, `is_suspect`, `event_ts` (corregido por watermark/drift cuando aplique), `dedup_group_id`.

### fact_access_event  (estrella; grano: evento de paso válido)
`event_uuid (PK)`, `member_id (FK)`, `device_id (FK)`, `event_ts`, `direction`, `date_key`, `time_key`. Particionada por día (tiempo simulado). Índices: `(member_id, event_ts)`, `(device_id, event_ts)`.

### fact_session  (grano: una visita reconstruida)
`session_id (PK)`, `member_id (FK)`, `device_in`, `device_out`, `ts_in`, `ts_out`, `duration_min`, `n_reentries`, `imputed_out (bool)`, `is_double_visit (bool)`, `date_key`. Producto de la sesionización (ver skill `data-quality-and-noise`).

## Cómo se llena (hoy)
- **`gymsim tick`** inserta directamente en `raw.access_event_raw` los eventos de la ventana
  `(checkpoint, ahora]`, de forma **idempotente** (`event_uuid` por contenido + `ON CONFLICT DO
  NOTHING`). El checkpoint vive en `raw.sim_state`. Lo dispara el cron de GitHub Actions.
- **Contrato del evento** (campos del mensaje): obligatorios `event_uuid, device_id, raw_seq,
  credential_id, direction, result, device_ts`; opcionales `reason, ingested_at`.
- **Llegada tardía/fuera de orden:** los eventos se ubican por `event_ts` (ocurrencia simulada),
  no por hora de inserción.

## Diagrama lógico (estrella)
```
            dim_date     dim_time
                \           /
   dim_member --- fact_access_event --- dim_device
                       |
                  fact_session (derivado)
```

## PII / privacidad
- `member_id` es surrogate; el contacto vive aislado en `dim_member`.
- Para analítica se puede trabajar con vistas anonimizadas (sin email/phone). Minimización por diseño.
