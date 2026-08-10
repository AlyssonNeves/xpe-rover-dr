#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for S02.17 joystick axis shaping configuration."""

import pytest

from app import rover_config


def test_default_joystick_axis_shaping_matches_deployment_configuration():
    joystick = rover_config.get_joystick_config()

    assert joystick["axis_center"] == 127
    assert joystick["axis_deadzone"] == 7
    assert joystick["axis_max"] == 255
    assert joystick["axis_response_intensity"] == 1.0


def test_configuration_rejects_deadzone_that_consumes_one_axis_side():
    with pytest.raises(RuntimeError, match="axis_deadzone"):
        rover_config.validate_joystick_configuration({
            "axis_center": 127,
            "axis_deadzone": 127,
            "axis_max": 255,
            "axis_response_intensity": 1.0
        })


def test_configuration_rejects_non_positive_response_intensity():
    with pytest.raises(RuntimeError, match="axis_response_intensity"):
        rover_config.validate_joystick_configuration({
            "axis_center": 127,
            "axis_deadzone": 7,
            "axis_max": 255,
            "axis_response_intensity": 0.0
        })
