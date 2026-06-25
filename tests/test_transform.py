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


def test_real_transform_files_parse_into_statements():
    """Cada .sql real debe partirse en >=1 sentencia no vacía (TRUNCATE + INSERT)."""
    files = sorted(TRANSFORMS_DIR.glob("*.sql"))
    assert files, f"no se encontraron .sql en {TRANSFORMS_DIR}"
    for f in files:
        stmts = _split_statements(f.read_text(encoding="utf-8"))
        assert stmts, f"{f.name} no produjo sentencias"
        assert all(s.strip() for s in stmts)
        # cada transform trunca su tabla destino antes de reinsertar (idempotencia)
        assert any(s.upper().startswith("TRUNCATE") or "TRUNCATE" in s.upper() for s in stmts)


def test_run_transforms_raises_when_no_sql(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_transforms("postgresql://x/y", transforms_dir=tmp_path)
