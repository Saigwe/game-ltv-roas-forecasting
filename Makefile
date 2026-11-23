PY ?= python
DB ?= warehouse/ua.duckdb

.PHONY: all data report test clean

all: data report

data:
	$(PY) generator/simulate_cohorts.py --db $(DB)

report:
	$(PY) -m analysis.report --db $(DB) --out results/results.md

test:
	$(PY) -m pytest -q

clean:
	rm -rf warehouse
