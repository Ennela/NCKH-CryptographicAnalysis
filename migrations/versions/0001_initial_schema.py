"""Initial schema — exec init.sql

Revision ID: 0001
Revises: (none)
Create Date: 2026-06-09

Migration đầu tiên: đọc file infra/postgres/init.sql (nguồn sự thật duy nhất)
và thực thi toàn bộ trên DB.

LƯU Ý QUAN TRỌNG:
    Phải chạy ở isolation_level AUTOCOMMIT vì TimescaleDB continuous aggregate
    (CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous)) không chạy được
    bên trong transaction block.
"""

from typing import Sequence, Union
from pathlib import Path

from alembic import op


# Revision identifiers — Alembic sử dụng để quản lý thứ tự migration.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _find_init_sql() -> Path:
    """
    Tìm file init.sql từ thư mục gốc project.
    Hỗ trợ chạy cả khi cwd = project root hoặc cwd = migrations/.

    Returns:
        Path tuyệt đối đến init.sql.

    Raises:
        FileNotFoundError: nếu không tìm thấy init.sql.
    """
    # Bắt đầu từ thư mục chứa file migration này, leo lên tìm project root
    candidates = [
        Path(__file__).resolve().parent.parent.parent
        / "infra"
        / "postgres"
        / "init.sql",
        Path.cwd() / "infra" / "postgres" / "init.sql",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "Không tìm thấy infra/postgres/init.sql. "
        "Hãy chạy alembic từ thư mục gốc project."
    )


def upgrade() -> None:
    """
    Đọc và thực thi init.sql — AUTOCOMMIT mode.

    Không dùng op.execute() bình thường vì nó chạy trong transaction.
    Thay vào đó, lấy raw connection và set isolation_level = AUTOCOMMIT
    trước khi exec từng statement.
    """
    init_sql_path = _find_init_sql()
    sql_content = init_sql_path.read_text(encoding="utf-8")

    # Lấy connection gốc (DBAPI level) và bật AUTOCOMMIT
    connection = op.get_bind()
    raw_conn = connection.connection  # unwrap sang DBAPI connection
    raw_conn.set_isolation_level(0)  # 0 = AUTOCOMMIT cho psycopg2

    # Thực thi toàn bộ script — psycopg2 hỗ trợ multi-statement execute
    cursor = raw_conn.cursor()
    cursor.execute(sql_content)
    cursor.close()


def downgrade() -> None:
    """
    Xóa toàn bộ 3 schema (CASCADE) — MẤT HẾT dữ liệu.
    Xóa cả trigger function trong public schema.
    """
    connection = op.get_bind()
    raw_conn = connection.connection
    raw_conn.set_isolation_level(0)

    cursor = raw_conn.cursor()
    cursor.execute("DROP SCHEMA IF EXISTS market CASCADE;")
    cursor.execute("DROP SCHEMA IF EXISTS ml CASCADE;")
    cursor.execute("DROP SCHEMA IF EXISTS ops CASCADE;")
    cursor.execute("DROP FUNCTION IF EXISTS public.set_updated_at() CASCADE;")
    cursor.close()
