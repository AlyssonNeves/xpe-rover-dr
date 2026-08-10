#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Automated unit tests for AppLogger and rover configuration helpers.
"""

import io
import json
import os
import re
import sys
import unittest

from app import rover_config
from infrastructure.logging.app_logger import AppLogger


class AppLoggerTestCase(unittest.TestCase):
    """Validates centralized log formatting."""

    def _capture_stderr(self, callback):
        """Captures stderr emitted by a logging callback."""
        original_stderr = sys.stderr
        stream = io.StringIO()
        sys.stderr = stream

        try:
            callback()
        finally:
            sys.stderr = original_stderr

        return stream.getvalue()

    def test_status_writes_formatted_message_to_stderr(self):
        """Status log must include timestamp, level, thread, and message."""
        output = self._capture_stderr(
            lambda: AppLogger.status("system ready")
        )

        self.assertRegex(
            output,
            r"^\d{2}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d{3} "
            r"\[STATUS\]\[.{23}\] system ready\n$"
        )

    def test_error_writes_formatted_message_to_stderr(self):
        """Error log must include timestamp, level, thread, and message."""
        output = self._capture_stderr(
            lambda: AppLogger.error("system failed")
        )

        self.assertRegex(
            output,
            r"^\d{2}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d{3} "
            r"\[ERROR \]\[.{23}\] system failed\n$"
        )

    def test_timestamp_uses_expected_precision(self):
        """Logger timestamp must use milliseconds precision."""
        timestamp = AppLogger._timestamp()

        self.assertTrue(
            re.match(r"^\d{2}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d{3}$", timestamp)
        )


class RoverConfigTestCase(unittest.TestCase):
    """Validates canonical immutable configuration defaults."""

    def test_application_version_is_explicit_semantic_version(self):
        """Application version must use the explicit release identifier."""
        self.assertEqual(
            rover_config.APPLICATION_VERSION,
            rover_config.DEFAULT_CONFIGURATION.application_version
        )
        self.assertRegex(
            rover_config.APPLICATION_VERSION,
            r"^\d+\.\d+\.\d+$"
        )

    def test_sensor_definitions_have_required_fields(self):
        """Each configured sensor must expose required metadata fields."""
        required_fields = (
            "name", "address", "mode", "unit", "supported_modes"
        )
        definitions = rover_config.DEFAULT_CONFIGURATION.sensor_definitions

        for sensor_code, sensor_definition in definitions.items():
            for field_name in required_fields:
                self.assertIn(field_name, sensor_definition, sensor_code)
            self.assertIn(
                sensor_definition["mode"],
                sensor_definition["supported_modes"],
                sensor_code
            )

    def test_boolean_parser_accepts_common_values(self):
        """Boolean parser must support common environment values."""
        self.assertTrue(rover_config.parse_boolean("true"))
        self.assertTrue(rover_config.parse_boolean("1"))
        self.assertTrue(rover_config.parse_boolean("yes"))
        self.assertFalse(rover_config.parse_boolean("false", default=True))
        self.assertFalse(rover_config.parse_boolean("0", default=True))
        self.assertFalse(rover_config.parse_boolean("no", default=True))
        self.assertTrue(rover_config.parse_boolean(None, default=True))

    def test_hardware_is_enabled_by_default(self):
        """Rover hardware mode must be enabled by default for EV3 deployment."""
        self.assertTrue(
            rover_config.DEFAULT_CONFIGURATION.hardware_enabled
        )

    def test_motor_definitions_match_physical_installation(self):
        """Canonical motor definitions must match the installed hardware."""
        definitions = rover_config.DEFAULT_CONFIGURATION.motor_definitions
        self.assertEqual({"LLM", "LMM", "RMM", "RLM"}, set(definitions))

        expected_polarities = {
            "LLM": "inversed",
            "LMM": "inversed",
            "RLM": "inversed",
            "RMM": "normal"
        }
        for motor_code, motor_definition in definitions.items():
            self.assertIn("name", motor_definition, motor_code)
            self.assertIn("address", motor_definition, motor_code)
            self.assertIn("motor_class", motor_definition, motor_code)
            self.assertIn(
                motor_definition["motor_class"],
                ("LargeMotor", "MediumMotor"),
                motor_code
            )
            self.assertEqual(
                expected_polarities[motor_code],
                motor_definition["polarity"]
            )

    def test_mecanum_speed_factors_apply_physical_gear_compensation(self):
        """Canonical defaults must compensate the front-wheel transmission."""
        expected = {
            "front_left_speed_factor": -0.8,
            "rear_left_speed_factor": 1.0,
            "front_right_speed_factor": -0.8,
            "rear_right_speed_factor": 1.0
        }
        factors = dict(
            (key, rover_config.DEFAULT_CONFIGURATION.mecanum[key])
            for key in expected
        )

        self.assertEqual(expected, factors)
        self.assertAlmostEqual(
            abs(expected["front_left_speed_factor"]) * 1.25,
            expected["rear_left_speed_factor"]
        )
        self.assertAlmostEqual(
            abs(expected["front_right_speed_factor"]) * 1.25,
            expected["rear_right_speed_factor"]
        )

    def test_gyro_port_setup_uses_canonical_defaults(self):
        """Canonical defaults must force the EV3 gyro UART port path."""
        configuration = rover_config.DEFAULT_CONFIGURATION
        self.assertEqual(
            "ev3-uart",
            configuration.sensor_definitions["GYR"]["port_mode"]
        )
        expected = {
            "connection_timeout_seconds": 10.0,
            "connection_retry_seconds": 0.1
        }
        actual = dict(
            (key, configuration.field_heading[key]) for key in expected
        )
        self.assertEqual(expected, actual)

    def test_field_heading_controls_use_canonical_defaults(self):
        """FIELD calibration and recentering must have one default source."""
        configuration = rover_config.DEFAULT_CONFIGURATION
        expected_heading = {
            "angle_sign": -1.0,
            "angle_offset_deg": 0.0,
            "runtime_recenter_enabled": True,
            "recenter_requires_neutral": True
        }
        expected_buttons = {
            "emergency_stop": 304,
            "field_recenter": 307
        }
        self.assertEqual(
            expected_heading,
            dict((key, configuration.field_heading[key])
                 for key in expected_heading)
        )
        self.assertEqual(
            expected_buttons,
            configuration.joystick["button_codes"].to_dict()
        )

    def test_joystick_startup_and_response_use_canonical_defaults(self):
        """Joystick startup and shaping must have one default source."""
        expected = {
            "connection_timeout_seconds": 10.0,
            "passive_reconnect_seconds": 4.0,
            "discovery_poll_seconds": 0.25,
            "axis_center": 127,
            "axis_deadzone": 7,
            "axis_max": 255,
            "axis_response_intensity": 1.0,
            "neutral_stability_seconds": 0.25,
            "neutral_poll_seconds": 0.05
        }
        actual = dict((
            key, rover_config.DEFAULT_CONFIGURATION.joystick[key]
        ) for key in expected)
        self.assertEqual(expected, actual)

    def test_packaged_json_contains_only_non_default_overrides(self):
        """Packaged JSON must not duplicate canonical Python defaults."""
        project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        config_path = os.path.join(
            project_root, "config", "rover_config.json"
        )
        with open(config_path, "r") as config_file:
            overrides = json.load(config_file)

        defaults = rover_config.build_default_configuration_values()
        redundant_paths = []

        def collect_redundant(current_overrides, current_defaults, prefix=""):
            for key, value in current_overrides.items():
                path_name = "{}.{}".format(prefix, key) if prefix else key
                default_value = current_defaults.get(key)
                if isinstance(value, dict) and isinstance(default_value, dict):
                    collect_redundant(value, default_value, path_name)
                elif key in current_defaults and value == default_value:
                    redundant_paths.append(path_name)

        collect_redundant(overrides, defaults)
        self.assertEqual([], redundant_paths)

    def test_default_value_builder_returns_independent_deep_copies(self):
        """Callers must never mutate the canonical default tree."""
        first = rover_config.build_default_configuration_values()
        second = rover_config.build_default_configuration_values()

        first["mecanum"]["front_left_speed_factor"] = 99.0

        self.assertEqual(-0.8, second["mecanum"]["front_left_speed_factor"])
        self.assertEqual(
            -0.8,
            rover_config.DEFAULT_CONFIGURATION.mecanum[
                "front_left_speed_factor"
            ]
        )

    def test_mecanum_strafe_compensation_uses_canonical_default(self):
        """Canonical defaults must retain the 1.1 strafe factor."""
        self.assertEqual(
            1.1,
            rover_config.DEFAULT_CONFIGURATION.mecanum[
                "strafe_compensation"
            ]
        )

    def test_default_configuration_has_no_operational_tokens(self):
        """Fallback defaults must not contain deployment credentials."""
        configuration = rover_config.DEFAULT_CONFIGURATION
        self.assertIsNone(configuration.shutdown_token)
        self.assertIsNone(configuration.hardware_api_token)

    def test_security_validation_is_owned_by_configuration_object(self):
        """Canonical validation must reject missing deployment credentials."""
        with self.assertRaisesRegex(RuntimeError, "ROVER_SHUTDOWN_TOKEN"):
            rover_config.DEFAULT_CONFIGURATION.validate_security()


if __name__ == "__main__":
    unittest.main()
