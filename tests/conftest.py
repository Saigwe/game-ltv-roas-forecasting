import duckdb
import pytest

from forecast.ltv import backtest_rows, load_cohorts
from generator.simulate_cohorts import load, simulate


@pytest.fixture(scope="session")
def con(tmp_path_factory):
    db = tmp_path_factory.mktemp("wh") / "ua.duckdb"
    load(db, simulate(scale=1.0, seed=7))
    with duckdb.connect(str(db)) as c:
        yield c


@pytest.fixture(scope="session")
def cohorts(con):
    return load_cohorts(con)


@pytest.fixture(scope="session")
def bt_rows(cohorts):
    return backtest_rows(cohorts)
