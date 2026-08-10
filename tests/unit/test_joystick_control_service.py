#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for the synchronous LOCAL + MANUAL joystick path."""

import time

from ports.joystick_port import JoystickPort
from app.services.joystick_control_service import JoystickControlService


class FakeJoystickPort(JoystickPort):
    def __init__(self, events=None, read_error=None):
        self.events = list(events or [])
        self.read_error = read_error
        self.opened = False
        self.closed = False

    def open(self):
        self.opened = True
        return "Test Controller"

    def read_event(self, timeout_seconds=None):
        del timeout_seconds
        if self.events:
            return self.events.pop(0)
        if self.read_error is not None:
            error = self.read_error
            self.read_error = None
            raise error
        time.sleep(0.001)
        return None

    def close(self):
        self.closed = True


class FakeManualDrivePort(object):
    def __init__(self, acquire_success=True):
        self.acquire_success = acquire_success
        self.acquire_calls = []
        self.drive_calls = []
        self.mecanum_calls = []
        self.auxiliary_calls = []
        self.stop_calls = 0
        self.release_calls = []

    def acquire(self, session_id, motor_codes=None):
        self.acquire_calls.append((session_id, motor_codes))
        if self.acquire_success:
            return {"success": True, "direct_hardware": True}
        return {"success": False, "error": "motor unavailable"}

    def apply_drive_setpoint(self, session_id, left, right, stop_action=None):
        del stop_action
        self.drive_calls.append((session_id, left, right))
        return {"success": True, "direct_hardware": True}

    def apply_mecanum_setpoint(
            self, session_id, front_left, rear_left, front_right, rear_right,
            stop_action=None):
        del stop_action
        self.mecanum_calls.append((
            session_id, front_left, rear_left, front_right, rear_right
        ))
        return {"success": True, "direct_hardware": True}

    def apply_auxiliary_setpoint(
            self, session_id, motor_code, speed_sp, stop_action=None):
        del stop_action
        self.auxiliary_calls.append((session_id, motor_code, speed_sp))
        return {"success": True, "direct_hardware": True}

    def emergency_stop(self, stop_action=None):
        del stop_action
        self.stop_calls += 1
        return {"success": True, "direct_hardware": True}

    def release(self, session_id, stop=True):
        self.release_calls.append((session_id, stop))
        return {"success": True}


def build_service(manual_drive=None):
    joystick = FakeJoystickPort()
    manual = manual_drive or FakeManualDrivePort()
    service = JoystickControlService(
        joystick_port=joystick,
        manual_drive_port=manual,
        max_speed_sp=600,
        auxiliary_speed_sp=400,
        axis_center=127,
        axis_max=255,
        poll_seconds=0.001
    )
    return service, joystick, manual


def test_forward_and_backward_commands_follow_left_stick_y():
    service, _, manual = build_service()

    service.process_event({"type": 3, "code": 1, "value": 0})
    service.process_event({"type": 3, "code": 1, "value": 255})

    assert manual.drive_calls[0][1:] == (600, 600)
    assert manual.drive_calls[1][1:] == (-600, -600)


def test_right_stick_x_performs_arcade_rotation():
    service, _, manual = build_service()

    service.process_event({"type": 3, "code": 3, "value": 255})

    assert manual.drive_calls[-1][1:] == (600, -600)


def test_combined_translation_and_rotation_is_normalized():
    service, _, manual = build_service()

    service.process_event({"type": 3, "code": 1, "value": 0})
    service.process_event({"type": 3, "code": 3, "value": 255})

    assert manual.drive_calls[-1][1:] == (600, 0)


def test_centered_traction_and_steering_send_zero_setpoint_directly():
    service, _, manual = build_service()

    service.process_event({"type": 3, "code": 1, "value": 0})
    service.process_event({"type": 3, "code": 1, "value": 127})
    service.process_event({"type": 3, "code": 3, "value": 127})

    assert manual.drive_calls[-1][1:] == (0, 0)


