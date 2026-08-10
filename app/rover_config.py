#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Canonical Rover configuration defaults and merge helpers.

This module is the only source of configuration default values. It performs no
file, environment, network, or hardware access. Runtime configuration is
resolved explicitly by ``RoverConfigurationLoader`` using this precedence:

    Python defaults < JSON overrides < environment overrides
"""

import copy

from app.configuration import RoverConfiguration

APPLICATION_NAME = "Rover DR"
APPLICATION_VERSION = "0.68.0"
REST_HOST = "0.0.0.0"
REST_PORT = 8080
MECANUM_FRONT_GEAR_RATIO = 1.25
MECANUM_REAR_GEAR_RATIO = 1.0

MECANUM_FRONT_SPEED_FACTOR = (
    MECANUM_REAR_GEAR_RATIO / MECANUM_FRONT_GEAR_RATIO
)
MECANUM_REAR_SPEED_FACTOR = 1.0


def parse_boolean(value, default=False):
    """Parses common textual boolean forms without reading the environment."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in ("true", "1", "yes", "y", "on"):
        return True
    if normalized in ("false", "0", "no", "n", "off"):
        return False
    return default


_DEFAULT_CONFIGURATION_VALUES = {
    "application_name": APPLICATION_NAME,
    "application_version": APPLICATION_VERSION,
    "rest_host": REST_HOST,
    "rest_port": REST_PORT,
    "shutdown_token": None,
    "hardware_api_token": None,
    "shutdown_confirmation_required": True,
    "hardware_enabled": True,
    "motor_gateway_max_objects": 32,
    "motor_gateway_object_ttl_seconds": 1800,
    "motor_gateway_max_watchdog_ms": 60000,
    "motor_gateway_wait_max_timeout_ms": 60000,
    "motor_command_timeout_ms": 10000,
    "motor_run_forever_watchdog_ms": 2000,
    "motor_stall_timeout_ms": 1500,
    "motor_default_stop_action": "brake",
    "motor_ramp_up_ms": 300,
    "motor_ramp_down_ms": 300,
    "sensor_definitions": {
        "TMP": {
            "name": "Temperature",
            "address": "in1:i2c76",
            "mode": "NXT-TEMP-C",
            "unit": "C",
            "supported_modes": ["NXT-TEMP-C", "NXT-TEMP-F"]
        },
        "GYR": {
            "name": "Gyroscope",
            "address": "in3",
            "port_mode": "ev3-uart",
            "mode": "GYRO-ANG",
            "unit": "deg",
            "supported_modes": ["GYRO-ANG", "GYRO-RATE"]
        },
        "RCS": {
            "name": "Right Color Sensor",
            "address": "in2:i2c80:mux1",
            "mode": "COL-REFLECT",
            "unit": "%",
            "supported_modes": [
                "COL-REFLECT", "COL-AMBIENT", "COL-COLOR"
            ]
        },
        "LCS": {
            "name": "Left Color Sensor",
            "address": "in2:i2c81:mux2",
            "mode": "COL-REFLECT",
            "unit": "%",
            "supported_modes": [
                "COL-REFLECT", "COL-AMBIENT", "COL-COLOR"
            ]
        },
        "TCH": {
            "name": "Touch Sensor",
            "address": "in2:i2c82:mux3",
            "mode": "TOUCH",
            "unit": "pressed",
            "supported_modes": ["TOUCH"]
        }
    },
    "motor_definitions": {
        "RLM": {
            "name": "Right Large Motor",
            "address": "outD",
            "motor_class": "LargeMotor",
            "polarity": "inversed",
            "limits": {
                "max_relative_position_sp": 7200,
                "max_speed_ratio": 1.0
            }
        },
        "RMM": {
            "name": "Right Medium Motor",
            "address": "outC",
            "motor_class": "MediumMotor",
            "polarity": "normal",
            "limits": {
                "max_relative_position_sp": 7200,
                "min_position_sp": -3600,
                "max_position_sp": 3600,
                "max_speed_ratio": 1.0
            }
        },
        "LLM": {
            "name": "Left Large Motor",
            "address": "outA",
            "motor_class": "LargeMotor",
            "polarity": "inversed",
            "limits": {
                "max_relative_position_sp": 7200,
                "max_speed_ratio": 1.0
            }
        },
        "LMM": {
            "name": "Left Medium Motor",
            "address": "outB",
            "motor_class": "MediumMotor",
            "polarity": "inversed",
            "limits": {
                "max_relative_position_sp": 7200,
                "min_position_sp": -3600,
                "max_position_sp": 3600,
                "max_speed_ratio": 1.0
            }
        }
    },
    "drive": {
        "left_motor_code": "LLM",
        "right_motor_code": "RLM",
        "gyro_sensor_code": "GYR",
        "wheel_diameter_mm": 56.0,
        "track_width_mm": 120.0,
        "left_speed_factor": 1.0,
        "right_speed_factor": 1.0,
        "heading_kp": 2.0,
        "control_interval_ms": 50,
        "distance_tolerance_mm": 5.0,
        "angle_tolerance_deg": 2.0,
        "stall_timeout_ms": 1200,
        "max_recovery_attempts": 2,
        "recovery_distance_mm": 50.0,
        "telemetry_limit": 1000
    },
    "mecanum": {
        "front_right_motor_code": "RLM",
        "rear_right_motor_code": "RMM",
        "front_left_motor_code": "LLM",
        "rear_left_motor_code": "LMM",
        "front_right_speed_factor": -MECANUM_FRONT_SPEED_FACTOR,
        "rear_right_speed_factor": MECANUM_REAR_SPEED_FACTOR,
        "front_left_speed_factor": -MECANUM_FRONT_SPEED_FACTOR,
        "rear_left_speed_factor": MECANUM_REAR_SPEED_FACTOR,
        "strafe_compensation": 1.1
    },
    "field_heading": {
        "sensor_code": "GYR",
        "poll_seconds": 0.02,
        "max_age_seconds": 0.1,
        "connection_timeout_seconds": 10.0,
        "connection_retry_seconds": 0.1,
        "reset_on_start": True,
        "angle_sign": -1.0,
        "angle_offset_deg": 0.0,
        "runtime_recenter_enabled": True,
        "recenter_requires_neutral": True,
        "max_consecutive_failures": 3
    },
    "joystick": {
        "device_name": "Wireless Controller",
        "device_address": "41:42:76:52:94:E8",
        "auto_connect": True,
        "connection_retry_seconds": 3.0,
        "connection_timeout_seconds": 10.0,
        "passive_reconnect_seconds": 4.0,
        "discovery_poll_seconds": 0.25,
        "max_speed_sp": 600,
        "auxiliary_speed_sp": 600,
        "axis_center": 127,
        "axis_deadzone": 7,
        "axis_max": 255,
        "axis_response_intensity": 1.0,
        "neutral_stability_seconds": 0.25,
        "neutral_poll_seconds": 0.05,
        "left_auxiliary_motor_code": "LMM",
        "right_auxiliary_motor_code": "RMM",
        "button_codes": {
            "emergency_stop": 304,
            "field_recenter": 307
        },
        "poll_seconds": 0.01
    },
    "source_path": None
}


def build_default_configuration_values():
    """Returns a mutable deep copy of the canonical default tree."""
    return copy.deepcopy(_DEFAULT_CONFIGURATION_VALUES)


def merge_configuration_values(base_values, override_values):
    """Recursively merges override mappings without mutating either input."""
    result = copy.deepcopy(dict(base_values or {}))
    for key, value in dict(override_values or {}).items():
        current = result.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            result[key] = merge_configuration_values(current, value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def build_default_configuration():
    """Builds and validates the immutable canonical default snapshot."""
    configuration = RoverConfiguration(build_default_configuration_values())
    configuration.validate()
    return configuration


DEFAULT_CONFIGURATION = build_default_configuration()
