# gymsim — Simulador de la registradora de un gimnasio

Genera los registros de **entrada/salida** que produciría la máquina registradora a la entrada de
un gimnasio, **lo más parecido a la realidad** (incluyendo el ruido y los errores típicos del
hardware), y los va guardando en **Supabase** para hacer analítica después.

## Qué hace realista a los datos
- **Horarios reales:** L-V 5:00–22:00; sáb/dom/festivos 7:00–15:00; **cerrado** 1-ene, 25-dic y
  Viernes Santo (festivos de Colombia, Ley Emiliani).
- **Picos por hora** (mañana y tarde), efecto de día de semana y **estacionalidad** (pico de año
  nuevo, bajón vacacional), más azar diario.
- **Tipos de socio:** constante, casual, esporádico, en racha (ramp-up), decadente→se va (churn),
  fantasma (paga y no asiste), nuevo.
- **Relaciones:** grupos (parejas/amigos) que **co-asisten**.
- **Doble visita real** (entra 2+ veces el mismo día).
- **Ruido de la registradora:** doble lectura (rebote), re-entradas (salió a una llamada / por
  agua), desfase de reloj, marcajes faltantes, accesos denegados, credenciales compartidas.

> Se genera primero la **verdad** (las visitas reales) y encima el **ruido** del hardware,
> conservando el ground-truth para luego validar la analítica.

## Estructura
```
src/gymsim/
  config.py        configuración (perfiles, arquetipos, ruido, dispositivos)
  domain/          calendario, arquetipos, socios, evento de paso
  simulation/      población · comportamiento (visitas) · ruido · ventana · motor
  sinks/           destinos: memory · jsonl · postgres (Supabase)
  live.py          gymsim tick (llenado autónomo incremental, serializado con advisory lock)
  transform.py     gymsim transform (ejecuta los SQL de analítica raw→staging→curated)
  db/              modelos SQLAlchemy (esquemas raw/staging/curated)
  cli.py           comandos: tick / simulate / transform
configs/gym.yaml   configuración del gimnasio
sql/transforms/    SQL de analítica (reconstruye visitas tolerando el ruido)
.github/workflows/ cron gratuito que llena la BD solo
docs/              visión y preguntas de negocio, modelo de datos, arquitectura
```

## Empezar
```bash
uv sync
cp .env.example .env          # pon tu DATABASE_URL de Supabase (Session pooler, puerto 5432)
```

### Ver los datos sin tocar la BD
```bash
uv run gymsim simulate --sink jsonl --out data/events.jsonl --days 60 --ground-truth data/truth.jsonl
```
Genera `data/events.jsonl` (eventos con ruido) y `data/truth.jsonl` (visitas reales).

### Cargar histórico en Supabase (de una vez)
```bash
uv run gymsim simulate --sink postgres --days 180
```
Crea las tablas solo e inserta de forma idempotente.

## Que se llene sola y gratis: `gymsim tick` + GitHub Actions
Un **cron de GitHub Actions** dispara `gymsim tick` cada 30 min; cada tick inserta en Supabase los
eventos ocurridos **desde el último checkpoint**, anclando el tiempo simulado al reloj real. Sin
servidor, sin costo.

- Generación **determinista por día** + `event_uuid` por contenido → **idempotente** (regenerar
  una ventana da los mismos eventos; nada se duplica).
- Robusto a retrasos: si el cron se atrasa, el siguiente tick rellena el hueco.

**Activarlo (una vez):**
1. Sube el repo a GitHub.
2. **Settings → Secrets and variables → Actions** → secret `DATABASE_URL` con tu cadena de Supabase.
3. El workflow [`.github/workflows/fill-db.yml`](.github/workflows/fill-db.yml) corre solo. Ajusta
   `SIM_ACCEL` (24 → 1 día por hora real) y la frecuencia.

> **Minutos gratis:** repo público = Actions ilimitado; repo privado = 2.000 min/mes (cada 30 min cabe).

**Probar un tick en local:** `uv run gymsim tick --accel 24`

## Analítica (capa SQL, automática)
`sql/transforms/` reconstruye las visitas a partir de los eventos crudos tolerando el ruido
(deduplica rebotes, fusiona re-entradas, imputa marcajes faltantes). El workflow ejecuta
`gymsim transform` **después de cada tick**, así que la capa `curated` (la que consume la
analítica) queda siempre al día sin intervención manual.

Para correrlo a mano (no necesita `psql`; usa la misma `DATABASE_URL`):
```bash
uv run gymsim transform
```
Aplica en orden los `.sql` del directorio, **en una sola transacción** (o queda todo consistente
o no cambia nada) y es idempotente (cada SQL hace `TRUNCATE + INSERT`).

## Tests
```bash
uv run --extra dev pytest -q
```
