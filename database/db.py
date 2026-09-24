"""
Database connection and operations module for HealthGuard.
Provides connection pooling, schema initialization, and transactional helpers.
"""

import os
import sqlite3
from typing import Any, Dict, List, Optional

# Default database location in the project root
DEFAULT_DB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "healthguard.db")
)
SCHEMA_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "schema.sql"))


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Returns an SQLite connection configured with Row factory
    and enabled Foreign Key constraints.
    """
    path = db_path or os.environ.get("HEALTHGUARD_DB_PATH", DEFAULT_DB_PATH)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """
    Executes schema.sql to initialize the database tables.
    """
    conn = get_db_connection(db_path)
    try:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()


def query_db(
    query: str,
    args: tuple = (),
    one: bool = False,
    db_path: Optional[str] = None,
) -> Any:
    """
    Utility function to run a SELECT query and return dictionary-like records.
    """
    conn = get_db_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute(query, args)
        rv = cur.fetchall()
        if one:
            return dict(rv[0]) if rv else None
        return [dict(row) for row in rv]
    finally:
        conn.close()


def execute_db(
    query: str,
    args: tuple = (),
    commit: bool = True,
    db_path: Optional[str] = None,
) -> int:
    """
    Utility function to run INSERT, UPDATE, DELETE statements.
    Returns the lastrowid or rowcount.
    """
    conn = get_db_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute(query, args)
        if commit:
            conn.commit()
        return cur.lastrowid
    finally:
        conn.close()
