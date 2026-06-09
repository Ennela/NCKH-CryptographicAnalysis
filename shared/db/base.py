"""
DeclarativeBase — SQLAlchemy 2.0 style.

Tất cả ORM models trong dự án phải kế thừa từ class ``Base`` này.
Alembic ``env.py`` cũng import ``Base.metadata`` để autogenerate.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class cho mọi ORM model trong dự án."""

    pass
