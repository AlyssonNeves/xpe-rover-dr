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


def test_bluetooth_connection_values_are_exposed_by_joystick_configuration():
    joystick = rover_config.get_joystick_config()
    assert joystick["device_name"] == "Wireless Controller"
    assert joystick["device_address"] == "41:42:76:52:94:E8"
    assert joystick["auto_connect"] is True
    assert joystick["connection_retry_seconds"] == 3.0
    assert joystick["connection_timeout_seconds"] == 10.0
    assert joystick["discovery_poll_seconds"] == 0.25


def test_auto_connect_requires_a_bluetooth_address():
    with __import__("pytest").raises(RuntimeError, match="device_address"):
        rover_config.validate_joystick_configuration({
            "axis_center": 127,
            "axis_deadzone": 7,
            "axis_max": 255,
            "axis_response_intensity": 1.0,
            "auto_connect": True,
            "device_address": ""
        })
