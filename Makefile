PYTHON ?= python3

.PHONY: help install install-source fetch prepare build verify sample
help:
	@echo "install        Install model dependencies"
	@echo "install-source Install source parsing dependencies"
	@echo "fetch          Download missing originals and parse source data"
	@echo "prepare        Parse originals already present in raw/ (offline)"
	@echo "build          Rebuild distributions from bundled normalized sources"
	@echo "verify         Verify rebuilt data and probability constraints"
	@echo "sample         Sample 10 synthetic residents of Minato aged 35-39"
install:
	$(PYTHON) -m pip install -r requirements.txt
install-source:
	$(PYTHON) -m pip install -r requirements-source.txt
fetch:
	$(PYTHON) src/download_sources.py
	$(PYTHON) src/fetch_education.py
	$(PYTHON) src/parse_education.py
prepare:
	$(PYTHON) src/parse_census.py
	$(PYTHON) src/parse_income.py
	$(PYTHON) src/parse_tax.py
	$(PYTHON) src/parse_education.py
build:
	$(PYTHON) src/build.py
	$(PYTHON) src/refine_tax.py
	$(PYTHON) src/export.py
	$(PYTHON) src/build_education.py
	$(PYTHON) src/export_education.py
verify:
	$(PYTHON) src/verify.py
	$(PYTHON) src/verify_education.py
sample:
	$(PYTHON) src/persona_v2.py --municipality 13103 --age 35 --sample 10 --seed 7

.PHONY: build-education verify-education
build-education:
	$(PYTHON) src/build_education.py
	$(PYTHON) src/export_education.py
verify-education:
	$(PYTHON) src/verify_education.py
