#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Immutable application configuration models.

This module contains data-only configuration objects. It performs no file,
environment, network, or hardware access during import. Configuration default
resolution belongs to ``RoverConfigurationLoader`` and ``app.rover_config``.
"""

import copy
import math

try:
    from collections.abc import Mapping
except ImportError:  # pragma: no cover - Python 3.5 compatibility
    from collections import Mapping


class FrozenMapping(Mapping):
    """Small recursively immutable mapping compatible with Python 3.5."""

    def __init__(self, values=None):
        self._values = {}
        for key, value in dict(values or {}).items():
            self._values[key] = freeze_value(value)

    def __getitem__(self, key):
        return self._values[key]

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def get(self, key, default=None):
        return self._values.get(key, default)

    def items(self):
        return self._values.items()

    def keys(self):
        return self._values.keys()

    def values(self):
        return self._values.values()

    def to_dict(self):
        return thaw_value(self)


def freeze_value(value):
    """Recursively freezes configuration collections."""
    if isinstance(value, FrozenMapping):
        return value
    if isinstance(value, dict):
        return FrozenMapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(freeze_value(item) for item in value)
    return copy.deepcopy(value)


def thaw_value(value):
    """Returns a mutable deep copy of a frozen configuration value."""
    if isinstance(value, FrozenMapping):
        return dict((key, thaw_value(item)) for key, item in value.items())
    if isinstance(value, tuple):
        return [thaw_value(item) for item in value]
    return copy.deepcopy(value)


class RoverConfiguration(object):
    """Immutable, fully resolved configuration snapshot."""

    __slots__ = (
        "application_name", "application_version", "rest_host", "rest_port",
        "shutdown_token", "hardware_api_token",
        "shutdown_confirmation_required", "hardware_enabled",
        "motor_gateway_max_objects", "motor_gateway_object_ttl_seconds",
        "motor_gateway_max_watchdog_ms", "motor_gateway_wait_max_timeout_ms",
        "motor_command_timeout_ms", "motor_run_forever_watchdog_ms",
        "motor_stall_timeout_ms", "motor_default_stop_action",
        "motor_ramp_up_ms", "motor_ramp_down_ms", "sensor_definitions",
        "motor_definitions", "drive", "mecanum", "field_heading", "joystick",
        "source_path", "_sealed"
    )

    def __init__(self, values):
        data = dict(values or {})
        self._require_top_level_values(data)
        object.__setattr__(self, "application_name", data["application_name"])
        object.__setattr__(self, "application_version", data["application_version"])
        object.__setattr__(self, "rest_host", data["rest_host"])
        object.__setattr__(self, "rest_port", int(data["rest_port"]))
        object.__setattr__(self, "shutdown_token", data["shutdown_token"])
        object.__setattr__(self, "hardware_api_token", data["hardware_api_token"])
        object.__setattr__(
            self, "shutdown_confirmation_required",
            self._require_boolean_value(
                "shutdown_confirmation_required",
                data["shutdown_confirmation_required"]
            )
        )
        object.__setattr__(
            self, "hardware_enabled",
            self._require_boolean_value(
                "hardware_enabled", data["hardware_enabled"]
            )
        )
        object.__setattr__(
            self, "motor_gateway_max_objects",
            int(data["motor_gateway_max_objects"])
        )
        object.__setattr__(
            self, "motor_gateway_object_ttl_seconds",
            int(data["motor_gateway_object_ttl_seconds"])
        )
        object.__setattr__(
            self, "motor_gateway_max_watchdog_ms",
            int(data["motor_gateway_max_watchdog_ms"])
        )
        object.__setattr__(
            self, "motor_gateway_wait_max_timeout_ms",
            int(data["motor_gateway_wait_max_timeout_ms"])
        )
        object.__setattr__(
            self, "motor_command_timeout_ms", int(data["motor_command_timeout_ms"])
        )
        object.__setattr__(
            self, "motor_run_forever_watchdog_ms",
            int(data["motor_run_forever_watchdog_ms"])
        )
        object.__setattr__(
            self, "motor_stall_timeout_ms", int(data["motor_stall_timeout_ms"])
        )
        object.__setattr__(
            self, "motor_default_stop_action", data["motor_default_stop_action"]
        )
        object.__setattr__(self, "motor_ramp_up_ms", int(data["motor_ramp_up_ms"]))
        object.__setattr__(
            self, "motor_ramp_down_ms", int(data["motor_ramp_down_ms"])
        )
        object.__setattr__(
            self, "sensor_definitions", FrozenMapping(data["sensor_definitions"])
        )
        object.__setattr__(
            self, "motor_definitions", FrozenMapping(data["motor_definitions"])
        )
        object.__setattr__(self, "drive", FrozenMapping(data["drive"]))
        object.__setattr__(self, "mecanum", FrozenMapping(data["mecanum"]))
        object.__setattr__(
            self, "field_heading", FrozenMapping(data["field_heading"])
        )
        object.__setattr__(self, "joystick", FrozenMapping(data["joystick"]))
        object.__setattr__(self, "source_path", data["source_path"])
        object.__setattr__(self, "_sealed", True)

    @staticmethod
    def _require_top_level_values(data):
        required = (
            "application_name", "application_version", "rest_host", "rest_port",
            "shutdown_token", "hardware_api_token",
            "shutdown_confirmation_required", "hardware_enabled",
            "motor_gateway_max_objects", "motor_gateway_object_ttl_seconds",
            "motor_gateway_max_watchdog_ms", "motor_gateway_wait_max_timeout_ms",
            "motor_command_timeout_ms", "motor_run_forever_watchdog_ms",
            "motor_stall_timeout_ms", "motor_default_stop_action",
            "motor_ramp_up_ms", "motor_ramp_down_ms", "sensor_definitions",
            "motor_definitions", "drive", "mecanum", "field_heading", "joystick",
            "source_path"
        )
        missing = [key for key in required if key not in data]
        if missing:
            raise RuntimeError(
                "Configuration snapshot is not fully resolved; missing: {0}.".format(
                    ", ".join(missing)
                )
            )

    @staticmethod
    def _require_boolean_value(name, value):
        if not isinstance(value, bool):
            raise RuntimeError("{0} must be a boolean.".format(name))
        return value

    def __setattr__(self, name, value):
        if getattr(self, "_sealed", False):
            raise AttributeError("RoverConfiguration is immutable.")
        object.__setattr__(self, name, value)

    def validate(self):
        """Validates the fully merged runtime configuration."""
        self._validate_top_level_ranges()
        self._validate_sensor_definitions()
        self._validate_motor_definitions()
        self._validate_drive_configuration()
        self._validate_mecanum_configuration()
        self._validate_field_heading_configuration()
        self._validate_joystick_configuration()

    def _validate_top_level_ranges(self):
        if not str(self.application_name).strip():
            raise RuntimeError("application_name must not be empty.")
        if not str(self.application_version).strip():
            raise RuntimeError("application_version must not be empty.")
        if not str(self.rest_host).strip():
            raise RuntimeError("rest_host must not be empty.")
        self._require_range("rest_port", self.rest_port, minimum=1, maximum=65535)
        positive_values = (
            ("motor_gateway_max_objects", self.motor_gateway_max_objects),
            ("motor_gateway_object_ttl_seconds", self.motor_gateway_object_ttl_seconds),
            ("motor_gateway_max_watchdog_ms", self.motor_gateway_max_watchdog_ms),
            (
                "motor_gateway_wait_max_timeout_ms",
                self.motor_gateway_wait_max_timeout_ms
            ),
            ("motor_command_timeout_ms", self.motor_command_timeout_ms),
            ("motor_run_forever_watchdog_ms", self.motor_run_forever_watchdog_ms),
            ("motor_stall_timeout_ms", self.motor_stall_timeout_ms)
        )
        for name, value in positive_values:
            self._require_positive(name, value)
        for name, value in (
                ("motor_ramp_up_ms", self.motor_ramp_up_ms),
                ("motor_ramp_down_ms", self.motor_ramp_down_ms)):
            self._require_non_negative(name, value)
        if self.motor_default_stop_action not in ("coast", "brake", "hold"):
            raise RuntimeError(
                "motor_default_stop_action must be coast, brake, or hold."
            )

    def _validate_sensor_definitions(self):
        required = ("name", "address", "mode", "unit", "supported_modes")
        for sensor_code, definition in self.sensor_definitions.items():
            self._require_mapping_keys(
                "sensor_definitions.{0}".format(sensor_code), definition, required
            )
            supported_modes = tuple(definition["supported_modes"])
            if definition["mode"] not in supported_modes:
                raise RuntimeError(
                    "Sensor {0} mode must be included in supported_modes.".format(
                        sensor_code
                    )
                )
            port_mode = definition.get("port_mode")
            if port_mode is not None and not str(port_mode).strip():
                raise RuntimeError(
                    "Sensor {0} port_mode must not be empty.".format(
                        sensor_code
                    )
                )

    def _validate_motor_definitions(self):
        required = ("name", "address", "motor_class", "polarity", "limits")
        addresses = []
        for motor_code, definition in self.motor_definitions.items():
            self._require_mapping_keys(
                "motor_definitions.{0}".format(motor_code), definition, required
            )
            if definition["motor_class"] not in ("LargeMotor", "MediumMotor"):
                raise RuntimeError(
                    "Motor {0} uses an unsupported motor_class.".format(motor_code)
                )
            if definition["polarity"] not in ("normal", "inversed"):
                raise RuntimeError(
                    "Motor {0} polarity must be normal or inversed.".format(
                        motor_code
                    )
                )
            addresses.append(definition["address"])
        if len(addresses) != len(set(addresses)):
            raise RuntimeError("Motor definitions must use distinct output addresses.")

    def _validate_drive_configuration(self):
        required = (
            "left_motor_code", "right_motor_code", "gyro_sensor_code",
            "wheel_diameter_mm", "track_width_mm", "left_speed_factor",
            "right_speed_factor", "heading_kp", "control_interval_ms",
            "distance_tolerance_mm", "angle_tolerance_deg", "stall_timeout_ms",
            "max_recovery_attempts", "recovery_distance_mm", "telemetry_limit"
        )
        self._require_mapping_keys("drive", self.drive, required)
        self._require_motor_reference("drive.left_motor_code", self.drive["left_motor_code"])
        self._require_motor_reference(
            "drive.right_motor_code", self.drive["right_motor_code"]
        )
        if self.drive["left_motor_code"] == self.drive["right_motor_code"]:
            raise RuntimeError("Differential drive motors must be distinct.")
        self._require_sensor_reference(
            "drive.gyro_sensor_code", self.drive["gyro_sensor_code"]
        )
        for key in (
                "wheel_diameter_mm", "track_width_mm", "control_interval_ms",
                "distance_tolerance_mm", "angle_tolerance_deg", "stall_timeout_ms",
                "recovery_distance_mm", "telemetry_limit"):
            self._require_positive("drive.{0}".format(key), self.drive[key])
        self._require_non_negative(
            "drive.max_recovery_attempts", self.drive["max_recovery_attempts"]
        )
        for key in ("left_speed_factor", "right_speed_factor", "heading_kp"):
            self._require_finite("drive.{0}".format(key), self.drive[key])

    def _validate_mecanum_configuration(self):
        code_keys = (
            "front_left_motor_code", "rear_left_motor_code",
            "front_right_motor_code", "rear_right_motor_code"
        )
        factor_keys = (
            "front_left_speed_factor", "rear_left_speed_factor",
            "front_right_speed_factor", "rear_right_speed_factor"
        )
        self._require_mapping_keys(
            "mecanum", self.mecanum,
            code_keys + factor_keys + ("strafe_compensation",)
        )
        motor_codes = tuple(self.mecanum[key] for key in code_keys)
        if len(set(motor_codes)) != 4:
            raise RuntimeError("Mecanum motor codes must identify four distinct motors.")
        for key, motor_code in zip(code_keys, motor_codes):
            self._require_motor_reference("mecanum.{0}".format(key), motor_code)
        for key in factor_keys:
            self._require_finite("mecanum.{0}".format(key), self.mecanum[key])
            if float(self.mecanum[key]) == 0.0:
                raise RuntimeError("mecanum.{0} must not be zero.".format(key))
        self._require_positive(
            "mecanum.strafe_compensation", self.mecanum["strafe_compensation"]
        )

    def _validate_field_heading_configuration(self):
        required = (
            "sensor_code", "poll_seconds", "max_age_seconds",
            "connection_timeout_seconds", "connection_retry_seconds",
            "reset_on_start", "angle_sign", "angle_offset_deg",
            "runtime_recenter_enabled", "recenter_requires_neutral",
            "max_consecutive_failures"
        )
        self._require_mapping_keys("field_heading", self.field_heading, required)
        self._require_boolean_value(
            "field_heading.reset_on_start",
            self.field_heading["reset_on_start"]
        )
        self._require_sensor_reference(
            "field_heading.sensor_code", self.field_heading["sensor_code"]
        )
        self._require_positive(
            "field_heading.poll_seconds", self.field_heading["poll_seconds"]
        )
        self._require_positive(
            "field_heading.max_age_seconds", self.field_heading["max_age_seconds"]
        )
        self._require_positive(
            "field_heading.connection_timeout_seconds",
            self.field_heading["connection_timeout_seconds"]
        )
        self._require_positive(
            "field_heading.connection_retry_seconds",
            self.field_heading["connection_retry_seconds"]
        )
        if (float(self.field_heading["connection_retry_seconds"]) >
                float(self.field_heading["connection_timeout_seconds"])):
            raise RuntimeError(
                "field_heading.connection_retry_seconds must not exceed "
                "connection_timeout_seconds."
            )
        self._require_positive(
            "field_heading.max_consecutive_failures",
            self.field_heading["max_consecutive_failures"]
        )
        self._require_finite(
            "field_heading.angle_sign", self.field_heading["angle_sign"]
        )
        if float(self.field_heading["angle_sign"]) not in (-1.0, 1.0):
            raise RuntimeError(
                "field_heading.angle_sign must be either -1.0 or 1.0."
            )
        self._require_finite(
            "field_heading.angle_offset_deg",
            self.field_heading["angle_offset_deg"]
        )
        self._require_boolean_value(
            "field_heading.runtime_recenter_enabled",
            self.field_heading["runtime_recenter_enabled"]
        )
        self._require_boolean_value(
            "field_heading.recenter_requires_neutral",
            self.field_heading["recenter_requires_neutral"]
        )

    def _validate_joystick_configuration(self):
        required = (
            "device_name", "device_address", "auto_connect",
            "connection_retry_seconds", "connection_timeout_seconds",
            "passive_reconnect_seconds", "discovery_poll_seconds",
            "max_speed_sp", "auxiliary_speed_sp",
            "axis_center", "axis_deadzone", "axis_max",
            "axis_response_intensity", "neutral_stability_seconds",
            "neutral_poll_seconds", "left_auxiliary_motor_code",
            "right_auxiliary_motor_code",
            "button_codes", "poll_seconds"
        )
        self._require_mapping_keys("joystick", self.joystick, required)
        if not str(self.joystick["device_name"]).strip():
            raise RuntimeError("joystick.device_name must not be empty.")
        self._require_boolean_value(
            "joystick.auto_connect", self.joystick["auto_connect"]
        )
        for key in (
                "connection_retry_seconds", "connection_timeout_seconds",
                "discovery_poll_seconds", "max_speed_sp", "auxiliary_speed_sp",
                "axis_max", "axis_response_intensity",
                "neutral_stability_seconds", "neutral_poll_seconds",
                "poll_seconds"):
            self._require_positive("joystick.{0}".format(key), self.joystick[key])
        self._require_non_negative(
            "joystick.passive_reconnect_seconds",
            self.joystick["passive_reconnect_seconds"]
        )
        if (float(self.joystick["passive_reconnect_seconds"]) >=
                float(self.joystick["connection_timeout_seconds"])):
            raise RuntimeError(
                "joystick.passive_reconnect_seconds must be less than "
                "connection_timeout_seconds."
            )
        if (float(self.joystick["neutral_poll_seconds"]) >
                float(self.joystick["neutral_stability_seconds"])):
            raise RuntimeError(
                "joystick.neutral_poll_seconds must not exceed "
                "neutral_stability_seconds."
            )
        self._require_non_negative_integer(
            "joystick.axis_center", self.joystick["axis_center"]
        )
        self._require_non_negative_integer(
            "joystick.axis_deadzone", self.joystick["axis_deadzone"]
        )
        self._require_non_negative_integer(
            "joystick.axis_max", self.joystick["axis_max"]
        )
        axis_center = int(self.joystick["axis_center"])
        axis_deadzone = int(self.joystick["axis_deadzone"])
        axis_max = int(self.joystick["axis_max"])
        if axis_center <= 0 or axis_center >= axis_max:
            raise RuntimeError(
                "joystick.axis_center must be greater than zero and less "
                "than axis_max."
            )
        maximum_deadzone = min(axis_center, axis_max - axis_center)
        if axis_deadzone >= maximum_deadzone:
            raise RuntimeError(
                "joystick.axis_deadzone must be smaller than the usable "
                "axis range on both sides of axis_center."
            )
        for key in ("left_auxiliary_motor_code", "right_auxiliary_motor_code"):
            self._require_motor_reference(
                "joystick.{0}".format(key), self.joystick[key]
            )
        button_codes = self.joystick["button_codes"]
        self._require_mapping_keys(
            "joystick.button_codes", button_codes,
            ("emergency_stop", "field_recenter")
        )
        for key in ("emergency_stop", "field_recenter"):
            self._require_non_negative_integer(
                "joystick.button_codes.{0}".format(key), button_codes[key]
            )
        if int(button_codes["emergency_stop"]) == int(
                button_codes["field_recenter"]):
            raise RuntimeError(
                "joystick.button_codes values must be distinct."
            )

    def validate_security(self):
        """Validates mandatory credentials without reading the environment."""
        missing = []
        shutdown_token = (self.shutdown_token or "").strip()
        hardware_token = (self.hardware_api_token or "").strip()
        if not shutdown_token:
            missing.append("ROVER_SHUTDOWN_TOKEN")
        if self.hardware_enabled and not hardware_token:
            missing.append("ROVER_HARDWARE_API_TOKEN")
        if missing:
            raise RuntimeError(
                "Missing required security configuration: {0}. Define the "
                "environment variable(s) before starting Rover DR.".format(
                    ", ".join(missing)
                )
            )
        if self.hardware_enabled and shutdown_token == hardware_token:
            raise RuntimeError(
                "ROVER_SHUTDOWN_TOKEN and ROVER_HARDWARE_API_TOKEN must use "
                "different values in hardware mode."
            )

    @staticmethod
    def _require_mapping_keys(section_name, mapping, required_keys):
        missing = [key for key in required_keys if key not in mapping]
        if missing:
            raise RuntimeError(
                "Configuration section {0} is missing: {1}.".format(
                    section_name, ", ".join(missing)
                )
            )

    def _require_motor_reference(self, name, motor_code):
        if motor_code not in self.motor_definitions:
            raise RuntimeError(
                "{0} references unknown motor code: {1}.".format(name, motor_code)
            )

    def _require_sensor_reference(self, name, sensor_code):
        if sensor_code not in self.sensor_definitions:
            raise RuntimeError(
                "{0} references unknown sensor code: {1}.".format(name, sensor_code)
            )

    @staticmethod
    def _require_finite(name, value):
        try:
            numeric = float(value)
        except (TypeError, ValueError) as error:
            raise RuntimeError("{0} must be numeric.".format(name)) from error
        if not math.isfinite(numeric):
            raise RuntimeError("{0} must be finite.".format(name))

    @classmethod
    def _require_positive(cls, name, value):
        cls._require_finite(name, value)
        if float(value) <= 0.0:
            raise RuntimeError("{0} must be greater than zero.".format(name))

    @classmethod
    def _require_non_negative(cls, name, value):
        cls._require_finite(name, value)
        if float(value) < 0.0:
            raise RuntimeError("{0} must not be negative.".format(name))

    @classmethod
    def _require_non_negative_integer(cls, name, value):
        cls._require_finite(name, value)
        numeric = float(value)
        if numeric < 0.0 or numeric != int(numeric):
            raise RuntimeError(
                "{0} must be a non-negative integer.".format(name)
            )

    @classmethod
    def _require_range(cls, name, value, minimum, maximum):
        cls._require_finite(name, value)
        numeric = float(value)
        if numeric < minimum or numeric > maximum:
            raise RuntimeError(
                "{0} must be between {1} and {2}.".format(
                    name, minimum, maximum
                )
            )

    @property
    def drive_left_motor_code(self):
        return self.drive["left_motor_code"]

    @property
    def drive_right_motor_code(self):
        return self.drive["right_motor_code"]

    @property
    def joystick_device_name(self):
        return self.joystick["device_name"]
