#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for local manual joystick control."""

import time
import unittest

from app.operation_mode_service import (
    DifferentialModes, Drives, Fronts, RoverOperationMode
)
from app.rover_config import DEFAULT_CONFIGURATION
from app.services.joystick_control_service import (
    JoystickControlService as _JoystickControlService
)


CENTER = 127
MINIMUM = 0
MAXIMUM = 255


def local_mode(front=Fronts.NOSE, drive=Drives.DIFFERENTIAL,
               centric=None, differential_mode=None):
    return RoverOperationMode(
        front=front,
        drive=drive,
        centric=centric,
        differential_mode=differential_mode
    )


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
        "mecanum_strafe_compensation": 1.0,
        # Generic joystick tests use the Duowhell mechanical convention
        # explicitly. Canonical startup defaults are tested separately.
        "operation_mode": local_mode(
            differential_mode=DifferentialModes.DUOWHELL
        )
    }
    values.update(overrides)
    return _JoystickControlService(*args, **values)


def wait_until(predicate, timeout=1.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


class FakeJoystickPort(object):
    def open(self):
        return "Wireless Controller"

    def read_event_batch(self, timeout_seconds, max_events):
        del timeout_seconds
        del max_events
        return []

    def close(self):
        pass


class FakeJoystickConnectionStatusPort(object):
    def __init__(self):
        self.error_calls = []
        self.connected_calls = []

    def show_joystick_connection_error(self, message, retry_seconds):
        self.error_calls.append((message, retry_seconds))

    def show_joystick_connected(self, device_name):
        self.connected_calls.append(device_name)


class RecordingStatusLedPort(object):
    def __init__(self):
        self.calls = []

    def set_fault(self, source, active=True):
        self.calls.append((source, active))


class FakeManualDrivePort(object):
    def __init__(self):
        self.acquire_calls = []
        self.drive_calls = []
        self.mecanum_calls = []
        self.auxiliary_calls = []
        self.emergency_stop_calls = 0
        self.release_calls = []

    def acquire(self, session_id, motor_codes=None):
        self.acquire_calls.append((session_id, motor_codes))
        return {"success": True}

    def apply_drive_setpoint(
            self, session_id, left_speed_sp, right_speed_sp,
            stop_action=None):
        self.drive_calls.append((
            session_id, left_speed_sp, right_speed_sp, stop_action
        ))
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

    def apply_auxiliary_setpoint(
            self, session_id, motor_code, speed_sp, stop_action=None):
        self.auxiliary_calls.append((
            session_id, motor_code, speed_sp, stop_action
        ))
        return {"success": True}

    def emergency_stop(self, stop_action=None):
        del stop_action
        self.emergency_stop_calls += 1
        return {"success": True}

    def release(self, session_id, stop=True):
        self.release_calls.append((session_id, stop))
        return {"success": True}


class DifferentialJoystickControlServiceTests(unittest.TestCase):
    def setUp(self):
        self.manual_drive = FakeManualDrivePort()
        self.service = build_joystick_service(
            FakeJoystickPort(), self.manual_drive, "Wireless Controller",
            max_speed_sp=600, auxiliary_speed_sp=400
        )
        self.service._acquire_manual_session()

    def _axis(self, code, value):
        self.service.process_event_batch([{"type": 3, "code": code, "value": value}])

    def test_left_stick_up_drives_both_traction_motors_forward(self):
        self._axis(1, MINIMUM)

        session_id, left, right, stop_action = self.manual_drive.drive_calls[-1]
        self.assertEqual(self.service._session_id, session_id)
        self.assertEqual((600, 600), (left, right))
        self.assertIsNone(stop_action)

    def test_left_stick_down_reverses_both_traction_motors(self):
        self._axis(1, MAXIMUM)

        self.assertEqual(
            (-600, -600), self.manual_drive.drive_calls[-1][1:3]
        )

    def test_partial_left_stick_has_progressive_exponential_speed(self):
        self._axis(1, 63)
        partial = self.manual_drive.drive_calls[-1][1]
        self._axis(1, MINIMUM)
        maximum = self.manual_drive.drive_calls[-1][1]

        self.assertGreater(partial, 0)
        self.assertLess(partial, maximum)
        self.assertEqual(600, maximum)

    def test_right_stick_right_rotates_clockwise_in_place(self):
        self._axis(3, MAXIMUM)

        self.assertEqual(
            (600, -600), self.manual_drive.drive_calls[-1][1:3]
        )

    def test_right_stick_left_rotates_counterclockwise_in_place(self):
        self._axis(3, MINIMUM)

        self.assertEqual(
            (-600, 600), self.manual_drive.drive_calls[-1][1:3]
        )

    def test_arcade_drive_combines_forward_and_right_rotation(self):
        self._axis(1, MINIMUM)
        self._axis(3, 191)
        left, right = self.manual_drive.drive_calls[-1][1:3]

        self.assertEqual(600, left)
        self.assertGreater(right, 0)
        self.assertLess(right, left)

    def test_arcade_drive_normalizes_combined_output(self):
        self._axis(1, MINIMUM)
        self._axis(3, MAXIMUM)

        left, right = self.manual_drive.drive_calls[-1][1:3]
        self.assertEqual(600, left)
        self.assertEqual(0, right)
        self.assertLessEqual(max(abs(left), abs(right)), 600)

    def test_left_stick_horizontal_is_ignored_in_differential_mode(self):
        calls_before = len(self.manual_drive.drive_calls)
        self._axis(0, MAXIMUM)

        self.assertEqual(calls_before, len(self.manual_drive.drive_calls))

    def test_r2_and_l2_are_ignored_in_differential_mode(self):
        calls_before = len(self.manual_drive.drive_calls)
        self._axis(5, MAXIMUM)
        self._axis(2, MAXIMUM)

        self.assertEqual(calls_before, len(self.manual_drive.drive_calls))

    def test_stick_deadzone_produces_zero_setpoint(self):
        self._axis(1, CENTER + 7)

        self.assertEqual((0, 0), self.manual_drive.drive_calls[-1][1:3])

    def test_deadzone_is_removed_from_the_remaining_axis_travel(self):
        self.assertEqual(0.0, self.service._normalized_stick_axis(CENTER + 7))
        self.assertAlmostEqual(
            1.0 / 121.0,
            self.service._normalized_stick_axis(CENTER + 8)
        )
        self.assertEqual(1.0, self.service._normalized_stick_axis(MAXIMUM))
        self.assertEqual(-1.0, self.service._normalized_stick_axis(MINIMUM))

    def test_lower_response_intensity_increases_partial_stick_authority(self):
        intensity_two = self.service._shaped_stick_axis(191)
        intensity_four_service = build_joystick_service(
            FakeJoystickPort(), FakeManualDrivePort(), "Wireless Controller",
            axis_response_intensity=4.0
        )
        intensity_four = intensity_four_service._shaped_stick_axis(191)

        self.assertGreater(intensity_two, intensity_four)
        self.assertLess(intensity_two, 1.0)

    def test_dpad_controls_and_stops_left_auxiliary_motor(self):
        self._axis(17, -1)
        _, code, speed, _ = self.manual_drive.auxiliary_calls[-1]
        self.assertEqual(("LMM", 400), (code, speed))

        self._axis(17, 0)
        _, code, speed, _ = self.manual_drive.auxiliary_calls[-1]
        self.assertEqual(("LMM", 0), (code, speed))

    def test_horizontal_dpad_controls_right_auxiliary_motor(self):
        self._axis(16, -1)

        _, code, speed, _ = self.manual_drive.auxiliary_calls[-1]
        self.assertEqual(("RMM", 400), (code, speed))

    def test_unchanged_drive_setpoint_can_be_republished_explicitly(self):
        self._axis(1, MINIMUM)
        first_call_count = len(self.manual_drive.drive_calls)

        self.service._update_drive(force_publish=True)

        self.assertEqual(first_call_count + 1, len(self.manual_drive.drive_calls))
        self.assertEqual(
            (600, 600), self.manual_drive.drive_calls[-1][1:3]
        )

    def test_stop_button_stops_every_manual_motor(self):
        self.service.process_event_batch([{"type": 1, "code": 304, "value": 1}])

        self.assertEqual(1, self.manual_drive.emergency_stop_calls)
        self.assertTrue(self.service._neutral_required)

    def test_emergency_stop_requires_both_drive_axes_to_return_neutral(self):
        self._axis(1, MINIMUM)
        self._axis(3, MAXIMUM)
        self.service.process_event_batch([{"type": 1, "code": 304, "value": 1}])
        calls_after_stop = len(self.manual_drive.drive_calls)

        self._axis(1, CENTER)
        self.assertEqual(calls_after_stop, len(self.manual_drive.drive_calls))
        self.assertTrue(self.service._neutral_required)

        self._axis(3, CENTER)
        self.assertFalse(self.service._neutral_required)
        self.assertEqual(calls_after_stop, len(self.manual_drive.drive_calls))

        self._axis(1, MINIMUM)
        self.assertEqual((600, 600), self.manual_drive.drive_calls[-1][1:3])

    def test_motion_resumes_only_after_neutral_release(self):
        self._axis(1, MINIMUM)
        self.service.process_event_batch([{"type": 1, "code": 304, "value": 1}])
        calls_after_stop = len(self.manual_drive.drive_calls)

        self._axis(1, MINIMUM)
        self.assertEqual(calls_after_stop, len(self.manual_drive.drive_calls))
        self._axis(1, CENTER)
        self._axis(1, MINIMUM)

        self.assertEqual((600, 600), self.manual_drive.drive_calls[-1][1:3])


class MecanumJoystickControlServiceTests(unittest.TestCase):
    def setUp(self):
        self.manual_drive = FakeManualDrivePort()
        self.service = build_joystick_service(
            FakeJoystickPort(),
            self.manual_drive,
            "Wireless Controller",
            max_speed_sp=600,
            operation_mode=local_mode(drive=Drives.MECANUM),
        )
        self.service._acquire_manual_session()

    def _axis(self, code, value, service=None):
        active = service or self.service
        active.process_event_batch([{"type": 3, "code": code, "value": value}])

    def test_forward_vector_moves_immediately_without_trigger(self):
        self._axis(1, MINIMUM)

        self.assertEqual(
            (600, 600, 600, 600),
            self.manual_drive.mecanum_calls[-1][1:5]
        )

    def test_backward_vector_reverses_all_logical_wheel_setpoints(self):
        self._axis(1, MAXIMUM)

        self.assertEqual(
            (-600, -600, -600, -600),
            self.manual_drive.mecanum_calls[-1][1:5]
        )

    def test_right_strafe_uses_standard_mecanum_ratios(self):
        self._axis(0, MAXIMUM)

        self.assertEqual(
            (600, -600, -600, 600),
            self.manual_drive.mecanum_calls[-1][1:5]
        )

    def test_left_strafe_uses_opposite_standard_mecanum_ratios(self):
        self._axis(0, MINIMUM)

        self.assertEqual(
            (-600, 600, 600, -600),
            self.manual_drive.mecanum_calls[-1][1:5]
        )

    def test_forward_right_diagonal_activates_one_wheel_diagonal(self):
        self._axis(0, MAXIMUM)
        self._axis(1, MINIMUM)

        self.assertEqual(
            (600, 0, 0, 600),
            self.manual_drive.mecanum_calls[-1][1:5]
        )

    def test_right_stick_clockwise_rotation_uses_standard_ratios(self):
        self._axis(3, MAXIMUM)

        self.assertEqual(
            (600, 600, -600, -600),
            self.manual_drive.mecanum_calls[-1][1:5]
        )

    def test_right_stick_counterclockwise_rotation_reverses_ratios(self):
        self._axis(3, MINIMUM)

        self.assertEqual(
            (-600, -600, 600, 600),
            self.manual_drive.mecanum_calls[-1][1:5]
        )

    def test_translation_and_rotation_use_shared_denominator(self):
        self._axis(0, MAXIMUM)
        self._axis(1, MINIMUM)
        self._axis(3, MAXIMUM)

        self.assertEqual(
            (600, 200, -200, 200),
            self.manual_drive.mecanum_calls[-1][1:5]
        )

    def test_partial_stick_directly_controls_progressive_speed(self):
        self._axis(1, 63)
        partial = self.manual_drive.mecanum_calls[-1][1]
        self._axis(1, MINIMUM)
        maximum = self.manual_drive.mecanum_calls[-1][1]

        self.assertGreater(partial, 0)
        self.assertLess(partial, maximum)
        self.assertEqual(600, maximum)

    def test_r2_and_l2_are_ignored_in_mecanum_mode(self):
        calls_before = len(self.manual_drive.mecanum_calls)
        self._axis(5, MAXIMUM)
        self._axis(2, MAXIMUM)

        self.assertEqual(calls_before, len(self.manual_drive.mecanum_calls))

    def test_configured_strafe_compensation_matches_reference(self):
        service = build_joystick_service(
            FakeJoystickPort(), self.manual_drive, "Wireless Controller",
            max_speed_sp=600,
            operation_mode=local_mode(drive=Drives.MECANUM),
            mecanum_strafe_compensation=1.1
        )
        service._acquire_manual_session()
        self._axis(0, MAXIMUM, service)
        self._axis(1, MINIMUM, service)
        self._axis(3, MAXIMUM, service)

        self.assertEqual(
            (600, 174, -213, 213),
            self.manual_drive.mecanum_calls[-1][1:5]
        )

    def test_linux_abs_y_up_is_inverted_to_positive_forward(self):
        self.assertEqual(-1.0, self.service._normalized_stick_axis(MINIMUM))

        self._axis(1, MINIMUM)

        self.assertEqual(1.0, self.service._direction_y)

    def test_forward_profile_contains_no_physical_motor_correction(self):
        ratios = (0.25, -0.5, 0.75, 1.0)

        self.assertEqual(
            ratios, self.service._apply_mecanum_direction(ratios)
        )

    def test_tail_setup_inverts_forward_mecanum_motion(self):
        service = build_joystick_service(
            FakeJoystickPort(), self.manual_drive, "Wireless Controller",
            max_speed_sp=600,
            operation_mode=local_mode(
                front=Fronts.TAIL, drive=Drives.MECANUM
            ),
        )
        service._acquire_manual_session()
        self._axis(1, MINIMUM, service)

        self.assertEqual(
            (-600, -600, -600, -600),
            self.manual_drive.mecanum_calls[-1][1:5]
        )

    def test_tail_setup_inverts_right_strafe_relative_to_nose(self):
        service = build_joystick_service(
            FakeJoystickPort(), self.manual_drive, "Wireless Controller",
            max_speed_sp=600,
            operation_mode=local_mode(
                front=Fronts.TAIL, drive=Drives.MECANUM
            ),
        )
        service._acquire_manual_session()
        self._axis(0, MAXIMUM, service)

        self.assertEqual(
            (-600, 600, 600, -600),
            self.manual_drive.mecanum_calls[-1][1:5]
        )

    def test_tail_setup_inverts_left_strafe_relative_to_nose(self):
        service = build_joystick_service(
            FakeJoystickPort(), self.manual_drive, "Wireless Controller",
            max_speed_sp=600,
            operation_mode=local_mode(
                front=Fronts.TAIL, drive=Drives.MECANUM
            ),
        )
        service._acquire_manual_session()
        self._axis(0, MINIMUM, service)

        self.assertEqual(
            (600, -600, -600, 600),
            self.manual_drive.mecanum_calls[-1][1:5]
        )

    def test_tail_setup_maps_forward_right_diagonal_to_backward_left(self):
        service = build_joystick_service(
            FakeJoystickPort(), self.manual_drive, "Wireless Controller",
            max_speed_sp=600,
            operation_mode=local_mode(
                front=Fronts.TAIL, drive=Drives.MECANUM
            ),
        )
        service._acquire_manual_session()
        self._axis(0, MAXIMUM, service)
        self._axis(1, MINIMUM, service)

        self.assertEqual(
            (-600, 0, 0, -600),
            self.manual_drive.mecanum_calls[-1][1:5]
        )

    def test_tail_setup_preserves_operator_facing_clockwise_rotation(self):
        service = build_joystick_service(
            FakeJoystickPort(), self.manual_drive, "Wireless Controller",
            max_speed_sp=600,
            operation_mode=local_mode(
                front=Fronts.TAIL, drive=Drives.MECANUM
            ),
        )
        service._acquire_manual_session()
        self._axis(3, MAXIMUM, service)

        self.assertEqual(
            (600, 600, -600, -600),
            self.manual_drive.mecanum_calls[-1][1:5]
        )

    def test_dpad_does_not_override_medium_motors_in_mecanum_mode(self):
        self._axis(17, -1)

        self.assertEqual([], self.manual_drive.auxiliary_calls)

    def test_emergency_stop_requires_all_mecanum_axes_to_return_neutral(self):
        self._axis(0, MAXIMUM)
        self._axis(1, MINIMUM)
        self._axis(3, MAXIMUM)
        self.service.process_event_batch([{"type": 1, "code": 304, "value": 1}])
        calls_after_stop = len(self.manual_drive.mecanum_calls)

        self._axis(0, CENTER)
        self._axis(1, CENTER)
        self.assertEqual(calls_after_stop, len(self.manual_drive.mecanum_calls))
        self.assertTrue(self.service._neutral_required)

        self._axis(3, CENTER)
        self.assertFalse(self.service._neutral_required)
        self.assertEqual(calls_after_stop, len(self.manual_drive.mecanum_calls))

        self._axis(1, MINIMUM)
        self.assertEqual(
            (600, 600, 600, 600),
            self.manual_drive.mecanum_calls[-1][1:5]
        )

    def test_rejects_unsupported_mecanum_centric_value(self):
        with self.assertRaises(ValueError):
            build_joystick_service(
                FakeJoystickPort(), self.manual_drive,
                "Wireless Controller",
                operation_mode={
                    "drive": Drives.MECANUM,
                    "centric": "WORLD"
                }
            )

    def test_rejects_non_manual_operation_mode(self):
        with self.assertRaises(ValueError):
            build_joystick_service(
                FakeJoystickPort(), self.manual_drive,
                "Wireless Controller",
                operation_mode={"command": "REMOTE"}
            )


class DefaultDifferentialModeTests(unittest.TestCase):
    def test_default_canonical_differential_mode_reaches_joystick_as_r_bogie(self):
        manual_drive = FakeManualDrivePort()
        service = build_joystick_service(
            FakeJoystickPort(), manual_drive, "Wireless Controller",
            max_speed_sp=600,
            operation_mode=local_mode()
        )
        service._acquire_manual_session()

        service.process_event_batch([
            {"type": 3, "code": 1, "value": MINIMUM}
        ])

        self.assertEqual(DifferentialModes.R_BOGIE, service.differential_mode)
        self.assertEqual((-600, -600), manual_drive.drive_calls[-1][1:3])


class WheelsDirectionConventionTests(unittest.TestCase):
    def _service(self, front=Fronts.NOSE,
                 differential_mode=DifferentialModes.DUOWHELL):
        manual_drive = FakeManualDrivePort()
        service = build_joystick_service(
            FakeJoystickPort(), manual_drive, "Wireless Controller",
            max_speed_sp=600,
            operation_mode=local_mode(
                front=front, differential_mode=differential_mode
            ),
        )
        service._acquire_manual_session()
        return service, manual_drive

    def test_nose_duowhell_keeps_current_nose_direction(self):
        service, manual_drive = self._service(
            Fronts.NOSE, DifferentialModes.DUOWHELL
        )
        service.process_event_batch([{"type": 3, "code": 1, "value": MINIMUM}])
        self.assertEqual((600, 600), manual_drive.drive_calls[-1][1:3])

    def test_nose_r_bogie_reverses_current_nose_direction(self):
        service, manual_drive = self._service(
            Fronts.NOSE, DifferentialModes.R_BOGIE
        )
        service.process_event_batch([{"type": 3, "code": 1, "value": MINIMUM}])
        self.assertEqual((-600, -600), manual_drive.drive_calls[-1][1:3])

    def test_tail_duowhell_keeps_current_tail_direction(self):
        service, manual_drive = self._service(
            Fronts.TAIL, DifferentialModes.DUOWHELL
        )
        service.process_event_batch([{"type": 3, "code": 1, "value": MINIMUM}])
        self.assertEqual((-600, -600), manual_drive.drive_calls[-1][1:3])

    def test_tail_r_bogie_reverses_current_tail_direction(self):
        service, manual_drive = self._service(
            Fronts.TAIL, DifferentialModes.R_BOGIE
        )
        service.process_event_batch([{"type": 3, "code": 1, "value": MINIMUM}])
        self.assertEqual((600, 600), manual_drive.drive_calls[-1][1:3])

    def test_tail_duowhell_preserves_operator_facing_right_rotation(self):
        service, manual_drive = self._service(
            Fronts.TAIL, DifferentialModes.DUOWHELL
        )
        service.process_event_batch([{"type": 3, "code": 3, "value": MAXIMUM}])
        self.assertEqual((600, -600), manual_drive.drive_calls[-1][1:3])

    def test_r_bogie_reverses_the_complete_differential_setpoint(self):
        nose_duowhell, _ = self._service(
            Fronts.NOSE, DifferentialModes.DUOWHELL
        )
        nose_r_bogie, _ = self._service(
            Fronts.NOSE, DifferentialModes.R_BOGIE
        )
        self.assertEqual(
            tuple(-value for value in nose_duowhell._apply_differential_direction(120, -80)),
            nose_r_bogie._apply_differential_direction(120, -80)
        )

    def test_tail_setup_reassigns_forward_right_curve(self):
        service, manual_drive = self._service(
            Fronts.TAIL, DifferentialModes.DUOWHELL
        )
        service.process_event_batch([{"type": 3, "code": 1, "value": MINIMUM}])
        service.process_event_batch([{"type": 3, "code": 3, "value": MAXIMUM}])
        self.assertEqual((0, -600), manual_drive.drive_calls[-1][1:3])


class JoystickSetupValidationTests(unittest.TestCase):
    def test_rejects_non_positive_response_intensity(self):
        with self.assertRaisesRegex(
                ValueError, "axis_response_intensity"):
            build_joystick_service(
                FakeJoystickPort(), FakeManualDrivePort(),
                "Wireless Controller", axis_response_intensity=0.0
            )

    def test_rejects_deadzone_that_consumes_an_axis_side(self):
        with self.assertRaisesRegex(ValueError, "axis_deadzone"):
            build_joystick_service(
                FakeJoystickPort(), FakeManualDrivePort(),
                "Wireless Controller", axis_deadzone=127
            )

    def test_rejects_unsupported_drive(self):
        with self.assertRaises(ValueError):
            build_joystick_service(
                FakeJoystickPort(), FakeManualDrivePort(),
                "Wireless Controller", operation_mode={"drive": "TRACKS"}
            )

    def test_rejects_unsupported_front(self):
        with self.assertRaises(ValueError):
            build_joystick_service(
                FakeJoystickPort(), FakeManualDrivePort(),
                "Wireless Controller", operation_mode={"front": "SIDEWAYS"}
            )


class RecordingLogger(object):
    def __init__(self):
        self.status_messages = []
        self.warning_messages = []
        self.error_messages = []

    def status(self, message):
        self.status_messages.append(message)

    def warning(self, message):
        self.warning_messages.append(message)

    def error(self, message):
        self.error_messages.append(message)


class InitiallyUnavailableJoystickPort(object):
    def __init__(self):
        self.open_calls = 0
        self.closed_calls = 0
        self.events = []

    def is_available(self):
        return self.open_calls > 0

    def open(self):
        self.open_calls += 1
        if self.open_calls == 1:
            raise RuntimeError("Joystick was not found")
        self.events = [
            {"type": 3, "code": 1, "value": MINIMUM},
            None
        ]
        return "Wireless Controller"

    def refresh_absolute_state(self, axis_codes):
        return dict((code, CENTER) for code in axis_codes)

    def read_event_batch(self, timeout_seconds, max_events):
        del timeout_seconds
        events = []
        while self.events and len(events) < max_events:
            event = self.events.pop(0)
            if event is None:
                break
            events.append(event)
        return events

    def close(self):
        self.closed_calls += 1


def test_prepare_start_resolves_bluetooth_before_motor_session():
    joystick = InitiallyUnavailableJoystickPort()
    manual_drive = FakeManualDrivePort()
    connection_status = FakeJoystickConnectionStatusPort()
    progress = RecordingStartupProgressPort()
    status_led = RecordingStatusLedPort()
    service = build_joystick_service(
        joystick, manual_drive, "Wireless Controller",
        connection_retry_seconds=0.01,
        connection_status_port=connection_status,
        startup_progress_port=progress,
        status_led_port=status_led
    )

    service.prepare_start()

    assert joystick.open_calls == 2
    assert connection_status.error_calls[:2] == [
        ("Joystick not found. Trying to connect.", 0.05),
        ("Joystick still not found. Starting a new search.", 0.05)
    ]
    assert progress.messages[0] == (
        "Joystick connected. Starting control initialization."
    )
    assert len(manual_drive.acquire_calls) == 1
    assert manual_drive.emergency_stop_calls == 0
    assert service._prepared_device_name == "Wireless Controller"


def test_initialization_progress_starts_only_after_joystick_connection():
    joystick = InitiallyUnavailableJoystickPort()
    manual_drive = FakeManualDrivePort()
    logger = RecordingLogger()
    connection_status = FakeJoystickConnectionStatusPort()
    progress = RecordingStartupProgressPort()
    service = build_joystick_service(
        joystick, manual_drive, "Wireless Controller",
        poll_seconds=0.001, connection_retry_seconds=0.01, logger=logger,
        connection_status_port=connection_status,
        startup_progress_port=progress,
        neutral_stability_seconds=0.01, neutral_poll_seconds=0.005
    )

    service.start()
    assert wait_until(lambda: len(manual_drive.drive_calls) == 1)
    service.stop()

    assert progress.messages[0] == (
        "Joystick connected. Starting control initialization."
    )
    assert any(
        message.startswith("Joystick opened in ")
        for message in progress.messages
    )
    assert connection_status.error_calls[:2] == [
        ("Joystick not found. Trying to connect.", 0.05),
        ("Joystick still not found. Starting a new search.", 0.05)
    ]

def test_initially_missing_joystick_is_retried_and_connected_safely():
    joystick = InitiallyUnavailableJoystickPort()
    manual_drive = FakeManualDrivePort()
    logger = RecordingLogger()
    connection_status = FakeJoystickConnectionStatusPort()
    status_led = RecordingStatusLedPort()
    service = build_joystick_service(
        joystick, manual_drive, "Wireless Controller",
        poll_seconds=0.001, connection_retry_seconds=0.01, logger=logger,
        connection_status_port=connection_status,
        status_led_port=status_led,
        neutral_stability_seconds=0.01, neutral_poll_seconds=0.005
    )

    service.start()
    assert wait_until(lambda: len(manual_drive.drive_calls) == 1)
    service.stop()

    assert joystick.open_calls >= 2
    assert len(manual_drive.acquire_calls) == 1
    assert manual_drive.drive_calls[0][1:3] == (600, 600)
    assert any(
        "Joystick still not found" in item
        for item in logger.warning_messages
    )
    assert not any(
        "Joystick still not found" in item
        for item in logger.error_messages
    )
    assert any("Joystick connected" in item for item in logger.status_messages)
    assert connection_status.error_calls[:2] == [
        ("Joystick not found. Trying to connect.", 0.05),
        ("Joystick still not found. Starting a new search.", 0.05)
    ]
    assert connection_status.connected_calls == ["Wireless Controller"]
    assert ("bluetooth", True) in status_led.calls
    assert ("bluetooth", False) in status_led.calls
    assert ("control_initialization", False) in status_led.calls
    assert ("motor", False) in status_led.calls


class DisconnectThenReconnectJoystickPort(object):
    def __init__(self):
        self.open_calls = 0
        self.closed_calls = 0
        self.events = []
        self.snapshot_calls = 0

    def open(self):
        self.open_calls += 1
        self.snapshot_calls = 0
        self.events = [
            {"type": 3, "code": 1, "value": MINIMUM},
            None
        ]
        return "Wireless Controller"

    def refresh_absolute_state(self, axis_codes):
        self.snapshot_calls += 1
        values = dict((code, CENTER) for code in axis_codes)
        if self.open_calls > 1 and self.snapshot_calls == 1:
            values[1] = MINIMUM
        return values

    def read_event_batch(self, timeout_seconds, max_events):
        del timeout_seconds
        events = []
        while self.events and len(events) < max_events:
            event = self.events.pop(0)
            if event is None:
                break
            events.append(event)
        if not events and not self.events and self.open_calls == 1:
            raise OSError("Bluetooth joystick disconnected")
        return events

    def close(self):
        self.closed_calls += 1


def test_disconnect_stops_releases_reconnects_and_requires_neutral():
    joystick = DisconnectThenReconnectJoystickPort()
    manual_drive = FakeManualDrivePort()
    connection_status = FakeJoystickConnectionStatusPort()
    service = build_joystick_service(
        joystick, manual_drive, "Wireless Controller",
        poll_seconds=0.001, connection_retry_seconds=0.01,
        connection_status_port=connection_status,
        neutral_stability_seconds=0.01, neutral_poll_seconds=0.005
    )

    service.start()
    assert wait_until(lambda: len(manual_drive.drive_calls) == 2)
    service.stop()

    assert joystick.open_calls >= 2
    assert len(manual_drive.acquire_calls) >= 2
    assert len(manual_drive.release_calls) >= 2
    assert manual_drive.emergency_stop_calls >= 2
    assert manual_drive.drive_calls[0][1:3] == (600, 600)
    assert manual_drive.drive_calls[1][1:3] == (600, 600)
    assert all(call[1:3] != (0, 0) for call in manual_drive.drive_calls)
    assert any(
        message == (
            "Joystick Bluetooth connection lost. Starting a new search."
        )
        for message, unused_retry in connection_status.error_calls
    )
    assert len(connection_status.connected_calls) >= 2


class RejectingManualDrivePort(FakeManualDrivePort):
    def apply_drive_setpoint(
            self, session_id, left_speed_sp, right_speed_sp,
            stop_action=None):
        self.drive_calls.append((
            session_id, left_speed_sp, right_speed_sp, stop_action
        ))
        return {
            "success": False,
            "error": "LargeMotor(outD) is not connected.",
            "failed_motor_code": "RLM",
            "rolled_back": True
        }


def test_hardware_rejection_terminates_manual_session_without_watchdog_cycle():
    manual_drive = RejectingManualDrivePort()
    service = build_joystick_service(
        FakeJoystickPort(), manual_drive, "Wireless Controller"
    )
    service._session_id = "manual-session"

    service.process_event_batch([{"type": 3, "code": 1, "value": MINIMUM}])
    assert wait_until(lambda: service._session_id is None)

    assert service._session_id is None
    assert service._neutral_required is True
    assert service._last_drive == (0, 0)
    assert manual_drive.release_calls == [("manual-session", True)]



def test_only_public_batch_event_contract_remains():
    service = build_joystick_service(
        FakeJoystickPort(), FakeManualDrivePort(), "Wireless Controller"
    )

    assert callable(service.process_event_batch)
    assert not hasattr(service, "handle_event")
    assert not hasattr(service, "_handle_event_batch")
    assert not hasattr(service, "_handle_differential_absolute")
    assert not hasattr(service, "_handle_mecanum_absolute")

def test_differential_event_batch_dispatches_only_newest_axis_state():
    manual_drive = FakeManualDrivePort()
    service = build_joystick_service(
        FakeJoystickPort(), manual_drive, "Wireless Controller",
        max_speed_sp=600
    )
    service._acquire_manual_session()

    service.process_event_batch([
        {"type": 3, "code": 1, "value": 63},
        {"type": 3, "code": 1, "value": 31},
        {"type": 3, "code": 1, "value": MINIMUM}
    ])

    assert len(manual_drive.drive_calls) == 1
    assert manual_drive.drive_calls[0][1:3] == (600, 600)


def test_mecanum_event_batch_combines_newest_three_axis_values_once():
    manual_drive = FakeManualDrivePort()
    service = build_joystick_service(
        FakeJoystickPort(), manual_drive, "Wireless Controller",
        max_speed_sp=600, operation_mode=local_mode(drive=Drives.MECANUM)
    )
    service._acquire_manual_session()

    service.process_event_batch([
        {"type": 3, "code": 0, "value": MINIMUM},
        {"type": 3, "code": 0, "value": MAXIMUM},
        {"type": 3, "code": 1, "value": MINIMUM},
        {"type": 3, "code": 3, "value": MAXIMUM}
    ])

    assert len(manual_drive.mecanum_calls) == 1
    assert manual_drive.mecanum_calls[0][1:5] == (600, 200, -200, 200)


if __name__ == "__main__":
    unittest.main()


class RecordingStartupProgressPort(object):
    def __init__(self):
        self.messages = []

    def show_startup_progress(self, message):
        self.messages.append(message)


class StartupMovementJoystickPort(object):
    def __init__(self):
        self.refresh_calls = []
        self.snapshot_index = 0
        self.snapshots = [
            {1: MINIMUM, 3: CENTER},
            {1: MINIMUM, 3: CENTER},
            {1: CENTER, 3: CENTER},
            {1: CENTER, 3: CENTER},
            {1: CENTER, 3: CENTER}
        ]
        self.events = [
            {"type": 3, "code": 1, "value": MINIMUM},
            None
        ]

    def open(self):
        return "Wireless Controller"

    def refresh_absolute_state(self, axis_codes):
        self.refresh_calls.append(tuple(axis_codes))
        index = min(self.snapshot_index, len(self.snapshots) - 1)
        self.snapshot_index += 1
        snapshot = self.snapshots[index]
        return dict((code, snapshot[code]) for code in axis_codes)

    def read_event_batch(self, timeout_seconds, max_events):
        del timeout_seconds
        events = []
        while self.events and len(events) < max_events:
            event = self.events.pop(0)
            if event is None:
                break
            events.append(event)
        return events

    def close(self):
        return None


def test_startup_movements_are_consumed_without_motor_dispatch_until_neutral():
    joystick = StartupMovementJoystickPort()
    manual_drive = FakeManualDrivePort()
    progress = RecordingStartupProgressPort()
    connection_status = FakeJoystickConnectionStatusPort()
    service = build_joystick_service(
        joystick, manual_drive, "Wireless Controller",
        poll_seconds=0.001,
        connection_retry_seconds=0.01,
        startup_progress_port=progress,
        connection_status_port=connection_status,
        neutral_stability_seconds=0.01, neutral_poll_seconds=0.005
    )

    service.start()
    assert wait_until(lambda: len(manual_drive.drive_calls) == 1)
    service.stop()

    assert len(joystick.refresh_calls) >= 3
    assert all(call == (1, 3) for call in joystick.refresh_calls)
    assert manual_drive.drive_calls[0][1:3] == (600, 600)
    assert manual_drive.auxiliary_calls == []
    assert any(
        message.startswith("Center joystick:")
        for message in progress.messages
    )
    assert any(
        message.startswith("Neutral detected. Verifying")
        for message in progress.messages
    )
    assert any(
        message.startswith("Joystick neutral stable")
        for message in progress.messages
    )
    assert connection_status.connected_calls == ["Wireless Controller"]


class UnreadableAxisJoystickPort(object):
    def open(self):
        return "Wireless Controller"

    def refresh_absolute_state(self, axis_codes):
        del axis_codes
        raise RuntimeError(
            "Unable to read current joystick axis code(s): 3."
        )

    def read_event_batch(self, timeout_seconds, max_events):
        del timeout_seconds
        del max_events
        return []

    def close(self):
        return None


def test_unreadable_axis_fails_explicitly_without_false_bluetooth_error():
    joystick = UnreadableAxisJoystickPort()
    manual_drive = FakeManualDrivePort()
    progress = RecordingStartupProgressPort()
    connection_status = FakeJoystickConnectionStatusPort()
    logger = RecordingLogger()
    service = build_joystick_service(
        joystick, manual_drive, "Wireless Controller",
        connection_retry_seconds=0.01,
        startup_progress_port=progress,
        connection_status_port=connection_status,
        neutral_stability_seconds=0.01,
        neutral_poll_seconds=0.005,
        logger=logger
    )

    service.start()
    assert wait_until(lambda: any(
        message.startswith("Joystick\ninitialization\nfailed. Retrying")
        for message in progress.messages
    ))
    service.stop()

    assert manual_drive.drive_calls == []
    assert connection_status.error_calls == []
    assert connection_status.connected_calls == []
    assert any(
        "Unable to read current joystick axis code(s): 3" in message
        for message in logger.error_messages
    )

def test_initialization_failure_identifies_motor_on_operator_display():
    progress = RecordingStartupProgressPort()
    logger = RecordingLogger()
    service = build_joystick_service(
        FakeJoystickPort(), FakeManualDrivePort(), "Wireless Controller",
        connection_retry_seconds=3.0, startup_progress_port=progress,
        logger=logger
    )

    service._log_connection_failure(
        RuntimeError("LargeMotor(outA) is not connected."),
        connected=True, control_ready=False
    )

    assert progress.messages[-1] == (
        "Motor\ninitialization\nfailed. Retrying\nin 3.0 s."
    )
    assert logger.status_messages[-1] == (
        "Motor initialization failed. Retrying in 3.0 s."
    )


def test_initialization_failure_identifies_sensor_on_operator_display():
    progress = RecordingStartupProgressPort()
    logger = RecordingLogger()
    service = build_joystick_service(
        FakeJoystickPort(), FakeManualDrivePort(), "Wireless Controller",
        connection_retry_seconds=3.0, startup_progress_port=progress,
        logger=logger
    )

    service._log_connection_failure(
        RuntimeError("GyroSensor(in3) is not connected."),
        connected=True, control_ready=False
    )

    assert progress.messages[-1] == (
        "Sensor\ninitialization\nfailed. Retrying\nin 3.0 s."
    )
    assert logger.status_messages[-1] == (
        "Sensor initialization failed. Retrying in 3.0 s."
    )

