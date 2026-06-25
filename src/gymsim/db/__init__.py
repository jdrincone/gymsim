"""Capa de base de datos: modelos SQLAlchemy 2.0 y utilidades de conexión.

Las transformaciones analíticas raw→staging→curated viven en SQL (sql/transforms/),
no en el ORM. Ver docs/01-modelo-de-datos.md y la decisión db-layer-sqlalchemy-alembic.
"""
from .models import Base

__all__ = ["Base"]
