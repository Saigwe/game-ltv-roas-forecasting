"""Early LTV forecasts for acquisition cohorts, a leakage-free backtest, and a spend recommendation per channel.

Two forecasting methods, both from the first k days of a cohort:
- multiplier: the cohort's cumulative revenue per install at day k, times how much cohorts of the same channel grew
  from day k to day 180. Only cohorts already 180 days old on the forecast date are used, so nothing leaks.
- curve fit: a power law fitted to the cohort's own first k days, extrapolated to day 180.
The backtest decides which to trust; it is not assumed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import duckdb
import numpy as np
import pandas as pd

HORIZON = 180
N_REFERENCE = 8          # most recent mature cohorts used to learn the day-k to day-180 multiplier
MIN_REFERENCE = 4

CURVES_SQL = """
create schema if not exists mart;
create or replace table mart.cohort_weeks as
select cast(date_trunc('week', install_date) as date) as cohort_week, channel,
       sum(installs) as installs, sum(spend_usd) as spend_usd, max(install_date) as last_install_date
from raw.installs
group by all;

-- Weekly cohorts. A day is kept only once every install in the week has reached it, so partial days never
-- make a young cohort look worse.
create or replace table mart.cohort_curves as
with as_of as (select max(install_date) as d from raw.installs),
daily as (
    select cast(date_trunc('week', install_date) as date) as cohort_week, channel, day_n,
           sum(revenue_usd) as revenue_usd, sum(active_users) as active_users
    from raw.cohort_days
    group by all
)
select w.cohort_week, w.channel, w.installs, w.spend_usd, w.last_install_date, d.day_n,
       d.active_users / w.installs as retention,
       sum(d.revenue_usd) over (partition by w.cohort_week, w.channel order by d.day_n) / w.installs
           as cum_arpu_usd
