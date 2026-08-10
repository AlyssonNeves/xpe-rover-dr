#!/usr/bin/env python3
"""Fail when cyclomatic complexity exceeds the accepted project ceiling."""
import json
import subprocess
import sys

MAX_COMPLEXITY = 15
paths = ["app", "adapters", "bootstrap", "infrastructure", "ports", "main.py"]
output = subprocess.check_output(["radon", "cc", "-j"] + paths)
report = json.loads(output.decode("utf-8"))
violations = []
for filename, blocks in report.items():
    for block in blocks:
        complexity = block.get("complexity", 0)
        if complexity > MAX_COMPLEXITY:
            violations.append((filename, block["lineno"], block["name"], complexity))
for item in violations:
    print("{}:{} {} complexity={} (max={})".format(*(item + (MAX_COMPLEXITY,))))
if violations:
    sys.exit(1)
print("Complexity check passed (maximum {}).".format(MAX_COMPLEXITY))
