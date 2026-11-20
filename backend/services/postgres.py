"""Shared PostgreSQL connection utilities for OnboardAI."""

import os
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor

from backend.config import settings


@contextmanager
def postgres_connection():
    """Provide a PostgreSQL connection with commit and rollback."""

    connection = psycopg2.connect(
        host=settings.pg_host,
        port=settings.pg_port,
        dbname=settings.pg_database,
        user=settings.pg_user,
        password=settings.pg_password or os.environ.get("PGPASSWORD", ""),
        connect_timeout=10,
        cursor_factory=RealDictCursor,
    )

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def check_postgres_connection() -> bool:
    """Verify PostgreSQL connectivity."""

    with postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 AS connected")
            return cursor.fetchone()["connected"] == 1