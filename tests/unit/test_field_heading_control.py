#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for dedicated gyro monitoring and FIELD-centric control."""

import sys
import types
import unittest
from unittest import mock

from adapters.out_ev3_gyro_sensor import Ev3GyroSensorAdapter
from adapters.out_heading_state import HeadingStateQueryAdapter
from app.configuration import RoverConfiguration
from app.rover_config import (
    DEFAULT_CONFIGURATION, build_default_configuration_values,
    merge_configuration_values
)
from app.operation_mode_service import Centrics, Drives, RoverOperationMode
from app.services.field_heading_reference_service import (
    FieldHeadingReferenceService
)
from app.services.joystick_control_service import (
    JoystickControlService as _JoystickControlService
)
from bootstrap.rover_assembly import build_local_manual_application
from infrastructure.monitoring.gyro_heading_monitor import GyroHeadingMonitor
from infrastructure.state.heading_state_store import HeadingStateStore


CENTER = 127
MINIMUM = 0
MAXIMUM = 255


def build_joystick_service(*args, **overrides):
    joystick = DEFAULT_CONFIGURATION.joystick
    values = {
        "max_speed_sp": joystick["max_speed_sp"],
        "auxiliary_speed_sp": joystick["auxiliary_speed_sp"],
        "axis_center": joystick["axis_center"],
        "axis_deadzone": joystick["axis_deadzone"],
        "axis_max": joystick["axis_max"],
        "axis_response_intensity": joystick[
            "axis_response_intensity"
        ],
        "neutral_stability_seconds": joystick[
            "neutral_stability_seconds"
        ],
        "neutral_poll_seconds": joystick["neutral_poll_seconds"],
        "left_auxiliary_motor_code": joystick["left_auxiliary_motor_code"],
        "right_auxiliary_motor_code": joystick["right_auxiliary_motor_code"],
        "poll_seconds": joystick["poll_seconds"],
        "connection_retry_seconds": joystick["connection_retry_seconds"],
        "mecanum_strafe_compensation": (
            DEFAULT_CONFIGURATION.mecanum["strafe_compensation"]
        ),
        "operation_mode": RoverOperationMode(
            drive=Drives.MECANUM, centric=Centrics.FIELD
        )
    }
    values.update(overrides)
    return _JoystickControlService(*args, **values)


def resolved_configuration(overrides):
    values = merge_configuration_values(
        build_default_configuration_values(), overrides
    )
    return RoverConfiguration(values)


class FakeJoystickPort(object):
    def open(self):
        return "Wireless Controller"

    def read_event_batch(self, timeout_seconds, max_events):
        del timeout_seconds
        del max_events
        return []

    def close(self):
        return None

    def is_available(self):
        return True


class FakeManualDrivePort(object):
    def __init__(self):
        self.mecanum_calls = []
        self.emergency_stop_calls = 0

    def acquire(self, session_id, motor_codes=None):
        del session_id
        del motor_codes
        return {"success": True}

    def apply_drive_setpoint(self, *args, **kwargs):
        del args
        del kwargs
        return {"success": True}

    def apply_mecanum_setpoint(
            self, session_id, front_left_speed_sp, rear_left_speed_sp,
            front_right_speed_sp, rear_right_speed_sp, stop_action=None):
        self.mecanum_calls.append((
            session_id,
            front_left_speed_sp,
            rear_left_speed_sp,
            front_right_speed_sp,
            rear_right_speed_sp,
            stop_action
        ))
        return {"success": True}

    def apply_auxiliary_setpoint(self, *args, **kwargs):
        del args
        del kwargs
        return {"success": True}

    def emergency_stop(self, stop_action=None):
        del stop_action
        self.emergency_stop_calls += 1
        return {"success": True}

    def release(self, session_id, stop=True):
        del session_id
        del stop
        return {"success": True}


class MutableHeadingQuery(object):
    def __init__(self, heading_deg=0.0):
        self.heading_deg = heading_deg

    def get_heading_deg(self):
        return self.heading_deg

    def get_heading_snapshot(self):
        return {
            "fresh": self.heading_deg is not None,
            "heading_deg": self.heading_deg,
            "age_seconds": 0.0,
            "error": None
        }


