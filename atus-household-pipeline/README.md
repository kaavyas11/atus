# ATUS Household Composition: ETL + Analysis

**Code sample cover page.** This project turns a course exercise (DS340 HW2, originally written against a
~3,000-household subset using the `csv` module) into a reproducible pipeline over the full American Time Use
Survey (ATUS) multi-year files, 2003-2025. It answers: *How large are U.S. households, how often do they include
children, how many have a single adult, and what share of those adults are women?*

It is meant to show, in one small repo: data acquisition, SQL-based transformation, explicit data-reliability
checks, weighted estimation with quantified uncertainty, honest statement of limitations, tests, and containerised
reproducibility.

## Pipeline

```
BLS zip files ──extract──► raw_roster, raw_respondent (SQLite) ──SQL──► household ──validate──► analyze ──► outputs/
```

| Stage | Where | What it does |
|---|---|---|
| Extract | `atus_pipeline/extract.py` | Cached, atomic download from BLS; reads the CSV-format `.dat` inside each zip; `TUCASEID` kept as text |
| Load / Transform | `atus_pipeline/load.py`, `sql/household.sql` | Raw tables are loaded untouched; household composition is derived in SQL |
| Validate | `atus_pipeline/validate.py` | 12 SQL checks (key uniqueness, referential integrity, value ranges, weights, structural expectations). Errors halt the run; a JSON report is written |
| Analyze | `atus_pipeline/analyze.py` | Survey-weighted ratio estimates, 95% bootstrap CIs, by-year trends, figure |
| Provenance | `outputs/run_manifest.json` | Input file SHA-256s, parameters, row counts, warnings |

## Run it

```bash
pip install -r requirements.txt
python -m atus_pipeline                       # downloads ~ a few MB of BLS files, runs everything
python -m unittest discover -s tests -t .     # or: python -m pytest

# or with Docker
docker build -t atus . && docker run --rm -v "$PWD/outputs:/app/outputs" atus
```

Useful flags: `--roster-zip/--resp-zip` (use local files), `--child-max-age 17`, `--bootstraps 500`, `--seed 0`.
Outputs: `estimates.csv`, `estimates_by_year.csv`, `household_trends.png`, `validation_report.json`, `run_manifest.json`.

## Methodological choices (and what changed from the homework)

1. **Non-household children are excluded.** The ATUS roster lists household members *and* the respondent's own
   non-household children under 18 (`TERRP = 40`). Counting them inflates household size and child presence.
   The original notebook did not separate them.
2. **One explicit age threshold.** The notebook treated age <= 18 as "child" and > 18 as "adult", so 18-year-olds
   counted as children. The threshold is now a single parameter, defaulting to child <= 17 (18-year-olds are adults).
   Every member is exactly one of the two; change it with `--child-max-age 18` to reproduce the old definition.
3. **Survey weights.** Unweighted shares describe the sample, not the population. Estimates use the respondent's
   `TUFINLWGT`, normalised within year so each year counts equally in pooled results. Unweighted values are kept
   in the output for comparison.
4. **Uncertainty.** Every estimate has a 95% percentile bootstrap CI (resampling households).

## Limitations

- **Weights describe people, not households.** ATUS samples one person (15+) per household, so "share of
  households with a child" is really "share of people 15+ who live in a household with a child."
- **Bootstrap is an approximation.** It ignores ATUS's stratified design and weight calibration. BLS publishes replicate
  weights for design-based variance estimation; swapping them in is the natural next step.
- **Disrupted collection years.** 2020 (COVID-19) and late 2025 (federal shutdown) have atypical sampling; BLS
  notices describe the effect. Treat those years' point estimates with caution.
- **The `TERRP = 40` code should be confirmed** against the data dictionary for the file vintage used (a validation
  warning fires if no such rows are found).
- Source file names follow BLS's multi-year pattern (`atusrost-0325.zip`, `atusresp-0325.zip`); if BLS changes
  them, edit `YEAR_SPAN` in `config.py`.

## Layout

```
atus_pipeline/  config.py extract.py load.py validate.py analyze.py cli.py sql/household.sql
tests/          synthetic fixture with hand-computed expected values
Dockerfile  requirements.txt
```
