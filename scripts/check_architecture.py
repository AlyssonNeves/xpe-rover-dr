#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Static dependency-direction checks for the Rover hexagonal architecture."""

import ast
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def imports(path):
    with open(path, "r") as source:
        tree = ast.parse(source.read(), filename=path)
    result = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.append(node.module)
    return result


def python_files(directory):
    for root, _dirs, files in os.walk(os.path.join(ROOT, directory)):
        for filename in files:
            if filename.endswith(".py"):
                yield os.path.join(root, filename)


def main():
    violations = []
    for path in python_files("app"):
        for name in imports(path):
            if name.startswith("adapters") or name.startswith("infrastructure"):
                violations.append((path, name))
    for path in python_files("ports"):
        for name in imports(path):
            if name.startswith(("app", "adapters", "infrastructure")):
                violations.append((path, name))
    if os.path.isdir(os.path.join(ROOT, "services")):
        violations.append(("services", "legacy package must be removed"))
    for path, name in violations:
        print("Architecture violation: {0} -> {1}".format(path, name))
    if violations:
        return 1
    print("Architecture dependency check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
