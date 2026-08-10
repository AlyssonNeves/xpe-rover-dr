#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for the direct, no-queue manual motor-control service."""

from services.manual_drive_service import ManualDriveService


DRIVE = {"left_motor_code": "LLM", "right_motor_code": "RLM"}
JOYSTICK = {
    "left_auxiliary_motor_code": "LMM",
    "right_auxiliary_motor_code": "RMM"
}


class FakeHardware(object):
    def __init__(self):
        self.ensure_calls = []
        self.run_calls = []
        self.stop_calls = []
        self.errors = {}
        self.run_failures = {}
        self.stop_failures = {}

    def get_motor_definition(self, motor_code):
        return {"code": motor_code}

    def ensure_connected(self, motor_code):
        self.ensure_calls.append(motor_code)
        if motor_code in self.errors:
            return None
        return object()

    def get_error(self, motor_code):
        return self.errors.get(motor_code)

    def run_forever(self, motor_code, speed_sp):
        self.run_calls.append((motor_code, speed_sp))
        error = self.run_failures.get(motor_code)
        return {"success": error is None, "hardware_error": error}

    def stop(self, motor_code, stop_action=None, connected_only=False):
        self.stop_calls.append((motor_code, stop_action, connected_only))
        error = self.stop_failures.get(motor_code)
        return {"success": error is None, "hardware_error": error}


def build_service(hardware=None):
    hardware = hardware or FakeHardware()
    service = ManualDriveService(
        hardware, DRIVE, JOYSTICK, default_stop_action="brake"
    )
    return service, hardware


def acquire_service(hardware=None):
    service, hardware = build_service(hardware)
    result = service.acquire("session-1")
    assert result["success"] is True
    return service, hardware


def test_acquire_preconnects_and_safely_stops_all_manual_motors():
    service, hardware = acquire_service()

    assert hardware.ensure_calls == ["LLM", "RLM", "LMM", "RMM"]
    assert [item[0] for item in hardware.stop_calls] == [
        "LLM", "RLM", "LMM", "RMM"
    ]
    assert all(item[2] is True for item in hardware.stop_calls)


def test_drive_setpoints_are_written_synchronously_without_watchdog():
    service, hardware = acquire_service()
    hardware.run_calls[:] = []

    result = service.apply_drive_setpoint("session-1", 600, 450)

    assert result == {
        "success": True,
        "direct_hardware": True,
        "watchdog_enabled": False,
        "setpoint": (600, 450)
    }
    assert hardware.run_calls == [("LLM", 600), ("RLM", 450)]


def test_zero_drive_setpoint_stops_both_traction_motors():
    service, hardware = acquire_service()
    hardware.stop_calls[:] = []

    result = service.apply_drive_setpoint("session-1", 0, 0)

    assert result["success"] is True
    assert [item[0] for item in hardware.stop_calls] == ["LLM", "RLM"]


def test_right_motor_failure_rolls_back_both_traction_motors():
    hardware = FakeHardware()
    service, hardware = acquire_service(hardware)
    hardware.stop_calls[:] = []
    hardware.run_failures["RLM"] = "right motor failed"

    result = service.apply_drive_setpoint("session-1", 500, 500)

    assert result["success"] is False
    assert result["failed_motor_code"] == "RLM"
    assert [item[0] for item in hardware.stop_calls] == ["LLM", "RLM"]


def test_auxiliary_motor_uses_same_direct_hardware_path():
    service, hardware = acquire_service()
    hardware.run_calls[:] = []

    result = service.apply_auxiliary_setpoint("session-1", "LMM", -400)

    assert result["success"] is True
    assert result["watchdog_enabled"] is False
    assert hardware.run_calls == [("LMM", -400)]


def test_emergency_stop_is_synchronous_for_every_owned_motor():
    service, hardware = acquire_service()
    hardware.stop_calls[:] = []

    result = service.emergency_stop()

    assert result["success"] is True
    assert [item[0] for item in hardware.stop_calls] == [
        "LLM", "RLM", "LMM", "RMM"
    ]


def test_acquire_failure_rolls_back_only_previously_connected_motors():
    hardware = FakeHardware()
    hardware.errors["LMM"] = "not connected"
    service, hardware = build_service(hardware)

    result = service.acquire("session-1")

    assert result["success"] is False
    assert result["failed_motor_code"] == "LMM"
    assert [item[0] for item in hardware.stop_calls] == ["LLM", "RLM"]


def test_second_session_cannot_take_manual_motor_ownership():
    service, _ = acquire_service()

    result = service.acquire("session-2")

    assert result["success"] is False
    assert "already owned" in result["error"]


class RecordingStatePublisher(object):
    def __init__(self):
        self.published = []

    def publish_motor_state(self, motor_code, state):
        self.published.append((motor_code, dict(state)))


def test_direct_drive_publishes_state_through_dedicated_port():
    hardware = FakeHardware()
    publisher = RecordingStatePublisher()
    service = ManualDriveService(
        hardware, DRIVE, JOYSTICK, default_stop_action="brake",
        motor_state_publisher_port=publisher
    )
    assert service.acquire("session-1")["success"] is True
    publisher.published[:] = []

    result = service.apply_drive_setpoint("session-1", 500, -400)

    assert result["success"] is True
    assert [(code, state["speed"]) for code, state in publisher.published] == [
        ("LLM", 500), ("RLM", -400)
    ]
    assert all(
        state["source"] == "local-manual-direct"
        for _, state in publisher.published
    )
    assert all(
        state["watchdog_enabled"] is False
        for _, state in publisher.published
    )


def test_emergency_stop_publishes_stopped_state_without_using_store_directly():
    hardware = FakeHardware()
    publisher = RecordingStatePublisher()
    service = ManualDriveService(
        hardware, DRIVE, JOYSTICK, default_stop_action="brake",
        motor_state_publisher_port=publisher
    )
    assert service.acquire("session-1")["success"] is True
    publisher.published[:] = []

    result = service.emergency_stop()

    assert result["success"] is True
    assert [code for code, _ in publisher.published] == [
        "LLM", "RLM", "LMM", "RMM"
    ]
    assert all(state["speed"] == 0 for _, state in publisher.published)
    assert all(state["state"] == [] for _, state in publisher.published)
