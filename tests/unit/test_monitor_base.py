#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Automated unit tests for services.monitor_base.
"""

import unittest

from infrastructure.monitoring.monitor_base import MonitorBase


class OneCycleMonitor(MonitorBase):
    """Monitor test double that stops after one cycle."""

    def __init__(self):
        """Initializes test monitor."""
        MonitorBase.__init__(
            self,
            name="TestMonitor",
            interval_seconds=0.001
        )
        self.initialized = False
        self.cycles = 0
        self.finalized = False

    def on_initialize(self):
        """Marks initialization."""
        self.initialized = True

    def on_cycle(self):
        """Runs a single cycle and requests stop."""
        self.cycles += 1
        self.stop()

    def on_finalize(self):
        """Marks finalization."""
        self.finalized = True


class InitializationFailureMonitor(MonitorBase):
    """Monitor test double that fails during initialization."""

    def __init__(self):
        """Initializes test monitor."""
        MonitorBase.__init__(
            self,
            name="BrokenMonitor",
            interval_seconds=0.001
        )
        self.finalized = False

    def on_initialize(self):
        """Raises initialization failure."""
        raise RuntimeError("initialization failed")

    def on_cycle(self):
        """No cycle should run when initialization fails."""
        raise AssertionError("cycle should not run")

    def on_finalize(self):
        """Marks finalization."""
        self.finalized = True


class CycleFailureMonitor(MonitorBase):
    """Monitor test double that fails during cycle execution."""

    def __init__(self):
        """Initializes test monitor."""
        MonitorBase.__init__(
            self,
            name="CycleMonitor",
            interval_seconds=0.001
        )
        self.finalized = False

    def on_cycle(self):
        """Raises cycle failure."""
        raise ValueError("cycle failed")

    def on_finalize(self):
        """Marks finalization."""
        self.finalized = True


class MonitorBaseTestCase(unittest.TestCase):
    """Validates monitor lifecycle, failure state, and failure policy."""

    def test_successful_monitor_initializes_cycles_and_finalizes(self):
        """Successful monitor must initialize, run one cycle, and finalize."""
        monitor = OneCycleMonitor()

        monitor.start()
        initialized = monitor.wait_until_initialized(1.0)
        monitor.join(1.0)

        self.assertTrue(initialized)
        self.assertTrue(monitor.is_initialized())
        self.assertFalse(monitor.has_failed())
        self.assertTrue(monitor.initialized)
        self.assertEqual(1, monitor.cycles)
        self.assertTrue(monitor.finalized)
        self.assertFalse(monitor.is_alive())

    def test_stop_sets_stopping_state(self):
        """stop must request monitor shutdown."""
        monitor = OneCycleMonitor()

        self.assertFalse(monitor.is_stopping())

        monitor.stop()

        self.assertTrue(monitor.is_stopping())

    def test_initialization_failure_releases_wait_and_registers_failure(self):
        """Initialization failure must release waiters and register details."""
        monitor = InitializationFailureMonitor()

        monitor.start()
        initialized = monitor.wait_until_initialized(1.0)
        monitor.join(1.0)

        self.assertFalse(initialized)
        self.assertFalse(monitor.is_initialized())
        self.assertTrue(monitor.has_failed())
        self.assertTrue(monitor.finalized)
        self.assertFalse(monitor.is_alive())

        failure_state = monitor.get_failure_state()

        self.assertTrue(failure_state["failed"])
        self.assertFalse(failure_state["critical"])
        self.assertEqual("RuntimeError", failure_state["failure_type"])
        self.assertEqual(
            "initialization failed",
            failure_state["failure_message"]
        )

    def test_cycle_failure_registers_failure_state(self):
        """Cycle failure must be stored in diagnostic state."""
        monitor = CycleFailureMonitor()

        monitor.start()
        initialized = monitor.wait_until_initialized(1.0)
        monitor.join(1.0)

        self.assertTrue(initialized)
        self.assertTrue(monitor.has_failed())
        self.assertTrue(monitor.finalized)

        failure_state = monitor.get_failure_state()

        self.assertTrue(failure_state["failed"])
        self.assertEqual("ValueError", failure_state["failure_type"])
        self.assertEqual("cycle failed", failure_state["failure_message"])

    def test_critical_failure_notifies_handler(self):
        """Critical monitor failures must notify configured failure handler."""
        notifications = []

        def failure_handler(monitor, error):
            """Collects critical failure notification."""
            notifications.append((monitor.get_monitor_name(), str(error)))

        monitor = CycleFailureMonitor()
        monitor.set_failure_policy(
            critical=True,
            failure_handler=failure_handler
        )

        monitor.start()
        monitor.wait_until_initialized(1.0)
        monitor.join(1.0)

        self.assertTrue(monitor.is_critical())
        self.assertEqual(
            [("Cycle", "cycle failed")],
            notifications
        )
        self.assertTrue(monitor.get_failure_state()["critical"])

    def test_non_critical_failure_does_not_notify_handler(self):
        """Non-critical monitor failures must not notify handler."""
        notifications = []

        def failure_handler(monitor, error):
            """Collects failure notification."""
            notifications.append((monitor, error))

        monitor = CycleFailureMonitor()
        monitor.set_failure_policy(
            critical=False,
            failure_handler=failure_handler
        )

        monitor.start()
        monitor.wait_until_initialized(1.0)
        monitor.join(1.0)

        self.assertEqual([], notifications)


if __name__ == "__main__":
    unittest.main()
