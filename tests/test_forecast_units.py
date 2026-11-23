from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from forecast.ltv import HORIZON, Cohorts, forecast_curve_fit, multiplier_curve, reference_cohorts


def toy(curves: dict, last_install: dict, as_of: date) -> Cohorts:
    idx = pd.MultiIndex.from_tuples(list(curves), names=["cohort_week", "channel"])
    cum = pd.DataFrame([curves[k] for k in curves], index=idx, columns=range(HORIZON))
    meta = pd.DataFrame({"installs": 100, "spend_usd": 100.0,
                         "last_install_date": [last_install[k] for k in curves]}, index=idx)
    return Cohorts(meta, cum, as_of)


def test_curve_fit_recovers_an_exact_power_law():
    d = np.arange(1, HORIZON + 1)
    key = (date(2025, 1, 6), "x")
    c = toy({key: 0.2 * d ** 0.45}, {key: date(2025, 1, 12)}, date(2026, 1, 1))
    assert forecast_curve_fit(c, key, 14) == pytest.approx(0.2 * HORIZON ** 0.45, rel=1e-9)


def test_reference_cohorts_never_leak_the_future():
    weeks = [date(2025, 1, 6) + timedelta(weeks=i) for i in range(40)]
    curves = {(w, "x"): np.linspace(1, 2, HORIZON) for w in weeks}
    c = toy(curves, {k: k[0] + timedelta(days=6) for k in curves}, date(2026, 1, 1))
    known_on = date(2025, 9, 1)
    refs = reference_cohorts(c, "x", known_on)
    assert refs, "expected some mature cohorts"
    for w, _ in refs:
        assert w + timedelta(days=6) + timedelta(days=HORIZON - 1) <= known_on


def test_multiplier_is_one_at_day_k_and_grows():
    key = (date(2025, 1, 6), "x")
    c = toy({key: np.linspace(1, 3, HORIZON)}, {key: date(2025, 1, 12)}, date(2026, 1, 1))
    m = multiplier_curve(c, [key], 14)
    assert m[13] == pytest.approx(1.0) and m[-1] == pytest.approx(3 / (1 + 2 * 13 / (HORIZON - 1)))
