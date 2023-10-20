format:
	black inngest

format-check:
	black --check inngest

precommit: format-check lint test type-check

lint:
	pylint inngest

test:
	pytest inngest

type-check:
	mypy inngest