def test_dpad_controls_auxiliary_motors_through_manual_drive_port():
    service, _, manual = build_service()

    service.process_event({"type": 3, "code": 17, "value": -1})
    service.process_event({"type": 3, "code": 16, "value": 1})
    service.process_event({"type": 3, "code": 17, "value": 0})

    assert ("local-manual", "LMM", 400) in manual.auxiliary_calls
    assert ("local-manual", "RMM", -400) in manual.auxiliary_calls
    assert manual.auxiliary_calls[-1] == ("local-manual", "LMM", 0)


def test_emergency_stop_button_uses_single_synchronous_stop_boundary():
    service, _, manual = build_service()

    service.process_event({"type": 1, "code": 304, "value": 1})

    assert manual.stop_calls == 1


def test_worker_acquires_manual_motors_before_processing_events():
    joystick = FakeJoystickPort([
        {"type": 3, "code": 1, "value": 0},
        {"type": 1, "code": 304, "value": 1}
    ])
    manual = FakeManualDrivePort()
    service = JoystickControlService(
        joystick, manual, poll_seconds=0.001
    )

    service.start()
    deadline = time.time() + 0.2
    while not manual.drive_calls and time.time() < deadline:
        time.sleep(0.002)
    service.stop()

    assert joystick.opened is True
    assert joystick.closed is True
    assert manual.acquire_calls == [("local-manual", None)]
    assert manual.drive_calls[0][1:] == (600, 600)
    assert manual.stop_calls >= 1
    assert manual.release_calls == [("local-manual", False)]


def test_worker_does_not_process_motion_when_motor_acquisition_fails():
    joystick = FakeJoystickPort([
        {"type": 3, "code": 1, "value": 0}
    ])
    manual = FakeManualDrivePort(acquire_success=False)
    service = JoystickControlService(
        joystick, manual, poll_seconds=0.001
    )

    service.start()
    deadline = time.time() + 0.05
    while not manual.acquire_calls and time.time() < deadline:
        time.sleep(0.002)
    service.stop()

    assert manual.acquire_calls == [("local-manual", None)]
    assert manual.drive_calls == []
    assert manual.stop_calls >= 1


def test_invalid_axis_configuration_is_rejected():
    try:
        JoystickControlService(
            FakeJoystickPort(), FakeManualDrivePort(),
            axis_center=255, axis_max=255
        )
    except ValueError as error:
        assert "axis_center" in str(error)
    else:
        raise AssertionError("Invalid axis configuration was accepted")


def test_disconnect_stops_motors_invalidates_session_and_clears_axis_state():
    joystick = FakeJoystickPort(
        events=[{"type": 3, "code": 1, "value": 0}],
        read_error=OSError("device disappeared")
    )
    manual = FakeManualDrivePort()
    service = JoystickControlService(
        joystick, manual, poll_seconds=0.001
    )

    service.start()
    deadline = time.time() + 0.2
    while service._thread.is_alive() and time.time() < deadline:
        time.sleep(0.002)

    assert service._thread.is_alive() is False
    assert manual.drive_calls[0][1:] == (600, 600)
    assert manual.stop_calls >= 1
    assert manual.release_calls == [("local-manual", True)]
    assert service._acquired is False
    assert service._translation == 0.0
    assert service._rotation == 0.0
    assert service._neutral_required is True
    assert service._neutral_pending_axes == {1, 3}


def test_post_disconnect_restart_blocks_motion_until_both_axes_are_neutral():
    joystick = FakeJoystickPort(read_error=OSError("Bluetooth lost"))
    manual = FakeManualDrivePort()
    service = JoystickControlService(
        joystick, manual, poll_seconds=0.001
    )

    service.start()
    deadline = time.time() + 0.2
    while service._thread.is_alive() and time.time() < deadline:
        time.sleep(0.002)
    assert service._neutral_required is True

    # Reappearance is explicit in S02.07; automatic reconnection belongs to
    # S02.19. Non-neutral input must not restart the Rover.
    joystick.closed = False
    joystick.events = [
        {"type": 3, "code": 1, "value": 0},
        {"type": 3, "code": 3, "value": 127},
        {"type": 3, "code": 1, "value": 127},
        {"type": 3, "code": 1, "value": 0}
    ]
    service.start()
    deadline = time.time() + 0.2
    while len(manual.drive_calls) < 1 and time.time() < deadline:
        time.sleep(0.002)
    service.stop()

    assert manual.acquire_calls == [
        ("local-manual", None), ("local-manual", None)
    ]
    assert len(manual.drive_calls) == 1
    assert manual.drive_calls[0][1:] == (600, 600)
    assert service._neutral_required is False


