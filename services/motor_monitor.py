#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Motor monitoring service with basic EV3 command execution."""

from app.rover_config import MONITOR_INTERVAL_SECONDS, get_motor_definitions
from services.monitor_base import MonitorBase
from services.motor_state_store import MotorStateStore


class Ev3MotorHardwareBackend(object):
    """Loads the supported python-ev3dev2 motor classes when available."""

    def __init__(self):
        self._motor_classes = {}
        self.error_message = None
        self._load_motor_classes()

    def _load_motor_classes(self):
        try:
            from ev3dev2.motor import LargeMotor  # pylint: disable=import-error
            from ev3dev2.motor import MediumMotor  # pylint: disable=import-error

            self._motor_classes = {
                "LargeMotor": LargeMotor,
                "MediumMotor": MediumMotor
            }
            self.error_message = None
        except Exception as error:  # pragma: no cover - environment dependent
            self._motor_classes = {}
            self.error_message = str(error)

    def is_available(self):
        return bool(self._motor_classes)

    def get_motor_class(self, motor_class_name):
        return self._motor_classes.get(motor_class_name)


class MotorRegistry(object):
    """Owns physical motor instances and performs EV3 read/write access."""

    VALID_STOP_ACTIONS = ("coast", "brake", "hold")

    def __init__(self, motor_definitions, hardware_backend):
        self.motor_definitions = motor_definitions
        self.hardware_backend = hardware_backend
        self._motors = {}
        self._errors = {}

    @staticmethod
    def _safe_get(motor, attribute_name, default=None):
        try:
            return getattr(motor, attribute_name)
        except Exception:  # pragma: no cover - depends on EV3 driver
            return default

    @staticmethod
    def _normalize_state(value):
        if value is None:
            return []
        if isinstance(value, (tuple, set)):
            return list(value)
        if isinstance(value, list):
            return value
        return [value]

    def connect_motor(self, motor_code):
        definition = self.motor_definitions.get(motor_code)
        if definition is None:
            return None

        motor_class = self.hardware_backend.get_motor_class(
            definition.get("motor_class")
        )
        if motor_class is None:
            self._errors[motor_code] = (
                self.hardware_backend.error_message
                or "Configured motor class is not available"
            )
            return None

        try:
            motor = motor_class(definition["address"])
            polarity = definition.get("polarity")
            if polarity is not None:
                motor.polarity = polarity
            self._motors[motor_code] = motor
            self._errors[motor_code] = None
            return motor
        except Exception as error:  # pragma: no cover - hardware dependent
            self._motors.pop(motor_code, None)
            self._errors[motor_code] = str(error)
            return None

    def get_motor(self, motor_code):
        motor = self._motors.get(motor_code)
        if motor is None:
            motor = self.connect_motor(motor_code)
        if motor is None:
            return None

        connected = self._safe_get(motor, "connected", True)
        if connected is False:
            self._motors.pop(motor_code, None)
            self._errors[motor_code] = "Motor is disconnected"
            return None
        return motor

    def read_motor(self, motor_code):
        motor = self.get_motor(motor_code)
        if motor is None:
            return None

        return {
            "position": self._safe_get(motor, "position", 0),
            "speed": self._safe_get(motor, "speed", 0),
            "duty_cycle": self._safe_get(motor, "duty_cycle", 0),
            "state": self._normalize_state(self._safe_get(motor, "state", [])),
            "driver_name": self._safe_get(motor, "driver_name"),
            "max_speed": self._safe_get(motor, "max_speed"),
            "polarity": self._safe_get(motor, "polarity"),
            "connected": True
        }

    def _apply_stop_action(self, motor, stop_action):
        if stop_action is not None:
            motor.stop_action = stop_action

    def execute(self, motor_code, operation_name, operation):
        """Executes one immediate hardware operation without queueing."""
        motor = self.get_motor(motor_code)
        if motor is None:
            return False, self.get_error(motor_code)

        try:
            operation(motor)
            self._errors[motor_code] = None
            return True, None
        except Exception as error:  # pragma: no cover - hardware dependent
            self._errors[motor_code] = "{} failed: {}".format(
                operation_name, error
            )
            return False, self._errors[motor_code]

    def stop_motor(self, motor_code, stop_action=None):
        def operation(motor):
            self._apply_stop_action(motor, stop_action)
            motor.stop()
        return self.execute(motor_code, "stop", operation)

    def run_timed_motor(self, motor_code, speed_sp, time_sp, stop_action=None):
        def operation(motor):
            self._apply_stop_action(motor, stop_action)
            motor.run_timed(speed_sp=speed_sp, time_sp=time_sp)
        return self.execute(motor_code, "run-timed", operation)

    def run_forever_motor(self, motor_code, speed_sp, stop_action=None):
        def operation(motor):
            self._apply_stop_action(motor, stop_action)
            motor.run_forever(speed_sp=speed_sp)
        return self.execute(motor_code, "run-forever", operation)

    def run_to_rel_pos_motor(
        self, motor_code, speed_sp, position_sp, stop_action=None
    ):
        def operation(motor):
            self._apply_stop_action(motor, stop_action)
            motor.run_to_rel_pos(speed_sp=speed_sp, position_sp=position_sp)
        return self.execute(motor_code, "run-to-rel-pos", operation)

    def reset_motor(self, motor_code):
        return self.execute(motor_code, "reset", lambda motor: motor.reset())

    def get_error(self, motor_code):
        return self._errors.get(motor_code)


