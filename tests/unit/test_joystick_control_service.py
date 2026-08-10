#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for the synchronous LOCAL + MANUAL joystick path."""

import time

from ports.joystick_port import JoystickPort
from services.joystick_control_service import JoystickControlService


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
