.PHONY: install lint typecheck test demo benchmark
install:
	python -m pip install -e ".[dev]"
lint:
	ruff check src tests benchmarks
typecheck:
	mypy src/marketstream --follow-imports=silent
test:
	python -m pytest -q --cov=marketstream --cov-report=term-missing
demo:
	marketstream run -c configs/demo.yaml
benchmark:
	python benchmarks/benchmark_pipeline.py --sizes 10000 100000
