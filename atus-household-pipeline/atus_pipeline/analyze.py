"""Weighted household-composition estimates with bootstrap uncertainty.

Every estimate is a ratio  sum(w * numerator) / sum(w * denominator)  over
households, where w is the respondent's survey weight (normalised within
year so each year contributes equally to pooled estimates). Uncertainty comes
from a nonparametric bootstrap that resamples households with replacement.

Limitation: a bootstrap over final weights ignores the ATUS's stratified
design and weight calibration. BLS publishes replicate weights (the
"atuswgts" file) for design-based variance; the bootstrap here is a transparent
approximation, so intervals should be read as indicative, not exact.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

MAX_SIZE_BUCKET = 7  # household sizes >= 7 are pooled


def read_households(conn: sqlite3.Connection) -> pd.DataFrame:
    h = pd.read_sql("SELECT * FROM household", conn)
    # Normalise weights within year: each survey year gets equal total weight.
    h["w"] = h["weight"] / h.groupby("year")["weight"].transform("sum")
    return h


def make_specs(h: pd.DataFrame) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Map estimate name -> (numerator indicator, denominator indicator)."""
    ones = np.ones(len(h))
    f = lambda s: s.to_numpy(dtype=float)  # noqa: E731
    alone = h.n_members == 1
    one_adult = h.n_adults == 1
    one_adult_with_child = one_adult & (h.n_children > 0)

    specs = {
        "share_households_with_child": (f(h.n_children > 0), ones),
        "share_one_adult_households": (f(one_adult), ones),
        "share_living_alone_who_are_women": (f(alone & (h.n_women == 1)), f(alone)),
        "share_single_adult_with_child_who_are_women":
            (f(one_adult_with_child & (h.n_adult_women == 1)), f(one_adult_with_child)),
    }
    for k in range(1, MAX_SIZE_BUCKET):
        specs[f"household_size_{k}"] = (f(h.n_members == k), ones)
    specs[f"household_size_{MAX_SIZE_BUCKET}plus"] = (f(h.n_members >= MAX_SIZE_BUCKET), ones)
    return specs


def estimate(h: pd.DataFrame, n_boot: int = 500, seed: int = 0, ci: float = 0.95) -> pd.DataFrame:
    """Point estimates (weighted and unweighted) plus bootstrap percentile CIs."""
    specs = make_specs(h)
    names = list(specs)
    w = h["w"].to_numpy()
    N = np.column_stack([w * specs[k][0] for k in names])
    D = np.column_stack([w * specs[k][1] for k in names])
    Nu = np.column_stack([specs[k][0] for k in names])
    Du = np.column_stack([specs[k][1] for k in names])

    with np.errstate(divide="ignore", invalid="ignore"):
        weighted = N.sum(0) / D.sum(0)
        unweighted = Nu.sum(0) / Du.sum(0)
        rng = np.random.default_rng(seed)
        n = len(h)
        reps = np.empty((n_boot, len(names)))
        for b in range(n_boot):
            idx = rng.integers(0, n, n)
            reps[b] = N[idx].sum(0) / D[idx].sum(0)

    alpha = (1 - ci) / 2
    lo, hi = np.nanquantile(reps, [alpha, 1 - alpha], axis=0) if n > 0 else (np.nan, np.nan)
    return pd.DataFrame({
        "estimate": names,
        "weighted": weighted,
        "ci_low": lo,
        "ci_high": hi,
        "unweighted": unweighted,
        "n_households": n,
        "n_denominator": [int((specs[k][1] > 0).sum()) for k in names],
    })


def estimate_by_year(h: pd.DataFrame, n_boot: int = 300, seed: int = 0) -> pd.DataFrame:
    parts = []
    for year, g in h.groupby("year"):
        g = g.copy()
        g["w"] = g["weight"] / g["weight"].sum()
        out = estimate(g, n_boot=n_boot, seed=seed)
        out.insert(0, "year", year)
        parts.append(out)
    return pd.concat(parts, ignore_index=True)


def plot_trends(by_year: pd.DataFrame, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    panels = [
        ("share_households_with_child", "Households with a child"),
        ("share_one_adult_households", "One-adult households"),
        ("share_single_adult_with_child_who_are_women", "Women among single-adult\nhouseholds with a child"),
    ]
    fig, axes = plt.subplots(1, len(panels), figsize=(13, 3.8), sharex=True)
    for ax, (key, title) in zip(axes, panels):
        d = by_year[by_year.estimate == key].sort_values("year")
        ax.plot(d.year, d.weighted, marker="o", ms=3.5, color="tab:blue")
        ax.fill_between(d.year, d.ci_low, d.ci_high, alpha=0.25, color="tab:blue", linewidth=0)
        ax.axvline(2020, color="gray", ls=":", lw=1)
        ax.set_title(title, fontsize=10)
        ax.set_ylabel("Weighted share")
        ax.set_xlabel("Survey year")
        ax.grid(alpha=0.3)
    fig.suptitle("ATUS household composition by year (shaded: 95% bootstrap CI; dotted: 2020, COVID-19 collection disruption)",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
