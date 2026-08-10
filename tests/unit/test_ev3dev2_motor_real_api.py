#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Contract evidence against python-ev3dev2==2.1.0.post1 when installed."""

import inspect
import unittest

import pytest

try:
    from ev3dev2 import motor
except ImportError:
    raise unittest.SkipTest("python-ev3dev2 is not installed")


@pytest.mark.parametrize("class_name", [
    "LargeMotor", "MediumMotor", "MotorSet", "MoveTank", "MoveSteering",
    "MoveJoystick", "MoveDifferential"
])
def test_supported_official_classes_have_inspectable_signatures(class_name):
    cls = getattr(motor, class_name)
    inspect.signature(cls)


@pytest.mark.parametrize("class_name,method_name", [
    ("LargeMotor", "on"), ("LargeMotor", "run_forever"),
    ("MediumMotor", "run_direct"), ("MotorSet", "off"),
    ("MoveTank", "on"), ("MoveSteering", "on"),
    ("MoveJoystick", "on"), ("MoveDifferential", "odometry_start"),
    ("MoveDifferential", "odometry_stop")
])
def test_critical_official_method_signatures(class_name, method_name):
    inspect.signature(getattr(getattr(motor, class_name), method_name))
