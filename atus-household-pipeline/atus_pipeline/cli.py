"""Command-line entry point:  python -m atus_pipeline [options]"""
from __future__ import annotations

import argparse
import json
import logging
import platform
from datetime import datetime, timezone
from pathlib import Path

from . import analyze, config, extract, load, validate

log = logging.getLogger("atus_pipeline")


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ATUS household-composition ETL + analysis.")
    p.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    p.add_argument("--db", type=Path, default=Path("data/atus.db"))
    p.add_argument("--out-dir", type=Path, default=Path("outputs"))
    p.add_argument("--roster-zip", type=Path, help="Use a local roster zip instead of downloading.")
    p.add_argument("--resp-zip", type=Path, help="Use a local respondent zip instead of downloading.")
    p.add_argument("--refresh", action="store_true", help="Re-download even if cached.")
    p.add_argument("--child-max-age", type=int, default=config.CHILD_MAX_AGE)
    p.add_argument("--bootstraps", type=int, default=500)
    p.add_argument("--seed", type=int, default=0)
    return p.parse_args(argv)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.db.parent.mkdir(parents=True, exist_ok=True)

    # 1. Extract
    roster_zip = args.roster_zip or extract.download(config.ROSTER_ZIP, args.raw_dir, args.refresh)
    resp_zip = args.resp_zip or extract.download(config.RESPONDENT_ZIP, args.raw_dir, args.refresh)
    roster = extract.read_zipped_csv(roster_zip, config.ROSTER_COLS)
    respondent = extract.read_zipped_csv(resp_zip, config.RESPONDENT_COLS)

    # 2. Load + transform (SQL)
    conn = load.connect(args.db)
    load.load_raw(conn, roster, respondent)
    n_households = load.build_household(conn, args.child_max_age)
    log.info("Built household table: %d households", n_households)

    # 3. Validate (raises on any error-level failure)
    checks = validate.validate(conn, args.out_dir / "validation_report.json")

    # 4. Analyze
    h = analyze.read_households(conn)
    overall = analyze.estimate(h, n_boot=args.bootstraps, seed=args.seed)
    by_year = analyze.estimate_by_year(h, n_boot=max(args.bootstraps // 2, 100), seed=args.seed)
    overall.to_csv(args.out_dir / "estimates.csv", index=False)
    by_year.to_csv(args.out_dir / "estimates_by_year.csv", index=False)
    analyze.plot_trends(by_year, args.out_dir / "household_trends.png")

    # 5. Provenance
    (args.out_dir / "run_manifest.json").write_text(json.dumps({
        "run_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "inputs": {p.name: extract.sha256(p) for p in (roster_zip, resp_zip)},
        "params": {"child_max_age": args.child_max_age, "bootstraps": args.bootstraps, "seed": args.seed},
        "rows": {"roster": len(roster), "respondent": len(respondent), "households": n_households},
        "warnings": [c.name + ": " + c.detail for c in checks if c.severity == "warning"],
    }, indent=2))

    print(overall.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    conn.close()
    return 0
