#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Unit tests for the minimal process entry point."""

import importlib
import unittest

try:
    from unittest import mock
except ImportError:  # pragma: no cover
    import mock

import main as main_module


class FakeLogger(object):
    def __init__(self):
        self.messages = []

    def status(self, message):
        self.messages.append(message)

    def error(self, message):
        self.messages.append(message)


class FakeRuntime(object):
    def __init__(self, ready=True, exit_code=0, start_error=None):
        self.ready = ready
        self.exit_code = exit_code
        self.start_error = start_error
        self.logger = FakeLogger()
        self.start_calls = 0
        self.stop_or_join_calls = 0
        self.finish_calls = 0
        self.shutdown_requests = 0

    def start(self):
        self.start_calls += 1
        if self.start_error is not None:
            raise self.start_error

    def request_shutdown(self):
        self.shutdown_requests += 1

    def stop_or_join(self):
        self.stop_or_join_calls += 1

    def finish(self):
        self.finish_calls += 1


class MainLifecycleTestCase(unittest.TestCase):
    def setUp(self):
        self.module = importlib.reload(main_module)

    def test_request_shutdown_is_safe_before_runtime_exists(self):
        self.module.request_shutdown()
        self.assertIsNone(self.module.runtime)

    def test_request_shutdown_delegates_to_runtime_context(self):
        runtime = FakeRuntime()
        self.module.runtime = runtime
        self.module.request_shutdown()
        self.assertEqual(1, runtime.shutdown_requests)

    def test_main_returns_startup_exit_code_without_registering_signals(self):
        runtime = FakeRuntime(ready=False, exit_code=1)
        with mock.patch.object(
                self.module, "prepare_rover_runtime", return_value=runtime):
            with mock.patch.object(self.module.signal, "signal") as signal_mock:
                result = self.module.main()
        self.assertEqual(1, result)
        signal_mock.assert_not_called()

    def test_main_registers_signals_and_runs_prepared_runtime(self):
        runtime = FakeRuntime()
        with mock.patch.object(
                self.module, "prepare_rover_runtime", return_value=runtime):
            with mock.patch.object(self.module.signal, "signal") as signal_mock:
                result = self.module.main()
        self.assertEqual(0, result)
        self.assertEqual(1, runtime.start_calls)
        self.assertEqual(1, runtime.stop_or_join_calls)
        self.assertEqual(1, runtime.finish_calls)
        registered = [item[0][0] for item in signal_mock.call_args_list]
        self.assertIn(self.module.signal.SIGINT, registered)
        self.assertIn(self.module.signal.SIGTERM, registered)

    def test_startup_error_returns_nonzero_without_escaping(self):
        runtime = FakeRuntime(
            start_error=self.module.ApplicationStartupError("gyro missing")
        )
        with mock.patch.object(
                self.module, "prepare_rover_runtime", return_value=runtime):
            with mock.patch.object(self.module.signal, "signal"):
                result = self.module.main()

        self.assertEqual(1, result)
        self.assertEqual(1, runtime.stop_or_join_calls)
        self.assertEqual(1, runtime.finish_calls)
        self.assertIn(
            "Rover startup aborted: gyro missing", runtime.logger.messages
        )

    def test_keyboard_interrupt_uses_runtime_shutdown_path(self):
        runtime = FakeRuntime(start_error=KeyboardInterrupt())
        with mock.patch.object(
                self.module, "prepare_rover_runtime", return_value=runtime):
            with mock.patch.object(self.module.signal, "signal"):
                self.module.main()
        self.assertEqual(1, runtime.shutdown_requests)
        self.assertEqual(1, runtime.stop_or_join_calls)
        self.assertEqual(1, runtime.finish_calls)


if __name__ == "__main__":
    unittest.main()
