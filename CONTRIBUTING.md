# Contributing

Use Python 3.10 through 3.13 for compatibility work. Create an isolated environment, install test and demo dependencies, then run the checks below.

```bash
python3 -m venv .venv
.venv/bin/python3 -m pip install -e '.[test,demo]'
.venv/bin/python3 -m compileall -q agentload examples tests
AGENTLOAD_REQUIRE_E2E=1 .venv/bin/pytest -q -rs
```

The end-to-end test starts a local Uvicorn process. It must execute in CI. A managed local sandbox may skip it only when loopback listener creation is denied with `EPERM` or `EACCES`.

Keep traces free of prompts, response bodies, authorization headers, environment values, and credentials. Use sanitized fixtures in issues and tests. Do not commit `dist/`, generated results, virtual environments, or secrets.

Before opening a pull request, run `git diff --check`, explain the observable behavior changed, and update tests and documentation when public behavior changes.
