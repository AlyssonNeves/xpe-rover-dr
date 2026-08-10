#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Automated unit tests for app.rover_application lifecycle behavior.
"""

import threading
import time
import unittest

from app.monitor_registration import MonitorRegistration
from app.rover_application import RoverApplication
from tests.unit.fakes import (
    FakeApplicationConcurrency, FakeProcessControl
)


class FakeRestApiServer(object):
    """Test double for REST API server lifecycle operations."""

    def __init__(self):
        """Initializes call counters."""
        self.started = False
        self.stopped = False
        self.start_calls = 0
        self.stop_calls = 0

    def start(self):
        """Records server start."""
        self.started = True
        self.start_calls += 1

    def stop(self):
        """Records server stop."""
        self.stopped = True
        self.stop_calls += 1


class FakeApplicationMonitor(threading.Thread):
    """Thread-based monitor fake compatible with RoverApplication."""

    def __init__(self, name, fail_on_start=False):
        """Initializes fake monitor state."""
        threading.Thread.__init__(self, name=name + "Thread")
        self.daemon = True
        self.name_value = name
        self.fail_on_start = fail_on_start
        self.started_event = threading.Event()
        self.stop_event = threading.Event()
        self.initialized_event = threading.Event()
        self.failed = False
        self.critical = None
        self.failure_handler = None
        self.prepare_for_shutdown_calls = 0
        self.stop_calls = 0

    def get_monitor_name(self):
        """Returns monitor display name."""
        return self.name_value

    def set_failure_policy(self, critical, failure_handler):
        """Stores configured failure policy."""
        self.critical = critical
        self.failure_handler = failure_handler

    def wait_until_initialized(self, timeout_seconds=5.0):
        """Waits until the fake monitor initializes."""
        return self.initialized_event.wait(timeout_seconds)

    def is_critical(self):
        """Returns criticality flag."""
        return bool(self.critical)

    def has_failed(self):
        """Returns failure flag."""
        return self.failed

    def prepare_for_shutdown(self):
        """Records shutdown preparation."""
        self.prepare_for_shutdown_calls += 1

    def stop(self):
        """Records stop request."""
        self.stop_calls += 1
        self.stop_event.set()

    def run(self):
        """Runs until stopped or records startup failure."""
        self.started_event.set()

        if self.fail_on_start:
            self.failed = True
            self.initialized_event.set()
            return

        self.initialized_event.set()
        self.stop_event.wait(1.0)


class FakeManagedResource(object):
    """Closeable resource fake managed by RoverApplication."""

    def __init__(self):
        """Initializes the close counter."""
        self.close_calls = 0

    def close(self):
        """Records a resource close request."""
        self.close_calls += 1


class FakeRuntimeComponent(object):
    """Startable and stoppable runtime component fake."""

    def __init__(self, name=None, stop_order=None):
        self.name = name
        self.stop_order = stop_order
        self.start_calls = 0
        self.stop_calls = 0

    def start(self):
        self.start_calls += 1

    def stop(self):
        self.stop_calls += 1
        if self.stop_order is not None:
            self.stop_order.append(self.name)


def _registration(monitor, critical=False):
    return MonitorRegistration(
        component=monitor,
        name=monitor.get_monitor_name(),
        critical=critical
    )


class RoverApplicationLifecycleTestCase(unittest.TestCase):
    """Validates RoverApplication lifecycle coordination."""

    def test_constructor_rejects_missing_lifecycle_ports(self):
        server = FakeRestApiServer()

        with self.assertRaisesRegex(
                ValueError, "concurrency_port is required"):
            RoverApplication(
                rest_api_server=server,
                concurrency_port=None,
                process_control_port=FakeProcessControl()
            )

        with self.assertRaisesRegex(
                ValueError, "process_control_port is required"):
            RoverApplication(
                rest_api_server=server,
                concurrency_port=FakeApplicationConcurrency(),
                process_control_port=None
            )

    def test_runtime_preparation_happens_before_any_component_starts(self):
        server = FakeRestApiServer()
        events = []
        display_state = {"bluetooth_error": False}

        class DisplayComponent(object):
            def start(self):
                events.append(
                    ("display_start", display_state["bluetooth_error"])
                )

            @staticmethod
            def stop():
                return None

        class JoystickComponent(object):
            @staticmethod
            def prepare_start():
                display_state["bluetooth_error"] = True
                events.append(("joystick_prepare", True))

            def start(self):
                events.append(("joystick_start", True))

            @staticmethod
            def stop():
                return None

        application = RoverApplication(
            rest_api_server=server,
            runtime_components=[DisplayComponent(), JoystickComponent()],
            concurrency_port=FakeApplicationConcurrency(),
            process_control_port=FakeProcessControl(),
        )

        application.start()

        self.assertEqual(
            [
                ("joystick_prepare", True),
                ("display_start", True),
                ("joystick_start", True)
            ],
            events
        )


    def test_early_display_starts_before_runtime_preparation(self):
        server = FakeRestApiServer()
        events = []

        class EarlyDisplayComponent(object):
            start_before_startup_checks = True

            @staticmethod
            def start():
                events.append("display_start")

            @staticmethod
            def stop():
                return None

        class JoystickComponent(object):
            @staticmethod
            def prepare_start():
                events.append("joystick_prepare")

            @staticmethod
            def start():
                events.append("joystick_start")

            @staticmethod
            def stop():
                return None

        application = RoverApplication(
            rest_api_server=server,
            runtime_components=[EarlyDisplayComponent(), JoystickComponent()],
            concurrency_port=FakeApplicationConcurrency(),
            process_control_port=FakeProcessControl(),
        )

        application.start()

        self.assertEqual(
            ["display_start", "joystick_prepare", "joystick_start"],
            events
        )

    def test_constructor_configures_monitor_criticality(self):
        """Sensor and motor monitors must be critical; controller not."""
        server = FakeRestApiServer()
        controller = FakeApplicationMonitor("Controller")
        sensor = FakeApplicationMonitor("Sensor")
        motor = FakeApplicationMonitor("Motor")

        RoverApplication(
            rest_api_server=server,
            monitor_registrations=[
                _registration(controller, False),
                _registration(sensor, True),
                _registration(motor, True)
            ],
            concurrency_port=FakeApplicationConcurrency(),
            process_control_port=FakeProcessControl(),
        )

        self.assertFalse(controller.critical)
        self.assertTrue(sensor.critical)
        self.assertTrue(motor.critical)
        self.assertIsNotNone(controller.failure_handler)
        self.assertIsNotNone(sensor.failure_handler)
        self.assertIsNotNone(motor.failure_handler)

    def test_start_starts_monitors_before_rest_server(self):
        """Application start must initialize monitors and then REST server."""
        server = FakeRestApiServer()
        monitor = FakeApplicationMonitor("Controller")
        application = RoverApplication(
            rest_api_server=server,
            monitor_registrations=[_registration(monitor, False)],
            concurrency_port=FakeApplicationConcurrency(),
            process_control_port=FakeProcessControl(),
        )

        application.start()

        self.assertTrue(monitor.started_event.is_set())
        self.assertTrue(server.started)

        application.stop()

    def test_stop_is_idempotent_for_server_stop(self):
        """Repeated stop calls must not stop the REST server twice."""
        server = FakeRestApiServer()
        monitor = FakeApplicationMonitor("Controller")
        application = RoverApplication(
            rest_api_server=server,
            monitor_registrations=[_registration(monitor, False)],
            concurrency_port=FakeApplicationConcurrency(),
            process_control_port=FakeProcessControl(),
        )

        application.start()
        application.stop()
        application.stop()

        self.assertEqual(1, server.stop_calls)
        self.assertEqual(1, monitor.prepare_for_shutdown_calls)
        self.assertEqual(1, monitor.stop_calls)


    def test_runtime_components_start_and_stop_with_application(self):
        """Runtime components must follow the application lifecycle."""
        server = FakeRestApiServer()
        component = FakeRuntimeComponent()
        application = RoverApplication(
            rest_api_server=server,
            runtime_components=[component],
            concurrency_port=FakeApplicationConcurrency(),
            process_control_port=FakeProcessControl(),
        )

        application.start()
        application.stop()
        application.stop()

        self.assertEqual(1, component.start_calls)
        self.assertEqual(1, component.stop_calls)

    def test_runtime_components_stop_in_reverse_assembly_order(self):
        """Dependent runtime components must stop before their providers."""
        server = FakeRestApiServer()
        stop_order = []
        provider = FakeRuntimeComponent("provider", stop_order)
        dependent = FakeRuntimeComponent("dependent", stop_order)
        application = RoverApplication(
            rest_api_server=server,
            runtime_components=[provider, dependent],
            concurrency_port=FakeApplicationConcurrency(),
            process_control_port=FakeProcessControl(),
        )

        application.start()
        application.stop()

        self.assertEqual(["dependent", "provider"], stop_order)

    def test_stop_closes_managed_resources_once(self):
        """Application shutdown must close managed resources idempotently."""
        server = FakeRestApiServer()
        resource = FakeManagedResource()
        application = RoverApplication(
            rest_api_server=server,
            monitor_registrations=[],
            managed_resources=[resource],
            concurrency_port=FakeApplicationConcurrency(),
            process_control_port=FakeProcessControl(),
        )

        application.stop()
        application.stop()

        self.assertEqual(1, resource.close_calls)

    def test_shutdown_request_is_scheduled_once_by_concurrency_port(self):
        """Repeated signal requests must schedule only one shutdown."""
        server = FakeRestApiServer()
        concurrency = FakeApplicationConcurrency()
        application = RoverApplication(
            rest_api_server=server,
            concurrency_port=concurrency,
            monitor_registrations=[],
            process_control_port=FakeProcessControl(),
        )

        self.assertTrue(application.request_shutdown())
        self.assertFalse(application.request_shutdown())

        self.assertEqual(1, concurrency.async_calls)
        self.assertEqual(1, server.stop_calls)
        self.assertTrue(concurrency.stop_completed)
        self.assertFalse(hasattr(application, "_stopped"))
        self.assertFalse(hasattr(application, "_restart_requested"))

    def test_restart_request_is_scheduled_once_by_concurrency_port(self):
        """Repeated restart requests must schedule only one shutdown."""
        server = FakeRestApiServer()
        concurrency = FakeApplicationConcurrency()
        application = RoverApplication(
            rest_api_server=server,
            concurrency_port=concurrency,
            monitor_registrations=[],
            process_control_port=FakeProcessControl(),
        )

        self.assertTrue(application.request_restart())
        self.assertFalse(application.request_restart())

        self.assertEqual(1, concurrency.async_calls)
        self.assertEqual(1, server.stop_calls)
        self.assertTrue(application.is_restart_requested())

    def test_restart_cannot_replace_an_existing_shutdown_request(self):
        """A late restart must not change an already claimed shutdown."""
        server = FakeRestApiServer()
        concurrency = FakeApplicationConcurrency()
        application = RoverApplication(
            rest_api_server=server,
            concurrency_port=concurrency,
            monitor_registrations=[],
            process_control_port=FakeProcessControl(),
        )

        self.assertTrue(application.request_shutdown())
        self.assertFalse(application.request_restart())

        self.assertFalse(application.is_restart_requested())
        self.assertEqual(1, concurrency.async_calls)

    def test_non_critical_monitor_failure_does_not_stop_application(self):
        """Non-critical failure handler must not trigger application stop."""
        server = FakeRestApiServer()
        controller = FakeApplicationMonitor("Controller")
        concurrency = FakeApplicationConcurrency()
        application = RoverApplication(
            rest_api_server=server,
            concurrency_port=concurrency,
            monitor_registrations=[_registration(controller, False)],
            process_control_port=FakeProcessControl(),
        )

        controller.failure_handler(controller, RuntimeError("failure"))

        time.sleep(0.01)

        self.assertFalse(server.stopped)
        self.assertEqual(0, concurrency.async_calls)

    def test_critical_monitor_failure_requests_shutdown_once(self):
        """Critical monitor failure must trigger one asynchronous shutdown."""
        server = FakeRestApiServer()
        sensor = FakeApplicationMonitor("Sensor")
        concurrency = FakeApplicationConcurrency()
        application = RoverApplication(
            rest_api_server=server,
            concurrency_port=concurrency,
            monitor_registrations=[_registration(sensor, True)],
            process_control_port=FakeProcessControl(),
        )

        sensor.start()
        self.assertTrue(sensor.wait_until_initialized(1.0))

        sensor.failure_handler(sensor, RuntimeError("failure"))
        sensor.failure_handler(sensor, RuntimeError("failure"))

        self.assertTrue(concurrency.wait_for_stop_completed(1.0))
        self.assertEqual(1, concurrency.async_calls)
        self.assertTrue(server.stopped)
        self.assertEqual(1, server.stop_calls)


if __name__ == "__main__":
    unittest.main()
