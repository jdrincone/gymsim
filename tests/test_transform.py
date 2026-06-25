"""Tests del parseo de los SQL de analítica (sin BD: solo el split de sentencias)."""
from __future__ import annotations

from pathlib import Path

import pytest

from gymsim.transform import _split_statements, run_transforms

TRANSFORMS_DIR = Path(__file__).resolve().parents[1] / "sql" / "transforms"


def test_split_ignores_comments_and_blanks():
    sql = """
    -- un comentario
    TRUNCATE foo;
    -- otro comentario
    INSERT INTO foo VALUES (1);
    -- comentario final suelto, sin sentencia
    """
    stmts = _split_statements(sql)
    assert len(stmts) == 2
    assert "TRUNCATE foo" in stmts[0]
    assert "INSERT INTO foo" in stmts[1]


def test_split_empty_is_empty():
    assert _split_statements("   \n -- solo comentarios \n") == []


def test_split_semicolon_inside_comment_does_not_break_statement():
    """Un ';' dentro de un comentario NO debe partir la sentencia (regresión: issue del run #1)."""
    sql = "-- excluye denegados; conserva el grano\nTRUNCATE foo;\nINSERT INTO foo VALUES (1);"
    stmts = _split_statements(sql)
    assert stmts == ["TRUNCATE foo", "INSERT INTO foo VALUES (1)"]


_SQL_KEYWORDS = ("TRUNCATE", "INSERT", "WITH", "UPDATE", "SELECT", "CREATE", "DELETE")


def test_real_transform_files_parse_into_executable_statements():
    """Cada sentencia real debe empezar por una palabra clave SQL (no por prosa de un comentario)."""
    files = sorted(TRANSFORMS_DIR.glob("*.sql"))
    assert files, f"no se encontraron .sql en {TRANSFORMS_DIR}"
    for f in files:
        stmts = _split_statements(f.read_text(encoding="utf-8"))
        assert stmts, f"{f.name} no produjo sentencias"
        for s in stmts:
            assert s.upper().startswith(_SQL_KEYWORDS), f"{f.name}: sentencia no-SQL -> {s[:40]!r}"
        # cada transform trunca su tabla destino antes de reinsertar (idempotencia)
        assert any(s.upper().startswith("TRUNCATE") for s in stmts)


def test_run_transforms_raises_when_no_sql(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_transforms("postgresql://x/y", transforms_dir=tmp_path)
