---
name: data-quality-and-noise
description: Referencia de los modos de ruido/error que el simulador inyecta a propósito (duplicados de lector, re-entradas, drift de reloj, marcajes faltantes, accesos denegados, credenciales compartidas, eventos tardíos/fuera de orden) y de la lógica de sesionización y deduplicación que la analítica debe usar para tolerarlos. Úsala al implementar o revisar limpieza de datos, reconstrucción de visitas, o al ajustar las tasas de ruido del simulador.
---

# Calidad de datos y ruido — gimnasio

El simulador genera primero la **verdad limpia** (visitas reales) y luego aplica una **capa de ruido** que imita los defectos del hardware de control de acceso. La analítica debe recuperar la verdad. El ground-truth se exporta para validar.

## Catálogo de ruido inyectado
| Fenómeno | Cómo se ve en los datos | Parámetro del simulador |
|---|---|---|
| Doble lectura / rebote | mismo `member_id` + dirección en < ~2 s, casi idénticos | `noise.duplicate_rate` |
| Re-entrada legítima (llamada, agua) | varios IN/OUT en una visita; gaps cortos (< ~15 min) | `noise.reentry_prob`, `noise.reentry_gap` |
| Drift de reloj | timestamps adelantados/atrasados por dispositivo | `noise.clock_drift_sec` |
| Marcaje faltante (tailgating) | IN sin OUT o OUT sin IN | `noise.missing_mark_prob` |
| Acceso denegado | evento `DENIED` (no es visita) | `noise.denied_rate` |
| Credencial compartida | un `member_id`, dos patrones incoherentes | `noise.shared_credential_pairs` |
| Tardío / fuera de orden | `event_ts` << hora de ingesta; lotes reenviados | `noise.late_delivery_prob` |

## Sesionización (reconstruir visitas) — reglas
1. **Deduplicar rebotes:** colapsar eventos con misma `(member_id, device, direction)` dentro de `dedup_window` (~5 s) en uno.
2. **Emparejar IN/OUT** por socio en orden temporal.
3. **Fusionar re-entradas:** si un OUT y el siguiente IN del mismo socio distan < `reentry_merge_gap` (~15 min), es la misma visita (no dos).
4. **Imputar marcajes faltantes:** IN sin OUT → cerrar con duración mediana del arquetipo o por cierre del local; OUT sin IN → abrir o descartar según política.
5. **Excluir DENIED** del conteo de visitas (pero conservarlos para análisis de fricción/fraude).
6. **Marcar, no borrar:** en `staging` se etiquetan los eventos sospechosos; el borrado real solo ocurre al construir `fact_session` en `curated`.

## Métricas de calidad que debes reportar
- % de eventos duplicados detectados vs. inyectados (recall de deduplicación).
- % de visitas con re-entradas fusionadas correctamente.
- % de sesiones con marcaje imputado.
- Tasa de eventos tardíos / fuera de orden.

## Validación
Compara siempre las visitas reconstruidas contra el ground-truth (`data/truth.jsonl`): nº de visitas reales por socio/día, duración real. Reporta matriz de confusión de la sesionización. Si el recall de deduplicación o el emparejamiento cae, ajusta ventanas o revisa el modo de ruido en `gymsim/simulation/noise.py`.
