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
	@echo "synthetic-employment  Recovery of the unobserved education x status x industry x income association (stage A)"
	@echo "export-employment-web Publish stage A for the Explorer (graph.json v3, employment_inputs.bin, employment/agg_*.bin)"
	@echo "verify-web-employment jsdom check: the page reproduces the Python stage-A blocks (needs node + jsdom)"
	@echo "fetch-household  Fetch/normalize census household tables for stage B"
	@echo "build-household  Generate household compositions for selected municipalities (stage B, experimental)"
	@echo "sample-household  Integer households + linked members for the selected municipalities (stage B, Issue #23)"
	@echo "export-household-web Household summaries for the Explorer (web/household/<code>.json)"
	@echo "fetch-workplace  Fetch/normalize census commuting OD/ODI tables for stage C (142 workbooks, about 400 MB)"
	@echo "build-workplace  Fit residence x workplace x industry for all municipalities (stage C, experimental)"
	@echo "verify-workplace Check margins and evaluate on the held-out ODI tables"
	@echo "experiment     Compare M0 with M1/M2 (education-composition income re-estimation) on held-out cities"
	@echo "synthetic      Recovery experiment on virtual populations with known joint distributions"
	@echo "synthetic-m12  Same with industry: M0/M1/M2/M12 recovery under generating processes that violate the estimator assumptions (Issue #21)"
	@echo "fetch-tax-status Fetch FY2023 市町村税課税状況等の調 municipal tables (independent evaluation only)"
	@echo "validate-m12   Same-denominator comparison, coefficient sensitivity and the independent tax check for M12 (Issue #21)"
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

.PHONY: synthetic-employment export-employment-web verify-web-employment
synthetic-employment:
	$(PYTHON) src/pipeline.py synthetic-employment
export-employment-web:
	$(PYTHON) src/pipeline.py export-employment-web
verify-web-employment: site
	node tests/web_employment_check.cjs dist/site

.PHONY: fetch-employment build-employment verify-employment fetch-household build-household
fetch-employment:
	$(PYTHON) src/pipeline.py fetch-employment
build-employment:
	$(PYTHON) src/pipeline.py build-employment
verify-employment:
	$(PYTHON) src/pipeline.py verify-employment
fetch-household:
	$(PYTHON) src/pipeline.py fetch-household
build-household:
	$(PYTHON) src/pipeline.py build-household
.PHONY: fetch-workplace build-workplace verify-workplace
fetch-workplace:
	$(PYTHON) src/pipeline.py fetch-workplace
build-workplace:
	$(PYTHON) src/pipeline.py build-workplace
verify-workplace:
	$(PYTHON) src/pipeline.py verify-workplace
synthetic-m12:
	$(PYTHON) src/pipeline.py synthetic-m12
fetch-tax-status:
	$(PYTHON) src/pipeline.py fetch-tax-status
validate-m12:
	$(PYTHON) src/pipeline.py validate-m12

.PHONY: sample-household export-household-web
sample-household:
	for c in 13103 47201 01555; do $(PYTHON) src/household_sample.py --municipality $$c --population --sa --link-population --seed 1; done
export-household-web:
	$(PYTHON) src/pipeline.py export-household-web
