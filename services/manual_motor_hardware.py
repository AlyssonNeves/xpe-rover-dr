#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Minimal EV3 motor registry dedicated to LOCAL + MANUAL operation."""


class DirectMotorHardwareBackend(object):
    """Loads only the EV3 motor classes required by direct manual control."""

    def __init__(self, motor_classes=None):
        self._motor_classes = dict(motor_classes or {})
        self.error_message = None
        if not self._motor_classes:
            self._load_motor_classes()

    def _load_motor_classes(self):
        try:
            from ev3dev2.motor import LargeMotor  # pylint: disable=import-error
            from ev3dev2.motor import MediumMotor  # pylint: disable=import-error
            self._motor_classes = {
                "LargeMotor": LargeMotor,
                "MediumMotor": MediumMotor
            }
        except Exception as error:  # pragma: no cover - hardware dependent
            self._motor_classes = {}
            self.error_message = str(error)

    def get_motor_class(self, motor_class_name):
        return self._motor_classes.get(motor_class_name)


class DirectMotorRegistry(object):
    """Caches physical EV3 drivers without queues, watchdogs or monitors."""

    def __init__(self, motor_definitions, hardware_backend=None):
        self._definitions = motor_definitions
        self._backend = hardware_backend or DirectMotorHardwareBackend()
        self._motors = {}
        self._errors = {}

    def get_motor(self, motor_code):
        motor = self._motors.get(motor_code)
        if motor is None:
            motor = self._connect_motor(motor_code)
        if motor is None:
            return None
        try:
            connected = getattr(motor, "connected", True)
        except Exception:  # pragma: no cover - hardware dependent
            connected = True
        if connected is False:
            self._motors.pop(motor_code, None)
            self._errors[motor_code] = "Motor is disconnected"
            return None
        return motor

    def get_error(self, motor_code):
        return self._errors.get(motor_code)

    def run_forever_motor(self, motor_code, speed_sp, stop_action=None):
        def operation(motor):
            if stop_action is not None:
                motor.stop_action = stop_action
            motor.run_forever(speed_sp=int(speed_sp))
        return self._execute(motor_code, "run-forever", operation)

    def stop_motor(self, motor_code, stop_action=None):
        def operation(motor):
            if stop_action is not None:
                motor.stop_action = stop_action
            motor.stop()
        return self._execute(motor_code, "stop", operation)

    def _connect_motor(self, motor_code):
        definition = self._definitions.get(motor_code)
        if definition is None:
            self._errors[motor_code] = "Unknown motor code"
            return None
        motor_class = self._backend.get_motor_class(
            definition.get("motor_class")
        )
        if motor_class is None:
            self._errors[motor_code] = (
                self._backend.error_message
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

    def _execute(self, motor_code, operation_name, operation):
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
