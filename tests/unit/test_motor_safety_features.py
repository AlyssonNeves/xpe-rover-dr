import time

from infrastructure.monitoring.motor_monitor import MotorLifecycleStates, MotorMonitor
from infrastructure.state.motor_state_store import MotorStateStore
from tests.unit.test_adapters_and_monitors import FakeEv3Motor, FakeMotorHardwareBackend


class RampMotor(FakeEv3Motor):
    def __init__(self, address):
        super(RampMotor, self).__init__(address)
        self.ramp_up_sp = 0
        self.ramp_down_sp = 0


def build_monitor(motor_class=RampMotor):
    return MotorMonitor(
        state_store=MotorStateStore(),
        motor_definitions={
            "A": {"name": "A", "address": "outA", "motor_class": "LargeMotor"},
            "B": {"name": "B", "address": "outB", "motor_class": "LargeMotor"},
        },
        hardware_enabled=True,
        hardware_backend=FakeMotorHardwareBackend(
            available=True, motor_classes={"LargeMotor": motor_class}
        ),
    )


def test_native_ramp_profile_is_configured_once():
    monitor = build_monitor()
    state = monitor.run_timed_motor("A", 300, 1000, profile="ramp-up-down")
    driver = monitor.motor_registry._motors["A"]
    assert state["command_state"] == "DISPATCHED"
    assert driver.ramp_up_sp > 0
    assert driver.ramp_down_sp > 0
    assert len(driver.run_timed_calls) == 1


def test_stop_all_motors_stops_every_driver_with_configured_action():
    monitor = build_monitor()
    monitor.run_forever_motor("A", 200, watchdog_ms=5000)
    monitor.run_forever_motor("B", 200, watchdog_ms=5000)
    results = monitor.stop_all_motors(stop_action="hold")
    assert results["A"]["success"] is True
    assert results["B"]["success"] is True
    assert monitor.motor_registry._motors["A"].stop_calls[-1] == {"stop_action": "hold"}
    assert monitor.motor_registry._motors["B"].stop_calls[-1] == {"stop_action": "hold"}


def test_run_forever_watchdog_stops_motor_and_marks_timeout():
    monitor = build_monitor()
    monitor.run_forever_motor("A", 200, watchdog_ms=1)
    time.sleep(0.005)
    monitor._evaluate_active_commands()
    state = monitor.state_store.get_motor("A")
    assert state["command_state"] == MotorLifecycleStates.TIMED_OUT
    assert state["motion_state"] == "STOPPED"
    assert monitor.motor_registry._motors["A"].stop_calls


def test_continuous_command_ignores_finite_timeout_while_watchdog_is_valid():
    monitor = build_monitor()
    monitor.run_forever_motor("A", 200, watchdog_ms=5000)

    active = monitor._active_commands["A"]
    active["deadline"] = time.time() - 1.0
    active["watchdog_deadline"] = time.time() + 5.0
    stop_count_before = len(monitor.motor_registry._motors["A"].stop_calls)

    monitor._evaluate_active_commands()

    state = monitor.state_store.get_motor("A")
    assert state["command_state"] == "DISPATCHED"
    assert "A" in monitor._active_commands
    assert len(monitor.motor_registry._motors["A"].stop_calls) == stop_count_before


def test_driver_stalled_state_is_detected_and_stopped():
    monitor = build_monitor()
    monitor.run_timed_motor("A", 200, 1000)
    monitor.motor_registry._motors["A"].state = {"stalled"}
    monitor._evaluate_active_commands()
    state = monitor.state_store.get_motor("A")
    assert state["command_state"] == MotorLifecycleStates.STALLED
    assert state["motion_state"] == "STALLED"
    assert monitor.motor_registry._motors["A"].stop_calls


def test_run_direct_dispatches_native_duty_cycle_command():
    monitor = build_monitor()
    state = monitor.run_direct_motor("A", 35, watchdog_ms=5000)
    driver = monitor.motor_registry._motors["A"]
    assert state["command_state"] == "DISPATCHED"
    assert driver.run_direct_calls[-1] == {"duty_cycle_sp": 35}


def test_run_direct_watchdog_stops_motor_and_marks_timeout():
    monitor = build_monitor()
    monitor.run_direct_motor("A", 20, watchdog_ms=1)
    time.sleep(0.005)
    monitor._evaluate_active_commands()
    state = monitor.state_store.get_motor("A")
    assert state["command_state"] == MotorLifecycleStates.TIMED_OUT
    assert monitor.motor_registry._motors["A"].stop_calls
