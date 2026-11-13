"""Data-quality checks. Errors stop the pipeline; warnings are reported.

Each check is a SQL query so the logic is easy to audit and to port to a
production database.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from . import config

log = logging.getLogger(__name__)


class ValidationError(RuntimeError):
    pass


@dataclass
class Check:
    name: str
    passed: bool
    severity: str  # "error" | "warning"
    detail: str


def _scalar(conn: sqlite3.Connection, sql: str, *params):
    return conn.execute(sql, params).fetchone()[0]


def run_checks(conn: sqlite3.Connection) -> list[Check]:
    checks: list[Check] = []

    def add(name: str, bad_count: int, severity: str = "error", what: str = "rows"):
        checks.append(Check(name, bad_count == 0, severity, f"{bad_count} {what}"))

    # --- Keys and referential integrity ---
    add("roster key (TUCASEID, TULINENO) is unique",
        _scalar(conn, """SELECT COUNT(*) FROM (SELECT 1 FROM raw_roster
                         GROUP BY TUCASEID, TULINENO HAVING COUNT(*) > 1)"""),
        what="duplicated keys")
    add("respondent TUCASEID is unique",
        _scalar(conn, """SELECT COUNT(*) FROM (SELECT 1 FROM raw_respondent
                         GROUP BY TUCASEID HAVING COUNT(*) > 1)"""),
        what="duplicated cases")
    add("every respondent has roster rows",
        _scalar(conn, """SELECT COUNT(*) FROM raw_respondent r WHERE NOT EXISTS
                         (SELECT 1 FROM raw_roster m WHERE m.TUCASEID = r.TUCASEID)"""),
        what="respondents with no roster")
    add("every roster case has a respondent",
        _scalar(conn, """SELECT COUNT(DISTINCT TUCASEID) FROM raw_roster m WHERE NOT EXISTS
                         (SELECT 1 FROM raw_respondent r WHERE r.TUCASEID = m.TUCASEID)"""),
        what="roster cases with no respondent")

    # --- Value-level checks ---
    add("no missing values in key analytic columns",
        _scalar(conn, """SELECT COUNT(*) FROM raw_roster WHERE TEAGE IS NULL OR TESEX IS NULL
                         OR TERRP IS NULL OR TULINENO IS NULL"""))
    add(f"TEAGE within [{config.AGE_MIN}, {config.AGE_MAX}]",
        _scalar(conn, "SELECT COUNT(*) FROM raw_roster WHERE TEAGE < ? OR TEAGE > ?",
                config.AGE_MIN, config.AGE_MAX))
    add(f"TESEX in {config.VALID_SEX}",
        _scalar(conn, "SELECT COUNT(*) FROM raw_roster WHERE TESEX NOT IN (?, ?)",
                *config.VALID_SEX))
    add("survey weights are present and positive",
        _scalar(conn, "SELECT COUNT(*) FROM raw_respondent WHERE TUFINLWGT IS NULL OR TUFINLWGT <= 0"))
    add("TUCASEID is a 14-digit string",
        _scalar(conn, """SELECT COUNT(*) FROM raw_respondent
                         WHERE length(TUCASEID) <> 14 OR TUCASEID GLOB '*[^0-9]*'"""))

    # --- Structural expectations ---
    add(f"every household has a member aged {config.RESPONDENT_MIN_AGE}+ (the respondent)",
        _scalar(conn, f"""SELECT COUNT(*) FROM (SELECT TUCASEID FROM raw_roster
                          WHERE TERRP <> {config.NONHOUSEHOLD_CHILD_TERRP}
                          GROUP BY TUCASEID HAVING MAX(TEAGE) < {config.RESPONDENT_MIN_AGE})"""),
        what="households")
    add("household table row count == respondent count",
        abs(_scalar(conn, "SELECT COUNT(*) FROM raw_respondent")
            - _scalar(conn, "SELECT COUNT(*) FROM household")),
        what="households lost or gained in the build")
    add("household members partition into children + adults",
        _scalar(conn, "SELECT COUNT(*) FROM household WHERE n_members <> n_children + n_adults"))

    # --- Warnings (informative, not fatal) ---
    n_nonhh = _scalar(conn, f"SELECT COUNT(*) FROM raw_roster WHERE TERRP = {config.NONHOUSEHOLD_CHILD_TERRP}")
    checks.append(Check("non-household children found and excluded", n_nonhh > 0, "warning",
                        f"{n_nonhh} roster rows with TERRP={config.NONHOUSEHOLD_CHILD_TERRP}; "
                        "if 0, verify the code against the data dictionary"))
    max_line = _scalar(conn, "SELECT MAX(TULINENO) FROM raw_roster")
    checks.append(Check("max roster line number is plausible", max_line <= 30, "warning",
                        f"max TULINENO = {max_line}"))
    years = conn.execute("SELECT MIN(year), MAX(year), COUNT(DISTINCT year) FROM household").fetchone()
    checks.append(Check("years covered", True, "warning",
                        f"{years[0]}-{years[1]} ({years[2]} distinct years)"))
    return checks


def validate(conn: sqlite3.Connection, report_path: Path | None = None) -> list[Check]:
    checks = run_checks(conn)
    for c in checks:
        level = logging.INFO if c.passed else (logging.ERROR if c.severity == "error" else logging.WARNING)
        log.log(level, "[%s] %s -- %s", "PASS" if c.passed else "FAIL", c.name, c.detail)
    if report_path is not None:
        report_path.write_text(json.dumps([asdict(c) for c in checks], indent=2))
    failed = [c for c in checks if not c.passed and c.severity == "error"]
    if failed:
        raise ValidationError("; ".join(f"{c.name} ({c.detail})" for c in failed))
    return checks
