"""Genera un dashboard HTML autocontenido a partir de la BD del gym (solo lectura).

Todos los números salen de consultas a Postgres/Supabase; nada se inventa. Embebe los datos
como JSON en el HTML y los grafica con Chart.js (CDN). Reutilizable: vuelve a correrlo para
refrescar el tablero a medida que la BD crece.

Uso:
    uv run python scripts/build_dashboard.py [--out dashboard.html]
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

DOW = {1: "Lun", 2: "Mar", 3: "Mié", 4: "Jue", 5: "Vie", 6: "Sáb", 7: "Dom"}


def _engine():
    load_dotenv()
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("ERROR: define DATABASE_URL (.env o variable de entorno)")
    if dsn.startswith("postgresql://"):
        dsn = dsn.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(dsn, future=True)


def collect(engine) -> dict:
    """Ejecuta todas las consultas y arma el diccionario de datos del dashboard."""
    def rows(sql):
        with engine.connect() as c:
            return [dict(m) for m in c.execute(text(sql)).mappings().all()]

    def one(sql):
        with engine.connect() as c:
            return c.execute(text(sql)).mappings().first()

    meta = one(
        "SELECT now() AS generated_at, "
        "(SELECT max(loaded_at) FROM raw.access_event_raw) AS last_loaded, "
        "(SELECT sim_checkpoint FROM raw.sim_state) AS sim_checkpoint, "
        "(SELECT min(ts_in)::date FROM curated.fact_session) AS data_from, "
        "(SELECT max(ts_in)::date FROM curated.fact_session) AS data_to"
    )

    kpis = one(
        "SELECT "
        "(SELECT count(*) FROM raw.access_event_raw) AS eventos_raw, "
        "(SELECT count(*) FROM curated.fact_session) AS sesiones, "
        "(SELECT count(DISTINCT member_id) FROM curated.fact_session) AS socios_activos, "
        "(SELECT count(*) FROM curated.dim_member) AS socios_catalogo, "
        "(SELECT round(avg(duration_min)::numeric,1) FROM curated.fact_session) AS dur_media, "
        "(SELECT round(percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_min)::numeric,1) "
        "   FROM curated.fact_session) AS dur_mediana, "
        "(SELECT round(100.0*avg(is_double_visit::int),1) FROM curated.fact_session) AS pct_doble"
    )

    # churn: recencia contra el máximo ts_in observado (el "ahora" simulado)
    recencia = rows(
        "WITH ref AS (SELECT max(ts_in) AS ahora FROM curated.fact_session), "
        "per AS (SELECT member_id, max(ts_in) AS ultima FROM curated.fact_session GROUP BY member_id) "
        "SELECT CASE "
        " WHEN (SELECT ahora FROM ref)-ultima > interval '28 days' THEN 'Churneado (>28d)' "
        " WHEN (SELECT ahora FROM ref)-ultima > interval '14 days' THEN 'En riesgo (14-28d)' "
        " WHEN (SELECT ahora FROM ref)-ultima > interval '7 days'  THEN 'Enfriándose (7-14d)' "
        " ELSE 'Activo (<7d)' END AS segmento, count(*) AS socios "
        "FROM per GROUP BY 1 ORDER BY 1"
    )

    ocup_hora = rows(
        "SELECT extract(hour from ts_in)::int AS hora, count(*) AS sesiones "
        "FROM curated.fact_session GROUP BY 1 ORDER BY 1"
    )
    afluencia_dow = rows(
        "SELECT extract(isodow from ts_in)::int AS dow, count(*) AS sesiones, "
        "count(distinct member_id) AS socios FROM curated.fact_session GROUP BY 1 ORDER BY 1"
    )
    tendencia = rows(
        "SELECT to_char(date_trunc('week', ts_in),'YYYY-MM-DD') AS semana, count(*) AS sesiones, "
        "count(distinct member_id) AS socios FROM curated.fact_session GROUP BY 1 ORDER BY 1"
    )
    heat = rows(
        "SELECT extract(isodow from ts_in)::int AS dow, extract(hour from ts_in)::int AS hora, "
        "count(*) AS c FROM curated.fact_session GROUP BY 1,2"
    )
    arquetipo = rows(
        "WITH ref AS (SELECT max(ts_in) AS ahora FROM curated.fact_session), "
        "per AS (SELECT member_id, count(*) v, max(ts_in) ultima FROM curated.fact_session GROUP BY member_id) "
        "SELECT m.archetype_hint AS arquetipo, count(*) AS socios, round(avg(p.v),1) AS visitas_media, "
        "round(100.0*avg(((SELECT ahora FROM ref)-p.ultima > interval '28 days')::int),0) AS pct_churn "
        "FROM per p JOIN curated.dim_member m USING(member_id) "
        "GROUP BY 1 ORDER BY 2 DESC"
    )
    frecuencia = rows(
        "WITH per AS (SELECT member_id, count(*) v FROM curated.fact_session GROUP BY member_id) "
        "SELECT CASE WHEN v=1 THEN '1' WHEN v<=5 THEN '2-5' WHEN v<=20 THEN '6-20' "
        "WHEN v<=50 THEN '21-50' ELSE '50+' END AS rango, count(*) AS socios, min(v) AS ord "
        "FROM per GROUP BY 1 ORDER BY ord"
    )
    calidad = one(
        "SELECT "
        "(SELECT count(*) FROM staging.access_event WHERE is_duplicate) AS duplicados, "
        "(SELECT count(*) FROM staging.access_event WHERE is_denied) AS denegados, "
        "(SELECT count(*) FROM staging.access_event WHERE is_suspect) AS sospechosos, "
        "(SELECT count(*) FROM staging.access_event "
        "  WHERE NOT is_duplicate AND NOT is_denied AND member_id IS NOT NULL) AS validos, "
        "(SELECT round(100.0*avg((n_reentries>0)::int),1) FROM curated.fact_session) AS pct_reentrada, "
        "(SELECT round(100.0*avg(imputed_out::int),1) FROM curated.fact_session) AS pct_imputada"
    )
    dispositivo = rows(
        "SELECT device_id, direction, count(*) AS eventos "
        "FROM curated.fact_access_event GROUP BY 1,2 ORDER BY 1,2"
    )

    # matriz del heatmap hora(5-22) x día(1-7)
    hours = list(range(5, 23))
    matrix = [[0] * len(hours) for _ in range(7)]
    for r in heat:
        d, h = int(r["dow"]), int(r["hora"])
        if h in hours and 1 <= d <= 7:
            matrix[d - 1][hours.index(h)] = int(r["c"])

    def num(v):
        return float(v) if v is not None else 0

    return {
        "meta": {
            "generated_at": str(meta["generated_at"]),
            "last_loaded": str(meta["last_loaded"]),
            "sim_checkpoint": str(meta["sim_checkpoint"]),
            "data_from": str(meta["data_from"]),
            "data_to": str(meta["data_to"]),
        },
        "kpis": {k: num(kpis[k]) for k in kpis.keys()},
        "recencia": [{"segmento": r["segmento"], "socios": int(r["socios"])} for r in recencia],
        "ocup_hora": [{"hora": int(r["hora"]), "sesiones": int(r["sesiones"])} for r in ocup_hora],
        "afluencia_dow": [
            {"dia": DOW[int(r["dow"])], "sesiones": int(r["sesiones"]), "socios": int(r["socios"])}
            for r in afluencia_dow
        ],
        "tendencia": [
            {"semana": r["semana"], "sesiones": int(r["sesiones"]), "socios": int(r["socios"])}
            for r in tendencia
        ],
        "heatmap": {"hours": hours, "dows": [DOW[i] for i in range(1, 8)], "matrix": matrix},
        "arquetipo": [
            {
                "arquetipo": r["arquetipo"],
                "socios": int(r["socios"]),
                "visitas_media": num(r["visitas_media"]),
                "pct_churn": num(r["pct_churn"]),
            }
            for r in arquetipo
        ],
        "frecuencia": [{"rango": r["rango"], "socios": int(r["socios"])} for r in frecuencia],
        "calidad": {k: num(calidad[k]) for k in calidad.keys()},
        "dispositivo": [
            {"device": r["device_id"], "direction": r["direction"], "eventos": int(r["eventos"])}
            for r in dispositivo
        ],
    }


def render(data: dict) -> str:
    """Inyecta los datos y la librería Chart.js INCRUSTADA (sin CDN → funciona offline)."""
    chartjs = (Path(__file__).resolve().parent / "chart.umd.min.js").read_text(encoding="utf-8")
    html = HTML_TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    html = html.replace("__CHARTJS__", "<script>\n" + chartjs + "\n</script>")
    return html


def main() -> int:
    ap = argparse.ArgumentParser(description="Genera el dashboard HTML desde la BD")
    ap.add_argument("--out", default="dashboard.html")
    args = ap.parse_args()
    engine = _engine()
    try:
        data = collect(engine)
    finally:
        engine.dispose()
    out = Path(args.out)
    out.write_text(render(data), encoding="utf-8")
    print(f"[dashboard] {out.resolve()}  ({data['kpis']['sesiones']:.0f} sesiones, "
          f"{data['kpis']['eventos_raw']:.0f} eventos)")
    return 0


HTML_TEMPLATE = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gym · Dashboard de afluencia y retención</title>
__CHARTJS__
<style>
  :root{--bg:#0f1419;--card:#1a2027;--card2:#222b34;--ink:#e6edf3;--mut:#8b98a5;
        --acc:#3fb950;--acc2:#58a6ff;--warn:#d29922;--bad:#f85149;--grid:#2d3640}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
       font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
  header{padding:22px 28px;border-bottom:1px solid var(--grid)}
  h1{margin:0 0 4px;font-size:20px}
  .sub{color:var(--mut);font-size:13px}
  .wrap{padding:22px 28px;max-width:1400px;margin:0 auto}
  .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:22px}
  .kpi{background:var(--card);border:1px solid var(--grid);border-radius:10px;padding:14px 16px}
  .kpi .v{font-size:24px;font-weight:700}
  .kpi .l{color:var(--mut);font-size:12px;margin-top:2px}
  .grid{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}
  .card{background:var(--card);border:1px solid var(--grid);border-radius:12px;padding:16px}
  .card h3{margin:0 0 12px;font-size:14px;font-weight:600}
  .card .note{color:var(--mut);font-size:12px;margin-top:8px}
  .full{grid-column:1/-1}
  canvas{max-height:300px}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--grid)}
  th{color:var(--mut);font-weight:600}
  .bar{height:8px;border-radius:4px;background:var(--acc2)}
  .hm{display:grid;gap:2px;font-size:11px}
  .hm .cell{height:22px;border-radius:3px;display:flex;align-items:center;justify-content:center;color:#0b0f14}
  .hm .lbl{color:var(--mut);display:flex;align-items:center}
  .pill{padding:2px 8px;border-radius:20px;font-size:11px;font-weight:600}
  @media(max-width:900px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<header>
  <h1>🏋️ Gym · Dashboard de afluencia y retención</h1>
  <div class="sub" id="sub"></div>
</header>
<div class="wrap">
  <div class="kpis" id="kpis"></div>
  <div class="grid">
    <div class="card"><h3>Ocupación por hora (¿horas pico?)</h3><canvas id="c_hora"></canvas>
      <div class="note">Patrón bimodal mañana/tarde. Decisión: personal y clases en los picos.</div></div>
    <div class="card"><h3>Afluencia por día de semana</h3><canvas id="c_dow"></canvas>
      <div class="note">L-J fuertes, domingo el más flojo (cierre 7-15h).</div></div>
    <div class="card full"><h3>Tendencia semanal — salud del negocio</h3><canvas id="c_tend"></canvas>
      <div class="note">Sesiones y socios activos por semana. Pendiente negativa = la base se enfría.</div></div>
    <div class="card full"><h3>Mapa de calor · ocupación hora × día</h3><div id="heat"></div>
      <div class="note">Más oscuro = más sesiones. Guía aforo, clases y staffing.</div></div>
    <div class="card"><h3>Segmentación por recencia (retención)</h3><canvas id="c_rec"></canvas>
      <div class="note">Activo / enfriándose / en riesgo / churneado → prioriza campañas.</div></div>
    <div class="card"><h3>Distribución de frecuencia (visitas/socio)</h3><canvas id="c_frec"></canvas></div>
    <div class="card full"><h3>Validación: arquetipo real vs churn detectado (ground-truth)</h3>
      <table id="t_arq"></table>
      <div class="note">La analítica de recencia recupera la verdad: decadente/fantasma = alto % churn.</div></div>
    <div class="card"><h3>Calidad de datos / ruido del hardware</h3><canvas id="c_cal"></canvas>
      <div class="note">Lo que el pipeline limpió antes de reconstruir visitas.</div></div>
    <div class="card"><h3>Flujo por dispositivo / puerta</h3><canvas id="c_dev"></canvas></div>
  </div>
  <div class="note" style="margin-top:18px;color:var(--mut)">
    Datos extraídos en vivo de la base (capa <code>curated</code>). Ningún valor es inventado.
  </div>
</div>
<script>
const D = __DATA__;
const fmt = n => Number(n).toLocaleString('es-CO');
const C = {acc:'#3fb950',acc2:'#58a6ff',warn:'#d29922',bad:'#f85149',mut:'#8b98a5',
           pal:['#58a6ff','#3fb950','#d29922','#f85149','#a371f7','#ff7b72','#39c5cf']};
const HAS_CHART = (typeof Chart !== 'undefined');

document.getElementById('sub').innerHTML =
  `Datos: <b>${D.meta.data_from}</b> → <b>${D.meta.data_to}</b> · `+
  `checkpoint sim: ${D.meta.sim_checkpoint?.slice(0,16)||'—'} · `+
  `última carga real: ${D.meta.last_loaded?.slice(0,16)||'—'} · `+
  `generado: ${D.meta.generated_at?.slice(0,16)||'—'}`;

const k=D.kpis, churn = (D.recencia.find(r=>r.segmento.startsWith('Churneado'))||{}).socios||0;
const enRiesgo = (D.recencia.find(r=>r.segmento.startsWith('En riesgo'))||{}).socios||0;
const kpiList = [
  ['Eventos crudos', fmt(k.eventos_raw)],
  ['Sesiones reales', fmt(k.sesiones)],
  ['Socios activos', fmt(k.socios_activos)],
  ['Catálogo socios', fmt(k.socios_catalogo)],
  ['Dur. mediana (min)', fmt(k.dur_mediana)],
  ['% doble visita', k.pct_doble+'%'],
  ['Churneados', fmt(churn)],
  ['En riesgo', fmt(enRiesgo)],
];
document.getElementById('kpis').innerHTML = kpiList.map(
  ([l,v])=>`<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');

if (HAS_CHART) {
Chart.defaults.color='#8b98a5'; Chart.defaults.borderColor='#2d3640'; Chart.defaults.font.size=11;
const bar=(id,labels,data,color,label)=>new Chart(document.getElementById(id),{type:'bar',
  data:{labels,datasets:[{label:label||'',data,backgroundColor:color,borderRadius:4}]},
  options:{plugins:{legend:{display:!!label}},scales:{y:{beginAtZero:true,grid:{color:'#2d3640'}},x:{grid:{display:false}}}}});

bar('c_hora', D.ocup_hora.map(r=>r.hora+'h'), D.ocup_hora.map(r=>r.sesiones), C.acc2);
bar('c_dow', D.afluencia_dow.map(r=>r.dia), D.afluencia_dow.map(r=>r.sesiones), C.acc);
bar('c_frec', D.frecuencia.map(r=>r.rango), D.frecuencia.map(r=>r.socios), C.warn);

new Chart(document.getElementById('c_tend'),{type:'line',
  data:{labels:D.tendencia.map(r=>r.semana),datasets:[
    {label:'Sesiones',data:D.tendencia.map(r=>r.sesiones),borderColor:C.acc2,backgroundColor:'transparent',tension:.3},
    {label:'Socios activos',data:D.tendencia.map(r=>r.socios),borderColor:C.acc,backgroundColor:'transparent',tension:.3,yAxisID:'y2'}]},
  options:{interaction:{mode:'index',intersect:false},scales:{
    y:{beginAtZero:true,grid:{color:'#2d3640'}},
    y2:{position:'right',beginAtZero:true,grid:{display:false}},x:{grid:{display:false}}}}});

new Chart(document.getElementById('c_rec'),{type:'doughnut',
  data:{labels:D.recencia.map(r=>r.segmento),datasets:[{data:D.recencia.map(r=>r.socios),
    backgroundColor:[C.acc,C.warn,'#db6d28',C.bad]}]},
  options:{plugins:{legend:{position:'right'}}}});

const cal=D.calidad;
new Chart(document.getElementById('c_cal'),{type:'bar',
  data:{labels:['Válidos','Duplicados','Denegados','Sospechosos'],
    datasets:[{data:[cal.validos,cal.duplicados,cal.denegados,cal.sospechosos],
      backgroundColor:[C.acc,C.warn,C.bad,'#a371f7'],borderRadius:4}]},
  options:{plugins:{legend:{display:false}},scales:{y:{beginAtZero:true,grid:{color:'#2d3640'}},x:{grid:{display:false}}}}});

const dev=D.dispositivo, devIds=[...new Set(dev.map(d=>d.device))];
const ins=devIds.map(id=>(dev.find(d=>d.device===id&&d.direction==='IN')||{}).eventos||0);
const outs=devIds.map(id=>(dev.find(d=>d.device===id&&d.direction==='OUT')||{}).eventos||0);
new Chart(document.getElementById('c_dev'),{type:'bar',
  data:{labels:devIds,datasets:[
    {label:'IN',data:ins,backgroundColor:C.acc2,borderRadius:4},
    {label:'OUT',data:outs,backgroundColor:C.warn,borderRadius:4}]},
  options:{scales:{y:{beginAtZero:true,grid:{color:'#2d3640'}},x:{grid:{display:false}}}}});
}  // fin if(HAS_CHART)

// tabla arquetipo
const maxV=Math.max(...D.arquetipo.map(r=>r.visitas_media));
document.getElementById('t_arq').innerHTML =
  '<tr><th>Arquetipo real</th><th>Socios</th><th>Visitas media</th><th>% churn detectado</th></tr>'+
  D.arquetipo.map(r=>{
    const col = r.pct_churn>=50?C.bad:(r.pct_churn>=20?C.warn:C.acc);
    return `<tr><td>${r.arquetipo}</td><td>${fmt(r.socios)}</td>
      <td>${r.visitas_media} <span class="bar" style="display:inline-block;width:${60*r.visitas_media/maxV}px"></span></td>
      <td><span class="pill" style="background:${col}22;color:${col}">${r.pct_churn}%</span></td></tr>`;
  }).join('');

// heatmap
const H=D.heatmap, maxC=Math.max(...H.matrix.flat());
const col = v => { if(!v) return '#161b22'; const t=v/maxC;
  const r=Math.round(33+t*(88-33)),g=Math.round(38+t*(166-38)),b=Math.round(45+t*(80-45));
  return `rgb(${r},${g},${b})`; };
let html='<div class="hm" style="grid-template-columns:42px repeat('+H.hours.length+',1fr)">';
html+='<div class="lbl"></div>'+H.hours.map(h=>`<div class="lbl" style="justify-content:center">${h}</div>`).join('');
H.dows.forEach((d,i)=>{ html+=`<div class="lbl">${d}</div>`;
  H.hours.forEach((h,j)=>{ const v=H.matrix[i][j];
    html+=`<div class="cell" style="background:${col(v)}" title="${d} ${h}h: ${fmt(v)} sesiones">${v?'':''}</div>`;});});
html+='</div>';
document.getElementById('heat').innerHTML=html;
</script>
</body>
</html>"""


if __name__ == "__main__":
    raise SystemExit(main())
