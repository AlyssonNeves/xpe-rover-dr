#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Shared low-level EV3 motor driver repository."""

from app.rover_config import MOTOR_DEFAULT_STOP_ACTION


class Ev3MotorDriverRepository(object):
    """Caches native drivers and centralizes safe read/write operations."""

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
            self._errors[motor_code] = "Unknown motor code"
            return None
        try:
            motor = self.hardware_backend.create_motor(definition)
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

    def execute(self, motor_code, operation_name, operation):
        motor = self.get_motor(motor_code)
        if motor is None:
            return False, self.get_error(motor_code)
        try:
            operation(motor)
            self._errors[motor_code] = None
            return True, None
        except Exception as error:  # pragma: no cover - hardware dependent
            self._errors[motor_code] = "{0} failed: {1}".format(
                operation_name, error
            )
            return False, self._errors[motor_code]

    @staticmethod
    def _apply_stop_action(motor, stop_action):
        if stop_action is not None:
            motor.stop_action = stop_action

    def configure_motion(self, motor_code, stop_action=None,
                         ramp_up_sp=None, ramp_down_sp=None):
        stop_action = stop_action or MOTOR_DEFAULT_STOP_ACTION

        def operation(motor):
            self._apply_stop_action(motor, stop_action)
            if hasattr(motor, "ramp_up_sp"):
                motor.ramp_up_sp = max(0, int(ramp_up_sp or 0))
            if hasattr(motor, "ramp_down_sp"):
                motor.ramp_down_sp = max(0, int(ramp_down_sp or 0))
        return self.execute(motor_code, "configure-motion", operation)

    def stop_motor(self, motor_code, stop_action=None):
        stop_action = stop_action or MOTOR_DEFAULT_STOP_ACTION

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

    def run_to_rel_pos_motor(self, motor_code, speed_sp, position_sp,
                             stop_action=None):
        def operation(motor):
            self._apply_stop_action(motor, stop_action)
            motor.run_to_rel_pos(speed_sp=speed_sp, position_sp=position_sp)
        return self.execute(motor_code, "run-to-rel-pos", operation)

    def reset_motor(self, motor_code):
        return self.execute(motor_code, "reset", lambda motor: motor.reset())

    def is_running(self, motor_code):
        motor = self.get_motor(motor_code)
        if motor is None:
            return False
        state = self._normalize_state(self._safe_get(motor, "state", []))
        return "running" in state

    def get_error(self, motor_code):
        return self._errors.get(motor_code)