from mart.cohort_weeks w
join daily d using (cohort_week, channel)
cross join as_of
where w.last_install_date + cast(d.day_n as integer) <= as_of.d;
"""


@dataclass
class Cohorts:
    meta: pd.DataFrame            # one row per (cohort_week, channel)
    cum: pd.DataFrame             # cumulative ARPU, columns 0..179, NaN where not yet observed
    as_of: date

    def observed_days(self) -> pd.Series:
        return self.cum.notna().sum(axis=1)


def load_cohorts(con: duckdb.DuckDBPyConnection) -> Cohorts:
    con.execute(CURVES_SQL)
    meta = con.execute("select * from mart.cohort_weeks order by channel, cohort_week").df()
    meta["last_install_date"] = pd.to_datetime(meta["last_install_date"]).dt.date
    meta = meta.set_index(["cohort_week", "channel"])
    long = con.execute("select cohort_week, channel, day_n, cum_arpu_usd from mart.cohort_curves").df()
    cum = long.pivot_table(index=["cohort_week", "channel"], columns="day_n", values="cum_arpu_usd")
    cum = cum.reindex(index=meta.index, columns=range(HORIZON))
    (as_of,) = con.execute("select max(install_date) from raw.installs").fetchone()
    return Cohorts(meta, cum, as_of)


def reference_cohorts(c: Cohorts, channel: str, known_on: date) -> list:
    """Cohorts of the channel that were already 180 days old on `known_on`: the only ones a forecaster had."""
    m = c.meta.xs(channel, level="channel")
    mature = m[[d + timedelta(days=HORIZON - 1) <= known_on for d in m["last_install_date"]]]
    return [(w, channel) for w in mature.index[-N_REFERENCE:]]


def multiplier_curve(c: Cohorts, refs: list, k: int) -> np.ndarray:
    """Median growth of cumulative ARPU from day k-1 to every later day, across reference cohorts."""
    ref = c.cum.loc[refs].to_numpy()
    return np.median(ref / ref[:, [k - 1]], axis=0)


def forecast_multiplier(c: Cohorts, key: tuple, k: int):
    """Forecast the cumulative ARPU curve to day 180 from the first k days, or None without enough history."""
    known_on = c.meta.loc[key, "last_install_date"] + timedelta(days=k - 1)
    refs = reference_cohorts(c, key[1], known_on)
    if len(refs) < MIN_REFERENCE:
        return None
    return c.cum.loc[key, k - 1] * multiplier_curve(c, refs, k)


def forecast_curve_fit(c: Cohorts, key: tuple, k: int) -> float:
    """Power law cum_arpu(d) = a * (d + 1)^b fitted on days 0..k-1, read at day 179."""
    y = c.cum.loc[key, : k - 1].to_numpy()
    x = np.log(np.arange(1, k + 1))
    b, log_a = np.polyfit(x, np.log(y), 1)
    return float(np.exp(log_a) * HORIZON ** b)


def backtest_rows(c: Cohorts, ks=(7, 14, 30)) -> pd.DataFrame:
    """Score both methods on cohorts whose real 180-day value is known, using only what was known at day k."""
    rows = []
    complete = c.observed_days() == HORIZON
    for key in c.cum.index[complete]:
        if key[1] == "organic":
            continue
        actual = c.cum.loc[key, HORIZON - 1]
        for k in ks:
            curve = forecast_multiplier(c, key, k)
            if curve is None:
                continue
            for method, pred in (("multiplier", curve[-1]), ("curve_fit", forecast_curve_fit(c, key, k))):
                rows.append((key[0], key[1], k, method, pred, actual))
    df = pd.DataFrame(rows, columns=["cohort_week", "channel", "k", "method", "pred", "actual"])
    df["error"] = (df["pred"] - df["actual"]) / df["actual"]
    return df


def backtest(rows: pd.DataFrame) -> pd.DataFrame:
    return (rows.assign(ape=rows["error"].abs())
                .groupby(["channel", "k", "method"])
                .agg(cohorts=("ape", "size"), mape=("ape", "mean"), bias=("error", "mean"),
                     p90_abs_error=("ape", lambda s: s.quantile(0.9)))
                .reset_index())


def recommend(c: Cohorts, bt_rows: pd.DataFrame, k: int = 30, recent: int = 8) -> pd.DataFrame:
    """Forecast 180-day ROAS of each paid channel's newest cohorts that have k days of data, and decide.

    The interval comes from the backtest: the 5th to 95th percentile of the multiplier method's errors for this
    channel at this k, applied to the forecast. Per-cohort errors are wider than the error on eight cohorts pooled,
    so the interval is deliberately conservative.
    """
    rows = []
    days_seen = c.observed_days()
    for ch in sorted(c.meta.index.get_level_values("channel").unique()):
        if ch == "organic":
            continue
        keys = [kk for kk in c.cum.index if kk[1] == ch and k <= days_seen[kk] < HORIZON][-recent:]
        spend = c.meta.loc[keys, "spend_usd"].sum()
        installs = c.meta.loc[keys, "installs"].to_numpy()
        rev_curve = sum(forecast_multiplier(c, kk, k) * n for kk, n in zip(keys, installs))
        roas7 = sum(c.cum.loc[kk, 6] * n for kk, n in zip(keys, installs)) / spend
        roas = rev_curve[-1] / spend
        err = bt_rows.query("channel == @ch and k == @k and method == 'multiplier'")["error"]
        e_lo, e_hi = err.quantile([0.05, 0.95])
        lo, hi = roas / (1 + e_hi), roas / (1 + e_lo)
        paid_back = np.nonzero(rev_curve >= spend)[0]
        decision = "scale" if lo > 1 else "cut" if hi < 1 else "hold"
        rows.append(dict(channel=ch, cohorts=len(keys), installs=int(installs.sum()), spend_usd=round(spend, 2),
                         cpi_usd=round(spend / installs.sum(), 2), roas_d7=round(roas7, 3),
                         roas_d180_forecast=round(roas, 3), roas_d180_low=round(lo, 3), roas_d180_high=round(hi, 3),
                         payback_day=int(paid_back[0]) if len(paid_back) else None, decision=decision,
                         cohort_weeks=[str(kk[0]) for kk in keys]))
    return pd.DataFrame(rows)
