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

# ---------------------------------------------------------------------------
# Transitional compatibility surface
# ---------------------------------------------------------------------------
# Production startup resolves one immutable RoverConfiguration through
# RoverConfigurationLoader.  These aliases keep legacy modules/tests working
# during the incremental migration without reintroducing environment-backed
# mutable configuration state.

HARDWARE_ENABLED = DEFAULT_CONFIGURATION.hardware_enabled
MONITOR_INTERVAL_SECONDS = 1.0
SHUTDOWN_JOIN_TIMEOUT_SECONDS = 2.0
MOTOR_COMMAND_TIMEOUT_MS = DEFAULT_CONFIGURATION.motor_command_timeout_ms
MOTOR_RUN_FOREVER_WATCHDOG_MS = (
    DEFAULT_CONFIGURATION.motor_run_forever_watchdog_ms
)
MOTOR_STALL_TIMEOUT_MS = DEFAULT_CONFIGURATION.motor_stall_timeout_ms
MOTOR_POSITION_TOLERANCE = 5
MOTOR_DEFAULT_STOP_ACTION = DEFAULT_CONFIGURATION.motor_default_stop_action
MOTOR_RAMP_UP_MS = DEFAULT_CONFIGURATION.motor_ramp_up_ms
MOTOR_RAMP_DOWN_MS = DEFAULT_CONFIGURATION.motor_ramp_down_ms
MOTOR_GATEWAY_MAX_OBJECTS = DEFAULT_CONFIGURATION.motor_gateway_max_objects
MOTOR_GATEWAY_OBJECT_TTL_SECONDS = (
    DEFAULT_CONFIGURATION.motor_gateway_object_ttl_seconds
)
MOTOR_GATEWAY_MAX_WATCHDOG_MS = (
    DEFAULT_CONFIGURATION.motor_gateway_max_watchdog_ms
)
MOTOR_GATEWAY_WAIT_MAX_TIMEOUT_MS = (
    DEFAULT_CONFIGURATION.motor_gateway_wait_max_timeout_ms
)
SENSOR_DEFINITIONS = DEFAULT_CONFIGURATION.sensor_definitions.to_dict()
MOTOR_DEFINITIONS = DEFAULT_CONFIGURATION.motor_definitions.to_dict()
DRIVE_CONFIG = DEFAULT_CONFIGURATION.drive.to_dict()
MECANUM_CONFIG = DEFAULT_CONFIGURATION.mecanum.to_dict()
FIELD_HEADING_CONFIG = DEFAULT_CONFIGURATION.field_heading.to_dict()
JOYSTICK_CONFIG = DEFAULT_CONFIGURATION.joystick.to_dict()
DRIVE_LEFT_MOTOR_CODE = DEFAULT_CONFIGURATION.drive_left_motor_code
DRIVE_RIGHT_MOTOR_CODE = DEFAULT_CONFIGURATION.drive_right_motor_code
DRIVE_GYRO_SENSOR_CODE = DEFAULT_CONFIGURATION.drive["gyro_sensor_code"]
DRIVE_WHEEL_DIAMETER_MM = float(
    DEFAULT_CONFIGURATION.drive["wheel_diameter_mm"]
)
DRIVE_TRACK_WIDTH_MM = float(DEFAULT_CONFIGURATION.drive["track_width_mm"])
FIELD_HEADING_MAX_AGE_SECONDS = float(
    DEFAULT_CONFIGURATION.field_heading["max_age_seconds"]
)


def get_hardware_enabled():
    """Compatibility helper for the deployment-level hardware override."""
    import os
    return parse_boolean(
        os.environ.get("ROVER_HARDWARE_ENABLED"),
        default=DEFAULT_CONFIGURATION.hardware_enabled
    )


def load_json_configuration(config_file_path):
    """Legacy strict reader retained only for incremental callers/tests."""
    import json
    try:
        with open(config_file_path, "r") as config_file:
            configuration = json.load(config_file)
    except IOError as error:
        raise RuntimeError(
            "Unable to read Rover configuration file: {0}".format(
                config_file_path
            )
        ) from error
    except ValueError as error:
        raise RuntimeError(
            "Invalid JSON content in Rover configuration file: {0}".format(
                config_file_path
            )
        ) from error
    if not isinstance(configuration, dict):
        raise RuntimeError("Rover configuration root must be a JSON object.")
    for section_name in ("sensor_definitions", "motor_definitions"):
        section = configuration.get(section_name)
        if not isinstance(section, dict) or not section:
            raise RuntimeError(
                "Configuration section '{0}' must be a non-empty object.".format(
                    section_name
                )
            )
    return configuration


