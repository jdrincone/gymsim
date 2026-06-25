---
name: gym-business-questions
description: Catálogo vivo de preguntas de negocio que los datos del gimnasio deben responder, mapeadas a la métrica, los datos fuente, si es batch o streaming, y la campaña proactiva que habilitan. Úsala cuando el usuario quiera saber qué se puede responder con los datos, priorizar analítica, o diseñar campañas. Para generar preguntas nuevas con profundidad, delega en el agente gym-business-analyst.
---

# Preguntas de negocio del gimnasio

Marco de trabajo: **decisión → dato → métrica → (batch|stream) → campaña**. El catálogo completo y razonado está en `docs/00-vision-y-preguntas.md`. Esta skill es la guía rápida.

## Cómo usarla
1. Identifica la **categoría** de la pregunta (individual, social, temporal, operativa, calidad).
2. Comprueba que el dato mínimo lo permita: `timestamp, dispositivo, id_persona, contacto`.
3. Define unidad de análisis (evento / sesión / día-cliente / semana-cliente) y ventana.
4. Decide **batch vs streaming** según latencia de la decisión.
5. Asóciala a una **campaña proactiva** (si aplica) que beneficie a negocio y socio.

## Categorías y ejemplos
- **Individual:** ¿Quién está en riesgo de churn (frecuencia cayendo)? ¿Quién es fantasma (paga, no asiste)? ¿Quién está en pico de entrenamiento? ¿Quién marca 2+ veces al día?
- **Social:** ¿Qué socios co-asisten sistemáticamente (parejas/grupos)? ¿Qué horarios/clases crean comunidad?
- **Temporal:** ¿Horas pico por día de semana? ¿Efecto estacional (enero, verano, festivos)? ¿Tendencia de afluencia?
- **Operativa/aforo:** ¿Cuándo se satura? ¿Qué registradora concentra flujo? ¿Conviene clase extra a cierta hora?
- **Calidad/fraude:** ¿Cuánta "afluencia" es ruido (duplicados/re-entradas)? ¿Hay credenciales compartidas?

## Reglas de respuesta
- Si una pregunta **no** se puede responder con los datos actuales, dilo y propón qué capturar.
- Distingue siempre **señal** (comportamiento real) de **ruido** (artefactos del hardware) — muchas preguntas exigen sesionizar y limpiar primero.
- Cada respuesta debe ser **verificable contra el ground-truth** del simulador.

Mantén `docs/00-vision-y-preguntas.md` actualizado cuando surjan preguntas nuevas.
