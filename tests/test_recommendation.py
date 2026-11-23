"""Score the day-30 recommendation against the held-out truth the forecaster never saw."""
import pytest

from forecast.ltv import recommend


@pytest.fixture(scope="module")
def rec(cohorts, bt_rows):
    return recommend(cohorts, bt_rows, k=30).set_index("channel")


def actual_roas(con, row):
    (rev,) = con.execute("""select sum(revenue_180d_usd) from truth.cohort_value
                            where channel = ? and cast(date_trunc('week', install_date) as date)
                                  in (select unnest(?::date[]))""", [row.name, row.cohort_weeks]).fetchone()
    return rev / row.spend_usd


def test_day7_roas_would_pick_the_wrong_channel(rec):
    assert rec["roas_d7"].idxmax() == "rewarded_network"
    assert rec["roas_d180_forecast"].idxmin() == "rewarded_network"


def test_forecast_ranking_matches_the_truth(con, rec):
    truth = {ch: actual_roas(con, row) for ch, row in rec.iterrows()}
    assert list(rec["roas_d180_forecast"].sort_values(ascending=False).index) == \
        sorted(truth, key=truth.get, reverse=True) == ["paid_video", "paid_social", "rewarded_network"]


def test_forecasts_are_close_and_ranges_contain_the_truth(con, rec):
    for ch, row in rec.iterrows():
        actual = actual_roas(con, row)
        assert row.roas_d180_forecast == pytest.approx(actual, rel=0.15), ch
        assert row.roas_d180_low <= actual <= row.roas_d180_high, ch


def test_decisions(rec):
    assert rec.loc["rewarded_network", "decision"] == "cut"
    assert rec.loc["paid_video", "decision"] in ("scale", "hold")
