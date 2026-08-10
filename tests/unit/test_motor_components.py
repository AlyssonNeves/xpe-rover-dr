#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Focused tests for components extracted from MotorMonitor."""

import pytest

from app.motor_lifecycle import MotorLifecycleStates
from infrastructure.motor.command_executor import MotorCommandExecutor
from infrastructure.motor.guarded_operation_manager import (
    MotorGuardedOperationManager
)
from infrastructure.motor.registries import GuardedOperationRegistry
from infrastructure.motor.safety_watchdog import MotorSafetyWatchdog
from infrastructure.motor.state_collector import MotorStateCollector
from infrastructure.motor.synchronized_executor import SynchronizedMotorExecutor
from infrastructure.state.motor_state_store import MotorStateStore


class Actions(object):
    STOP = "stop"
    RUN_TIMED = "run-timed"
    RUN_FOREVER = "run-forever"
    RUN_DIRECT = "run-direct"
    RUN_TO_REL_POS = "run-to-rel-pos"
    RUN_TO_ABS_POS = "run-to-abs-pos"
    RESET = "reset"


class FakeRepository(object):
    def __init__(self):
        self.calls = []
        self.snapshots = []

    def _result(self, name, *args):
        self.calls.append((name,) + args)
        return {"success": True, "hardware_error": None}

    def configure_motion(self, *args):
        return self._result("configure_motion", *args)

    def execute_stop(self, *args):
        return self._result("stop", *args)

    def execute_run_timed(self, *args):
        return self._result("run_timed", *args)

    def execute_run_forever(self, *args):
        return self._result("run_forever", *args)

    def execute_run_direct(self, *args):
        return self._result("run_direct", *args)

    def execute_run_to_rel_pos(self, *args):
        return self._result("run_to_rel_pos", *args)

    def execute_run_to_abs_pos(self, *args):
        return self._result("run_to_abs_pos", *args)

    def execute_reset(self, *args):
        return self._result("reset", *args)

    def read_all_motors(self):
        return list(self.snapshots)


class FakeBackend(object):
    error_message = "unavailable"

    def __init__(self, available=True):
        self.available = available

    def is_available(self):
        return self.available

    def get_motor_class(self, name):
        return object if self.available and name else None


class FakeLogger(object):
    errors = []

    @classmethod
    def error(cls, message):
        cls.errors.append(message)


def _executor(repository, available=True):
    return MotorCommandExecutor(
        repository, Actions, lambda: available, lambda: "offline",
        "brake", 300, 400, "direct", "ramp-up", "ramp-down",
        "ramp-up-down"
    )


@pytest.mark.parametrize("action,parameters,expected", [
    (Actions.STOP, {"stop_action": "hold"}, "stop"),
    (Actions.RUN_TIMED, {"speed_sp": 10, "time_sp": 20}, "run_timed"),
    (Actions.RUN_FOREVER, {"speed_sp": 10}, "run_forever"),
    (Actions.RUN_DIRECT, {"duty_cycle_sp": 10}, "run_direct"),
    (Actions.RUN_TO_REL_POS, {"speed_sp": 10, "position_sp": 90}, "run_to_rel_pos"),
    (Actions.RUN_TO_ABS_POS, {"speed_sp": 10, "position_sp": 90}, "run_to_abs_pos"),
    (Actions.RESET, {}, "reset")
])
def test_command_executor_dispatches_supported_operations(action, parameters, expected):
    repository = FakeRepository()
    result = _executor(repository).execute("M1", action, parameters)
    assert result["success"] is True
    assert expected in [call[0] for call in repository.calls]


def test_command_executor_handles_simulated_and_unsupported_operations():
    repository = FakeRepository()
    simulated = _executor(repository, available=False).execute("M1", Actions.STOP, {})
    assert simulated == {
        "executed": False, "success": True, "hardware_error": "offline"
    }
    unsupported = _executor(repository).execute("M1", "invalid", {})
    assert unsupported["success"] is False


