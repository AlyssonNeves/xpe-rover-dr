import json
import os
import tempfile
import time

import pytest

from app import rover_config
from app.rover_application import RoverApplication
from services.monitor_base import MonitorBase


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
