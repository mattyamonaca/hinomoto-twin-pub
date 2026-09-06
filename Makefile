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
	@echo "experiment     Compare M0 with M1 (education-composition income re-estimation) on held-out cities"
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
	$(PYTHON) src/dataset.py fetch-baseline
paths:
	$(PYTHON) src/pipeline.py paths
site:
	$(PYTHON) src/build_site.py
test:
	$(PYTHON) -m unittest discover -s tests -v
