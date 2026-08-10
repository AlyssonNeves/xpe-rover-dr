#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Centralized construction of native EV3 motor driver classes."""


class Ev3MotorDriverFactory(object):
    """Resolves supported python-ev3dev2 motor classes without leaking imports."""

    def __init__(self, enabled=True, motor_classes=None):
        self._motor_classes = dict(motor_classes or {})
        self.error_message = None
        if self._motor_classes:
            return
        if enabled:
            self._load_motor_classes()
        else:
            self.error_message = "Physical EV3 hardware is disabled"

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

    def create_motor(self, motor_definition):
        """Creates one native motor with the configured global polarity."""
        definition = dict(motor_definition or {})
        motor_class_name = definition.get("motor_class")
        motor_class = self.get_motor_class(motor_class_name)
        if motor_class is None:
            raise RuntimeError(
                self.error_message
                or "Configured motor class is not available: {}".format(
                    motor_class_name
                )
            )
        motor = motor_class(definition.get("address"))
        polarity = definition.get("polarity")
        if polarity is not None and hasattr(motor, "polarity"):
            motor.polarity = polarity
        return motor
