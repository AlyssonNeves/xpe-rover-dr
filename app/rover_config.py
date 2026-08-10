#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Central configuration settings for the Rover-DR application."""

import copy
import json
import math
import os


APPLICATION_NAME = "Rover-DR"
APPLICATION_VERSION = os.environ.get("ROVER_APPLICATION_VERSION", "0.1.0")

REST_HOST = "0.0.0.0"
REST_PORT = 8080

REST_SHUTDOWN_TOKEN = os.environ.get("ROVER_SHUTDOWN_TOKEN")
REST_HARDWARE_API_TOKEN = os.environ.get("ROVER_HARDWARE_API_TOKEN")

MONITOR_INTERVAL_SECONDS = 1.0
SHUTDOWN_JOIN_TIMEOUT_SECONDS = 2.0

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROVER_CONFIG_FILE = os.path.join(PROJECT_ROOT, "config", "rover_config.json")


def parse_boolean(value, default=False):
    """Parses a permissive boolean environment/configuration value."""
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


REST_SHUTDOWN_CONFIRMATION_REQUIRED = parse_boolean(
    os.environ.get("ROVER_SHUTDOWN_CONFIRMATION_REQUIRED"),
    default=True
)


def load_json_configuration(config_file_path=ROVER_CONFIG_FILE):
    """Loads and validates the centralized Rover JSON configuration."""
    try:
        with open(config_file_path, "r") as config_file:
            configuration = json.load(config_file)
    except IOError as error:
        raise RuntimeError(
            "Unable to read Rover configuration file: {}".format(
                config_file_path
            )
        ) from error
    except ValueError as error:
        raise RuntimeError(
            "Invalid JSON content in Rover configuration file: {}".format(
                config_file_path
            )
        ) from error

    if not isinstance(configuration, dict):
        raise RuntimeError("Rover configuration root must be a JSON object.")

    for section_name in ("sensor_definitions", "motor_definitions"):
        section = configuration.get(section_name)
        if not isinstance(section, dict) or not section:
            raise RuntimeError(
                "Configuration section '{}' must be a non-empty object.".format(
                    section_name
                )
            )

    return configuration


ROVER_JSON_CONFIG = load_json_configuration()


def get_hardware_enabled():
    """Returns whether physical EV3 integrations are enabled.

    ``ROVER_HARDWARE_ENABLED`` is the deployment-level override. When absent,
    the ``hardware_enabled`` value from ``config/rover_config.json`` is used.
    """
    configured_default = parse_boolean(
        ROVER_JSON_CONFIG.get("hardware_enabled"),
        default=False
    )
    return parse_boolean(
        os.environ.get("ROVER_HARDWARE_ENABLED"),
        default=configured_default
    )


# Single deployment-level switch for motors, sensors, display, buttons, LEDs,
# sound, hardware gateway and operator mode selection.
HARDWARE_ENABLED = get_hardware_enabled()

MOTOR_COMMAND_TIMEOUT_MS = int(
    ROVER_JSON_CONFIG.get("motor_command_timeout_ms", 10000)
)
MOTOR_RUN_FOREVER_WATCHDOG_MS = int(
    ROVER_JSON_CONFIG.get("motor_run_forever_watchdog_ms", 2000)
)
MOTOR_STALL_TIMEOUT_MS = int(
    ROVER_JSON_CONFIG.get("motor_stall_timeout_ms", 1500)
)
MOTOR_POSITION_TOLERANCE = int(
    ROVER_JSON_CONFIG.get("motor_position_tolerance", 5)
)
MOTOR_DEFAULT_STOP_ACTION = ROVER_JSON_CONFIG.get(
    "motor_default_stop_action", "brake"
)
MOTOR_RAMP_UP_MS = int(ROVER_JSON_CONFIG.get("motor_ramp_up_ms", 300))
MOTOR_RAMP_DOWN_MS = int(ROVER_JSON_CONFIG.get("motor_ramp_down_ms", 300))

MOTOR_GATEWAY_MAX_OBJECTS = int(
    ROVER_JSON_CONFIG.get("motor_gateway_max_objects", 32)
)
MOTOR_GATEWAY_OBJECT_TTL_SECONDS = int(
    ROVER_JSON_CONFIG.get("motor_gateway_object_ttl_seconds", 1800)
)
MOTOR_GATEWAY_MAX_WATCHDOG_MS = int(
    ROVER_JSON_CONFIG.get("motor_gateway_max_watchdog_ms", 60000)
)
MOTOR_GATEWAY_WAIT_MAX_TIMEOUT_MS = int(
    ROVER_JSON_CONFIG.get("motor_gateway_wait_max_timeout_ms", 60000)
)

SENSOR_DEFINITIONS = ROVER_JSON_CONFIG.get("sensor_definitions", {})
MOTOR_DEFINITIONS = ROVER_JSON_CONFIG.get("motor_definitions", {})

