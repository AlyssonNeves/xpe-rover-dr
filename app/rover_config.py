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
SENSOR_DEFINITIONS = ROVER_JSON_CONFIG.get("sensor_definitions", {})
MOTOR_DEFINITIONS = ROVER_JSON_CONFIG.get("motor_definitions", {})


def get_sensor_definitions():
    """Returns an isolated copy of the configured sensor registry."""
    return copy.deepcopy(SENSOR_DEFINITIONS)


def get_motor_definitions():
    """Returns an isolated copy of the configured motor registry."""
    return copy.deepcopy(MOTOR_DEFINITIONS)
