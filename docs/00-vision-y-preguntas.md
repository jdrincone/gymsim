# 00 — Visión y preguntas de negocio

## Visión
Construir un **simulador de afluencia de un gimnasio** que produzca datos lo más fieles a la realidad posible —incluyendo errores y ruido del hardware de registro— para alimentar **analítica avanzada batch y casi en tiempo real (streaming)**. Con esa analítica se diseñan **campañas proactivas** que benefician al negocio (retención, aforo, monetización) y al socio (mejor experiencia, acompañamiento).

El sistema se enfoca primero en el gimnasio, pero su motor está pensado para **generalizarse a otros negocios con afluencia física** (retail, oficinas, transporte) cambiando solo la configuración.

## Dato mínimo capturado
Por cada paso por la registradora: **timestamp, dispositivo (registradora), identificación de la persona, dirección (IN/OUT)**. Por cada persona: **datos de contacto** (email/teléfono) para campañas proactivas, separados de los hechos (PII).

## Principio rector
> **Verdad limpia → capa de ruido → persistencia.** El simulador conoce la verdad (visitas reales y arquetipo de cada socio); el hardware la "ensucia". La analítica debe recuperar la verdad y se valida contra el **ground-truth** exportado.

---

## Catálogo de preguntas de negocio
Formato: **pregunta → decisión que habilita → métrica → batch/stream → campaña proactiva**.

### A. Comportamiento individual
| Pregunta | Decisión | Métrica | B/S | Campaña |
|---|---|---|---|---|
| ¿Quién está en riesgo de irse (frecuencia cayendo)? | Intervenir antes de la baja | Tendencia de visitas/sem (EWMA/CUSUM), recencia/intervalo histórico | Stream (al cruzar umbral) | Check-in personal, incentivo |
| ¿Quién ya se fue de facto (churn comportamental)? | Reactivar o dar de baja | Recencia > k·intervalo, 0 visitas en ventana | Batch | Reactivación |
| ¿Quién es "fantasma" (paga, no asiste)? | Reonboarding | Membresía activa + visitas≈0 | Batch | Reonboarding/contacto |
| ¿Quién está en pico de entrenamiento (ramp-up)? | Aprovechar motivación | Pendiente positiva de frecuencia | Batch/Stream | Plan, PT, reto |
| ¿Quién es constante/embajador? | Fidelizar | Alta regularidad sostenida | Batch | Referidos, beneficios |
| ¿Quién es nuevo? | Onboarding crítico (sem 1-6) | Antigüedad < 6 sem | Stream | Onboarding guiado |
| ¿Quién marca 2+ veces al día? | Distinguir doble-visita real de ruido | Nº sesiones reales/día tras sesionizar | Batch | (calidad) / oferta día completo |

### B. Comportamiento social / grupal
| Pregunta | Decisión | Métrica | B/S |
|---|---|---|---|
| ¿Qué socios co-asisten sistemáticamente (parejas, amigos, grupos)? | Programas en grupo, referidos | Co-asistencia (mismas franjas/días) sobre el grafo de afinidad | Batch |
| ¿Qué horarios/clases crean comunidad? | Programación de clases | Densidad de co-asistencia por franja | Batch |
| ¿La asistencia acompañada mejora la retención? | Fomentar lo social | Retención de socios con vínculo vs. sin él | Batch |

### C. Temporal / estacional
| Pregunta | Decisión | Métrica | B/S |
|---|---|---|---|
| ¿Cuáles son las horas pico por día de semana? | Personal, aforo, clases | Perfil λ(hora, día) | Batch + Stream |
| ¿Cómo cambia la afluencia por estación (enero, verano, festivos)? | Planeación anual, precios | Índice estacional | Batch |
| ¿Hay tendencia (crece/decae la base activa)? | Salud del negocio | Activos por semana, cohortes | Batch |

### D. Operativa / aforo
| Pregunta | Decisión | Métrica | B/S |
|---|---|---|---|
| ¿Cuándo se satura el gimnasio? | Gestión de capacidad | Ocupación instantánea (IN−OUT acumulado) | Stream |
| ¿Qué registradora/puerta concentra el flujo? | Distribuir accesos | Eventos por dispositivo/tiempo | Batch + Stream |
| ¿Conviene una clase extra a cierta hora? | Oferta de clases | Demanda no atendida en pico | Batch |

### E. Calidad de datos / fraude
| Pregunta | Decisión | Métrica | B/S |
|---|---|---|---|
| ¿Cuánta "afluencia" es ruido (duplicados/re-entradas)? | Confiabilidad de KPIs | % eventos colapsados al sesionizar | Batch |
| ¿Hay credenciales compartidas? | Política de acceso/fraude | Patrones incoherentes para un mismo id | Batch |
| ¿Qué dispositivo tiene drift de reloj o cae? | Mantenimiento | Anomalía de timestamps/silencio | Stream |

---

## Segmentos operativos (salida de la analítica)
- **Nuevo**, **Constante/regular**, **Esporádico/casual**, **En riesgo**, **Churneado**, **Fantasma**, **En pico de entrenamiento**, **Doble-visita**. Definiciones cuantitativas en `docs/03-modelo-comportamental.md` y validables contra el arquetipo latente del simulador.

## Qué es batch y qué es streaming
- **Batch:** perfiles históricos por socio, segmentación, cohortes/retención, grafo social, índices estacionales, reentrenos. Sobre la capa `curated`.
- **Streaming (casi tiempo real, futuro):** ocupación/aforo en vivo, detección de saturación, alerta de socio que cruza umbral de riesgo, anomalía de dispositivo. Se haría leyendo la BD (no requiere infraestructura nueva).
