.PHONY: help all ingest profile audit estimate power gen clean deep-clean

PY ?= python

help:
	@echo ""
	@echo "  make ingest    download the reference experiment and load it into DuckDB"
	@echo "  make profile   capability matrix: what can this dataset actually support?"
	@echo "  make audit     design audit and covariate balance"
	@echo "  make estimate  ITT, LATE, and the exposure-bias decomposition"
	@echo "  make power     holdout size versus detectable effect"
	@echo "  make all       all of the above, in order"
	@echo ""
	@echo "  make gen       regenerate the generated SQL files"
	@echo "  make clean     drop the warehouse, keep the downloaded file"
	@echo "  make deep-clean also delete the downloaded file"
	@echo ""

all: ingest profile audit estimate power

ingest:
	$(PY) -m src.ingest.criteo_uplift

profile:
	$(PY) -m src.profile_asset bronze.criteo_uplift

audit:
	$(PY) -m src.sqlrun sql/01_design_audit.sql
	$(PY) -m src.sqlrun sql/04_covariate_balance.sql

estimate:
	$(PY) -m src.sqlrun sql/02_itt_and_late.sql
	$(PY) -m src.sqlrun sql/03_exposure_bias.sql

power:
	$(PY) -m src.power

gen:
	$(PY) scripts/gen_balance_sql.py

clean:
	rm -f data/incrementality.duckdb data/incrementality.duckdb.wal

deep-clean: clean
	rm -rf data/raw
