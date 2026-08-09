#!/usr/bin/env sh
set -eu
python -m compileall -q app adapters services ports main.py
flake8 app adapters services ports main.py
python scripts/check_complexity.py
coverage erase
coverage run -m pytest
coverage report --fail-under=60 -m
coverage xml