class RecordingLogger(object):
    def __init__(self):
        self.status_messages = []
        self.error_messages = []

    def status(self, message):
        self.status_messages.append(message)

    def error(self, message):
        self.error_messages.append(message)


class FieldJoystickControlTests(unittest.TestCase):
    def _service(self, heading=0.0):
        manual = FakeManualDrivePort()
        canonical_heading_query = MutableHeadingQuery(heading)
        field_reference = FieldHeadingReferenceService(
            canonical_heading_query
        )
        service = build_joystick_service(
            FakeJoystickPort(),
            manual,
            "Wireless Controller",
            max_speed_sp=600,
            operation_mode=RoverOperationMode(
                drive=Drives.MECANUM,
                centric=Centrics.FIELD
            ),
            heading_query_port=field_reference,
            field_heading_reference_port=field_reference,
            field_recenter_enabled=True,
            field_recenter_requires_neutral=True,
            field_recenter_button_code=307,
            logger=RecordingLogger()
        )
        service._acquire_manual_session()
        return service, manual, canonical_heading_query

    @staticmethod
    def _axis(service, code, value):
        service.process_event_batch([{"type": 3, "code": code, "value": value}])

    def test_field_mode_requires_explicit_heading_port(self):
        with self.assertRaisesRegex(ValueError, "HeadingQueryPort"):
            build_joystick_service(
                FakeJoystickPort(),
                FakeManualDrivePort(),
                "Wireless Controller",
                operation_mode=RoverOperationMode(
                    drive=Drives.MECANUM,
                    centric=Centrics.FIELD
                )
            )

    def test_zero_heading_matches_chassis_forward(self):
        service, manual, _ = self._service(heading=0.0)
        self._axis(service, 1, MINIMUM)
        self.assertEqual(
            (600, 600, 600, 600),
            manual.mecanum_calls[-1][1:5]
        )

    def test_clockwise_ninety_degree_heading_rotates_field_forward_left(self):
        service, manual, _ = self._service(heading=90.0)
        self._axis(service, 1, MINIMUM)
        self.assertEqual(
            (-600, 600, 600, -600),
            manual.mecanum_calls[-1][1:5]
        )

    def test_counterclockwise_heading_rotates_field_forward_right(self):
        service, manual, _ = self._service(heading=-90.0)
        self._axis(service, 1, MINIMUM)
        self.assertEqual(
            (600, -600, -600, 600),
            manual.mecanum_calls[-1][1:5]
        )

    def test_missing_heading_stops_once_and_requires_neutral_recovery(self):
        service, manual, heading = self._service(heading=0.0)
        self._axis(service, 1, MINIMUM)
        calls_before_loss = len(manual.mecanum_calls)

        heading.heading_deg = None
        self._axis(service, 0, MAXIMUM)
        self._axis(service, 0, MINIMUM)

        self.assertEqual(1, manual.emergency_stop_calls)
        self.assertEqual(calls_before_loss, len(manual.mecanum_calls))
        self.assertTrue(service._neutral_required)

        heading.heading_deg = 0.0
        self._axis(service, 1, MINIMUM)
        self.assertEqual(calls_before_loss, len(manual.mecanum_calls))
        self._axis(service, 0, CENTER)
        self._axis(service, 1, CENTER)
        self._axis(service, 3, CENTER)
        self._axis(service, 1, MINIMUM)
        self.assertEqual(
            (600, 600, 600, 600),
            manual.mecanum_calls[-1][1:5]
        )

    def test_field_heading_is_checked_after_bluetooth_and_motor_startup(self):
        service, _, heading = self._service(heading=None)
        with self.assertRaisesRegex(RuntimeError, "Gyro heading"):
            service._verify_runtime_dependencies()
        heading.heading_deg = 0.0
        service._verify_runtime_dependencies()

    def test_triangle_redefines_field_zero_without_resetting_sensor(self):
        service, _, canonical_heading = self._service(heading=72.0)

        service.process_event_batch([{"type": 1, "code": 307, "value": 1}])

        self.assertEqual(0.0, service.heading_query_port.get_heading_deg())
        canonical_heading.heading_deg = 92.0
        self.assertEqual(20.0, service.heading_query_port.get_heading_deg())
        self.assertTrue(any(
            "72.00 deg" in message
            for message in service.logger.status_messages
        ))

    def test_triangle_is_rejected_while_traction_controls_are_active(self):
        service, _, canonical_heading = self._service(heading=45.0)
        self._axis(service, 1, MINIMUM)

        service.process_event_batch([{"type": 1, "code": 307, "value": 1}])

        self.assertEqual(45.0, service.heading_query_port.get_heading_deg())
        canonical_heading.heading_deg = 55.0
        self.assertEqual(55.0, service.heading_query_port.get_heading_deg())
        self.assertTrue(any(
            "must be neutral" in message
            for message in service.logger.error_messages
        ))

    def test_triangle_is_rejected_without_fresh_heading(self):
        service, _, _ = self._service(heading=None)

        service.process_event_batch([{"type": 1, "code": 307, "value": 1}])

        self.assertTrue(any(
            "heading unavailable" in message
            for message in service.logger.error_messages
        ))

    def test_batched_triangle_press_is_not_lost_by_release_event(self):
        service, _, canonical_heading = self._service(heading=30.0)

        service.process_event_batch([
            {"type": 1, "code": 307, "value": 1},
            {"type": 1, "code": 307, "value": 0}
        ])

        self.assertEqual(0.0, service.heading_query_port.get_heading_deg())
        canonical_heading.heading_deg = 40.0
        self.assertEqual(10.0, service.heading_query_port.get_heading_deg())

    def test_batched_recenter_rejects_non_neutral_axis_in_same_cycle(self):
        service, _, _ = self._service(heading=30.0)

        service.process_event_batch([
            {"type": 1, "code": 307, "value": 1},
            {"type": 3, "code": 1, "value": MINIMUM}
        ])

        self.assertEqual(30.0, service.heading_query_port.get_heading_deg())
        self.assertTrue(any(
            "must be neutral" in message
            for message in service.logger.error_messages
        ))

    def test_emergency_stop_has_priority_over_recenter_in_same_batch(self):
        service, manual, _ = self._service(heading=30.0)

        service.process_event_batch([
            {"type": 1, "code": 307, "value": 1},
            {"type": 1, "code": 304, "value": 1}
        ])

        self.assertEqual(1, manual.emergency_stop_calls)
        self.assertEqual(30.0, service.heading_query_port.get_heading_deg())
        self.assertFalse(service.logger.status_messages)


