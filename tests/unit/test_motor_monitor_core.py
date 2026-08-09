import threading

import pytest

from services.motor_monitor import (
    MotorCommandActions, MotorLifecycleStates, MotorMonitor, MotorRegistry,
)
from services.motor_state_store import MotorStateStore


class FakeMotor(object):
    def __init__(self, address):
        self.address = address
        self.connected = True
        self.position = 0
        self.speed = 0
        self.duty_cycle = 0
        self.state = []
        self.driver_name = "fake"
        self.max_speed = 1000
        self.polarity = "normal"
        self.stop_action = "coast"
        self.ramp_up_sp = 0
        self.ramp_down_sp = 0
        self.calls = []

    def stop(self):
        self.calls.append(("stop", self.stop_action))
        self.state = []

    def run_timed(self, speed_sp, time_sp):
        self.calls.append(("run_timed", speed_sp, time_sp))
        self.speed = speed_sp
        self.state = []

    def run_forever(self, speed_sp):
        self.calls.append(("run_forever", speed_sp))
        self.speed = speed_sp
        self.state = ["running"]

    def run_to_rel_pos(self, speed_sp, position_sp):
        self.calls.append(("run_to_rel_pos", speed_sp, position_sp))
        self.position += position_sp
        self.state = []

    def reset(self):
        self.calls.append(("reset",))
        self.position = 0
        self.state = []


class FakeBackend(object):
    error_message = None

    def is_available(self):
        return True

    def get_motor_class(self, name):
        if name in ("LargeMotor", "MediumMotor"):
            return FakeMotor
        return None


def test_motor_registry_connect_read_and_execute_commands():
    definitions = {
        "A": {"name": "A", "address": "outA", "motor_class": "LargeMotor", "polarity": "inversed"}
    }
    registry = MotorRegistry(definitions, FakeBackend())
    motor = registry.connect_motor("A")
    assert motor.address == "outA"
    assert motor.polarity == "inversed"
    assert registry.read_motor("A")["connected"] is True
    assert registry.configure_motion("A", "brake", 100, 200)[0] is True
    assert motor.stop_action == "brake"
    assert motor.ramp_up_sp == 100 and motor.ramp_down_sp == 200
    assert registry.run_timed_motor("A", 100, 50, "hold")[0] is True
    assert registry.run_forever_motor("A", 120, "brake")[0] is True
    assert registry.is_running("A") is True
    assert registry.run_to_rel_pos_motor("A", 100, 90, "brake")[0] is True
    assert registry.reset_motor("A")[0] is True
    assert registry.stop_motor("A", "coast")[0] is True
    assert registry.get_motor("UNKNOWN") is None
    assert registry.read_motor("UNKNOWN") is None


def test_motor_registry_disconnected_and_missing_class_paths():
    definitions = {
        "A": {"name": "A", "address": "outA", "motor_class": "Missing"}
    }
    registry = MotorRegistry(definitions, FakeBackend())
    assert registry.connect_motor("missing") is None
    assert registry.connect_motor("A") is None
    assert registry.get_error("A")

    definitions["A"]["motor_class"] = "LargeMotor"
    registry = MotorRegistry(definitions, FakeBackend())
    motor = registry.get_motor("A")
    motor.connected = False
    assert registry.get_motor("A") is None
    assert registry.get_error("A") == "Motor is disconnected"


def build_monitor():
    return MotorMonitor(
        state_store=MotorStateStore(), interval_seconds=0.01,
        hardware_backend=FakeBackend()
    )


def test_motor_monitor_initial_state_queue_and_immediate_stop():
    monitor = build_monitor()
    assert len(monitor.list_motors()) == 4
    assert monitor.read_motor("LLM")["connected"] is True
    assert len(monitor.read_all_motors()) == 4
    assert monitor.get_command(99) is None
    assert monitor._normalize_priority(None) == 0
    assert monitor._normalize_priority(True) == 0
    assert monitor._normalize_priority(80) == 80

    queued = monitor.run_timed_motor("LLM", 200, 100, priority=80)
    assert queued["accepted"] is True
    assert queued["status"] == MotorLifecycleStates.QUEUED
    cid = queued["command_id"]
    assert monitor.get_command(cid)["priority"] == 80
    assert len(monitor.list_commands("LLM")) == 1
    assert monitor._queue_size("LLM") == 1

    forever = monitor.run_forever_motor("RLM", 100, watchdog_ms=1000)
    assert forever["accepted"] is True
    relative = monitor.run_to_rel_pos_motor("LMM", 100, 90)
    assert relative["accepted"] is True
    reset = monitor.reset_motor("RMM")
    assert reset["accepted"] is True
    assert monitor.run_timed_motor("UNKNOWN", 1, 1) is None

    cancelled = monitor.cancel_motor_commands("LLM")
    assert cid in cancelled["cancelled_command_ids"]
    assert monitor.cancel_motor_commands("UNKNOWN") is None

    stopped = monitor.stop_motor("LLM", "hold")
    assert stopped["accepted"] is True
    assert stopped["status"] == MotorLifecycleStates.COMPLETED
    assert monitor.stop_motor("UNKNOWN") is None


def test_motor_monitor_synchronized_and_guarded_operations():
    monitor = build_monitor()
    batch = monitor.run_synchronized_motors([
        {"code": "LLM", "action": MotorCommandActions.RUN_TO_REL_POS,
         "priority": 10, "parameters": {"speed_sp": 100, "position_sp": 90}},
        {"code": "RLM", "action": MotorCommandActions.RUN_TO_REL_POS,
         "priority": 10, "parameters": {"speed_sp": 100, "position_sp": 90}},
    ])
    assert batch["accepted"] is True
    assert len(batch["command_ids"]) == 2
    assert monitor.run_synchronized_motors([])["accepted"] is False
    bad = monitor.run_synchronized_motors([
        {"code": "UNKNOWN", "action": "run-forever", "parameters": {}}
    ])
    assert bad["accepted"] is False

    record = monitor.begin_guarded_operation(["LLM"], "native", "op-1")
    assert record["status"] == "RUNNING"
    reserved = monitor.run_forever_motor("LLM", 100)
    assert reserved["accepted"] is False
    with pytest.raises(ValueError):
        monitor.begin_guarded_operation(["LLM"], "other", "op-2")
    assert monitor.end_guarded_operation("missing") is None
    released = monitor.end_guarded_operation("op-1", stop=True)
    assert released["status"] == "COMPLETED"
    assert monitor.execute_guarded_operation(["RLM"], "read", lambda: 7) == 7
    with pytest.raises(ValueError):
        monitor.begin_guarded_operation([], "none", "op-x")
    with pytest.raises(ValueError):
        monitor.begin_guarded_operation(["UNKNOWN"], "none", "op-y")
