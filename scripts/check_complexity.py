#!/usr/bin/env python3
"""Fail when cyclomatic complexity exceeds the accepted project ceiling."""
import json
import subprocess
import sys

MAX_COMPLEXITY = 25
PATHS = ["app", "adapters", "bootstrap", "infrastructure", "ports", "main.py"]


def main():
    output = subprocess.check_output(["radon", "cc", "-j"] + PATHS)
    report = json.loads(output.decode("utf-8"))
    violations = []
    for filename, blocks in report.items():
        for block in blocks:
            complexity = block.get("complexity", 0)
            if complexity > MAX_COMPLEXITY:
                violations.append((filename, block["lineno"], block["name"], complexity))
    for filename, line, name, complexity in violations:
        print("{}:{} {} complexity={} (max={})".format(
            filename, line, name, complexity, MAX_COMPLEXITY
        ))
    if violations:
        return 1
    print("Complexity check passed (maximum {}).".format(MAX_COMPLEXITY))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
