#!/usr/bin/env python3
"""Parse production source using the Python 3.5 grammar accepted by EV3."""

import ast
import sys
from pathlib import Path


PATHS = ("app", "adapters", "bootstrap", "infrastructure", "ports", "main.py")


def production_files():
    for name in PATHS:
        path = Path(name)
        if path.is_file():
            yield path
        else:
            for source_path in sorted(path.rglob("*.py")):
                yield source_path


def main():
    failures = []
    for source_path in production_files():
        try:
            ast.parse(
                source_path.read_text(),
                filename=str(source_path),
                feature_version=(3, 5)
            )
        except SyntaxError as error:
            failures.append((source_path, error.lineno, error.msg))
    for source_path, line_number, message in failures:
        print("{}:{} {}".format(source_path, line_number, message))
    if failures:
        return 1
    print("Python 3.5 syntax compatibility check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
