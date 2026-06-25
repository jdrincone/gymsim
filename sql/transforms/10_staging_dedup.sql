-- ════════════════════════════════════════════════════════════════════════════
-- raw → staging: tipa, resuelve member_id desde credential_id y MARCA (no borra)
-- los eventos duplicados (rebote de lector), denegados y sospechosos.
-- Ver skill data-quality-and-noise. Idempotente (TRUNCATE + INSERT).
-- ════════════════════════════════════════════════════════════════════════════
TRUNCATE staging.access_event;

WITH base AS (
    SELECT
        r.event_uuid,
        m.member_id,
        r.device_id,
        r.direction,
        r.device_ts AS event_ts,          -- (en iteración 2: corregir drift con watermark)
        r.result,
        -- ventana de deduplicación: mismo socio+dispositivo+dirección en <= 5 s
        LAG(r.device_ts) OVER (
            PARTITION BY r.credential_id, r.device_id, r.direction
            ORDER BY r.device_ts
        ) AS prev_ts
    FROM raw.access_event_raw r
    LEFT JOIN curated.dim_member m ON m.external_id = r.credential_id
)
INSERT INTO staging.access_event
    (event_uuid, member_id, device_id, direction, event_ts,
     is_duplicate, is_denied, is_suspect)
SELECT
    event_uuid,
    member_id,
    device_id,
    direction,
    event_ts,
    (prev_ts IS NOT NULL AND event_ts - prev_ts <= INTERVAL '5 seconds') AS is_duplicate,
    (result = 'DENIED') AS is_denied,
    (member_id IS NULL) AS is_suspect      -- credencial no resuelta (compartida/desconocida)
FROM base;
