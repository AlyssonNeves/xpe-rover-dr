#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Deterministic collection helpers compatible with Python 3.5."""


def unique_preserving_order(values):
    """Returns unique values without relying on dictionary insertion order."""
    result = []
    seen = set()
    for value in values or ():
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)
