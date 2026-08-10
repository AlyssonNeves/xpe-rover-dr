#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Explicit Python-default, JSON, and environment configuration loader."""

import json
import os

from app.configuration import RoverConfiguration
from app.rover_config import (
    build_default_configuration_values,
    merge_configuration_values,
    parse_boolean
)


class RoverConfigurationLoader(object):
    """Resolves and validates one immutable configuration snapshot.

    Environment access is intentionally restricted to deployment-bound values.
    Physical, kinematic, joystick, gateway, and operational-rule settings are
    resolved only from the canonical Python defaults and JSON overrides.
    """

    CONFIG_FILE_ENVIRONMENT_VARIABLE = "ROVER_CONFIG_FILE"
    ENVIRONMENT_OVERRIDE_VARIABLES = (
        "ROVER_HARDWARE_ENABLED",
        "ROVER_SHUTDOWN_TOKEN",
        "ROVER_HARDWARE_API_TOKEN",
        "ROVER_REST_HOST",
        "ROVER_REST_PORT"
    )
    SUPPORTED_ENVIRONMENT_VARIABLES = (
        CONFIG_FILE_ENVIRONMENT_VARIABLE,
    ) + ENVIRONMENT_OVERRIDE_VARIABLES

    def __init__(self, project_root=None, environment=None):
        self.project_root = project_root or os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        self.environment = environment if environment is not None else os.environ

    def default_path(self):
        return os.path.join(self.project_root, "config", "rover_config.json")

    def load(self, config_file_path=None):
        """Loads defaults, then JSON overrides, then environment overrides."""
        self._validate_environment_surface()
        environment_path = self.environment.get(
            self.CONFIG_FILE_ENVIRONMENT_VARIABLE
        )
        explicit_path = config_file_path is not None or bool(
            environment_path and str(environment_path).strip()
        )
        path = config_file_path or environment_path or self.default_path()

        defaults = build_default_configuration_values()
        json_overrides = self._read_json(path, required=explicit_path)
        values = merge_configuration_values(defaults, json_overrides)
        values = merge_configuration_values(
            values, self._environment_overrides(values)
        )
        values["source_path"] = path if os.path.isfile(path) else None

        configuration = RoverConfiguration(values)
        configuration.validate()
        configuration.validate_security()
        return configuration

    def hardware_requested(self):
        """Best-effort hardware decision usable when configuration cannot load."""
        default = bool(build_default_configuration_values()["hardware_enabled"])
        return parse_boolean(
            self.environment.get("ROVER_HARDWARE_ENABLED"), default=default
        )

    def _validate_environment_surface(self):
        unsupported = sorted(
            name for name in self.environment
            if name.startswith("ROVER_")
            and name not in self.SUPPORTED_ENVIRONMENT_VARIABLES
        )
        if unsupported:
            raise RuntimeError(
                "Unsupported Rover environment variable(s): {0}. Move business "
                "and operational values to rover_config.json.".format(
                    ", ".join(unsupported)
                )
            )

    def _environment_overrides(self, resolved_values):
        """Returns the deliberately narrow deployment override set."""
        overrides = {}
        self._copy_text_override(overrides, "rest_host", "ROVER_REST_HOST")
        self._copy_text_override(
            overrides, "shutdown_token", "ROVER_SHUTDOWN_TOKEN",
            allow_empty=True
        )
        self._copy_text_override(
            overrides, "hardware_api_token", "ROVER_HARDWARE_API_TOKEN",
            allow_empty=True
        )
        self._copy_int_override(overrides, "rest_port", "ROVER_REST_PORT")
        self._copy_boolean_override(
            overrides, "hardware_enabled", "ROVER_HARDWARE_ENABLED",
            resolved_values["hardware_enabled"]
        )
        return overrides

    def _read_json(self, path, required):
        try:
            with open(path, "r") as config_file:
                data = json.load(config_file)
        except IOError as error:
            if not required and not os.path.exists(path):
                return {}
            raise RuntimeError(
                "Unable to read Rover configuration file: {0}".format(path)
            ) from error
        except ValueError as error:
            raise RuntimeError(
                "Invalid JSON content in Rover configuration file: {0}".format(path)
            ) from error
        if not isinstance(data, dict):
            raise RuntimeError(
                "Rover configuration root must be a JSON object: {0}".format(path)
            )
        return data

    def _copy_text_override(self, overrides, target_key, variable_name,
                            allow_empty=False):
        if variable_name not in self.environment:
            return
        raw = self.environment.get(variable_name)
        if raw is None:
            return
        value = str(raw)
        if not allow_empty and not value.strip():
            raise RuntimeError(
                "Invalid empty configuration for {0}.".format(variable_name)
            )
        overrides[target_key] = value

    def _copy_int_override(self, overrides, target_key, variable_name):
        if variable_name not in self.environment:
            return
        raw = self.environment.get(variable_name)
        if raw is None or str(raw).strip() == "":
            raise RuntimeError(
                "Invalid integer configuration for {0}: {1}".format(
                    variable_name, raw
                )
            )
        try:
            overrides[target_key] = int(raw)
        except (TypeError, ValueError) as error:
            raise RuntimeError(
                "Invalid integer configuration for {0}: {1}".format(
                    variable_name, raw
                )
            ) from error

    def _copy_boolean_override(self, overrides, target_key, variable_name,
                               default):
        if variable_name not in self.environment:
            return
        raw = self.environment.get(variable_name)
        normalized = str(raw).strip().lower() if raw is not None else ""
        accepted = (
            "true", "1", "yes", "y", "on",
            "false", "0", "no", "n", "off"
        )
        if normalized not in accepted:
            raise RuntimeError(
                "Invalid boolean configuration for {0}: {1}".format(
                    variable_name, raw
                )
            )
        overrides[target_key] = parse_boolean(raw, default=bool(default))
