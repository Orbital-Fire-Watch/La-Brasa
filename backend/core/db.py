"""One short-lived connection per request (the data set is small, this is fast enough)."""
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from core.config import STATEMENT_TIMEOUT_MS, database_url


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    conn = psycopg.connect(
        database_url(), row_factory=dict_row, autocommit=True,
        options=f"-c statement_timeout={STATEMENT_TIMEOUT_MS} -c TimeZone=UTC",
    )
    try:
        yield conn
    finally:
        conn.close()
