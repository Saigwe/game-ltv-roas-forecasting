"""Synthetic user-acquisition cohorts for a free-to-play mobile game.

Every number is invented. Each day, each channel brings a cohort of installs at a cost per install (CPI). Each player
has a lifetime, an ad value per active day and, for a few, a purchase habit. The warehouse only ever sees what had
happened by the as-of date; the full 180-day value of every cohort is kept apart, in `truth`, so tests can score
the forecasts.

Planted trap: rewarded_network players are cheap and earn quickly from ads, so that channel has the best day-7 ROAS,
but they churn within days. paid_video players start slowly and keep paying. Ranking channels on day-7 ROAS picks
the wrong one.

Usage: python generator/simulate_cohorts.py --db warehouse/ua.duckdb --scale 1.0 --seed 7
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

START = date(2025, 1, 6)
DAYS = 560               # cohorts installed over 80 weeks
AS_OF = START + timedelta(days=DAYS - 1)
HORIZON = 180            # LTV horizon: revenue on days 0..179 after install

CHANNELS = {
    # installs/day, CPI USD, lifetime Weibull shape & scale (days), daily active prob,
    # ad USD per active day, payer share, purchase prob per payer active day, mean purchase USD, payer ramp (days)
    "organic":          dict(installs=220, cpi=0.00, k=0.65, scale=40, active=0.55, ad=0.020, payer=0.070,
                             buy=0.10, price=9.0, ramp=10),
    "paid_social":      dict(installs=160, cpi=2.40, k=0.65, scale=35, active=0.55, ad=0.020, payer=0.070,
                             buy=0.10, price=9.0, ramp=10),
    "paid_video":       dict(installs=110, cpi=3.10, k=0.75, scale=70, active=0.60, ad=0.015, payer=0.080,
                             buy=0.11, price=10.0, ramp=25),
    "rewarded_network": dict(installs=180, cpi=0.90, k=0.55, scale=4, active=0.50, ad=0.110, payer=0.006,
                             buy=0.08, price=5.0, ramp=10),
}


def simulate(scale: float = 1.0, seed: int = 7) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    installs_rows, rev_rows, truth_rows = [], [], []
    days = np.arange(HORIZON)
    for d in range(DAYS):
        install_date = START + timedelta(days=d)
        observed = min(HORIZON, (AS_OF - install_date).days + 1)
        weekly = 1.0 + 0.15 * np.sin(2 * np.pi * d / 7)          # weekend install peaks
        for ch, p in CHANNELS.items():
            n = max(20, rng.poisson(p["installs"] * scale * weekly))
            spend = round(n * p["cpi"] * rng.lognormal(0, 0.08), 2)
            life = p["scale"] * rng.weibull(p["k"], n) + 1             # day-0 always active
            payer = rng.random(n) < p["payer"]
            alive = days[None, :] < life[:, None]
            active = alive & (rng.random((n, HORIZON)) < p["active"])
            active[:, 0] = True
            ad = active * p["ad"] * rng.lognormal(0, 0.3, (n, HORIZON))
            ramp = np.minimum(1.0, (days + 1) / p["ramp"])[None, :]     # payers buy more once they are invested
            buys = active & payer[:, None] & (rng.random((n, HORIZON)) < p["buy"] * ramp)
            iap = buys * rng.lognormal(np.log(p["price"]) - 0.18, 0.6, (n, HORIZON))
            rev = (ad + iap).sum(axis=0)
            act = active.sum(axis=0)
            installs_rows.append((install_date, ch, n, spend))
            truth_rows.append((install_date, ch, float(rev.sum()), float(rev[:7].sum())))
            for day_n in range(observed):
                rev_rows.append((install_date, ch, day_n, int(act[day_n]), round(float(rev[day_n]), 4)))
    return {
        "installs": pd.DataFrame(installs_rows, columns=["install_date", "channel", "installs", "spend_usd"]),
        "cohort_days": pd.DataFrame(rev_rows, columns=["install_date", "channel", "day_n", "active_users",
                                                       "revenue_usd"]),
        "truth": pd.DataFrame(truth_rows, columns=["install_date", "channel", "revenue_180d_usd", "revenue_7d_usd"]),
    }


def load(db_path: str | Path, tables: dict[str, pd.DataFrame]) -> dict[str, int]:
    """raw.* is what a warehouse would hold on the as-of date. truth.* exists only for scoring."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(db_path)) as con:
        con.execute("create schema if not exists raw; create schema if not exists truth")
        for name, df in tables.items():
            schema = "truth" if name == "truth" else "raw"
            con.register("df", df)
            con.execute(f"create or replace table {schema}.{name if name != 'truth' else 'cohort_value'} "
                        f"as select * from df")
            con.unregister("df")
        return {n: len(df) for n, df in tables.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="warehouse/ua.duckdb")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    print(json.dumps(load(a.db, simulate(a.scale, a.seed))))


if __name__ == "__main__":
    main()
