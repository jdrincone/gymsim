-- ════════════════════════════════════════════════════════════════════════════
-- curated.fact_access_event → curated.fact_session: RECONSTRUYE VISITAS.
-- Tolera el ruido: fusiona re-entradas cortas (salió a una llamada / agua) usando
-- gaps-and-islands. Una nueva sesión empieza en un IN cuyo gap con el evento
-- anterior del socio supera REENTRY_MERGE_GAP (15 min). Cada sesión = primer IN
-- hasta el último OUT antes del siguiente IN-de-nueva-sesión.
--
-- Nota (iteración 2): la imputación de marcajes faltantes (IN sin OUT / OUT sin IN)
-- se afina aquí; esta versión cierra con el último evento del bloque y marca imputed.
-- ════════════════════════════════════════════════════════════════════════════
TRUNCATE curated.fact_session;

WITH ordered AS (
    SELECT
        member_id,
        device_id,
        direction,
        event_ts,
        LAG(event_ts) OVER (PARTITION BY member_id ORDER BY event_ts) AS prev_ts
    FROM curated.fact_access_event
),
flagged AS (
    SELECT
        *,
        CASE
            WHEN direction = 'IN'
                 AND (prev_ts IS NULL OR event_ts - prev_ts > INTERVAL '15 minutes')
            THEN 1 ELSE 0
        END AS is_new_session
    FROM ordered
),
sessioned AS (
    SELECT
        *,
        SUM(is_new_session) OVER (
            PARTITION BY member_id ORDER BY event_ts
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS session_seq
    FROM flagged
),
agg AS (
    SELECT
        member_id,
        session_seq,
        MIN(event_ts)                                          AS ts_in,
        MAX(event_ts) FILTER (WHERE direction = 'OUT')         AS ts_out_raw,
        MAX(event_ts)                                          AS ts_last,
        (MIN(device_id) FILTER (WHERE direction = 'IN'))       AS device_in,
        (MIN(device_id) FILTER (WHERE direction = 'OUT'))      AS device_out,
        -- re-entradas = nº de IN extra dentro de la misma sesión
        GREATEST(COUNT(*) FILTER (WHERE direction = 'IN') - 1, 0) AS n_reentries
    FROM sessioned
    GROUP BY member_id, session_seq
)
INSERT INTO curated.fact_session
    (member_id, device_in, device_out, ts_in, ts_out, duration_min,
     n_reentries, imputed_out, is_double_visit, date_key)
SELECT
    a.member_id,
    a.device_in,
    a.device_out,
    a.ts_in,
    COALESCE(a.ts_out_raw, a.ts_last)                                  AS ts_out,
    EXTRACT(EPOCH FROM (COALESCE(a.ts_out_raw, a.ts_last) - a.ts_in)) / 60.0 AS duration_min,
    a.n_reentries,
    (a.ts_out_raw IS NULL)                                            AS imputed_out,
    -- doble-visita: el socio tiene más de una sesión ese día
    (COUNT(*) OVER (PARTITION BY a.member_id,
        (EXTRACT(YEAR FROM a.ts_in) * 10000 + EXTRACT(MONTH FROM a.ts_in) * 100
            + EXTRACT(DAY FROM a.ts_in))) > 1)                        AS is_double_visit,
    (EXTRACT(YEAR FROM a.ts_in) * 10000 + EXTRACT(MONTH FROM a.ts_in) * 100
        + EXTRACT(DAY FROM a.ts_in))::INT                            AS date_key
FROM agg a;