def test_auxiliary_motion_is_blocked_while_post_disconnect_gate_is_active():
    service, _, manual = build_service()
    service._neutral_required = True
    service._neutral_pending_axes = {1, 3}

    service.process_event({"type": 3, "code": 17, "value": -1})
    service.process_event({"type": 3, "code": 16, "value": 1})

    assert manual.auxiliary_calls == []


def test_unexpected_input_failure_still_uses_fail_safe_stop_boundary():
    joystick = FakeJoystickPort(read_error=RuntimeError("unexpected input error"))
    manual = FakeManualDrivePort()
    service = JoystickControlService(
        joystick, manual, poll_seconds=0.001
    )

    service.start()
    deadline = time.time() + 0.2
    while service._thread.is_alive() and time.time() < deadline:
        time.sleep(0.002)

    assert manual.stop_calls >= 1
    assert manual.release_calls == [("local-manual", True)]
    assert service._neutral_required is True


def test_mecanum_kinematics_use_standard_logical_wheel_ratios():
    service, _, _ = build_service()

    assert service._mecanum_setpoint(0.0, 1.0) == (600, 600, 600, 600)
    assert service._mecanum_setpoint(0.0, -1.0) == (-600, -600, -600, -600)
    assert service._mecanum_setpoint(1.0, 0.0) == (600, -600, -600, 600)
    assert service._mecanum_setpoint(-1.0, 0.0) == (-600, 600, 600, -600)


def test_mecanum_diagonal_and_rotation_share_one_normalization_denominator():
    service, _, _ = build_service()

    assert service._mecanum_setpoint(1.0, 1.0) == (600, 0, 0, 600)
    assert service._mecanum_setpoint(0.0, 0.0, 1.0) == (600, 600, -600, -600)
    assert service._mecanum_setpoint(1.0, 1.0, 1.0) == (600, 200, -200, 200)


def test_linux_evdev_y_axis_is_converted_to_positive_forward_convention():
    service, _, _ = build_service()

    assert service._normalize_axis(0) == -1.0
    assert -service._normalize_axis(0) == 1.0
    assert -service._normalize_axis(255) == -1.0


def test_stick_deadzone_produces_zero_setpoint():
    service, _, manual = build_service()

    service.process_event({"type": 3, "code": 1, "value": 134})

    assert manual.drive_calls[-1][1:] == (0, 0)


def test_deadzone_is_removed_from_remaining_axis_travel():
    service, _, _ = build_service()

    assert service._normalized_stick_axis(134) == 0.0
    assert abs(service._normalized_stick_axis(135) - (1.0 / 121.0)) < 1e-12
    assert service._normalized_stick_axis(255) == 1.0
    assert service._normalized_stick_axis(0) == -1.0


def test_exponential_response_preserves_sign_and_full_scale():
    service, _, _ = build_service()

    positive = service._shaped_stick_axis(191)
    negative = service._shaped_stick_axis(63)

    assert 0.0 < positive < 1.0
    assert -1.0 < negative < 0.0
    assert service._shaped_stick_axis(255) == 1.0
    assert service._shaped_stick_axis(0) == -1.0


def test_higher_response_intensity_softens_partial_stick_response():
    joystick = FakeJoystickPort()
    manual = FakeManualDrivePort()
    soft = JoystickControlService(
        joystick, manual, axis_deadzone=7, axis_response_intensity=1.0
    )
    stronger_curve = JoystickControlService(
        joystick, manual, axis_deadzone=7, axis_response_intensity=4.0
    )

    assert soft._shaped_stick_axis(191) > stronger_curve._shaped_stick_axis(191)


def test_joystick_rejects_deadzone_that_consumes_axis_side():
    try:
        JoystickControlService(
            FakeJoystickPort(), FakeManualDrivePort(), axis_deadzone=127
        )
    except ValueError as error:
        assert "axis_deadzone" in str(error)
    else:
        raise AssertionError("Invalid axis deadzone was accepted")


