#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Adapter exposing monitored heading state through a non-blocking port."""

import time

from ports.heading_query_port import HeadingQueryPort


class HeadingStateQueryAdapter(HeadingQueryPort):
    """Returns only recent cached samples; it never reads sensor hardware."""

    def __init__(self, state_store, max_age_seconds=0.1, clock=None):
        self._state_store = state_store
        self._max_age_seconds = max(0.001, float(max_age_seconds))
        self._clock = clock or time.monotonic

    def get_heading_deg(self):
        available, heading_deg, sample_time = self._state_store.get_sample()
        if not available or sample_time is None:
            return None
        age_seconds = max(0.0, self._clock() - float(sample_time))
        if age_seconds > self._max_age_seconds:
            return None
        return heading_deg

    def get_heading_snapshot(self):
        snapshot = self._state_store.get_snapshot()
        sample_time = snapshot.get("sample_monotonic")
        age_seconds = None
        fresh = False
        if sample_time is not None:
            age_seconds = max(0.0, self._clock() - float(sample_time))
            fresh = (
                bool(snapshot.get("available")) and
                age_seconds <= self._max_age_seconds
            )
        snapshot["age_seconds"] = age_seconds
        snapshot["fresh"] = fresh
        return snapshot
