#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for the dedicated local manual EV3 motor adapter."""

from app.rover_config import DEFAULT_CONFIGURATION
from app.services.manual_drive_service import ManualDriveService
from infrastructure.state.motor_state_store import MotorStateStore
from adapters.out_motor_state_publisher import MotorStateStorePublisherAdapter


class FakeConnectedMotor(object):
    def __init__(self):
        self.position = 123
        self.stop_calls = []

    def stop(self, stop_action=None):
        self.stop_calls.append(stop_action)


class FakeMotorHardwarePort(object):
    def __init__(self):
        self.motor_definitions = {
            "LLM": {
                "name": "Left Large",
                "address": "outA",
                "motor_class": "LargeMotor",
                "polarity": "inversed"
            },
            "LMM": {
                "name": "Left Medium",
                "address": "outB",
                "motor_class": "MediumMotor",
                "polarity": "inversed"
            },
            "RMM": {
                "name": "Right Medium",
                "address": "outC",
                "motor_class": "MediumMotor",
                "polarity": "normal"
            },
            "RLM": {
                "name": "Right Large",
                "address": "outD",
                "motor_class": "LargeMotor",
                "polarity": "normal"
            }
        }
        self.ensure_calls = []
        self.stop_calls = []
        self.run_calls = []
        self.errors = {}
        self.connected_motors = {}

    def get_motor_definition(self, motor_code):
        definition = self.motor_definitions.get(motor_code)
        return dict(definition) if definition is not None else None

    def ensure_connected(self, motor_code):
        self.ensure_calls.append(motor_code)
        if motor_code in self.errors:
            return None
        motor = self.connected_motors.get(motor_code)
        if motor is None:
            motor = FakeConnectedMotor()
            self.connected_motors[motor_code] = motor
        return motor

    def get_error(self, motor_code):
        return self.errors.get(motor_code)

    def run_forever(self, motor_code, speed_sp):
        self.run_calls.append((motor_code, speed_sp))
        return {"success": True, "hardware_error": None}

    def stop(self, motor_code, stop_action=None, connected_only=False):
        self.stop_calls.append((motor_code, stop_action, connected_only))
        return {"success": True, "hardware_error": None}


def acquire_adapter():
    hardware = FakeMotorHardwarePort()
    state_store = MotorStateStore()
    adapter = ManualDriveService(
        motor_hardware_port=hardware,
        drive_config=DEFAULT_CONFIGURATION.drive,
        mecanum_config=DEFAULT_CONFIGURATION.mecanum,
        joystick_config=DEFAULT_CONFIGURATION.joystick,
        default_stop_action=DEFAULT_CONFIGURATION.motor_default_stop_action,
        motor_state_publisher_port=MotorStateStorePublisherAdapter(state_store)
    )
    result = adapter.acquire(
        "session-1", motor_codes=("LMM", "RMM")
    )
    assert result["success"] is True
    return adapter, hardware, state_store


def test_acquire_preconnects_and_stops_all_manual_motors():
    adapter, hardware, state_store = acquire_adapter()

    assert hardware.ensure_calls == ["LLM", "RLM", "LMM", "RMM"]
    assert [call[0] for call in hardware.stop_calls] == [
        "LLM", "RLM", "LMM", "RMM"
    ]
    assert all(call[2] is True for call in hardware.stop_calls)
    assert all(
        motor["watchdog_enabled"] is False
        for motor in state_store.get_all_motors()
    )
    adapter.close()


def test_changed_speed_reissues_run_forever_for_immediate_hardware_update():
    adapter, hardware, _ = acquire_adapter()
    hardware.run_calls[:] = []

    first = adapter.apply_drive_setpoint("session-1", 300, 300)
    second = adapter.apply_drive_setpoint("session-1", 600, 500)

    assert first["success"] is True
    assert second["success"] is True
    assert hardware.run_calls == [
        ("LLM", 300), ("RLM", 300),
        ("LLM", 600), ("RLM", 500)
    ]
    assert second["watchdog_enabled"] is False