def test_joystick_rejects_non_positive_response_intensity():
    try:
        JoystickControlService(
            FakeJoystickPort(), FakeManualDrivePort(),
            axis_response_intensity=0.0
        )
    except ValueError as error:
        assert "axis_response_intensity" in str(error)
    else:
        raise AssertionError("Invalid response intensity was accepted")


def build_mecanum_service(strafe_compensation=1.0):
    joystick = FakeJoystickPort()
    manual = FakeManualDrivePort()
    service = JoystickControlService(
        joystick_port=joystick,
        manual_drive_port=manual,
        max_speed_sp=600,
        auxiliary_speed_sp=400,
        axis_center=127,
        axis_max=255,
        drive_mode=JoystickControlService.DRIVE_MECANUM,
        centric=JoystickControlService.CENTRIC_CHASSIS,
        mecanum_strafe_compensation=strafe_compensation,
        poll_seconds=0.001
    )
    return service, joystick, manual


def test_robot_centric_forward_uses_all_four_mecanum_wheels():
    service, _, manual = build_mecanum_service()

    service.process_event({"type": 3, "code": 1, "value": 0})

    assert manual.mecanum_calls[-1][1:] == (600, 600, 600, 600)
    assert manual.drive_calls == []


def test_robot_centric_right_strafe_uses_left_stick_x():
    service, _, manual = build_mecanum_service()

    service.process_event({"type": 3, "code": 0, "value": 255})

    assert manual.mecanum_calls[-1][1:] == (600, -600, -600, 600)


def test_robot_centric_right_stick_x_rotates_in_place():
    service, _, manual = build_mecanum_service()

    service.process_event({"type": 3, "code": 3, "value": 255})

    assert manual.mecanum_calls[-1][1:] == (600, 600, -600, -600)


def test_robot_centric_translation_rotation_share_one_denominator():
    service, _, manual = build_mecanum_service()

    service.process_event({"type": 3, "code": 0, "value": 255})
    service.process_event({"type": 3, "code": 1, "value": 0})
    service.process_event({"type": 3, "code": 3, "value": 255})

    assert manual.mecanum_calls[-1][1:] == (600, 200, -200, 200)


def test_strafe_compensation_is_applied_before_shared_normalization():
    service, _, manual = build_mecanum_service(strafe_compensation=1.1)

    service.process_event({"type": 3, "code": 0, "value": 255})
    service.process_event({"type": 3, "code": 1, "value": 0})
    service.process_event({"type": 3, "code": 3, "value": 255})

    assert manual.mecanum_calls[-1][1:] == (600, 174, -213, 213)


def test_dpad_is_ignored_when_medium_motors_are_mecanum_traction():
    service, _, manual = build_mecanum_service()

    service.process_event({"type": 3, "code": 17, "value": -1})
    service.process_event({"type": 3, "code": 16, "value": 1})

    assert manual.auxiliary_calls == []
    assert manual.mecanum_calls == []


def test_mecanum_disconnect_gate_requires_x_y_and_rx_neutral():
    service, _, _ = build_mecanum_service()
    service._invalidate_disconnected_session()

    assert service._neutral_pending_axes == {0, 1, 3}

    service.process_event({"type": 3, "code": 0, "value": 127})
    service.process_event({"type": 3, "code": 1, "value": 127})
    assert service._neutral_required is True
    service.process_event({"type": 3, "code": 3, "value": 127})
    assert service._neutral_required is False


def test_robot_centric_configuration_rejects_invalid_values():
    try:
        JoystickControlService(
            FakeJoystickPort(), FakeManualDrivePort(),
            drive_mode="UNKNOWN"
        )
    except ValueError as error:
        assert "drive mode" in str(error)
    else:
        raise AssertionError("Invalid drive mode was accepted")

    try:
        JoystickControlService(
            FakeJoystickPort(), FakeManualDrivePort(),
            mecanum_strafe_compensation=0.0
        )
    except ValueError as error:
        assert "strafe_compensation" in str(error)
    else:
        raise AssertionError("Invalid strafe compensation was accepted")