for motor_code, motor_definition in MOTOR_DEFINITIONS.items():
    polarity = motor_definition.get("polarity", "normal")
    if polarity not in ("normal", "inversed"):
        raise RuntimeError(
            "Motor '{}' has invalid polarity '{}'.".format(
                motor_code, polarity
            )
        )

JOYSTICK_CONFIG = copy.deepcopy(ROVER_JSON_CONFIG.get("joystick", {}))


def validate_joystick_configuration(configuration):
    """Validates stick geometry and response shaping configuration."""
    if not isinstance(configuration, dict):
        raise RuntimeError("Joystick configuration must be an object.")

    try:
        center = int(configuration.get("axis_center", 127))
        deadzone = int(configuration.get("axis_deadzone", 7))
        maximum = int(configuration.get("axis_max", 255))
        intensity = float(configuration.get("axis_response_intensity", 1.0))
        retry_seconds = float(
            configuration.get("connection_retry_seconds", 3.0)
        )
        timeout_seconds = float(
            configuration.get("connection_timeout_seconds", 10.0)
        )
        discovery_poll_seconds = float(
            configuration.get("discovery_poll_seconds", 0.25)
        )
    except (TypeError, ValueError):
        raise RuntimeError(
            "Joystick axis and Bluetooth timing values must be numeric."
        )

    if center <= 0 or center >= maximum:
        raise RuntimeError(
            "joystick.axis_center must be greater than zero and less than "
            "axis_max."
        )
    maximum_deadzone = min(center, maximum - center)
    if deadzone < 0 or deadzone >= maximum_deadzone:
        raise RuntimeError(
            "joystick.axis_deadzone must be non-negative and smaller than "
            "the usable axis range on both sides of axis_center."
        )
    if not math.isfinite(intensity) or intensity <= 0.0:
        raise RuntimeError(
            "joystick.axis_response_intensity must be finite and greater "
            "than zero."
        )
    for name, value in (
            ("connection_retry_seconds", retry_seconds),
            ("connection_timeout_seconds", timeout_seconds),
            ("discovery_poll_seconds", discovery_poll_seconds)):
        if not math.isfinite(value) or value <= 0.0:
            raise RuntimeError(
                "joystick.{0} must be finite and greater than zero.".format(
                    name
                )
            )
    device_name = str(
        configuration.get("device_name", "Wireless Controller") or ""
    ).strip()
    if not device_name:
        raise RuntimeError("joystick.device_name must not be empty.")
    auto_connect = parse_boolean(
        configuration.get("auto_connect"), default=False
    )
    device_address = str(configuration.get("device_address", "") or "").strip()
    if auto_connect and not device_address:
        raise RuntimeError(
            "joystick.device_address is required when auto_connect is enabled."
        )

    configuration["axis_center"] = center
    configuration["axis_deadzone"] = deadzone
    configuration["axis_max"] = maximum
    configuration["axis_response_intensity"] = intensity
    configuration["device_name"] = device_name
    configuration["device_address"] = device_address
    configuration["auto_connect"] = auto_connect
    configuration["connection_retry_seconds"] = retry_seconds
    configuration["connection_timeout_seconds"] = timeout_seconds
    configuration["discovery_poll_seconds"] = discovery_poll_seconds
    return configuration


JOYSTICK_CONFIG = validate_joystick_configuration(JOYSTICK_CONFIG)

DRIVE_CONFIG = copy.deepcopy(ROVER_JSON_CONFIG.get("drive", {}))
MECANUM_CONFIG = copy.deepcopy(ROVER_JSON_CONFIG.get("mecanum", {}))
FIELD_HEADING_CONFIG = copy.deepcopy(
    ROVER_JSON_CONFIG.get("field_heading", {"max_age_seconds": 0.1})
)
DRIVE_LEFT_MOTOR_CODE = DRIVE_CONFIG.get("left_motor_code", "LLM")
DRIVE_RIGHT_MOTOR_CODE = DRIVE_CONFIG.get("right_motor_code", "RLM")
DRIVE_GYRO_SENSOR_CODE = DRIVE_CONFIG.get("gyro_sensor_code", "GYR")
DRIVE_WHEEL_DIAMETER_MM = float(DRIVE_CONFIG.get("wheel_diameter_mm", 56.0))
DRIVE_TRACK_WIDTH_MM = float(DRIVE_CONFIG.get("track_width_mm", 120.0))

if DRIVE_LEFT_MOTOR_CODE not in MOTOR_DEFINITIONS:
    raise RuntimeError(
        "Configured left drive motor is not defined: {}".format(
            DRIVE_LEFT_MOTOR_CODE
        )
    )
if DRIVE_RIGHT_MOTOR_CODE not in MOTOR_DEFINITIONS:
    raise RuntimeError(
        "Configured right drive motor is not defined: {}".format(
            DRIVE_RIGHT_MOTOR_CODE
        )
    )
