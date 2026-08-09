#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Central configuration settings for the Rover-DR application.

This module is the single application-facing configuration entry point. Static
runtime defaults live here, while hardware registry metadata is loaded from the
JSON configuration file.
"""

import copy
import json
import os


APPLICATION_NAME = "Rover-DR"

# REST API network configuration.
REST_HOST = "0.0.0.0"
REST_PORT = 8080

# Shared monitoring cadence and lifecycle timeout.
MONITOR_INTERVAL_SECONDS = 1.0
SHUTDOWN_JOIN_TIMEOUT_SECONDS = 2.0

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROVER_CONFIG_FILE = os.path.join(PROJECT_ROOT, "config", "rover_config.json")


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

# Motor safety defaults. These values are centralized so execution workers,
# adapters and API validation use the same operational policy.
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

SENSOR_DEFINITIONS = ROVER_JSON_CONFIG.get("sensor_definitions", {})
MOTOR_DEFINITIONS = ROVER_JSON_CONFIG.get("motor_definitions", {})


def get_sensor_definitions():
    """Returns an isolated copy of the configured sensor registry."""
    return copy.deepcopy(SENSOR_DEFINITIONS)


def get_motor_definitions():
    """Returns an isolated copy of the configured motor registry."""
    return copy.deepcopy(MOTOR_DEFINITIONS)
