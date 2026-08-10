import json
import os
import tempfile
import time

import pytest

from app import rover_config
from app.rover_application import RoverApplication
from infrastructure.monitoring.monitor_base import MonitorBase


class CountingMonitor(MonitorBase):
    def __init__(self):
        super(CountingMonitor, self).__init__("Counting", 0.001)
        self.initialized = False
        self.cycles = 0
        self.finalized = False

    def on_initialize(self):
        self.initialized = True

    def on_cycle(self):
        self.cycles += 1
        if self.cycles >= 2:
            self.stop()

    def on_finalize(self):
        self.finalized = True


class FakeRest(object):
    def __init__(self):
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class Closable(object):
    def __init__(self): self.closed = False
    def close(self): self.closed = True


def test_monitor_base_runs_hooks():
    monitor = CountingMonitor()
    monitor.start()
    monitor.join(1)
    assert monitor.initialized is True
    assert monitor.cycles >= 2
    assert monitor.finalized is True
    assert monitor.is_stopping() is True


def test_rover_application_start_stop_is_ordered_and_idempotent():
    monitor = CountingMonitor()
    rest = FakeRest()
    managed = Closable()
    app = RoverApplication([monitor], rest, [managed])
    app.start()
    time.sleep(0.02)
    assert app.get_status() == app.RUNNING
    app.stop()
    app.stop()
    assert app.get_status() == app.STOPPED
    assert rest.started and rest.stopped
    assert managed.closed


def test_configuration_copy_and_invalid_files():
    sensors = rover_config.get_sensor_definitions()
    sensors["TMP"]["name"] = "changed"
    assert rover_config.get_sensor_definitions()["TMP"]["name"] != "changed"
    assert rover_config.get_drive_config()["left_motor_code"] == "LLM"
    mecanum = rover_config.get_mecanum_config()
    assert mecanum["front_left_motor_code"] == "LLM"
    assert mecanum["rear_left_motor_code"] == "LMM"
    assert mecanum["front_right_motor_code"] == "RLM"
    assert mecanum["rear_right_motor_code"] == "RMM"
    mecanum["front_left_speed_factor"] = 99.0
    assert rover_config.get_mecanum_config()["front_left_speed_factor"] == -0.8
    assert rover_config.get_mecanum_config()["strafe_compensation"] == 1.1
    motors = rover_config.get_motor_definitions()
    assert motors["LLM"]["polarity"] == "inversed"
    assert motors["LMM"]["polarity"] == "inversed"
    assert motors["RLM"]["polarity"] == "inversed"
    assert motors["RMM"]["polarity"] == "normal"

    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        with open(path, "w") as stream:
            stream.write("not json")
        with pytest.raises(RuntimeError):
            rover_config.load_json_configuration(path)
        with open(path, "w") as stream:
            json.dump({}, stream)
        with pytest.raises(RuntimeError):
            rover_config.load_json_configuration(path)
    finally:
        os.unlink(path)


def test_mecanum_front_rear_speed_factors_match_transmission_ratio():
    mecanum = rover_config.get_mecanum_config()

    assert rover_config.MECANUM_FRONT_GEAR_RATIO == 1.25
    assert rover_config.MECANUM_REAR_GEAR_RATIO == 1.0
    assert rover_config.MECANUM_FRONT_SPEED_FACTOR == 0.8
    assert rover_config.MECANUM_REAR_SPEED_FACTOR == 1.0
    assert mecanum["front_left_speed_factor"] == -0.8
    assert mecanum["front_right_speed_factor"] == -0.8
    assert mecanum["rear_left_speed_factor"] == 1.0
    assert mecanum["rear_right_speed_factor"] == 1.0
    assert (
        abs(mecanum["front_left_speed_factor"])
        * rover_config.MECANUM_FRONT_GEAR_RATIO
        == mecanum["rear_left_speed_factor"]
        * rover_config.MECANUM_REAR_GEAR_RATIO
    )


def test_hardware_environment_overrides_json_default(monkeypatch):
    monkeypatch.setenv("ROVER_HARDWARE_ENABLED", "false")
    assert rover_config.get_hardware_enabled() is False
    monkeypatch.setenv("ROVER_HARDWARE_ENABLED", "true")
    assert rover_config.get_hardware_enabled() is True


def test_security_configuration_depends_on_hardware_mode(monkeypatch):
    monkeypatch.delenv("ROVER_SHUTDOWN_TOKEN", raising=False)
    monkeypatch.delenv("ROVER_HARDWARE_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="ROVER_SHUTDOWN_TOKEN"):
        rover_config.validate_security_configuration()

    monkeypatch.setenv("ROVER_SHUTDOWN_TOKEN", "shutdown-secret")
    monkeypatch.setattr(rover_config, "HARDWARE_ENABLED", False)
    rover_config.validate_security_configuration()

    monkeypatch.setattr(rover_config, "HARDWARE_ENABLED", True)
    with pytest.raises(RuntimeError, match="ROVER_HARDWARE_API_TOKEN"):
        rover_config.validate_security_configuration()

    monkeypatch.setenv("ROVER_HARDWARE_API_TOKEN", "shutdown-secret")
    with pytest.raises(RuntimeError, match="different values"):
        rover_config.validate_security_configuration()

    monkeypatch.setenv("ROVER_HARDWARE_API_TOKEN", "hardware-secret")
    rover_config.validate_security_configuration()


def test_rover_application_restart_marks_request_and_stops():
    rest = FakeRest()
    app = RoverApplication([], rest)
    app.restart()
    assert app.is_restart_requested() is True
    assert app.get_status() == app.STOPPED
    assert rest.stopped is True
