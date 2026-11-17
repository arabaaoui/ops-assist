# Contributing

Use fictional data, preserve provider configuration and the read-only security boundary, and discuss changes with the maintainers. Do not add credentials or private incident data. Keep tests offline and avoid real model and embedding calls in tests.

With dependencies already installed, run:

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
OPS_ASSIST_TEST_ASYNC_TICK=1 .venv/bin/pytest -q
```

Explain behavior changes and their limits, update documentation, and add focused regression coverage. See [SECURITY.md](SECURITY.md) for vulnerability reports.
