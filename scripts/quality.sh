#!/usr/bin/env sh
set -eu
python -m compileall -q app adapters bootstrap infrastructure ports main.py
python scripts/check_python35_compatibility.py
python scripts/check_architecture.py
flake8 app adapters bootstrap infrastructure ports main.py
python scripts/check_complexity.py
coverage erase
coverage run -m pytest
coverage report --fail-under=70 -m
coverage xml