class FieldHeadingReferenceServiceTests(unittest.TestCase):
    def test_reference_service_preserves_canonical_heading_before_recenter(self):
        canonical = MutableHeadingQuery(125.0)
        reference = FieldHeadingReferenceService(canonical)

        self.assertEqual(125.0, reference.get_heading_deg())
        snapshot = reference.get_heading_snapshot()
        self.assertEqual(125.0, snapshot["canonical_heading_deg"])
        self.assertEqual(0.0, snapshot["reference_heading_deg"])
        self.assertEqual(125.0, snapshot["heading_deg"])

    def test_reference_service_recenter_is_runtime_only_and_normalized(self):
        canonical = MutableHeadingQuery(170.0)
        reference = FieldHeadingReferenceService(canonical)

        result = reference.set_current_heading_as_zero()
        canonical.heading_deg = -170.0

        self.assertTrue(result["success"])
        self.assertEqual(20.0, reference.get_heading_deg())
        self.assertEqual(-170.0, canonical.get_heading_deg())

    def test_reference_service_rejects_stale_sample_without_losing_zero(self):
        canonical = MutableHeadingQuery(40.0)
        reference = FieldHeadingReferenceService(canonical)
        reference.set_current_heading_as_zero()
        canonical.heading_deg = None

        result = reference.set_current_heading_as_zero()

        self.assertFalse(result["success"])
        self.assertIsNone(reference.get_heading_deg())
        canonical.heading_deg = 50.0
        self.assertEqual(10.0, reference.get_heading_deg())


class FakePhysicalGyro(object):
    def __init__(self):
        self.mode = "GYRO-RATE"
        self.angle = 12
        self.reset_calls = 0

    def reset(self):
        self.reset_calls += 1
        self.angle = 0


