#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for Rover state monitor diagnostics and safe fallbacks."""

import unittest

from app.services.rover_state_service import RoverStateService


class HasFailedOnlyMonitor(object):
    """Diagnostic test double exposing only has_failed."""

    def has_failed(self):
        return True


class UnknownDiagnosticMonitor(object):
    """Diagnostic test double exposing no known diagnostic method."""

    pass


class RoverStateDiagnosticsTestCase(unittest.TestCase):
    """Covers diagnostic fallback branches."""

    def test_monitor_with_only_has_failed_is_rejected(self):
        with self.assertRaises(TypeError):
            RoverStateService(monitors={"custom": HasFailedOnlyMonitor()})

    def test_monitor_without_diagnostic_contract_is_rejected(self):
        with self.assertRaises(TypeError):
            RoverStateService(monitors={"custom": UnknownDiagnosticMonitor()})


if __name__ == "__main__":
    unittest.main()
