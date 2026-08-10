#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Edge-case tests for the shared monitor lifecycle."""

import unittest

from infrastructure.monitoring.monitor_base import MonitorBase


class FinalizeFailureMonitor(MonitorBase):
    """Monitor that fails during finalization."""

    def __init__(self):
        MonitorBase.__init__(self, "FinalizeFailure", interval_seconds=0.001)
        self.cycles = 0

    def on_cycle(self):
        self.cycles += 1
        self.stop()

    def on_finalize(self):
        raise RuntimeError("finalize failed")


class MonitorBaseEdgeCasesTestCase(unittest.TestCase):
    """Covers optional hooks and exceptional lifecycle paths."""

    def test_optional_hooks_return_none(self):
        monitor = MonitorBase("Base")
        self.assertIsNone(monitor.on_initialize())
        self.assertIsNone(monitor.on_finalize())

    def test_base_on_cycle_raises_not_implemented(self):
        monitor = MonitorBase("Base")
        with self.assertRaises(NotImplementedError):
            monitor.on_cycle()

    def test_finalize_failure_is_logged_without_breaking_thread(self):
        monitor = FinalizeFailureMonitor()
        monitor.start()
        monitor.join(timeout=2.0)
        self.assertFalse(monitor.is_alive())
        self.assertEqual(1, monitor.cycles)

    def test_critical_failure_without_handler_is_safe(self):
        class FailingMonitor(MonitorBase):
            def __init__(self):
                MonitorBase.__init__(self, "NoHandler", interval_seconds=0.001)

            def on_cycle(self):
                raise RuntimeError("failure")

        monitor = FailingMonitor()
        monitor.set_failure_policy(critical=True, failure_handler=None)
        monitor.start()
        monitor.join(timeout=2.0)
        self.assertTrue(monitor.has_failed())


if __name__ == "__main__":
    unittest.main()
