#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Checks production syntax using the Python 3.5 grammar when available."""

import ast
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATHS = ("app", "adapters", "bootstrap", "infrastructure", "ports")


def production_files():
    for relative in PATHS:
        base = os.path.join(ROOT, relative)
        for root, _dirs, files in os.walk(base):
            for filename in files:
                if filename.endswith(".py"):
                    yield os.path.join(root, filename)
    yield os.path.join(ROOT, "main.py")


def main():
    for path in production_files():
        with open(path, "r") as source:
            text = source.read()
        try:
            ast.parse(text, filename=path, feature_version=(3, 5))
        except TypeError:
            # Python versions without feature_version still perform a syntax pass.
            ast.parse(text, filename=path)
        except SyntaxError as error:
            print("Python 3.5 syntax error in {0}: {1}".format(path, error))
            return 1
    print("Python 3.5 production syntax check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
