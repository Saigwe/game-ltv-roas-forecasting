from datetime import timedelta

from forecast.ltv import HORIZON, backtest


def test_cohort_curves_only_hold_complete_days(cohorts):
    seen = cohorts.observed_days()
    for key, n in seen.items():
        possible = (cohorts.as_of - cohorts.meta.loc[key, "last_install_date"]).days + 1
        assert n == min(HORIZON, possible)


def test_cumulative_revenue_never_falls(cohorts):
    diffs = cohorts.cum.diff(axis=1).iloc[:, 1:]
    assert (diffs.fillna(0) >= -1e-12).all().all()


def test_cohort_revenue_matches_raw(con, cohorts):
    """Day-0 revenue per install in the curves equals the raw table, week by week."""
    raw = con.execute("""select cast(date_trunc('week', d.install_date) as date) w, d.channel,
                                sum(d.revenue_usd) / any_value(t.installs) arpu
                         from raw.cohort_days d
                         join (select cast(date_trunc('week', install_date) as date) w, channel, sum(installs) installs
                               from raw.installs group by all) t
                           on t.w = cast(date_trunc('week', d.install_date) as date) and t.channel = d.channel
                         where d.day_n = 0 group by all""").df().set_index(["w", "channel"])["arpu"]
    assert (cohorts.cum[0] - raw.reindex(cohorts.cum.index)).abs().max() < 1e-9


def test_backtest_uses_only_mature_cohorts_and_multiplier_wins(cohorts, bt_rows):
    for w, ch in bt_rows[["cohort_week", "channel"]].drop_duplicates().itertuples(index=False):
        assert cohorts.observed_days()[(w, ch)] == HORIZON
    bt = backtest(bt_rows).set_index(["channel", "k", "method"])
    for ch in ("paid_social", "paid_video", "rewarded_network"):
        for k in (7, 14, 30):
            assert bt.loc[(ch, k, "multiplier"), "mape"] < bt.loc[(ch, k, "curve_fit"), "mape"]
        assert bt.loc[(ch, 30, "multiplier"), "mape"] < 0.15
