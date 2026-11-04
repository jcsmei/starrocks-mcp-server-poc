"""Connecting to StarRocks, and running SQL files against it.

StarRocks speaks MySQL's wire protocol on its frontend's query port,
so any MySQL driver connects to it.  Loading goes through a backend's
HTTP port instead, with Stream Load.
"""

import os
import time
from pathlib import Path

import pymysql

HOST = os.environ.get("STARROCKS_HOST", "127.0.0.1")
QUERY_PORT = int(os.environ.get("STARROCKS_QUERY_PORT", "9030"))
LOAD_PORT = int(os.environ.get("STARROCKS_LOAD_PORT", "8040"))
ADMIN_USER = os.environ.get("STARROCKS_ADMIN_USER", "root")
ADMIN_PASSWORD = os.environ.get("STARROCKS_ADMIN_PASSWORD", "")
AGENT_USER = "agent_reader"
AGENT_PASSWORD = os.environ.get("AGENT_PASSWORD", "")
DATABASE = "poc"
SQL_FOLDER = Path(__file__).parent.parent / "sql"


def connect(user=ADMIN_USER, password=ADMIN_PASSWORD, database=None):
    """Return a connection over the MySQL protocol."""
    return pymysql.connect(host=HOST, port=QUERY_PORT, user=user,
                           password=password, database=database,
                           autocommit=True, connect_timeout=10)


def query(connection, sql, args=None):
    """Return the column names and rows of one statement."""
    with connection.cursor() as cursor:
        cursor.execute(sql, args)
        columns = [column[0] for column in cursor.description or []]
        return columns, [list(row) for row in cursor.fetchall()]


def wait_until_ready(timeout=300):
    """Wait until the frontend answers and a backend is alive."""
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            with connect() as connection:
                columns, rows = query(connection, "SHOW BACKENDS")
                alive = columns.index("Alive")
                if rows and all(row[alive] == "true" for row in rows):
                    return
                last_error = "no live backend yet"
        except pymysql.MySQLError as error:
            last_error = error
        time.sleep(5)
    raise RuntimeError(f"StarRocks was not ready in {timeout} s: "
                       f"{last_error}")


def statements(path):
    """Return the statements in a SQL file, without comment lines."""
    text = "\n".join(line for line in path.read_text().splitlines()
                     if not line.strip().startswith("--"))
    text = text.replace("${AGENT_PASSWORD}", AGENT_PASSWORD)
    return [part.strip() for part in text.split(";") if part.strip()]


def run_file(connection, name):
    """Run every statement in one of the files in `sql/`."""
    for statement in statements(SQL_FOLDER / name):
        with connection.cursor() as cursor:
            cursor.execute(statement)
