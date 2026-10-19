.PHONY: install install-dev test test-integration validate dry-run report docker-build docker-test docker-run clean lint-imports

CONFIG ?= configs/report.example.json
DATA ?= examples/rna-seq/data
OUT ?= output
VERSION := $(shell awk -F '"' '/^\[project\][[:space:]]*$$/ {project=1; next} project && /^\[/ {exit} project && /^[[:space:]]*version[[:space:]]*=/ {print $$2; exit}' pyproject.toml)
IMAGE ?= bioreport:$(VERSION)
PLATFORM ?= linux/amd64

install:
	pip install -e .

install-dev:
	pip install -e '.[rna,ai,dev]'

test:
	python -m pytest -q tests -k "not integration"

test-integration:
	RUN_REPORT_INTEGRATION=1 python -m pytest -q tests/test_integration_render.py

validate:
	python -m bioreport validate -c $(CONFIG)

dry-run:
	python -m bioreport run -c $(CONFIG) -o $(OUT) --dry-run

report:
	python -m bioreport run -c $(CONFIG) -o $(OUT)

lint-imports:
	! rg --pcre2 -n "from omics\\.(?!rna)|import omics\\.(?!rna)" omics --glob '*.py'

docker-build:
	docker build --platform $(PLATFORM) -f deploy/Dockerfile -t $(IMAGE) .

docker-test:
	docker run --rm --entrypoint python $(IMAGE) /opt/bioreport-smoke-test.py

docker-run:
	mkdir -p "$(OUT)"
	docker run --rm \
	  -v "$(abspath $(CONFIG)):/config/report.json:ro" \
	  -v "$(abspath $(DATA)):/data:ro" \
	  -v "$(abspath $(OUT)):/workspace" \
	  $(IMAGE) run -c /config/report.json -o /workspace

clean:
	rm -rf output _deploy_temp dist *.egg-info
