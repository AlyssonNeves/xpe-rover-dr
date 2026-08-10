#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Additional RoverApplication lifecycle and assembly tests."""

import unittest

try:
    from unittest import mock
except ImportError:  # pragma: no cover
    import mock

from app.configuration import RoverConfiguration
from app.rover_config import (
    build_default_configuration_values, merge_configuration_values
)
from app.monitor_registration import MonitorRegistration
from app.operation_mode_service import (
    Centrics, Commands, Controls, DifferentialModes, Drives, Fronts, OperationModeService
)
from app.rover_application import (
    ApplicationStartupError, RoverApplication
)
from bootstrap import rover_assembly
from bootstrap.rover_assembly import build_rover_application
from tests.unit.fakes import (
    FakeApplicationConcurrency, FakeProcessControl
)


def resolved_configuration(overrides):
    values = merge_configuration_values(
        build_default_configuration_values(), overrides
    )
    return RoverConfiguration(values)


class FakeRestServer(object):
    """Fake REST server used by application lifecycle tests."""

    def __init__(self):
        self.start_calls = 0
        self.stop_calls = 0
        self.shutdown_callback = None
        self.restart_callback = None

    def start(self):
        self.start_calls += 1

    def stop(self):
        self.stop_calls += 1

    def set_shutdown_callback(self, callback):
        self.shutdown_callback = callback

    def set_restart_callback(self, callback):
        self.restart_callback = callback



class FakeMonitor(object):
    """Configurable monitor test double."""

    def __init__(self, name, initialized=True, failed=False, alive=False):
        self.name = name
        self.initialized = initialized
        self.failed = failed
        self.alive = alive
        self.started = 0
        self.stopped = 0
        self.prepared_for_shutdown = 0
        self.joined = 0
        self.critical = None
        self.failure_handler = None

    def get_monitor_name(self):
        return self.name

    def set_failure_policy(self, critical, failure_handler):
        self.critical = critical
        self.failure_handler = failure_handler

    def is_critical(self):
        return self.critical is True

    def start(self):
        self.started += 1

    def prepare_for_shutdown(self):
        self.prepared_for_shutdown += 1

    def stop(self):
        self.stopped += 1

    def join(self, timeout=None):
        self.joined += 1

    def is_alive(self):
        return self.alive

    def wait_until_initialized(self, timeout_seconds=None):
        return self.initialized

    def has_failed(self):
        return self.failed


def _registration(monitor, critical=False):
    return MonitorRegistration(
        component=monitor,
        name=monitor.get_monitor_name(),
        critical=critical
    )