def test_wheels_keeps_global_polarity_in_the_hardware_layer():
    adapter, hardware, _ = acquire_adapter()
    hardware.run_calls[:] = []

    result = adapter.apply_drive_setpoint("session-1", 100, 100)

    assert result["success"] is True
    assert hardware.run_calls == [("LLM", 100), ("RLM", 100)]
    assert hardware.motor_definitions["LLM"]["polarity"] == "inversed"
    assert hardware.motor_definitions["RLM"]["polarity"] == "normal"


def test_mecanum_composes_front_overlay_above_global_polarity():
    adapter, hardware, _ = acquire_adapter()
    hardware.run_calls[:] = []

    result = adapter.apply_mecanum_setpoint(
        "session-1", 100, 100, 100, 100
    )

    assert result["success"] is True
    assert hardware.run_calls == [
        ("LLM", -80),
        ("LMM", 100),
        ("RLM", -80),
        ("RMM", 100)
    ]
    polarity_sign = {"normal": 1, "inversed": -1}
    effective_signs = [
        (1 if speed > 0 else -1) * polarity_sign[
            hardware.motor_definitions[code]["polarity"]
        ]
        for code, speed in hardware.run_calls
    ]
    assert effective_signs == [1, -1, -1, 1]


def test_auxiliary_motor_uses_the_same_direct_no_watchdog_path():
    adapter, hardware, _ = acquire_adapter()
    hardware.run_calls[:] = []

    first = adapter.apply_auxiliary_setpoint(
        "session-1", "LMM", 400
    )
    second = adapter.apply_auxiliary_setpoint(
        "session-1", "LMM", -400
    )

    assert first["success"] is True
    assert second["success"] is True
    assert hardware.run_calls == [("LMM", 400), ("LMM", -400)]
    assert second["watchdog_enabled"] is False


def test_emergency_stop_synchronously_stops_every_owned_motor():
    adapter, hardware, _ = acquire_adapter()
    hardware.stop_calls[:] = []

    result = adapter.emergency_stop()

    assert result["success"] is True
    assert [call[0] for call in hardware.stop_calls] == [
        "LLM", "RLM", "LMM", "RMM"
    ]



def test_mecanum_setpoint_uses_configured_wheel_order_and_all_four_motors():
    adapter, hardware, _ = acquire_adapter()
    hardware.run_calls[:] = []

    result = adapter.apply_mecanum_setpoint(
        "session-1", 100, 200, -300, -400
    )

    assert result["success"] is True
    # Global left/right installation polarity belongs to the hardware adapter.
    # The Mecanum layer inverts and reduces only the front Large motors to
    # compensate the 1:1.25 front transmission; rear motors remain at 1.0.
    assert result["setpoint"] == (-80, 200, 240, -400)
    assert result["motor_codes"] == ["LLM", "LMM", "RLM", "RMM"]
    assert hardware.run_calls == [
        ("LLM", -80),
        ("LMM", 200),
        ("RLM", 240),
        ("RMM", -400)
    ]


def test_zero_mecanum_setpoint_stops_all_four_wheels_synchronously():
    adapter, hardware, _ = acquire_adapter()
    hardware.stop_calls[:] = []

    result = adapter.apply_mecanum_setpoint(
        "session-1", 0, 0, 0, 0
    )

    assert result["success"] is True
    assert [call[0] for call in hardware.stop_calls] == [
        "LLM", "LMM", "RLM", "RMM"
    ]




def test_prepare_start_defers_all_motor_io_until_joystick_session():
    hardware = FakeMotorHardwarePort()
    adapter = ManualDriveService(
        motor_hardware_port=hardware,
        drive_config=DEFAULT_CONFIGURATION.drive,
        mecanum_config=DEFAULT_CONFIGURATION.mecanum,
        joystick_config=DEFAULT_CONFIGURATION.joystick,
        default_stop_action=DEFAULT_CONFIGURATION.motor_default_stop_action
    )

    adapter.prepare_start()

    assert hardware.ensure_calls == []
    assert hardware.stop_calls == []