def _validated_section(section_name, values):
    overrides = {section_name: copy.deepcopy(dict(values or {}))}
    merged = merge_configuration_values(
        build_default_configuration_values(), overrides
    )
    configuration = RoverConfiguration(merged)
    configuration.validate()
    return getattr(configuration, section_name).to_dict()


def validate_joystick_configuration(configuration):
    """Validates a joystick mapping using the canonical immutable model."""
    return _validated_section("joystick", configuration)


def validate_field_heading_configuration(configuration):
    """Validates a FIELD heading mapping using the canonical model."""
    return _validated_section("field_heading", configuration)


def validate_security_configuration():
    """Legacy environment security check retained for direct callers."""
    import os
    shutdown_token = os.environ.get("ROVER_SHUTDOWN_TOKEN", "").strip()
    hardware_token = os.environ.get("ROVER_HARDWARE_API_TOKEN", "").strip()
    missing = []
    if not shutdown_token:
        missing.append("ROVER_SHUTDOWN_TOKEN")
    if HARDWARE_ENABLED and not hardware_token:
        missing.append("ROVER_HARDWARE_API_TOKEN")
    if missing:
        raise RuntimeError(
            "Missing required security configuration: {0}. Define the "
            "environment variable(s) before starting Rover-DR.".format(
                ", ".join(missing)
            )
        )
    if HARDWARE_ENABLED and shutdown_token == hardware_token:
        raise RuntimeError(
            "ROVER_SHUTDOWN_TOKEN and ROVER_HARDWARE_API_TOKEN must use "
            "different values in hardware mode."
        )


def get_application_version():
    return APPLICATION_VERSION


def get_sensor_definitions():
    return DEFAULT_CONFIGURATION.sensor_definitions.to_dict()


def get_motor_definitions():
    return DEFAULT_CONFIGURATION.motor_definitions.to_dict()


def get_joystick_config():
    return DEFAULT_CONFIGURATION.joystick.to_dict()


def get_drive_config():
    return DEFAULT_CONFIGURATION.drive.to_dict()


def get_mecanum_config():
    return DEFAULT_CONFIGURATION.mecanum.to_dict()


def get_field_heading_config():
    return DEFAULT_CONFIGURATION.field_heading.to_dict()

# Legacy validator behavior retained for callers from the incremental commits.
# The production loader validates strictly through RoverConfiguration.
import math as _compat_math


