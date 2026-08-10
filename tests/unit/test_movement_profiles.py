import threading

from app.command_service import CommandService
from app.models import CommandActions, CommandTargets
from app.services.drive_service import DriveService
from infrastructure.monitoring.motor_monitor import MotorCommandActions, MotorMonitor
from infrastructure.motor.driver_repository import Ev3MotorDriverRepository
from infrastructure.state.motor_state_store import MotorStateStore
from tests.unit.fakes import FakeControllerPort, FakeMotorPort, FakeSensorPort
from tests.unit.test_motor_monitor_core import FakeBackend


def build_monitor():
    return MotorMonitor(
        state_store=MotorStateStore(), interval_seconds=0.01,
        hardware_backend=FakeBackend()
    )


def test_supported_profiles_map_to_native_ev3_ramps():
    monitor = build_monitor()
    expected = {
        "direct": (0, 0),
        "ramp-up": (300, 0),
        "ramp-down": (0, 300),
        "ramp-up-down": (300, 300),
    }
    for profile, ramps in expected.items():
        command = {
            "motor_code": "LLM",
            "action": MotorCommandActions.RUN_TIMED,
            "parameters": {
                "speed_sp": 200, "time_sp": 10,
                "stop_action": "brake", "profile": profile
            }
        }
        accepted, error, outcome = monitor._execute_hardware_command(
            command, threading.Event()
        )
        assert accepted is True
        assert error is None
        assert outcome == "completed"
        motor = monitor.motor_registry.get_motor("LLM")
        assert (motor.ramp_up_sp, motor.ramp_down_sp) == ramps


def test_driver_repository_defaults_to_direct_without_implicit_ramp():
    definitions = {
        "A": {"name": "A", "address": "outA", "motor_class": "LargeMotor"}
    }
    repository = Ev3MotorDriverRepository(definitions, FakeBackend())
    motor = repository.get_motor("A")
    motor.ramp_up_sp = 999
    motor.ramp_down_sp = 999
    assert repository.configure_motion("A", "brake")[0] is True
    assert motor.ramp_up_sp == 0
    assert motor.ramp_down_sp == 0


def test_monitor_records_requested_profile_and_defaults_invalid_internal_value():
    monitor = build_monitor()
    queued = monitor.run_timed_motor("LLM", 200, 100, profile="ramp-up")
    record = monitor.get_command(queued["command_id"])
    assert record["parameters"]["profile"] == "ramp-up"

    direct = monitor.run_timed_motor("RLM", 200, 100, profile="unknown")
    record = monitor.get_command(direct["command_id"])
    assert record["parameters"]["profile"] == "direct"


def test_synchronized_batch_preserves_profile_per_motor():
    monitor = build_monitor()
    batch = monitor.run_synchronized_motors([
        {"code": "LLM", "action": "run-timed", "priority": 10,
         "parameters": {"speed_sp": 100, "time_sp": 10,
                        "profile": "ramp-up"}},
        {"code": "RLM", "action": "run-timed", "priority": 10,
         "parameters": {"speed_sp": 100, "time_sp": 10,
                        "profile": "ramp-down"}},
    ])
    assert batch["accepted"] is True
    records = [monitor.get_command(cid) for cid in batch["command_ids"]]
    assert records[0]["parameters"]["profile"] == "ramp-up"
    assert records[1]["parameters"]["profile"] == "ramp-down"


def test_drive_service_propagates_profile_to_both_traction_commands():
    motor_port = FakeMotorPort()
    drive = DriveService(
        motor_port, FakeSensorPort(),
        config={
            "left_motor_code": "LLM", "right_motor_code": "RLM",
            "gyro_sensor_code": "GYR", "wheel_diameter_mm": 56.0,
            "track_width_mm": 120.0, "left_speed_factor": 1.0,
            "right_speed_factor": 1.0,
        }
    )
    drive.drive_tank(200, 200, profile="ramp-up-down")
    assert [item["parameters"]["profile"] for item in motor_port.last_sync] == [
        "ramp-up-down", "ramp-up-down"
    ]
    drive.move_distance(100, 200, profile="ramp-down")
    assert [item["parameters"]["profile"] for item in motor_port.last_sync] == [
        "ramp-down", "ramp-down"
    ]


def test_command_service_rejects_unknown_profile_before_motor_port():
    service = CommandService(FakeSensorPort(), FakeMotorPort(), FakeControllerPort())
    result = service.execute(
        CommandTargets.MOTOR, CommandActions.RUN_TIMED_MOTOR,
        {"code": "LLM", "speed_sp": 100, "time_sp": 100,
         "profile": "smooth"}
    )
    assert result.status_code == 400
    assert "direct" in result.error
    assert "ramp-up-down" in result.error


def test_command_service_accepts_profile_for_motor_and_drive_commands():
    motor_port = FakeMotorPort()
    service = CommandService(FakeSensorPort(), motor_port, FakeControllerPort())
    result = service.execute(
        CommandTargets.MOTOR, CommandActions.RUN_TIMED_MOTOR,
        {"code": "LLM", "speed_sp": 100, "time_sp": 100,
         "profile": "ramp-up"}
    )
    assert result.status_code == 202

    sync = service.execute(
        CommandTargets.MOTOR, CommandActions.RUN_SYNCHRONIZED_MOTORS,
        {"commands": [
            {"code": "LLM", "action": "run-timed", "speed_sp": 100,
             "time_sp": 100, "profile": "ramp-up-down"}
        ]}
    )
    assert sync.status_code == 202
    assert motor_port.last_sync[0]["parameters"]["profile"] == "ramp-up-down"
