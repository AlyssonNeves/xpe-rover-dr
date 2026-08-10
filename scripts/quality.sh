#!/usr/bin/env sh
set -eu
# Keep the project quality gate independent from unrelated host pytest plugins.
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export DD_TRACE_ENABLED=false
export DD_PROFILING_ENABLED=false
export PYTHONUNBUFFERED=1
python -m compileall -q app adapters bootstrap infrastructure ports main.py
python scripts/check_python35_compatibility.py
flake8 app adapters bootstrap infrastructure ports main.py
python scripts/check_complexity.py
python -m pytest -q tests/unit/test_rest_api_server_http.py
coverage erase
coverage run -m pytest -q --ignore=tests/unit/test_rest_api_server_http.py
coverage json -o coverage.json
python scripts/check_critical_coverage.py coverage.json
