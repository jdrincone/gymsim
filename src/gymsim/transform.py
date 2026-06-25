"""Ejecuta los SQL de analítica (``sql/transforms/*.sql``) en orden: raw → staging → curated.

Se corre **después** de cada ``tick`` para que la capa ``curated`` —la que consume la
analítica— quede siempre al día sin intervención manual. Todo el lote se aplica en una sola
transacción: o queda consistente o no cambia nada. Cada SQL es idempotente (TRUNCATE + INSERT),
así que repetir la corrida es seguro.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text


def _normalize_dsn(dsn: str) -> str:
    """Normaliza el driver a psycopg v3 (igual que el sink)."""
    if dsn.startswith("postgresql://"):
        return dsn.replace("postgresql://", "postgresql+psycopg://", 1)
    return dsn


def _split_statements(sql: str) -> list[str]:
    """Parte un script en sentencias por ';'.

    psycopg ejecuta una sola sentencia por ``execute``; los .sql de este repo no contienen ';'
    dentro de literales, así que un split por ';' es suficiente y robusto. Se descartan los
    fragmentos que solo son comentarios o espacios (p. ej. el comentario final tras el último ';').
    """
    out: list[str] = []
    for chunk in sql.split(";"):
        body = "\n".join(
            ln for ln in chunk.splitlines() if not ln.strip().startswith("--")
        ).strip()
        if body:
            out.append(chunk.strip())
    return out


def run_transforms(dsn: str, transforms_dir: str | Path = "sql/transforms") -> dict:
    """Aplica, en orden alfabético, todos los .sql del directorio dentro de una transacción."""
    d = Path(transforms_dir)
    files = sorted(d.glob("*.sql"))
    if not files:
        raise FileNotFoundError(f"No hay archivos .sql en {d}")

    engine = create_engine(_normalize_dsn(dsn), future=True)
    applied: list[str] = []
    try:
        with engine.begin() as conn:
            for f in files:
                for stmt in _split_statements(f.read_text(encoding="utf-8")):
                    conn.execute(text(stmt))
                applied.append(f.name)
    finally:
        engine.dispose()
    return {"applied": applied, "count": len(applied)}
