check-venv:
	@if [ -z "$$VIRTUAL_ENV" ]; then \
		echo "virtual environment is not activated"; \
		exit 1; \
	fi

format: check-venv
	@black inngest tests
	@isort inngest tests

format-check: check-venv
	@black --check inngest tests
	@isort --check-only inngest tests

install: check-venv
	@pip install '.[extra]' -c constraints.txt


itest: check-venv
	@pytest tests

precommit: format-check lint type-check utest

lint: check-venv
	@pylint inngest

type-check: check-venv
	@mypy inngest

utest: check-venv
	@pytest inngest