class GyroAdapterAndMonitorTests(unittest.TestCase):
    def test_ev3_adapter_configures_and_resets_sensor_once(self):
        sensor = FakePhysicalGyro()
        adapter = Ev3GyroSensorAdapter(
            address="in3",
            mode="GYRO-ANG",
            reset_on_start=True,
            sensor_factory=lambda address: sensor
        )
        self.assertIs(sensor, adapter.open())
        self.assertEqual("GYRO-ANG", sensor.mode)
        self.assertEqual(1, sensor.reset_calls)
        self.assertEqual(0.0, adapter.read_heading_deg())
        self.assertIs(sensor, adapter.open())
        self.assertEqual(1, sensor.reset_calls)
        adapter.close()

    def test_ev3_adapter_prepares_uart_port_before_sensor_connection(self):
        events = []

        class FakePort(object):
            def __init__(self):
                self.modes = ("auto", "ev3-analog", "ev3-uart")
                self._mode = "ev3-analog"

            @property
            def mode(self):
                return self._mode

            @mode.setter
            def mode(self, value):
                events.append(("port_mode", value))
                self._mode = value

        port = FakePort()
        sensor = FakePhysicalGyro()
        attempts = [RuntimeError("not enumerated"), sensor]
        clock_values = iter([0.0, 0.01])

        def sensor_factory(address):
            events.append(("sensor_factory", address, port.mode))
            result = attempts.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        adapter = Ev3GyroSensorAdapter(
            address="in3",
            port_mode="ev3-uart",
            reset_on_start=False,
            connection_timeout_seconds=1.0,
            connection_retry_seconds=0.1,
            sensor_factory=sensor_factory,
            port_factory=lambda address: port,
            clock=lambda: next(clock_values),
            sleeper=lambda seconds: events.append(("sleep", seconds))
        )

        self.assertIs(sensor, adapter.open())
        self.assertEqual("ev3-uart", port.mode)
        self.assertEqual(("port_mode", "ev3-uart"), events[0])
        self.assertEqual(
            ("sensor_factory", "in3", "ev3-uart"), events[1]
        )
        self.assertEqual(0.1, events[2][1])
        self.assertEqual(
            ("sensor_factory", "in3", "ev3-uart"), events[3]
        )

    def test_ev3_adapter_reports_port_and_last_detection_error(self):
        port = type(
            "Port", (),
            {"modes": ("ev3-uart",), "mode": "ev3-uart"}
        )()
        clock_values = iter([0.0, 1.0])
        adapter = Ev3GyroSensorAdapter(
            address="in3",
            port_mode="ev3-uart",
            connection_timeout_seconds=0.5,
            connection_retry_seconds=0.1,
            sensor_factory=lambda address: (_ for _ in ()).throw(
                RuntimeError("device missing")
            ),
            port_factory=lambda address: port,
            clock=lambda: next(clock_values),
            sleeper=lambda seconds: None
        )

        with self.assertRaisesRegex(
                RuntimeError,
                "Gyroscope was not detected at in3.*device missing"):
            adapter.open()

    def test_ev3_adapter_normalizes_reversed_mounting_before_publication(self):
        sensor = FakePhysicalGyro()
        adapter = Ev3GyroSensorAdapter(
            reset_on_start=False,
            angle_sign=-1.0,
            sensor_factory=lambda address: sensor
        )
        adapter.open()
        self.assertEqual(-12.0, adapter.read_heading_deg())

    def test_ev3_adapter_applies_offset_after_mounting_sign(self):
        sensor = FakePhysicalGyro()
        adapter = Ev3GyroSensorAdapter(
            reset_on_start=False,
            angle_sign=-1.0,
            angle_offset_deg=5.0,
            sensor_factory=lambda address: sensor
        )
        adapter.open()
        self.assertEqual(-7.0, adapter.read_heading_deg())

    def test_ev3_adapter_rejects_non_sign_calibration(self):
        with self.assertRaisesRegex(ValueError, "either -1.0 or 1.0"):
            Ev3GyroSensorAdapter(angle_sign=0.5)

    def test_ev3_adapter_normalizes_short_input_address(self):
        ev3dev2_module = types.ModuleType("ev3dev2")
        ev3dev2_module.__path__ = []
        sensor_module = types.ModuleType("ev3dev2.sensor")
        sensor_module.__path__ = []
        sensor_module.INPUT_1 = "ev3-ports:in1"
        sensor_module.INPUT_2 = "ev3-ports:in2"
        sensor_module.INPUT_3 = "ev3-ports:in3"
        sensor_module.INPUT_4 = "ev3-ports:in4"
        lego_module = types.ModuleType("ev3dev2.sensor.lego")
        port_module = types.ModuleType("ev3dev2.port")

        class FakeGyroSensor(object):
            pass

        class FakeLegoPort(object):
            pass

        lego_module.GyroSensor = FakeGyroSensor
        port_module.LegoPort = FakeLegoPort
        modules = {
            "ev3dev2": ev3dev2_module,
            "ev3dev2.port": port_module,
            "ev3dev2.sensor": sensor_module,
            "ev3dev2.sensor.lego": lego_module
        }
        with mock.patch.dict(sys.modules, modules):
            loaded = Ev3GyroSensorAdapter._load_ev3_factories("in3")

        self.assertIs(FakeGyroSensor, loaded[0])
        self.assertIs(FakeLegoPort, loaded[1])
        self.assertEqual("ev3-ports:in3", loaded[2])

    def test_heading_query_rejects_stale_samples_without_hardware_read(self):
        now = [10.0]
        store = HeadingStateStore()
        store.update(42.0, sample_monotonic=10.0)
        query = HeadingStateQueryAdapter(
            store, max_age_seconds=0.1, clock=lambda: now[0]
        )
        self.assertEqual(42.0, query.get_heading_deg())
        now[0] = 10.101
        self.assertIsNone(query.get_heading_deg())
        self.assertFalse(query.get_heading_snapshot()["fresh"])

    def test_monitor_publishes_only_gyro_samples(self):
        class Sensor(object):
            def __init__(self):
                self.open_calls = 0
                self.close_calls = 0
                self.values = [10.0, 11.0]

            def open(self):
                self.open_calls += 1

            def read_heading_deg(self):
                return self.values.pop(0)

            def close(self):
                self.close_calls += 1

        sensor = Sensor()
        store = HeadingStateStore()
        clock = iter([1.0, 2.0])
        monitor = GyroHeadingMonitor(
            sensor, store, interval_seconds=0.02,
            clock=lambda: next(clock)
        )
        monitor.on_initialize()
        self.assertEqual(10.0, store.get_snapshot()["heading_deg"])
        monitor.on_cycle()
        self.assertEqual(11.0, store.get_snapshot()["heading_deg"])
        monitor.on_finalize()
        self.assertEqual((1, 1), (sensor.open_calls, sensor.close_calls))

    def test_field_graph_registers_only_critical_gyro_monitor(self):
        configuration = resolved_configuration({
            "application_name": "Rover DR",
            "application_version": "0.58.0",
            "hardware_enabled": True,
            "shutdown_token": "shutdown",
            "hardware_api_token": "hardware",
            "sensor_definitions": {
                "GYR": {
                    "name": "Gyroscope",
                    "address": "in3",
                    "mode": "GYRO-ANG",
                    "unit": "deg",
                    "supported_modes": ["GYRO-ANG", "GYRO-RATE"]
                }
            },
            "motor_definitions": {},
            "drive": {"gyro_sensor_code": "GYR"},
            "mecanum": {},
            "field_heading": {
                "sensor_code": "GYR",
                "poll_seconds": 0.02,
                "max_age_seconds": 0.1
            },
            "joystick": {"device_name": "Wireless Controller"}
        })
        application = build_local_manual_application(
            configuration,
            operation_mode_service=RoverOperationMode(
                drive=Drives.MECANUM,
                centric=Centrics.FIELD
            )
        )
        self.assertEqual(1, len(application.monitor_registrations))
        registration = application.monitor_registrations[0]
        self.assertEqual("Gyro Heading", registration.name)
        self.assertTrue(registration.critical)
        self.assertIsInstance(registration.component, GyroHeadingMonitor)
        self.assertEqual(1, len(application.monitors))
        joystick_service = application.runtime_components[-1]
        self.assertIsInstance(
            joystick_service.heading_query_port,
            FieldHeadingReferenceService
        )
        self.assertIs(
            joystick_service.heading_query_port,
            joystick_service.field_heading_reference_port
        )
        self.assertEqual(304, joystick_service.stop_button_code)
        self.assertEqual(307, joystick_service.field_recenter_button_code)
        self.assertTrue(joystick_service.field_recenter_enabled)
        self.assertTrue(joystick_service.field_recenter_requires_neutral)


if __name__ == "__main__":
    unittest.main()
