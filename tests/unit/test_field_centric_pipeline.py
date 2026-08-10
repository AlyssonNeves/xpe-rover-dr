#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for the cached FIELD-centric Mecanum pipeline introduced in S02.20."""

from adapters.out_heading_state import HeadingStateQueryAdapter
from app.operation_mode_service import Centrics, Drives, Fronts, OperationModeService
from app.services.joystick_control_service import JoystickControlService
from bootstrap.rover_assembly import build_local_manual_application
from infrastructure.state.heading_state_store import HeadingStateStore


class FakeJoystickPort(object):
    def open(self):
        return "Wireless Controller"

    def read_event(self, timeout_seconds=None):
        del timeout_seconds
        return None

    def close(self):
        return None

    def is_available(self):
        return True


class FakeManualDrivePort(object):
    def __init__(self):
        self.mecanum_calls = []
        self.stop_calls = 0

    def acquire(self, session_id, motor_codes=None):
        del session_id
        del motor_codes
        return {"success": True}

    def apply_drive_setpoint(self, *args, **kwargs):
        del args
        del kwargs
        return {"success": True}

    def apply_mecanum_setpoint(
            self, session_id, front_left, rear_left, front_right, rear_right,
            stop_action=None):
        del stop_action
        self.mecanum_calls.append((
            session_id, front_left, rear_left, front_right, rear_right
        ))
        return {"success": True}

    def apply_auxiliary_setpoint(self, *args, **kwargs):
        del args
        del kwargs
        return {"success": True}

    def emergency_stop(self, stop_action=None):
        del stop_action
        self.stop_calls += 1
        return {"success": True}

    def release(self, session_id, stop=True):
        del session_id
        del stop
        return {"success": True}


class MutableHeadingQuery(object):
    def __init__(self, heading_deg=0.0):
        self.heading_deg = heading_deg
        self.calls = 0

    def get_heading_deg(self):
        self.calls += 1
        return self.heading_deg

    def get_heading_snapshot(self):
        return {
            "fresh": self.heading_deg is not None,
            "heading_deg": self.heading_deg
        }


class RecordingLogger(object):
    def __init__(self):
        self.status_messages = []
        self.error_messages = []

    def status(self, message):
        self.status_messages.append(message)

    def error(self, message):
        self.error_messages.append(message)


def build_field_service(heading_deg=0.0):
    manual = FakeManualDrivePort()
    heading = MutableHeadingQuery(heading_deg)
    logger = RecordingLogger()
    service = JoystickControlService(
        joystick_port=FakeJoystickPort(),
        manual_drive_port=manual,
        max_speed_sp=600,
        axis_center=127,
        axis_deadzone=7,
        axis_max=255,
        axis_response_intensity=1.0,
        drive_mode=Drives.MECANUM,
        front=Fronts.NOSE,
        centric=Centrics.FIELD,
        mecanum_strafe_compensation=1.1,
        heading_query_port=heading,
        logger=logger
    )
    return service, manual, heading, logger


def axis(service, code, value):
    service.process_event({"type": 3, "code": code, "value": value})


def test_field_mode_requires_explicit_heading_query_port():
    try:
        JoystickControlService(
            FakeJoystickPort(),
            FakeManualDrivePort(),
            drive_mode=Drives.MECANUM,
            centric=Centrics.FIELD
        )
    except ValueError as error:
        assert "HeadingQueryPort" in str(error)
    else:
        raise AssertionError("FIELD mode accepted without heading query")


def test_zero_heading_matches_chassis_forward_vector():
    service, manual, _, _ = build_field_service(0.0)

    axis(service, 1, 0)

    assert manual.mecanum_calls[-1][1:] == (600, 600, 600, 600)


def test_positive_ninety_degree_heading_rotates_field_forward_left():
    service, manual, _, _ = build_field_service(90.0)

    axis(service, 1, 0)

    assert manual.mecanum_calls[-1][1:] == (-600, 600, 600, -600)


def test_negative_ninety_degree_heading_rotates_field_forward_right():
    service, manual, _, _ = build_field_service(-90.0)

    axis(service, 1, 0)

    assert manual.mecanum_calls[-1][1:] == (600, -600, -600, 600)


def test_missing_heading_stops_once_and_requires_neutral_before_recovery():
    service, manual, heading, logger = build_field_service(0.0)
    axis(service, 1, 0)
    calls_before_loss = len(manual.mecanum_calls)

    heading.heading_deg = None
    axis(service, 0, 255)
    axis(service, 0, 0)

    assert manual.stop_calls == 1
    assert len(manual.mecanum_calls) == calls_before_loss
    assert service._neutral_required is True
    assert service._field_heading_unavailable is True

    heading.heading_deg = 0.0
    axis(service, 0, 127)
    axis(service, 1, 127)
    axis(service, 3, 127)
    assert service._neutral_required is False
    assert service._field_heading_unavailable is False

    axis(service, 1, 0)
    assert manual.mecanum_calls[-1][1:] == (600, 600, 600, 600)
    assert any("heading restored" in message for message in logger.status_messages)


def test_chassis_mode_never_reads_heading_query():
    class FailingHeadingQuery(object):
        def get_heading_deg(self):
            raise AssertionError("CHASSIS path must not query heading")

    manual = FakeManualDrivePort()
    service = JoystickControlService(
        FakeJoystickPort(),
        manual,
        drive_mode=Drives.MECANUM,
        centric=Centrics.CHASSIS,
        heading_query_port=FailingHeadingQuery()
    )

    axis(service, 1, 0)

    assert manual.mecanum_calls[-1][1:] == (600, 600, 600, 600)


def test_heading_cache_adapter_rejects_stale_sample_without_sensor_io():
    store = HeadingStateStore()
    clock_values = [10.0]
    store.update(42.0, sample_monotonic=9.95)
    query = HeadingStateQueryAdapter(
        store, max_age_seconds=0.1, clock=lambda: clock_values[0]
    )

    assert query.get_heading_deg() == 42.0
    assert query.get_heading_snapshot()["fresh"] is True

    clock_values[0] = 10.2
    assert query.get_heading_deg() is None
    snapshot = query.get_heading_snapshot()
    assert snapshot["fresh"] is False
    assert snapshot["heading_deg"] == 42.0


def test_local_manual_field_graph_accepts_injected_cached_heading_source(monkeypatch):
    from bootstrap import rover_assembly

    monkeypatch.setattr(rover_assembly.rover_config, "HARDWARE_ENABLED", False)
    mode_service = OperationModeService(
        drive=Drives.MECANUM,
        centric=Centrics.FIELD
    )
    heading = MutableHeadingQuery(0.0)

    application = build_local_manual_application(
        operation_mode_service=mode_service,
        joystick_port=FakeJoystickPort(),
        heading_query_port=heading
    )

    assert application is not None


def test_local_manual_field_graph_rejects_missing_cached_heading_source(monkeypatch):
    from bootstrap import rover_assembly

    monkeypatch.setattr(rover_assembly.rover_config, "HARDWARE_ENABLED", False)
    mode_service = OperationModeService(
        drive=Drives.MECANUM,
        centric=Centrics.FIELD
    )

    try:
        build_local_manual_application(
            operation_mode_service=mode_service,
            joystick_port=FakeJoystickPort()
        )
    except RuntimeError as error:
        assert "cached heading" in str(error)
    else:
        raise AssertionError("FIELD graph accepted without cached heading")
