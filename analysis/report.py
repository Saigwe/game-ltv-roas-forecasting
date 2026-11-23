"""Run the backtest and the recommendation, score them against the held-out truth, write results/results.md."""
from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

from forecast.ltv import backtest, backtest_rows, load_cohorts, recommend


def true_roas(con, row) -> float:
    (rev,) = con.execute("""select sum(revenue_180d_usd) from truth.cohort_value
                            where channel = ? and cast(date_trunc('week', install_date) as date)
                                  in (select unnest(?::date[]))""", [row.channel, row.cohort_weeks]).fetchone()
    return rev / row.spend_usd


def build(db: str) -> str:
    con = duckdb.connect(db)
    c = load_cohorts(con)
    rows = backtest_rows(c)
    bt = backtest(rows)
    out = ["# Results", "", f"Synthetic data as of {c.as_of}: {len(c.meta):,} weekly channel cohorts, "
           f"{int(c.meta['installs'].sum()):,} installs. Regenerate with `make all`.", "",
           "## Backtest: forecast 180-day revenue per install from the first k days", "",
           "Only cohorts whose real 180-day value is known; each forecast uses only data that existed on its day k.", "",
           "| Channel | k | Multiplier MAPE | Curve-fit MAPE | Multiplier bias | Cohorts |", "|---|---|---|---|---|---|"]
    for (ch, k), g in bt.groupby(["channel", "k"]):
        m = g.set_index("method")
        out.append(f"| {ch} | {k} | {m.loc['multiplier', 'mape']:.1%} | {m.loc['curve_fit', 'mape']:.1%} | "
                   f"{m.loc['multiplier', 'bias']:+.1%} | {int(m.loc['multiplier', 'cohorts'])} |")
    out += ["", "A power law fitted to a cohort's own first days overshoots badly: revenue climbs fastest in the first days, "
            "so the fitted curve keeps climbing long after real players have left. Learning the growth from older cohorts of the same channel is far more accurate, so "
            "the recommendation uses the multiplier method.", ""]
    for k in (14, 30):
        r = recommend(c, rows, k)
        out += [f"## Recommendation from day {k}", "",
                "| Channel | Spend | CPI | D7 ROAS | D180 ROAS forecast | 90% range | Actual D180 ROAS | Payback day | Decision |",
                "|---|---|---|---|---|---|---|---|---|"]
        for row in r.itertuples():
            pay = "after 180" if row.payback_day is None or row.payback_day != row.payback_day else int(row.payback_day)
            out.append(f"| {row.channel} | ${row.spend_usd:,.0f} | ${row.cpi_usd:.2f} | {row.roas_d7:.2f} | "
                       f"{row.roas_d180_forecast:.2f} | {row.roas_d180_low:.2f} to {row.roas_d180_high:.2f} | "
                       f"{true_roas(con, row):.2f} | {pay} | **{row.decision}** |")
        out.append("")
    out += ["## What this shows", "",
            "- **Day-7 ROAS picks the wrong channel.** rewarded_network has by far the best day-7 ROAS and the worst "
            "180-day ROAS: its players earn quickly from ads and then leave. paid_video is the slowest starter and "
            "the only channel that pays back.",
            "- **Day 14 is too early for a slow-burn channel.** From day 14 the paid_video range does not quite reach "
            "its actual ROAS; from day 30 every range contains the actual value.",
            "- **Decisions use the low and high ends, not the point forecast.** A channel is scaled only when even "
            "the low end pays back, and cut only when even the high end does not.", ""]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="warehouse/ua.duckdb")
    ap.add_argument("--out", default="results/results.md")
    a = ap.parse_args()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(build(a.db), encoding="utf-8")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
