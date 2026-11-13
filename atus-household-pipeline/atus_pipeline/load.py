"""Load: write raw tables to SQLite and build the household table with SQL."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from . import config

SQL_DIR = Path(__file__).parent / "sql"


def connect(db_path: str | Path) -> sqlite3.Connection:
    return sqlite3.connect(str(db_path))


def load_raw(conn: sqlite3.Connection, roster: pd.DataFrame, respondent: pd.DataFrame) -> None:
    """Replace raw_roster / raw_respondent. Raw tables are never modified after this."""
    roster.to_sql("raw_roster", conn, if_exists="replace", index=False)
    respondent.to_sql("raw_respondent", conn, if_exists="replace", index=False)
    conn.execute("CREATE INDEX idx_roster_case ON raw_roster (TUCASEID)")
    conn.execute("CREATE INDEX idx_resp_case ON raw_respondent (TUCASEID)")
    conn.commit()


def build_household(conn: sqlite3.Connection, child_max_age: int = config.CHILD_MAX_AGE) -> int:
    """Run sql/household.sql. Returns the number of households built.

    Parameters are cast to int before being formatted into the SQL text, so
    this is not an injection vector (SQLite cannot bind parameters in DDL).
    """
    sql = (SQL_DIR / "household.sql").read_text().format(
        child_max_age=int(child_max_age),
        nonhh_code=int(config.NONHOUSEHOLD_CHILD_TERRP),
        female=int(config.SEX_FEMALE),
    )
    conn.executescript(sql)
    return conn.execute("SELECT COUNT(*) FROM household").fetchone()[0]
