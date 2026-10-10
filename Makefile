.PHONY: install install-dev test test-integration validate dry-run report docker-build docker-run clean lint-imports

CONFIG ?= configs/report.example.json
OUT ?= output

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
	docker build -f deploy/Dockerfile -t bioreport:latest .

docker-run:
	docker run --rm -v "$$(pwd)/$$(dirname $(CONFIG)):/data:ro" -v "$$(pwd)/$(OUT):/workspace" bioreport:latest -c "/data/$$(basename $(CONFIG))" -o /workspace

clean:
	rm -rf output _deploy_temp dist *.egg-info
