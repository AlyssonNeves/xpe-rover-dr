#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for S02.22 FIELD heading runtime recenter."""

import pytest

from app.operation_mode_service import Centrics, Drives, OperationModeService
from app.services.field_heading_reference_service import FieldHeadingReferenceService
from app.services.joystick_control_service import JoystickControlService
from bootstrap import rover_assembly


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


class FakeJoystickPort(object):
    def open(self):
        return "Wireless Controller"

    def read_event_batch(self, timeout_seconds, max_events):
        del timeout_seconds, max_events
        return []

    def close(self):
        return None

    def is_available(self):
        return True


class FakeManualDrivePort(object):
    def __init__(self):
        self.mecanum_calls = []

    def acquire(self, session_id, motor_codes=None):
        del session_id, motor_codes
        return {"success": True}

    def apply_drive_setpoint(self, *args, **kwargs):
        del args, kwargs
        return {"success": True}

    def apply_mecanum_setpoint(self, session_id, *setpoint, **kwargs):
        del kwargs
        self.mecanum_calls.append((session_id,) + tuple(setpoint))
        return {"success": True}

    def apply_auxiliary_setpoint(self, *args, **kwargs):
        del args, kwargs
        return {"success": True}

    def emergency_stop(self, stop_action=None):
        del stop_action
        return {"success": True}

    def release(self, session_id, stop=True):
        del session_id, stop
        return {"success": True}


class RecordingLogger(object):
    def __init__(self):
        self.status_messages = []
        self.error_messages = []

    def status(self, message):
        self.status_messages.append(message)

    def error(self, message):
        self.error_messages.append(message)


def build_service(heading_deg=30.0):
    canonical = MutableHeadingQuery(heading_deg)
    reference = FieldHeadingReferenceService(canonical)
    logger = RecordingLogger()
    service = JoystickControlService(
        joystick_port=FakeJoystickPort(),
        manual_drive_port=FakeManualDrivePort(),
        drive_mode=Drives.MECANUM,
        centric=Centrics.FIELD,
        heading_query_port=reference,
        field_heading_reference_port=reference,
        field_recenter_enabled=True,
        field_recenter_requires_neutral=True,
        field_recenter_button_code=307,
        logger=logger
    )
    return service, canonical, reference, logger


def test_reference_service_redefines_only_operational_zero():
    canonical = MutableHeadingQuery(72.0)
    reference = FieldHeadingReferenceService(canonical)

    result = reference.set_current_heading_as_zero()

    assert result["success"] is True
    assert result["reference_heading_deg"] == 72.0
    assert reference.get_heading_deg() == 0.0
    canonical.heading_deg = 92.0
    assert reference.get_heading_deg() == 20.0
    assert canonical.get_heading_deg() == 92.0


def test_reference_service_normalizes_relative_heading():
    canonical = MutableHeadingQuery(170.0)
    reference = FieldHeadingReferenceService(canonical)
    assert reference.set_current_heading_as_zero()["success"] is True
    canonical.heading_deg = -170.0
    assert reference.get_heading_deg() == 20.0


def test_reference_service_rejects_recenter_without_fresh_heading():
    reference = FieldHeadingReferenceService(MutableHeadingQuery(None))
    assert reference.set_current_heading_as_zero() == {
        "success": False,
        "reason": "heading_unavailable"
    }


def test_reference_snapshot_keeps_canonical_heading_separate():
    canonical = MutableHeadingQuery(45.0)
    reference = FieldHeadingReferenceService(canonical)
    reference.set_current_heading_as_zero()
    canonical.heading_deg = 60.0

    snapshot = reference.get_heading_snapshot()

    assert snapshot["canonical_heading_deg"] == 60.0
    assert snapshot["reference_heading_deg"] == 45.0
    assert snapshot["heading_deg"] == 15.0


def test_triangle_redefines_field_zero_when_controls_are_neutral():
    service, canonical, reference, logger = build_service(72.0)

    service.process_event_batch([{"type": 1, "code": 307, "value": 1}])

    assert reference.get_heading_deg() == 0.0
    canonical.heading_deg = 92.0
    assert reference.get_heading_deg() == 20.0
    assert any("72.00 deg" in item for item in logger.status_messages)


def test_triangle_is_rejected_while_traction_is_active():
    service, canonical, reference, logger = build_service(45.0)
    service.process_event_batch([{"type": 3, "code": 1, "value": 0}])

    service.process_event_batch([{"type": 1, "code": 307, "value": 1}])

    assert reference.get_heading_deg() == 45.0
    canonical.heading_deg = 55.0
    assert reference.get_heading_deg() == 55.0
    assert any("must be neutral" in item for item in logger.error_messages)


def test_triangle_is_rejected_without_fresh_heading():
    service, _, _, logger = build_service(None)
    service.process_event_batch([{"type": 1, "code": 307, "value": 1}])
    assert any("heading unavailable" in item for item in logger.error_messages)


def test_field_recenter_dependency_is_required_only_when_enabled():
    with pytest.raises(ValueError, match="FieldHeadingReferenceCommandPort"):
        JoystickControlService(
            FakeJoystickPort(), FakeManualDrivePort(),
            drive_mode=Drives.MECANUM,
            centric=Centrics.FIELD,
            heading_query_port=MutableHeadingQuery(0.0),
            field_recenter_enabled=True
        )


def test_field_graph_wraps_heading_for_control_but_keeps_rest_canonical(monkeypatch):
    monkeypatch.setattr(rover_assembly.rover_config, "HARDWARE_ENABLED", False)
    canonical = MutableHeadingQuery(30.0)
    mode = OperationModeService(
        drive=Drives.MECANUM,
        centric=Centrics.FIELD
    )

    application = rover_assembly.build_local_manual_application(
        operation_mode_service=mode,
        joystick_port=FakeJoystickPort(),
        heading_query_port=canonical
    )
    joystick_services = [
        item for item in application.runtime_components
        if isinstance(item, JoystickControlService)
    ]
    assert len(joystick_services) == 1
    joystick_service = joystick_services[0]
    assert isinstance(
        joystick_service.heading_query_port, FieldHeadingReferenceService
    )
    assert joystick_service.heading_query_port is (
        joystick_service.field_heading_reference_port
    )
    assert joystick_service.field_recenter_button_code == 307
    assert joystick_service.field_recenter_enabled is True
    assert joystick_service.field_recenter_requires_neutral is True

    # REST/sensor query remains backed by the canonical source, not the
    # operator's temporary FIELD zero.
    joystick_service.field_heading_reference_port.set_current_heading_as_zero()
    canonical.heading_deg = 40.0
    assert joystick_service.heading_query_port.get_heading_deg() == 10.0
    assert canonical.get_heading_deg() == 40.0


def test_configuration_rejects_duplicate_safety_button_codes():
    from app import rover_config
    config = rover_config.get_joystick_config()
    config["button_codes"] = {"emergency_stop": 304, "field_recenter": 304}
    with pytest.raises(RuntimeError, match="distinct"):
        rover_config.validate_joystick_configuration(config)


def test_field_configuration_resolves_recenter_flags():
    from app import rover_config
    config = rover_config.get_field_heading_config()
    config["runtime_recenter_enabled"] = "false"
    config["recenter_requires_neutral"] = "true"
    resolved = rover_config.validate_field_heading_configuration(config)
    assert resolved["runtime_recenter_enabled"] is False
    assert resolved["recenter_requires_neutral"] is True
