#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Thread-safe cache for the latest heading sample."""

import threading


class HeadingStateStore(object):
    """Stores one immutable-by-copy heading snapshot for control consumers."""

    def __init__(self):
        self._lock = threading.Lock()
        self._snapshot = {
            "available": False,
            "heading_deg": None,
            "sample_monotonic": None,
            "error": None
        }

    def update(self, heading_deg, sample_monotonic):
        """Publishes one successful heading sample."""
        with self._lock:
            self._snapshot = {
                "available": True,
                "heading_deg": float(heading_deg),
                "sample_monotonic": float(sample_monotonic),
                "error": None
            }

    def mark_unavailable(self, error=None, sample_monotonic=None):
        """Marks the cache unavailable without treating old data as fresh."""
        with self._lock:
            previous = self._snapshot
            self._snapshot = {
                "available": False,
                "heading_deg": previous.get("heading_deg"),
                "sample_monotonic": sample_monotonic,
                "error": str(error) if error is not None else None
            }

    def get_sample(self):
        """Returns the minimal tuple required by the low-latency control path."""
        with self._lock:
            snapshot = self._snapshot
            return (
                bool(snapshot.get("available")),
                snapshot.get("heading_deg"),
                snapshot.get("sample_monotonic")
            )

    def get_snapshot(self):
        """Returns a defensive copy of the cached state."""
        with self._lock:
            return dict(self._snapshot)
