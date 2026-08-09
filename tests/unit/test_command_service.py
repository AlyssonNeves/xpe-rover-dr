import pytest

from app.command_service import CommandService
from app.models import CommandActions as A, CommandTargets as T
from tests.unit.fakes import (
    FakeControllerPort, FakeDrivePort, FakeMotorPort, FakeRoverStatePort, FakeSensorPort,
)


@pytest.fixture
def service():
    return CommandService(
        FakeSensorPort(), FakeMotorPort(), FakeControllerPort(),
        rover_state_port=FakeRoverStatePort(), drive_port=FakeDrivePort()
    )


def test_envelope_and_target_validation(service):
    assert service.execute(None, "x").status_code == 400
    assert service.execute(T.SENSOR, None).status_code == 400
    assert service.execute(T.SENSOR, A.LIST_SENSORS, []).status_code == 400
    assert service.execute("unknown", "x").status_code == 400


def test_sensor_controller_and_rover_queries(service):
    assert service.execute(T.SENSOR, A.LIST_SENSORS).status_code == 200
    assert service.execute(T.SENSOR, A.READ_ALL_SENSORS).status_code == 200
    assert service.execute(T.SENSOR, A.READ_SENSOR, {"code": "tmp"}).data["code"] == "TMP"
    assert service.execute(T.SENSOR, A.READ_SENSOR, {"code": "BAD"}).status_code == 404
    assert service.execute(T.SENSOR, A.READ_SENSOR, {}).status_code == 400
    assert service.execute(T.CONTROLLER, A.READ_CONTROLLER_STATUS).status_code == 200
    assert service.execute(T.CONTROLLER, A.READ_CONTROLLER_NETWORK).status_code == 200
    assert service.execute(T.CONTROLLER, A.READ_CONTROLLER_BATTERY).status_code == 200
    assert service.execute(T.CONTROLLER, A.READ_CONTROLLER_SYSTEM).status_code == 200
    assert service.execute(T.ROVER, A.READ_ROVER_STATE).data["status"] == "consolidated"


def test_motor_queries_and_valid_execution(service):
    assert service.execute(T.MOTOR, A.LIST_MOTORS).status_code == 200
    assert service.execute(T.MOTOR, A.READ_ALL_MOTORS).status_code == 200
    assert service.execute(T.MOTOR, A.READ_MOTOR, {"code": "llm"}).status_code == 200
    assert service.execute(T.MOTOR, A.READ_MOTOR, {"code": "NOPE"}).status_code == 404

    result = service.execute(T.MOTOR, A.RUN_TIMED_MOTOR, {
        "code": "LLM", "speed_sp": 200, "time_sp": 500,
        "priority": 50, "stop_action": "brake", "timeout_ms": 1000,
    })
    assert result.status_code == 202
    cid = result.data["command_id"]
    assert service.execute(T.MOTOR, A.GET_MOTOR_COMMAND, {"command_id": cid}).status_code == 200
    assert service.execute(T.MOTOR, A.LIST_MOTOR_COMMANDS, {"code": "LLM"}).status_code == 200
    assert service.execute(T.MOTOR, A.CANCEL_MOTOR_COMMANDS, {"code": "LLM"}).status_code == 200
    assert service.execute(T.MOTOR, A.STOP_MOTOR, {"code": "LLM", "stop_action": "hold"}).status_code == 200
    assert service.execute(T.MOTOR, A.RESET_MOTOR, {"code": "LLM", "priority": 10}).status_code == 202


def test_motor_execution_rejects_bad_parameters(service):
    base = {"code": "LLM", "speed_sp": 200}
    assert service.execute(T.MOTOR, A.RUN_TIMED_MOTOR, dict(base, time_sp=0)).status_code == 400
    assert service.execute(T.MOTOR, A.RUN_TIMED_MOTOR, {"code": "LLM", "speed_sp": 0, "time_sp": 10}).status_code == 400
    assert service.execute(T.MOTOR, A.RUN_FOREVER_MOTOR, dict(base, watchdog_ms=50)).status_code == 400
    assert service.execute(T.MOTOR, A.RUN_TO_REL_POS_MOTOR, dict(base, position_sp=1000001)).status_code == 400
    assert service.execute(T.MOTOR, A.RESET_MOTOR, {"code": "!bad"}).status_code == 400
    assert service.execute(T.MOTOR, A.GET_MOTOR_COMMAND, {"command_id": 0}).status_code == 400
    assert service.execute(T.MOTOR, "missing", {}).status_code == 400


def test_synchronized_commands_are_normalized(service):
    result = service.execute(T.MOTOR, A.RUN_SYNCHRONIZED_MOTORS, {
        "priority": 20,
        "commands": [
            {"code": "LLM", "action": "run-timed", "speed_sp": 200, "time_sp": 100},
            {"code": "RLM", "action": "run-to-rel-pos", "speed_sp": 180, "position_sp": 90},
        ]
    })
    assert result.status_code == 202
    assert result.data["accepted"] is True
    duplicate = service.execute(T.MOTOR, A.RUN_SYNCHRONIZED_MOTORS, {
        "commands": [
            {"code": "LLM", "action": "run-forever", "speed_sp": 100},
            {"code": "LLM", "action": "run-forever", "speed_sp": 100},
        ]
    })
    assert duplicate.status_code == 400


def test_drive_commands_and_validation(service):
    assert service.execute(T.DRIVE, A.READ_DRIVE_STATUS).status_code == 200
    assert service.execute(T.DRIVE, A.DRIVE_TANK, {
        "left_speed_sp": 100, "right_speed_sp": -100, "watchdog_ms": 1000
    }).status_code == 202
    assert service.execute(T.DRIVE, A.STOP_DRIVE, {"stop_action": "brake"}).status_code == 200
    assert service.execute(T.DRIVE, A.RESET_DRIVE_ODOMETRY, {"x_mm": 1, "y_mm": 2, "heading_deg": 3}).status_code == 200
    assert service.execute(T.DRIVE, A.MOVE_DRIVE_DISTANCE, {"distance_mm": 100, "speed_sp": 200}).status_code == 202
    assert service.execute(T.DRIVE, A.ROTATE_DRIVE_ANGLE, {"angle_deg": 90, "speed_sp": 200}).status_code == 202
    assert service.execute(T.DRIVE, A.CURVE_DRIVE_RADIUS, {"radius_mm": 200, "angle_deg": 45, "speed_sp": 200}).status_code == 202
    assert service.execute(T.DRIVE, A.DRIVE_TANK, {"left_speed_sp": "fast", "right_speed_sp": 1}).status_code == 400
    assert service.execute(T.DRIVE, A.MOVE_DRIVE_DISTANCE, {"distance_mm": 0, "speed_sp": 200}).status_code == 400