class RoverApplicationAdditionalTestCase(unittest.TestCase):
    """Covers remaining RoverApplication behavior."""

    def test_start_returns_without_rest_server_when_stop_is_already_requested(self):
        server = FakeRestServer()
        concurrency = FakeApplicationConcurrency()
        concurrency.claim_stop()
        app = RoverApplication(
            server,
            concurrency_port=concurrency,
            monitor_registrations=[],
            process_control_port=FakeProcessControl(),
        )
        app.start()
        self.assertEqual(0, server.start_calls)

    def test_start_logs_timeout_for_non_initialized_monitor(self):
        server = FakeRestServer()
        monitor = FakeMonitor("Controller", initialized=False, failed=False)
        app = RoverApplication(
            server,
            monitor_registrations=[_registration(monitor, False)],
            concurrency_port=FakeApplicationConcurrency(),
            process_control_port=FakeProcessControl()
        )
        app.start()
        self.assertEqual(1, server.start_calls)

    def test_start_handles_critical_initialization_failure(self):
        server = FakeRestServer()
        monitor = FakeMonitor("Sensor", initialized=False, failed=True)
        concurrency = FakeApplicationConcurrency()
        app = RoverApplication(
            server,
            concurrency_port=concurrency,
            monitor_registrations=[_registration(monitor, True)],
            process_control_port=FakeProcessControl(),
        )

        with self.assertRaises(ApplicationStartupError):
            app.start()

        self.assertTrue(concurrency.lifecycle_request_claimed)
        self.assertFalse(concurrency.restart_requested)
        self.assertEqual(1, concurrency.async_calls)
        self.assertTrue(concurrency.stop_completed)
        self.assertEqual(0, server.start_calls)
        self.assertEqual(1, server.stop_calls)
        app.stop()
        self.assertEqual(1, server.stop_calls)

    def test_stop_logs_monitor_that_remains_alive(self):
        server = FakeRestServer()
        monitor = FakeMonitor("Sensor", alive=True)
        app = RoverApplication(
            server,
            monitor_registrations=[_registration(monitor, True)],
            concurrency_port=FakeApplicationConcurrency(),
            process_control_port=FakeProcessControl()
        )
        app.stop()
        self.assertEqual(1, monitor.prepared_for_shutdown)
        self.assertEqual(1, monitor.stopped)
        self.assertEqual(1, monitor.joined)

    def test_restart_current_process_uses_process_control_port(self):
        server = FakeRestServer()
        process_control = FakeProcessControl()
        app = RoverApplication(
            server,
            process_control_port=process_control,
            monitor_registrations=[],
            concurrency_port=FakeApplicationConcurrency(),
        )
        app._restart_current_process()
        self.assertEqual(1, process_control.restart_calls)

    def test_start_restarts_current_process_after_restart_request(self):
        server = FakeRestServer()
        concurrency = FakeApplicationConcurrency()
        concurrency.claim_restart_request()
        concurrency.mark_stop_completed()
        app = RoverApplication(
            server,
            concurrency_port=concurrency,
            monitor_registrations=[],
            process_control_port=FakeProcessControl(),
        )
        with mock.patch.object(app, "_restart_current_process") as restart_mock:
            app.start()
        self.assertEqual(1, server.start_calls)
        self.assertEqual(1, restart_mock.call_count)

    def test_startup_configuration_fault_is_deferred_to_alert_adapter(self):
        loader = mock.Mock()
        loader.hardware_requested.return_value = True
        logger = mock.Mock()
        status_led = mock.Mock()
        alert_adapter = mock.Mock()
        notifier = mock.Mock()
        notifier.show.return_value = True
        error = RuntimeError("missing token")

        with mock.patch.object(
                rover_assembly, "Ev3StatusLedAdapter",
                return_value=status_led) as status_led_class, mock.patch.object(
                rover_assembly, "Ev3OperatorAlertAdapter",
                return_value=alert_adapter) as alert_class, mock.patch.object(
                rover_assembly, "StartupErrorNotifier",
                return_value=notifier) as notifier_class:
            rover_assembly._report_startup_error(loader, logger, error)

        status_led_class.assert_not_called()
        status_led.set_fault.assert_not_called()
        alert_class.assert_called_once_with(
            status_led_factory=status_led_class,
            fault_source="configuration"
        )
        notifier_class.assert_called_once_with(alert_adapter)
        notifier.show.assert_called_once_with(str(error))

    def test_startup_alert_resources_are_warmed_before_configuration_load(self):
        loader = mock.Mock()
        loader.hardware_requested.return_value = True
        configuration = resolved_configuration({
            "hardware_enabled": False,
            "shutdown_token": "shutdown-test-token",
            "sensor_definitions": {},
            "motor_definitions": {},
            "drive": {},
            "mecanum": {},
            "joystick": {"device_name": "Wireless Controller"}
        })
        loader.load.return_value = configuration
        sequence = []

        def warm_resources():
            sequence.append("warm")

        def load_configuration():
            sequence.append("load")
            return configuration

        loader.load.side_effect = load_configuration

        with mock.patch.object(
                rover_assembly.Ev3OperatorAlertAdapter,
                "prepare_render_resources",
                side_effect=warm_resources), mock.patch.object(
                rover_assembly, "build_rover_application",
                return_value=object()):
            runtime = rover_assembly.prepare_rover_runtime(loader, mock.Mock())

        self.assertTrue(runtime.ready)
        self.assertEqual(["warm", "load"], sequence)

    def test_prepare_runtime_selects_one_cohesive_local_mode(self):
        configuration = resolved_configuration({
            "application_name": "Rover DR",
            "application_version": "0.47.0",
            "hardware_enabled": True,
            "shutdown_token": "shutdown-test-token",
            "hardware_api_token": "hardware-test-token",
            "sensor_definitions": {},
            "motor_definitions": {},
            "drive": {},
            "mecanum": {},
            "joystick": {"device_name": "Wireless Controller"}
        })
        loader = mock.Mock()
        loader.load.return_value = configuration
        logger = mock.Mock()
        application = object()
        command_control_selector = mock.Mock()
        command_control_selector.select_mode.return_value = {
            "command": Commands.LOCAL,
            "control": Controls.MANUAL
        }
        local_drive_selector = mock.Mock()
        local_drive_selector.select_setup.return_value = {
            "front": Fronts.TAIL,
            "drive": Drives.MECANUM,
            "centric": Centrics.CHASSIS
        }
        status_component = mock.Mock()
        cache_result = {
            "total": 14,
            "memory_hits": 0,
            "loaded": 14,
            "failed": []
        }

        with mock.patch.object(
                rover_assembly, "warm_monochrome_screen_cache",
                return_value=cache_result) as cache_mock, mock.patch.object(
                rover_assembly, "Ev3CommandControlSelectorAdapter",
                return_value=command_control_selector), mock.patch.object(
                rover_assembly, "Ev3LocalDriveSetupSelectorAdapter",
                return_value=local_drive_selector), mock.patch.object(
                rover_assembly, "Ev3OperationStatusAdapter",
                return_value=status_component), mock.patch.object(
                rover_assembly, "build_rover_application",
                return_value=application) as build_mock:
            runtime = rover_assembly.prepare_rover_runtime(loader, logger)

        cache_mock.assert_called_once_with()
        self.assertTrue(runtime.ready)
        status_component.start.assert_called_once_with()
        command_control_selector.select_mode.assert_called_once_with(
            Commands.LOCAL, Controls.MANUAL
        )
        local_drive_selector.select_setup.assert_called_once_with(
            Fronts.NOSE, Drives.DIFFERENTIAL, Centrics.CHASSIS,
            DifferentialModes.R_BOGIE
        )
        call = build_mock.call_args[1]
        self.assertIs(status_component, call["operation_status_component"])
        self.assertEqual(
            {
                "command": Commands.LOCAL,
                "control": Controls.MANUAL,
                "front": Fronts.TAIL,
                "drive": Drives.MECANUM,
                "centric": Centrics.CHASSIS,
                "differential_mode": None
            },
            call["operation_mode_service"].get_snapshot()
        )

    def test_prepare_runtime_selects_local_drive_for_automatic_control(self):
        configuration = resolved_configuration({
            "application_name": "Rover DR",
            "application_version": "0.47.0",
            "hardware_enabled": True,
            "shutdown_token": "shutdown-test-token",
            "hardware_api_token": "hardware-test-token",
            "sensor_definitions": {},
            "motor_definitions": {},
            "drive": {},
            "mecanum": {},
            "joystick": {"device_name": "Wireless Controller"}
        })
        loader = mock.Mock()
        loader.load.return_value = configuration
        command_control_selector = mock.Mock()
        command_control_selector.select_mode.return_value = {
            "command": Commands.LOCAL,
            "control": Controls.AUTOMATIC
        }
        local_drive_selector = mock.Mock()
        local_drive_selector.select_setup.return_value = {
            "front": Fronts.NOSE,
            "drive": Drives.DIFFERENTIAL,
            "centric": None
        }
        cache_result = {
            "total": 14, "memory_hits": 0, "loaded": 14,
            "failed": []
        }

        with mock.patch.object(
                rover_assembly, "warm_monochrome_screen_cache",
                return_value=cache_result), mock.patch.object(
                rover_assembly, "Ev3CommandControlSelectorAdapter",
                return_value=command_control_selector), mock.patch.object(
                rover_assembly, "Ev3LocalDriveSetupSelectorAdapter",
                return_value=local_drive_selector), mock.patch.object(
                rover_assembly, "build_rover_application",
                return_value=object()):
            runtime = rover_assembly.prepare_rover_runtime(loader, mock.Mock())

        self.assertTrue(runtime.ready)
        local_drive_selector.select_setup.assert_called_once_with(
            Fronts.NOSE, Drives.DIFFERENTIAL, Centrics.CHASSIS,
            DifferentialModes.R_BOGIE
        )

    def test_prepare_runtime_skips_local_drive_for_remote_command(self):
        configuration = resolved_configuration({
            "application_name": "Rover DR",
            "application_version": "0.47.0",
            "hardware_enabled": True,
            "shutdown_token": "shutdown-test-token",
            "hardware_api_token": "hardware-test-token",
            "sensor_definitions": {},
            "motor_definitions": {},
            "drive": {},
            "mecanum": {},
            "joystick": {"device_name": "Wireless Controller"}
        })
        loader = mock.Mock()
        loader.load.return_value = configuration
        command_control_selector = mock.Mock()
        command_control_selector.select_mode.return_value = {
            "command": Commands.REMOTE,
            "control": None
        }
        local_drive_selector = mock.Mock()
        cache_result = {
            "total": 14, "memory_hits": 0, "loaded": 14,
            "failed": []
        }

        with mock.patch.object(
                rover_assembly, "warm_monochrome_screen_cache",
                return_value=cache_result), mock.patch.object(
                rover_assembly, "Ev3CommandControlSelectorAdapter",
                return_value=command_control_selector), mock.patch.object(
                rover_assembly, "Ev3LocalDriveSetupSelectorAdapter",
                return_value=local_drive_selector), mock.patch.object(
                rover_assembly, "build_rover_application",
                return_value=object()) as build_mock:
            runtime = rover_assembly.prepare_rover_runtime(loader, mock.Mock())

        self.assertTrue(runtime.ready)
        local_drive_selector.select_setup.assert_not_called()
        self.assertEqual(
            {
                "command": Commands.REMOTE,
                "control": None,
                "front": None,
                "drive": None,
                "centric": None,
                "differential_mode": None
            },
            build_mock.call_args[1]["operation_mode_service"].get_snapshot()
        )

    def test_prepare_runtime_accepts_field_centric_selection(self):
        configuration = resolved_configuration({
            "application_name": "Rover DR",
            "application_version": "0.47.0",
            "hardware_enabled": True,
            "shutdown_token": "shutdown-test-token",
            "hardware_api_token": "hardware-test-token",
            "sensor_definitions": {},
            "motor_definitions": {},
            "drive": {},
            "mecanum": {},
            "joystick": {"device_name": "Wireless Controller"}
        })
        loader = mock.Mock()
        loader.load.return_value = configuration
        logger = mock.Mock()
        command_control_selector = mock.Mock()
        command_control_selector.select_mode.return_value = {
            "command": Commands.LOCAL,
            "control": Controls.MANUAL
        }
        local_drive_selector = mock.Mock()
        local_drive_selector.select_setup.return_value = {
            "front": Fronts.NOSE,
            "drive": Drives.MECANUM,
            "centric": Centrics.FIELD
        }
        cache_result = {
            "total": 14, "memory_hits": 0, "loaded": 14,
            "failed": []
        }

        with mock.patch.object(
                rover_assembly, "warm_monochrome_screen_cache",
                return_value=cache_result), mock.patch.object(
                rover_assembly, "Ev3CommandControlSelectorAdapter",
                return_value=command_control_selector), mock.patch.object(
                rover_assembly, "Ev3LocalDriveSetupSelectorAdapter",
                return_value=local_drive_selector), mock.patch.object(
                rover_assembly, "build_rover_application") as build_mock:
            runtime = rover_assembly.prepare_rover_runtime(loader, logger)

        self.assertTrue(runtime.ready)
        self.assertEqual(0, runtime.exit_code)
        build_mock.assert_called_once()
        self.assertEqual(
            Centrics.FIELD,
            build_mock.call_args[1][
                "operation_mode_service"
            ].get_snapshot()["centric"]
        )

    def test_prepare_runtime_without_hardware_uses_default_canonical_mode(self):
        configuration = resolved_configuration({
            "application_name": "Rover DR",
            "application_version": "0.47.0",
            "hardware_enabled": False,
            "shutdown_token": "shutdown-test-token",
            "sensor_definitions": {},
            "motor_definitions": {},
            "drive": {},
            "mecanum": {},
            "joystick": {"device_name": "Wireless Controller"}
        })
        loader = mock.Mock()
        loader.load.return_value = configuration
        application = object()

        with mock.patch.object(
                rover_assembly, "warm_monochrome_screen_cache") as cache_mock, \
                mock.patch.object(
                    rover_assembly, "build_rover_application",
                    return_value=application) as build_mock:
            runtime = rover_assembly.prepare_rover_runtime(loader, mock.Mock())

        cache_mock.assert_not_called()
        self.assertTrue(runtime.ready)
        self.assertIs(application, runtime.application)
        call = build_mock.call_args[1]
        self.assertIs(configuration, call["configuration"])
        self.assertEqual(
            {
                "command": Commands.LOCAL,
                "control": Controls.MANUAL,
                "front": Fronts.NOSE,
                "drive": Drives.DIFFERENTIAL,
                "centric": None,
                "differential_mode": DifferentialModes.R_BOGIE
            },
            call["operation_mode_service"].get_snapshot()
        )

    def test_local_manual_build_disables_motor_monitor_and_write_gateway(self):
        app = build_rover_application(
            operation_mode_service=OperationModeService()
        )
        monitor_names = [
            monitor.get_monitor_name() for monitor in app.monitors
        ]
        runtime_names = [
            component.__class__.__name__
            for component in app.runtime_components
        ]

        self.assertNotIn("Motor", monitor_names)
        self.assertIsNone(app.rest_api_server.motor_gateway_port)
        self.assertIn("JoystickControlService", runtime_names)
        self.assertIn("ManualDriveService", runtime_names)

    def test_local_manual_build_applies_selected_mecanum_setup_to_joystick(self):
        mode_service = OperationModeService(
            front=Fronts.TAIL,
            drive=Drives.MECANUM,
            centric=Centrics.CHASSIS
        )
        app = build_rover_application(operation_mode_service=mode_service)
        joystick = next(
            component for component in app.runtime_components
            if component.__class__.__name__ == "JoystickControlService"
        )

        self.assertEqual(Drives.MECANUM, joystick.drive)
        self.assertEqual(Fronts.TAIL, joystick.front)
        self.assertEqual(Centrics.CHASSIS, joystick.centric)
        self.assertFalse(hasattr(joystick, "mecanum_motion"))
        self.assertEqual(1.1, joystick.mecanum_strafe_compensation)

    def test_build_rover_application_wires_callbacks_and_monitors(self):
        app = build_rover_application(
            operation_mode_service=OperationModeService(
                command=Commands.REMOTE
            )
        )
        for resource in app.managed_resources:
            self.addCleanup(resource.close)
        self.assertEqual(3, len(app.monitors))
        self.assertIs(app, app.rest_api_server.shutdown_callback.__self__)
        self.assertIs(
            app.request_shutdown.__func__,
            app.rest_api_server.shutdown_callback.__func__
        )
        self.assertIs(app, app.rest_api_server.restart_callback.__self__)
        self.assertIs(
            app.request_restart.__func__,
            app.rest_api_server.restart_callback.__func__
        )


if __name__ == "__main__":
    unittest.main()