class MotorMonitor(MonitorBase):
    """Publishes motor state and exposes immediate basic motor commands."""

    def __init__(
        self,
        state_store=None,
        interval_seconds=None,
        hardware_backend=None
    ):
        interval = (
            MONITOR_INTERVAL_SECONDS
            if interval_seconds is None
            else interval_seconds
        )
        MonitorBase.__init__(self, "MotorMonitor", interval)
        self.state_store = state_store or MotorStateStore()
        self.motor_definitions = get_motor_definitions()
        self.hardware_backend = hardware_backend or Ev3MotorHardwareBackend()
        self.motor_registry = MotorRegistry(
            self.motor_definitions,
            self.hardware_backend
        )
        self._load_configured_motors()
        self._refresh_all_motors()

    def _base_snapshot(self, motor_code, definition):
        return {
            "code": motor_code,
            "name": definition["name"],
            "address": definition["address"],
            "motor_class": definition.get("motor_class"),
            "polarity": definition.get("polarity"),
            "position": 0,
            "speed": 0,
            "duty_cycle": 0,
            "state": [],
            "driver_name": None,
            "max_speed": None,
            "connected": False,
            "source": "ev3dev2",
            "error": None
        }

    def _load_configured_motors(self):
        for code, definition in self.motor_definitions.items():
            self.state_store.update_motor(
                code,
                self._base_snapshot(code, definition)
            )

    def _refresh_motor(self, motor_code):
        definition = self.motor_definitions[motor_code]
        snapshot = self._base_snapshot(motor_code, definition)
        hardware_snapshot = self.motor_registry.read_motor(motor_code)

        if hardware_snapshot is not None:
            snapshot.update(hardware_snapshot)
            snapshot["error"] = None
        else:
            snapshot["error"] = self.motor_registry.get_error(motor_code)

        self.state_store.update_motor(motor_code, snapshot)
        return snapshot

    def _refresh_all_motors(self):
        for motor_code in self.motor_definitions:
            self._refresh_motor(motor_code)

    def on_cycle(self):
        self._refresh_all_motors()

    def list_motors(self):
        return [
            {
                "code": item["code"],
                "name": item["name"],
                "address": item["address"],
                "connected": item["connected"]
            }
            for item in self.state_store.get_all_motors()
        ]

    def read_motor(self, motor_code):
        return self.state_store.get_motor(motor_code)

    def read_all_motors(self):
        return self.state_store.get_all_motors()

    def _command_result(self, motor_code, accepted, operation, error=None):
        if motor_code not in self.motor_definitions:
            return None

        snapshot = self._refresh_motor(motor_code)
        return {
            "accepted": bool(accepted),
            "operation": operation,
            "motor": snapshot,
            "error": error
        }

    def stop_motor(self, motor_code, stop_action=None):
        accepted, error = self.motor_registry.stop_motor(
            motor_code, stop_action
        )
        return self._command_result(motor_code, accepted, "stop", error)

    def run_timed_motor(self, motor_code, speed_sp, time_sp, stop_action=None):
        accepted, error = self.motor_registry.run_timed_motor(
            motor_code, speed_sp, time_sp, stop_action
        )
        return self._command_result(
            motor_code, accepted, "run-timed", error
        )

    def run_forever_motor(self, motor_code, speed_sp, stop_action=None):
        accepted, error = self.motor_registry.run_forever_motor(
            motor_code, speed_sp, stop_action
        )
        return self._command_result(
            motor_code, accepted, "run-forever", error
        )

    def run_to_rel_pos_motor(
        self, motor_code, speed_sp, position_sp, stop_action=None
    ):
        accepted, error = self.motor_registry.run_to_rel_pos_motor(
            motor_code, speed_sp, position_sp, stop_action
        )
        return self._command_result(
            motor_code, accepted, "run-to-rel-pos", error
        )

    def reset_motor(self, motor_code):
        accepted, error = self.motor_registry.reset_motor(motor_code)
        return self._command_result(motor_code, accepted, "reset", error)