def test_state_collector_initializes_and_refreshes_snapshots():
    store = MotorStateStore()
    repository = FakeRepository()
    definitions = {
        "M1": {"name": "Motor", "address": "outA", "motor_class": "LargeMotor"}
    }
    collector = MotorStateCollector(
        store, definitions, True, FakeBackend(True), repository, lambda code: 2
    )
    collector.load_initial_motors()
    assert store.get_motor("M1")["lifecycle_state"] == MotorLifecycleStates.HARDWARE_READY
    repository.snapshots = [{
        "code": "M1", "motor_class": "LargeMotor", "connected": True
    }]
    collector.refresh_hardware_state()
    assert store.get_motor("M1")["command_queue_size"] == 2


def test_state_collector_publishes_unavailable_hardware_state():
    store = MotorStateStore()
    collector = MotorStateCollector(
        store,
        {"M1": {"name": "Motor", "address": "outA", "motor_class": "LargeMotor"}},
        True,
        FakeBackend(False),
        FakeRepository(),
        lambda code: 0
    )
    collector.load_initial_motors()
    collector.refresh_hardware_state()
    assert store.get_motor("M1")["lifecycle_state"] == (
        MotorLifecycleStates.HARDWARE_UNAVAILABLE
    )


def test_guarded_operation_manager_reserves_releases_and_stops():
    repository = FakeRepository()
    preempted = []
    manager = MotorGuardedOperationManager(
        {"M1": {}}, GuardedOperationRegistry(), repository,
        lambda code, stop_running_command: preempted.append(code),
        "brake", FakeLogger
    )
    manager.begin(["M1"], "native", "op-1")
    with pytest.raises(ValueError, match="already reserved"):
        manager.begin(["M1"], "other", "op-2")
    released = manager.end("op-1", stop=True)
    assert released["status"] == "COMPLETED"
    assert preempted == ["M1"]
    assert repository.calls[-1][0] == "stop"


def test_guarded_operation_manager_releases_failed_operation():
    manager = MotorGuardedOperationManager(
        {"M1": {}}, GuardedOperationRegistry(), FakeRepository(),
        lambda code, stop_running_command: None, "brake", FakeLogger
    )
    with pytest.raises(RuntimeError):
        manager.execute(
            ["M1"], "native", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        )
    with pytest.raises(ValueError, match="At least one"):
        manager.begin([], "native", "empty")


def test_synchronized_executor_rejects_invalid_batches_and_maps_parameters():
    calls = []
    commands = []

    def enqueue(code, action, parameters, priority, batch_id):
        calls.append((code, action, parameters, priority, batch_id))
        commands.append({"command_id": len(calls), "batch_id": batch_id})
        return {"code": code}

    store = MotorStateStore()
    executor = SynchronizedMotorExecutor(
        {"M1": {}, "M2": {}}, Actions, enqueue, store, lambda: commands
    )
    assert executor.execute([])["success"] is False
    assert executor.execute([{"code": "UNKNOWN"}])["success"] is False
    result = executor.execute([
        {"code": "M1", "action": Actions.RUN_TIMED, "speed_sp": 10, "time_sp": 50},
        {"code": "M2", "action": Actions.RUN_TO_ABS_POS, "speed_sp": 20, "position_sp": 90}
    ])
    assert result["success"] is True
    assert len(result["command_ids"]) == 2
    assert calls[0][2]["time_sp"] == 50
    assert calls[1][2]["position_sp"] == 90


class SequenceEvent(object):
    def __init__(self, results):
        self.results = list(results)
        self.set_called = False

    def clear(self):
        self.set_called = False

    def set(self):
        self.set_called = True

    def wait(self, timeout):
        del timeout
        return self.results.pop(0)


def test_motor_safety_watchdog_runs_evaluator_and_reports_failures():
    calls = []
    FakeLogger.errors = []

    def evaluator():
        calls.append("evaluate")
        raise RuntimeError("watchdog failure")

    watchdog = MotorSafetyWatchdog(evaluator, FakeLogger, 0.001)
    watchdog._stop_event = SequenceEvent([False, True])
    watchdog._run()

    assert calls == ["evaluate"]
    assert "watchdog failure" in FakeLogger.errors[-1]


def test_motor_safety_watchdog_starts_and_stops_thread():
    calls = []
    watchdog = MotorSafetyWatchdog(lambda: calls.append("evaluate"), FakeLogger, 0.001)
    watchdog.start()
    watchdog.stop(0.5)

    assert watchdog._stop_event.is_set()
    assert watchdog._thread is not None
    assert not watchdog._thread.is_alive()