def validate_joystick_configuration(configuration):
    if not isinstance(configuration, dict):
        raise RuntimeError("Joystick configuration must be an object.")
    configuration = copy.deepcopy(configuration)
    try:
        center = int(configuration.get("axis_center", 127))
        deadzone = int(configuration.get("axis_deadzone", 7))
        maximum = int(configuration.get("axis_max", 255))
        intensity = float(configuration.get("axis_response_intensity", 1.0))
        retry_seconds = float(configuration.get("connection_retry_seconds", 3.0))
        timeout_seconds = float(configuration.get("connection_timeout_seconds", 10.0))
        passive_seconds = float(configuration.get("passive_reconnect_seconds", 4.0))
        discovery_seconds = float(configuration.get("discovery_poll_seconds", 0.25))
    except (TypeError, ValueError):
        raise RuntimeError("Joystick axis and Bluetooth timing values must be numeric.")
    if center <= 0 or center >= maximum:
        raise RuntimeError("joystick.axis_center must be greater than zero and less than axis_max.")
    maximum_deadzone = min(center, maximum - center)
    if deadzone < 0 or deadzone >= maximum_deadzone:
        raise RuntimeError("joystick.axis_deadzone must be non-negative and smaller than the usable axis range on both sides of axis_center.")
    if not _compat_math.isfinite(intensity) or intensity <= 0.0:
        raise RuntimeError("joystick.axis_response_intensity must be finite and greater than zero.")
    for name, value in (("connection_retry_seconds", retry_seconds), ("connection_timeout_seconds", timeout_seconds), ("discovery_poll_seconds", discovery_seconds)):
        if not _compat_math.isfinite(value) or value <= 0.0:
            raise RuntimeError("joystick.{0} must be finite and greater than zero.".format(name))
    if not _compat_math.isfinite(passive_seconds) or passive_seconds < 0.0 or passive_seconds > timeout_seconds:
        raise RuntimeError("joystick.passive_reconnect_seconds must be finite, non-negative and must not exceed connection_timeout_seconds.")
    device_name = str(configuration.get("device_name", "Wireless Controller") or "").strip()
    if not device_name:
        raise RuntimeError("joystick.device_name must not be empty.")
    auto_connect = parse_boolean(configuration.get("auto_connect"), default=False)
    device_address = str(configuration.get("device_address", "") or "").strip()
    if auto_connect and not device_address:
        raise RuntimeError("joystick.device_address is required when auto_connect is enabled.")
    button_codes = configuration.get("button_codes", {"emergency_stop": 304, "field_recenter": 307})
    if not isinstance(button_codes, dict):
        raise RuntimeError("joystick.button_codes must be an object.")
    emergency = int(button_codes.get("emergency_stop", 304))
    recenter = int(button_codes.get("field_recenter", 307))
    if emergency == recenter:
        raise RuntimeError("joystick.button_codes values must be distinct.")
    configuration.update({
        "axis_center": center, "axis_deadzone": deadzone, "axis_max": maximum,
        "axis_response_intensity": intensity, "device_name": device_name,
        "device_address": device_address, "auto_connect": auto_connect,
        "connection_retry_seconds": retry_seconds,
        "connection_timeout_seconds": timeout_seconds,
        "passive_reconnect_seconds": passive_seconds,
        "discovery_poll_seconds": discovery_seconds,
        "button_codes": {"emergency_stop": emergency, "field_recenter": recenter}
    })
    return configuration


def validate_field_heading_configuration(configuration):
    if not isinstance(configuration, dict):
        raise RuntimeError("field_heading configuration must be an object.")
    configuration = copy.deepcopy(configuration)
    sensor_code = str(configuration.get("sensor_code", "GYR") or "").strip()
    if not sensor_code or sensor_code not in SENSOR_DEFINITIONS:
        raise RuntimeError("field_heading.sensor_code must reference a configured sensor.")
    try:
        poll_seconds = float(configuration.get("poll_seconds", 0.02))
        max_age_seconds = float(configuration.get("max_age_seconds", 0.1))
        timeout_seconds = float(configuration.get("connection_timeout_seconds", 10.0))
        retry_seconds = float(configuration.get("connection_retry_seconds", 0.1))
        angle_sign = float(configuration.get("angle_sign", -1.0))
        angle_offset = float(configuration.get("angle_offset_deg", 0.0))
        max_failures = int(configuration.get("max_consecutive_failures", 3))
    except (TypeError, ValueError):
        raise RuntimeError("field_heading timing, calibration and failure values must be numeric.")
    for name, value in (("poll_seconds", poll_seconds), ("max_age_seconds", max_age_seconds), ("connection_timeout_seconds", timeout_seconds), ("connection_retry_seconds", retry_seconds)):
        if not _compat_math.isfinite(value) or value <= 0.0:
            raise RuntimeError("field_heading.{0} must be finite and greater than zero.".format(name))
    if retry_seconds > timeout_seconds:
        raise RuntimeError("field_heading.connection_retry_seconds must not exceed connection_timeout_seconds.")
    if angle_sign not in (-1.0, 1.0):
        raise RuntimeError("field_heading.angle_sign must be either -1.0 or 1.0.")
    if not _compat_math.isfinite(angle_offset) or max_failures <= 0:
        raise RuntimeError("Invalid field_heading calibration or failure limit.")
    configuration.update({
        "sensor_code": sensor_code, "poll_seconds": poll_seconds,
        "max_age_seconds": max_age_seconds, "connection_timeout_seconds": timeout_seconds,
        "connection_retry_seconds": retry_seconds,
        "reset_on_start": parse_boolean(configuration.get("reset_on_start"), default=True),
        "angle_sign": angle_sign, "angle_offset_deg": angle_offset,
        "runtime_recenter_enabled": parse_boolean(configuration.get("runtime_recenter_enabled"), default=True),
        "recenter_requires_neutral": parse_boolean(configuration.get("recenter_requires_neutral"), default=True),
        "max_consecutive_failures": max_failures
    })
    return configuration
