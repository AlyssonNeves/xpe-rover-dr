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
