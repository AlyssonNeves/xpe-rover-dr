import math
import pytest

from services.drive_service import DriveService
from tests.unit.fakes import FakeMotorPort, FakeSensorPort


def build_drive():
    return DriveService(
        FakeMotorPort(), FakeSensorPort(),
        config={
            "left_motor_code": "LLM", "right_motor_code": "RLM",
            "gyro_sensor_code": "GYR", "wheel_diameter_mm": 56.0,
            "track_width_mm": 120.0, "left_speed_factor": 1.0,
            "right_speed_factor": 1.0,
        }
    )


def test_drive_status_reset_and_odometry():
    drive = build_drive()
    first = drive.get_status()
    assert first["left_motor_code"] == "LLM"
    reset = drive.reset_odometry(10, 20, 30)
    assert reset["x_mm"] == 10.0
    drive.motor_port.motors["LLM"]["position"] = 360
    drive.motor_port.motors["RLM"]["position"] = 360
    drive.sensor_port.items["GYR"]["value"] = 15
    state = drive.get_status()
    assert state["pose"]["heading_deg"] == 15.0
    assert state["pose"]["distance_mm"] > 0


def test_drive_tank_stop_and_navigation_commands():
    drive = build_drive()
    tank = drive.drive_tank(200, -150, priority=5, watchdog_ms=1000)
    assert tank["accepted"] is True
    assert drive.motor_port.last_sync[0]["action"] == "run-forever"

    straight = drive.move_distance(100, 200)
    assert straight["navigation_action"] == "move-distance"
    rotate = drive.rotate_angle(90, 200)
    assert rotate["navigation_action"] == "rotate-angle"
    curve = drive.curve_radius(200, 45, 200)
    assert curve["navigation_action"] == "curve-radius"
    assert drive.stop("brake")["accepted"] is True


def test_curve_radius_rejects_too_small_radius_and_helpers():
    drive = build_drive()
    with pytest.raises(ValueError):
        drive.curve_radius(50, 45, 200)
    assert drive._normalize_angle(190) == -170.0
    degrees = drive._millimeters_to_degrees(math.pi * 56.0)
    assert degrees == 360
