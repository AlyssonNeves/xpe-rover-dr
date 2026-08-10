#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Shared factory for EV3 native motor drivers."""

try:
    from ev3dev2.motor import LargeMotor, MediumMotor
except ImportError:  # pragma: no cover - hardware dependency
    LargeMotor = None
    MediumMotor = None


class Ev3MotorDriverFactory(object):
    """Creates EV3 drivers with the globally configured motor polarity.

    Every monitored, REST-controlled and local-manual motor reaches hardware
    through this factory, making ``motor_definitions[*].polarity`` the single
    physical-installation rule for the whole application.
    """

    MOTOR_CLASSES = {
        "large": LargeMotor,
        "medium": MediumMotor,
        "LargeMotor": LargeMotor,
        "MediumMotor": MediumMotor
    }

    def __init__(self, motor_classes=None):
        self.error_message = None
        self.motor_classes = dict(
            motor_classes if motor_classes is not None else self.MOTOR_CLASSES
        )

    def is_available(self):
        return any(value is not None for value in self.motor_classes.values())

    def get_motor_class(self, motor_type):
        key = motor_type or "large"
        return (
            self.motor_classes.get(key)
            or self.motor_classes.get(str(key).lower())
        )

    def create_motor(self, motor_definition):
        definition = dict(motor_definition or {})
        class_key = definition.get(
            "motor_class", definition.get("type", "large")
        )
        motor_class = self.get_motor_class(class_key)
        if motor_class is None:
            raise RuntimeError(
                "EV3 motor driver is unavailable for type: {}".format(
                    class_key
                )
            )
        motor = motor_class(definition.get("address"))
        polarity = definition.get("polarity")
        if polarity and hasattr(motor, "polarity"):
            motor.polarity = polarity
        return motor
