# 03 — Modelo comportamental y distribuciones

Especifica el **modelo generativo** del simulador: qué distribución gobierna cada fenómeno y con qué parámetros. Separa la **señal** (comportamiento real) del **ruido** (artefactos de medición). Producido con el agente `behavioral-statistician`.

## 1. Llegadas en el tiempo — Proceso de Poisson No Homogéneo (NHPP)
La intensidad de llegadas instantánea:

```
λ(t) = λ_base · f_hora(hora) · f_diasemana(dia) · f_estacional(fecha) · ε
```

- **f_hora** — perfil bimodal: pico mañana (~6–9h), valle a media mañana/tarde, pico tarde (~17–21h), caída nocturna. (vector de 24 pesos, normalizado).
- **f_diasemana** — lun–jue alto, viernes medio, sábado mañana fuerte, domingo bajo.
- **f_estacional** — enero alto ("propósitos de año nuevo"), descenso feb–mar, bajón vacacional (verano/festivos), repunte septiembre.
- **ε** — ruido multiplicativo leve (p.ej. log-normal centrado en 1) para que no haya dos días idénticos.
- Simulación: muestreo por bin horario (Poisson por hora) o thinning de Lewis–Shedler.

> Importante: λ(t) modela la **intensidad agregada**, pero **quién** llega sale del modelo individual (sección 2); ambos se concilian (cada socio "compite" por generar las llegadas del bin según su propia intensidad).

## 2. Heterogeneidad individual — modelo jerárquico
Cada socio `i` tiene parámetros propios muestreados de poblaciones:

| Parámetro | Distribución | Notas |
|---|---|---|
| Frecuencia objetivo (visitas/semana) | mezcla / Gamma o log-normal | produce segmentos naturales (ver arquetipos) |
| Franja horaria preferida | von Mises sobre hora (1–2 modas) | "de mañana" vs "de tarde" |
| Días preferidos | distribución categórica sobre L–D | patrón semanal propio |
| Duración de sesión | log-normal truncada | mediana ~45–75 min |
| Probabilidad de re-entrada por visita | Bernoulli + Poisson truncado | salir a llamada/agua |

## 3. Arquetipos (trayectoria de vida del socio)
Cada socio sigue una trayectoria de frecuencia `λ_i(semana)`:

| Arquetipo | Trayectoria | Freq objetivo | % poblacional (sugerido) |
|---|---|---|---|
| **Constante/regular** | estable | 3–5 /sem | 30% |
| **Casual** | estable bajo | 1–2 /sem | 25% |
| **Esporádico** | intermitente, ráfagas | 0.3–1 /sem | 15% |
| **Ramp-up / pico** | creciente, sube de ~1 a ~5 /sem en **~10 semanas** | sube de 1→5 | 8% |
| **Decadente → churn** | decreciente hasta 0 (abandona) en **~10 semanas** | baja hasta abandonar | 12% |
| **Fantasma** | ~0 desde el inicio | ≈0 | 5% |
| **Nuevo (onboarding)** | alta varianza, se estabiliza en **~4 semanas** | indefinido | 5% (rotativo) |

- Las escalas de tiempo son **absolutas, en semanas desde la inscripción** (no relativas al horizonte), para que el ramp-up y el churn se vean en cualquier ventana de observación. Implementado en `domain/archetypes.py:weekly_frequency`.
- **Churn como caída sostenida** a ~0, no una fecha fija; distingue "pausa estacional" de "abandono".
- Altas/bajas a lo largo del horizonte (la base no es estática): llegan socios nuevos y otros se van.

## 4. Estructura social (relaciones entre socios)
- **Grafo de afinidad:** parejas/amigos/grupos de clase. Un socio "ancla" arrastra a su grupo a co-asistir con probabilidad `p_co` en las mismas franjas/días → **llegadas correlacionadas**.
- Permite responder las preguntas sociales (co-asistencia, comunidad, retención por vínculo) y validarlas contra el grafo latente.

## 5. Capa de ruido (medición) — se aplica DESPUÉS de la verdad
Ver detalle operativo en la skill `data-quality-and-noise`. Resumen de distribuciones:

| Fenómeno | Modelo |
|---|---|
| Doble lectura (rebote) | con prob. `duplicate_rate`, replicar evento con offset ~ exp(media≈1s) |
| Re-entrada legítima | nº re-entradas/visita ~ Poisson trunc.; gap ~ exp(media≈5 min) |
| Drift de reloj por dispositivo | offset ~ Normal(0, `clock_drift_sec`), lento en el tiempo |
| Marcaje faltante | con prob. `missing_mark_prob`, eliminar el IN o el OUT |
| Acceso denegado | con prob. `denied_rate`, evento DENIED (no visita) |
| Credencial compartida | fracción `shared_credential_pairs` de ids usados por 2 personas |
| Llegada tardía/fuera de orden | con prob. `late_delivery_prob`, retrasar ingesta y reordenar |

## 6. Reproducibilidad y validación
- Semilla global → ejecuciones deterministas dado `(config, seed)`.
- **Curvas que deben reproducirse** (tests estadísticos simulado vs. esperado):
  - Perfil horario **bimodal** y perfil semanal.
  - Distribución de frecuencias **multimodal** (segmentos).
  - **Curva de retención/supervivencia** por cohorte decreciente.
  - **Ley de co-asistencia** mayor dentro de grupos que entre extraños.
- El **ground-truth** (arquetipo, parámetros, visitas reales) se exporta a `data/truth.parquet` para medir si la analítica recupera la verdad.
