#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Thread-safe state store for the latest gyro heading sample."""

import threading


class HeadingStateStore(object):
    """Stores one immutable-by-copy heading snapshot."""

    def __init__(self):
        self._lock = threading.Lock()
        self._snapshot = {
            "available": False,
            "heading_deg": None,
            "sample_monotonic": None,
            "sensor_code": None,
            "address": None,
            "mode": None,
            "error": None
        }

    def update(self, heading_deg, sample_monotonic, sensor_code=None,
               address=None, mode=None):
        """Publishes one successful physical gyro sample."""
        with self._lock:
            self._snapshot = {
                "available": True,
                "heading_deg": float(heading_deg),
                "sample_monotonic": float(sample_monotonic),
                "sensor_code": sensor_code,
                "address": address,
                "mode": mode,
                "error": None
            }

    def mark_unavailable(self, error=None, sample_monotonic=None,
                         sensor_code=None, address=None, mode=None):
        """Publishes an unavailable state without retaining stale validity."""
        with self._lock:
            previous = self._snapshot
            self._snapshot = {
                "available": False,
                "heading_deg": previous.get("heading_deg"),
                "sample_monotonic": sample_monotonic,
                "sensor_code": sensor_code or previous.get("sensor_code"),
                "address": address or previous.get("address"),
                "mode": mode or previous.get("mode"),
                "error": str(error) if error is not None else None
            }

    def get_sample(self):
        """Returns the minimal immutable tuple used by the control loop."""
        with self._lock:
            snapshot = self._snapshot
            return (
                bool(snapshot.get("available")),
                snapshot.get("heading_deg"),
                snapshot.get("sample_monotonic")
            )

    def get_snapshot(self):
        """Returns a defensive copy of the current heading state."""
        with self._lock:
            return dict(self._snapshot)
