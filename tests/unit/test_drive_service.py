#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Unit tests for high-level Rover navigation."""

import time

from app.rover_config import DEFAULT_CONFIGURATION
from app.services.drive_service import DriveService


from tests.unit.fakes import FakeDriveMotorPort, FakeDriveSensorPort


def drive_config(overrides=None):
    values = dict(DEFAULT_CONFIGURATION.drive)
    values.update(overrides or {})
    return values


def make_service():
    motor_port = FakeDriveMotorPort()
    return DriveService(
        motor_query_port=motor_port,
        drive_motor_port=motor_port,
        motor_command_port=motor_port,
        motor_command_query_port=motor_port,
        sensor_port=FakeDriveSensorPort(),
        config=drive_config({
            "control_interval_ms": 1,
            "distance_tolerance_mm": 2.0,
            "stall_timeout_ms": 100,
            "max_recovery_attempts": 0,
            "telemetry_limit": 50
        })
    )


def wait_done(service):
    for _ in range(500):
        status = service.get_status()
        if status["state"] != "RUNNING":
            return status
        time.sleep(0.002)
    return service.get_status()


def test_odometry_uses_both_wheel_encoders():
    service = make_service()
    service.reset_odometry()
    service.motor_query_port.positions["LLM"] = 360.0
    service.motor_query_port.positions["RLM"] = 360.0
    status = service.get_status()
    assert status["pose"]["x_mm"] > 170.0
    assert abs(status["pose"]["y_mm"]) < 0.01


def test_move_distance_generates_trajectory_telemetry():
    service = make_service()
    result = service.move_distance(20.0, 200)
    assert result["accepted"] is True
    status = wait_done(service)
    assert status["state"] == "COMPLETED"
    assert service.motor_query_port.drive_calls
    assert service.get_telemetry()


def test_curve_rejects_radius_inside_track_width():
    service = make_service()
    try:
        service.curve_radius(50.0, 90.0, 200)
        assert False
    except ValueError as error:
        assert "half the track width" in str(error)


def test_speed_factors_compensate_motor_difference():
    motor_port = FakeDriveMotorPort()
    service = DriveService(
        motor_query_port=motor_port,
        drive_motor_port=motor_port,
        motor_command_port=motor_port,
        motor_command_query_port=motor_port,
        sensor_port=FakeDriveSensorPort(),
        config=drive_config({
            "left_speed_factor": 0.9,
            "right_speed_factor": 1.1
        })
    )
    assert service._apply_left_factor(100) == 90
    assert service._apply_right_factor(100) == 110