if DRIVE_LEFT_MOTOR_CODE == DRIVE_RIGHT_MOTOR_CODE:
    raise RuntimeError("Left and right drive motors must be different.")
if DRIVE_GYRO_SENSOR_CODE not in SENSOR_DEFINITIONS:
    raise RuntimeError(
        "Configured drive gyroscope is not defined: {}".format(
            DRIVE_GYRO_SENSOR_CODE
        )
    )
if DRIVE_WHEEL_DIAMETER_MM <= 0 or DRIVE_TRACK_WIDTH_MM <= 0:
    raise RuntimeError("Drive wheel diameter and track width must be positive.")

MECANUM_MOTOR_CODE_KEYS = (
    "front_left_motor_code",
    "rear_left_motor_code",
    "front_right_motor_code",
    "rear_right_motor_code"
)
MECANUM_SPEED_FACTOR_KEYS = (
    "front_left_speed_factor",
    "rear_left_speed_factor",
    "front_right_speed_factor",
    "rear_right_speed_factor"
)

if not MECANUM_CONFIG:
    raise RuntimeError("Mecanum configuration must be defined.")

mecanum_motor_codes = []
for key in MECANUM_MOTOR_CODE_KEYS:
    motor_code = MECANUM_CONFIG.get(key)
    if not motor_code:
        raise RuntimeError(
            "Mecanum configuration is missing '{}'.".format(key)
        )
    if motor_code not in MOTOR_DEFINITIONS:
        raise RuntimeError(
            "Configured Mecanum motor is not defined: {}".format(motor_code)
        )
    mecanum_motor_codes.append(motor_code)

if len(set(mecanum_motor_codes)) != 4:
    raise RuntimeError("Mecanum motor codes must identify four distinct motors.")

for key in MECANUM_SPEED_FACTOR_KEYS:
    try:
        factor = float(MECANUM_CONFIG.get(key, 1.0))
    except (TypeError, ValueError):
        raise RuntimeError(
            "Mecanum speed factor '{}' must be numeric.".format(key)
        )
    if factor == 0.0:
        raise RuntimeError(
            "Mecanum speed factor '{}' must not be zero.".format(key)
        )


try:
    MECANUM_STRAFE_COMPENSATION = float(
        MECANUM_CONFIG.get("strafe_compensation", 1.0)
    )
except (TypeError, ValueError):
    raise RuntimeError("Mecanum strafe_compensation must be numeric.")
if MECANUM_STRAFE_COMPENSATION <= 0.0:
    raise RuntimeError("Mecanum strafe_compensation must be positive.")


try:
    FIELD_HEADING_MAX_AGE_SECONDS = float(
        FIELD_HEADING_CONFIG.get("max_age_seconds", 0.1)
    )
except (TypeError, ValueError):
    raise RuntimeError("field_heading.max_age_seconds must be numeric.")
if (not math.isfinite(FIELD_HEADING_MAX_AGE_SECONDS) or
        FIELD_HEADING_MAX_AGE_SECONDS <= 0.0):
    raise RuntimeError(
        "field_heading.max_age_seconds must be finite and greater than zero."
    )
FIELD_HEADING_CONFIG["max_age_seconds"] = FIELD_HEADING_MAX_AGE_SECONDS


def validate_security_configuration():
    """Validates credentials required by the selected deployment mode.

    The shutdown token is mandatory in every mode. The hardware token is
    additionally mandatory when physical EV3 integration is enabled.
    """
    shutdown_token = os.environ.get("ROVER_SHUTDOWN_TOKEN", "").strip()
    hardware_token = os.environ.get("ROVER_HARDWARE_API_TOKEN", "").strip()
    missing = []

    if not shutdown_token:
        missing.append("ROVER_SHUTDOWN_TOKEN")
    if HARDWARE_ENABLED and not hardware_token:
        missing.append("ROVER_HARDWARE_API_TOKEN")

    if missing:
        raise RuntimeError(
            "Missing required security configuration: {}. Define the "
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
    """Returns the explicit Rover-DR semantic version identifier."""
    return APPLICATION_VERSION


def get_sensor_definitions():
    """Returns an isolated copy of the configured sensor registry."""
    return copy.deepcopy(SENSOR_DEFINITIONS)


def get_motor_definitions():
    """Returns an isolated copy of the configured motor registry."""
    return copy.deepcopy(MOTOR_DEFINITIONS)


def get_joystick_config():
    """Returns an isolated copy of the local-manual joystick configuration."""
    return copy.deepcopy(JOYSTICK_CONFIG)


def get_drive_config():
    """Returns an isolated copy of the differential-drive configuration."""
    return copy.deepcopy(DRIVE_CONFIG)


def get_mecanum_config():
    """Returns an isolated copy of the four-wheel Mecanum calibration."""
    return copy.deepcopy(MECANUM_CONFIG)


def get_field_heading_config():
    """Returns freshness settings for the cached FIELD heading pipeline."""
    return copy.deepcopy(FIELD_HEADING_CONFIG)