def test_acquire_stops_and_zeroes_every_manual_motor():
    hardware = FakeMotorHardwarePort()
    state_store = MotorStateStore()
    adapter = ManualDriveService(
        motor_hardware_port=hardware,
        drive_config=DEFAULT_CONFIGURATION.drive,
        mecanum_config=DEFAULT_CONFIGURATION.mecanum,
        joystick_config=DEFAULT_CONFIGURATION.joystick,
        default_stop_action=DEFAULT_CONFIGURATION.motor_default_stop_action,
        motor_state_publisher_port=MotorStateStorePublisherAdapter(state_store)
    )

    result = adapter.acquire("startup-session")

    assert result["success"] is True
    assert hardware.ensure_calls == ["LLM", "RLM", "LMM", "RMM"]
    for motor_code in hardware.ensure_calls:
        motor = hardware.connected_motors[motor_code]
        assert motor.position == 0
        assert motor.stop_calls
    assert all(
        motor["speed_sp"] == 0 and motor["motion_state"] == "STOPPED"
        for motor in state_store.get_all_motors()
    )

class RecordingStartupProgress(object):
    def __init__(self):
        self.messages = []

    def show_startup_progress(self, message):
        self.messages.append(message)


class RecordingManualDriveLogger(object):
    def __init__(self):
        self.status_messages = []
        self.error_messages = []

    def status(self, message):
        self.status_messages.append(message)

    def error(self, message):
        self.error_messages.append(message)


def test_acquire_publishes_timed_progress_for_each_motor():
    hardware = FakeMotorHardwarePort()
    progress = RecordingStartupProgress()
    logger = RecordingManualDriveLogger()
    timestamps = iter([index / 10.0 for index in range(20)])
    adapter = ManualDriveService(
        motor_hardware_port=hardware,
        drive_config=DEFAULT_CONFIGURATION.drive,
        mecanum_config=DEFAULT_CONFIGURATION.mecanum,
        joystick_config=DEFAULT_CONFIGURATION.joystick,
        default_stop_action=DEFAULT_CONFIGURATION.motor_default_stop_action,
        monotonic_clock=lambda: next(timestamps),
        logger=logger,
        startup_progress_port=progress
    )

    result = adapter.acquire("timed-session")

    assert result["success"] is True
    assert progress.messages[0] == "Connecting motor LLM."
    assert "Motor LLM connected and zeroed in 0.100 s." in progress.messages
    assert "Connecting motor RMM." in progress.messages
    assert progress.messages[-1].startswith("Motor session ready in ")
    assert logger.status_messages == progress.messages


class RecordingStatusLed(object):
    def __init__(self):
        self.calls = []

    def set_fault(self, source, active=True):
        self.calls.append((source, bool(active)))


def _manual_service_with_led(hardware, status_led):
    return ManualDriveService(
        motor_hardware_port=hardware,
        drive_config=DEFAULT_CONFIGURATION.drive,
        mecanum_config=DEFAULT_CONFIGURATION.mecanum,
        joystick_config=DEFAULT_CONFIGURATION.joystick,
        default_stop_action=DEFAULT_CONFIGURATION.motor_default_stop_action,
        status_led_port=status_led
    )


def test_acquire_publishes_motor_health_directly_to_status_led():
    hardware = FakeMotorHardwarePort()
    status_led = RecordingStatusLed()
    adapter = _manual_service_with_led(hardware, status_led)

    result = adapter.acquire("startup-health")

    assert result["success"] is True
    assert status_led.calls[-1] == ("motor", False)


def test_acquire_marks_motor_fault_when_hardware_is_missing():
    hardware = FakeMotorHardwarePort()
    hardware.errors["RMM"] = "Motor RMM is unavailable."
    status_led = RecordingStatusLed()
    adapter = _manual_service_with_led(hardware, status_led)

    result = adapter.acquire("startup-failure")

    assert result["success"] is False
    assert status_led.calls[-1] == ("motor", True)


def test_successful_manual_session_clears_previous_motor_fault():
    hardware = FakeMotorHardwarePort()
    status_led = RecordingStatusLed()
    adapter = _manual_service_with_led(hardware, status_led)
    status_led.set_fault("motor", True)

    result = adapter.acquire("session-led-recovery")

    assert result["success"] is True
    assert status_led.calls[-1] == ("motor", False)


def test_failed_manual_session_marks_motor_fault():
    hardware = FakeMotorHardwarePort()
    hardware.errors["LLM"] = "Motor LLM is unavailable."
    status_led = RecordingStatusLed()
    adapter = _manual_service_with_led(hardware, status_led)

    result = adapter.acquire("session-led-failure")

    assert result["success"] is False
    assert status_led.calls[-1] == ("motor", True)
