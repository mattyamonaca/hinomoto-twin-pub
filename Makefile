PYTHON ?= python3

.PHONY: help install install-source fetch prepare build verify sample dataset paths site test
help:
	@echo "install        Install model dependencies"
	@echo "install-source Install source parsing dependencies"
	@echo "fetch          Download missing originals and parse source data"
	@echo "prepare        Parse originals already present in raw/ (offline)"
	@echo "dataset        Import the pinned baseline data into the external data workspace"
	@echo "paths          Show resolved input/output paths"
	@echo "build          Rebuild distributions from the configured normalized sources"
	@echo "verify         Verify rebuilt data and probability constraints"
	@echo "sample         Sample 10 synthetic residents of Minato aged 35-39"
	@echo "sensitivity    Re-allocate education x income under alternative assumptions"
	@echo "fetch-industry Download and normalize the industry tables used by M2 (raw/industry, sources/industry)"
	@echo "fetch-employment  Fetch/normalize stage-A employment tables (ESS 10-1, 04000 by status)"
	@echo "build-employment  Allocate employment status x industry conditional on the production model"
	@echo "verify-employment Verify margins and evaluate on held-out city tables"
	@echo "fetch-household  Fetch/normalize census household tables for stage B"
	@echo "build-household  Generate household compositions for selected municipalities (stage B, experimental)"
	@echo "fetch-workplace  Fetch/normalize census commuting OD/ODI tables for stage C (142 workbooks, about 400 MB)"
	@echo "build-workplace  Fit residence x workplace x industry for all municipalities (stage C, experimental)"
	@echo "verify-workplace Check margins and evaluate on the held-out ODI tables"
	@echo "experiment     Compare M0 with M1/M2 (education-composition income re-estimation) on held-out cities"
	@echo "synthetic      Recovery experiment on virtual populations with known joint distributions"
	@echo "site           Assemble UI code and the configured web dataset into dist/site"
	@echo "test           Run storage/data-contract tests without the national dataset"
install:
	$(PYTHON) -m pip install -r requirements.txt
install-source:
	$(PYTHON) -m pip install -r requirements-source.txt
fetch:
	$(PYTHON) src/pipeline.py fetch
prepare:
	$(PYTHON) src/pipeline.py prepare
build:
	$(PYTHON) src/pipeline.py build
verify:
	$(PYTHON) src/pipeline.py verify
sample:
	$(PYTHON) src/persona_v2.py --municipality 13103 --age 35 --sample 10 --seed 7

.PHONY: build-education verify-education sensitivity
build-education:
	$(PYTHON) src/pipeline.py build-education
verify-education:
	$(PYTHON) src/pipeline.py verify-education
sensitivity:
	$(PYTHON) src/pipeline.py sensitivity
dataset:
	$(PYTHON) src/dataset.py fetch-production
paths:
	$(PYTHON) src/pipeline.py paths
site:
	$(PYTHON) src/build_site.py
test:
	$(PYTHON) -m unittest discover -s tests -v

fetch-industry:
	$(PYTHON) src/pipeline.py fetch-industry
experiment:
	$(PYTHON) src/pipeline.py experiment
synthetic:
	$(PYTHON) src/pipeline.py synthetic

.PHONY: fetch-workplace build-workplace verify-workplace
fetch-workplace:
	$(PYTHON) src/pipeline.py fetch-workplace
build-workplace:
	$(PYTHON) src/pipeline.py build-workplace
verify-workplace:
	$(PYTHON) src/pipeline.py verify-workplace
