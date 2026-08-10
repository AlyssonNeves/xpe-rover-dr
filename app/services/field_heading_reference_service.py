#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Thread-safe operational zero reference for FIELD-centric driving."""

import threading

from ports.field_heading_reference_command_port import (
    FieldHeadingReferenceCommandPort
)
from ports.heading_query_port import HeadingQueryPort


class FieldHeadingReferenceService(
        HeadingQueryPort, FieldHeadingReferenceCommandPort):
    """Converts canonical gyro headings into an operator FIELD reference.

    The wrapped query remains the source of fresh canonical samples. Redefining
    zero changes only this in-memory reference: it never resets the physical
    gyro and never mutates the monitored heading cache.
    """

    def __init__(self, canonical_heading_query_port):
        if canonical_heading_query_port is None:
            raise ValueError("Canonical HeadingQueryPort is required.")
        self._canonical_heading_query_port = canonical_heading_query_port
        self._reference_lock = threading.RLock()
        self._zero_reference_deg = 0.0

    def set_current_heading_as_zero(self):
        canonical_heading_deg = (
            self._canonical_heading_query_port.get_heading_deg()
        )
        if canonical_heading_deg is None:
            return {"success": False, "reason": "heading_unavailable"}

        canonical_heading_deg = float(canonical_heading_deg)
        with self._reference_lock:
            self._zero_reference_deg = canonical_heading_deg
        return {
            "success": True,
            "reference_heading_deg": canonical_heading_deg,
            "field_heading_deg": 0.0
        }

    def get_heading_deg(self):
        canonical_heading_deg = (
            self._canonical_heading_query_port.get_heading_deg()
        )
        if canonical_heading_deg is None:
            return None
        with self._reference_lock:
            reference_heading_deg = self._zero_reference_deg
        return self._normalize_angle(
            float(canonical_heading_deg) - reference_heading_deg
        )

    def get_heading_snapshot(self):
        snapshot = dict(
            self._canonical_heading_query_port.get_heading_snapshot()
        )
        canonical_heading_deg = snapshot.get("heading_deg")
        with self._reference_lock:
            reference_heading_deg = self._zero_reference_deg

        field_heading_deg = None
        if snapshot.get("fresh") and canonical_heading_deg is not None:
            field_heading_deg = self._normalize_angle(
                float(canonical_heading_deg) - reference_heading_deg
            )

        snapshot["canonical_heading_deg"] = canonical_heading_deg
        snapshot["reference_heading_deg"] = reference_heading_deg
        snapshot["heading_deg"] = field_heading_deg
        return snapshot

    @staticmethod
    def _normalize_angle(angle_deg):
        return ((float(angle_deg) + 180.0) % 360.0) - 180.0
