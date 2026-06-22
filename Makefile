.PHONY: install-dev lint typecheck test package package-smoke verify benchmark benchmark-json

install-dev:
	python -m pip install -e . build pytest pytest-cov mypy ruff twine types-Pygments

lint:
	ruff check src tests benchmarks

typecheck:
	mypy src/pymini

test:
	PYTHONPATH=src pytest -q

package:
	python -m build
	twine check dist/*

package-smoke: package
	@tmp_dir="$$(mktemp -d)"; \
	trap 'rm -rf "$$tmp_dir"' EXIT; \
	python -m venv "$$tmp_dir"; \
	"$$tmp_dir/bin/python" -m pip install --quiet dist/*.whl; \
	"$$tmp_dir/bin/pymini" -c "1 + 2" | grep -qx "3"; \
	"$$tmp_dir/bin/python" -c "import pymini; assert pymini.__version__ == '0.1.0'"

verify: lint typecheck test package-smoke

benchmark:
	PYTHONPATH=src python benchmarks/bench_basic.py

benchmark-json:
	PYTHONPATH=src python benchmarks/bench_basic.py --json
