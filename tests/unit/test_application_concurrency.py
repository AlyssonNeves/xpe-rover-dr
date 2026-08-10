#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for centralized application lifecycle synchronization."""

import unittest

from infrastructure.runtime.rover_runtime_context import RoverRuntimeContext
from infrastructure.runtime.threading_application_concurrency import (
    ThreadingApplicationConcurrency
)


class FakeApplication(object):
    def __init__(self):
        self.start_calls = 0
        self.request_shutdown_calls = 0
        self.stop_calls = 0

    def start(self):
        self.start_calls += 1

    def request_shutdown(self):
        self.request_shutdown_calls += 1
        return True

    def stop(self):
        self.stop_calls += 1


class ApplicationConcurrencyTestCase(unittest.TestCase):
    """Validates the single lifecycle-state owner."""

    def test_stop_claim_is_observable_and_single_owner(self):
        concurrency = ThreadingApplicationConcurrency()

        self.assertFalse(concurrency.is_stop_requested())
        self.assertTrue(concurrency.claim_stop())
        self.assertTrue(concurrency.is_stop_requested())
        self.assertFalse(concurrency.claim_stop())

    def test_shutdown_scheduling_is_rejected_after_stop_claim(self):
        concurrency = ThreadingApplicationConcurrency()

        self.assertTrue(concurrency.claim_stop())
        self.assertFalse(concurrency.claim_shutdown_request())

    def test_shutdown_scheduling_can_be_claimed_only_once(self):
        concurrency = ThreadingApplicationConcurrency()

        self.assertTrue(concurrency.claim_shutdown_request())
        self.assertFalse(concurrency.claim_shutdown_request())
        self.assertTrue(concurrency.claim_stop())

    def test_shutdown_claim_rejects_late_restart_without_changing_state(self):
        concurrency = ThreadingApplicationConcurrency()

        self.assertTrue(concurrency.claim_shutdown_request())
        self.assertFalse(concurrency.claim_restart_request())
        self.assertFalse(concurrency.is_restart_requested())

    def test_restart_claim_rejects_late_shutdown_and_sets_restart_state(self):
        concurrency = ThreadingApplicationConcurrency()

        self.assertTrue(concurrency.claim_restart_request())
        self.assertFalse(concurrency.claim_shutdown_request())
        self.assertTrue(concurrency.is_restart_requested())

    def test_critical_shutdown_uses_the_same_lifecycle_request_claim(self):
        concurrency = ThreadingApplicationConcurrency()

        self.assertTrue(concurrency.claim_critical_shutdown())
        self.assertFalse(concurrency.claim_restart_request())
        self.assertFalse(concurrency.is_restart_requested())

    def test_runtime_context_delegates_without_owning_shutdown_state(self):
        application = FakeApplication()
        context = RoverRuntimeContext(application=application)

        context.start()
        context.request_shutdown()
        context.stop_or_join()

        self.assertEqual(1, application.start_calls)
        self.assertEqual(1, application.request_shutdown_calls)
        self.assertEqual(1, application.stop_calls)
        self.assertFalse(hasattr(context, "_shutdown_lock"))
        self.assertFalse(hasattr(context, "_shutdown_requested"))
        self.assertFalse(hasattr(context, "_shutdown_thread"))


if __name__ == "__main__":
    unittest.main()
