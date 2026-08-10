#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for the first LOCAL + MANUAL joystick control increment."""

import time

from ports.joystick_port import JoystickPort
from services.joystick_control_service import JoystickControlService


class FakeJoystickPort(JoystickPort):
    def __init__(self, events=None):
        self.events = list(events or [])
        self.opened = False
        self.closed = False

    def open(self):
        self.opened = True
        return "Test Controller"

    def read_event(self, timeout_seconds=None):
        del timeout_seconds
        if self.events:
            return self.events.pop(0)
        time.sleep(0.001)
        return None

    def close(self):
        self.closed = True


class FakeDrivePort(object):
    def __init__(self):
        self.calls = []
        self.stop_calls = 0

    def drive_tank(self, left_speed_sp, right_speed_sp, priority=None,
                   stop_action=None, watchdog_ms=None):
        del priority, stop_action, watchdog_ms
        self.calls.append((left_speed_sp, right_speed_sp))
        return {"accepted": True}

    def stop(self, stop_action=None):
        del stop_action
        self.stop_calls += 1
        return {"accepted": True}


class FakeMotorPort(object):
    def __init__(self):
        self.run_calls = []
        self.stop_calls = []

    def run_forever_motor(self, motor_code, speed_sp, priority=None,
                          stop_action=None, watchdog_ms=None, timeout_ms=None):
        del priority, stop_action, watchdog_ms, timeout_ms
        self.run_calls.append((motor_code, speed_sp))
        return {"accepted": True}

    def stop_motor(self, motor_code, stop_action=None):
        del stop_action
        self.stop_calls.append(motor_code)
        return {"accepted": True}


def build_service(motor_port=None):
    joystick = FakeJoystickPort()
    drive = FakeDrivePort()
    service = JoystickControlService(
        joystick_port=joystick,
        drive_port=drive,
        motor_port=motor_port,
        max_speed_sp=600,
        auxiliary_speed_sp=400,
        axis_center=127,
        axis_max=255,
        poll_seconds=0.001
    )
    return service, joystick, drive


def test_forward_and_backward_commands_follow_left_stick_y():
    service, _, drive = build_service()

    service.process_event({"type": 3, "code": 1, "value": 0})
    service.process_event({"type": 3, "code": 1, "value": 255})

    assert drive.calls[0] == (600, 600)
    assert drive.calls[1] == (-600, -600)


def test_right_stick_x_performs_arcade_rotation():
    service, _, drive = build_service()

    service.process_event({"type": 3, "code": 3, "value": 255})

    assert drive.calls[-1] == (600, -600)


def test_combined_translation_and_rotation_is_normalized():
    service, _, drive = build_service()

    service.process_event({"type": 3, "code": 1, "value": 0})
    service.process_event({"type": 3, "code": 3, "value": 255})

    assert drive.calls[-1] == (600, 0)


def test_centered_traction_and_steering_stop_drive():
    service, _, drive = build_service()

    service.process_event({"type": 3, "code": 1, "value": 0})
    service.process_event({"type": 3, "code": 1, "value": 127})
    service.process_event({"type": 3, "code": 3, "value": 127})

    assert drive.stop_calls >= 1


def test_dpad_controls_the_two_auxiliary_motors():
    motors = FakeMotorPort()
    service, _, _ = build_service(motors)

    service.process_event({"type": 3, "code": 17, "value": -1})
    service.process_event({"type": 3, "code": 16, "value": 1})
    service.process_event({"type": 3, "code": 17, "value": 0})

    assert ("LMM", 400) in motors.run_calls
    assert ("RMM", -400) in motors.run_calls
    assert "LMM" in motors.stop_calls


def test_emergency_stop_button_stops_drive_and_auxiliary_motors():
    motors = FakeMotorPort()
    service, _, drive = build_service(motors)

    service.process_event({"type": 1, "code": 304, "value": 1})

    assert drive.stop_calls == 1
    assert motors.stop_calls == ["LMM", "RMM"]


def test_worker_opens_port_processes_events_and_closes_safely():
    joystick = FakeJoystickPort([
        {"type": 3, "code": 1, "value": 0},
        {"type": 1, "code": 304, "value": 1}
    ])
    drive = FakeDrivePort()
    service = JoystickControlService(
        joystick, drive, poll_seconds=0.001
    )

    service.start()
    deadline = time.time() + 0.2
    while not drive.calls and time.time() < deadline:
        time.sleep(0.002)
    service.stop()

    assert joystick.opened is True
    assert joystick.closed is True
    assert drive.calls[0] == (600, 600)
    assert drive.stop_calls >= 1


def test_invalid_axis_configuration_is_rejected():
    try:
        JoystickControlService(
            FakeJoystickPort(), FakeDrivePort(),
            axis_center=255, axis_max=255
        )
    except ValueError as error:
        assert "axis_center" in str(error)
    else:
        raise AssertionError("Invalid axis configuration was accepted")
