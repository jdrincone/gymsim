-- ════════════════════════════════════════════════════════════════════════════
-- staging → curated.fact_access_event: hechos de paso VÁLIDOS.
-- Excluye duplicados (rebote) y denegados; conserva el grano de evento.
-- ════════════════════════════════════════════════════════════════════════════
TRUNCATE curated.fact_access_event;

INSERT INTO curated.fact_access_event
    (event_uuid, member_id, device_id, event_ts, direction, date_key, time_key)
SELECT
    event_uuid,
    member_id,
    device_id,
    event_ts,
    direction,
    (EXTRACT(YEAR FROM event_ts) * 10000
        + EXTRACT(MONTH FROM event_ts) * 100
        + EXTRACT(DAY FROM event_ts))::INT AS date_key,
    (EXTRACT(HOUR FROM event_ts) * 100 + EXTRACT(MINUTE FROM event_ts))::INT AS time_key
FROM staging.access_event
WHERE NOT is_duplicate
  AND NOT is_denied
  AND member_id IS NOT NULL;
