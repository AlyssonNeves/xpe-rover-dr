#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for explicit, layered, fail-safe Rover configuration loading."""

import json

import pytest

from app.configuration import RoverConfiguration
from infrastructure.configuration.rover_configuration_loader import (
    RoverConfigurationLoader
)


def _write_config(path, hardware_enabled=False, extra=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    values = {"hardware_enabled": hardware_enabled}
    values.update(extra or {})
    path.write_text(json.dumps(values))


def test_loader_returns_immutable_validated_snapshot(tmp_path):
    config_path = tmp_path / "config" / "rover_config.json"
    _write_config(config_path)
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={"ROVER_SHUTDOWN_TOKEN": "shutdown-secret"}
    )
    configuration = loader.load()
    assert isinstance(configuration, RoverConfiguration)
    assert configuration.source_path == str(config_path)
    with pytest.raises(AttributeError):
        configuration.rest_port = 9999


def test_loader_deep_merges_partial_nested_json_over_defaults(tmp_path):
    config_path = tmp_path / "config" / "rover_config.json"
    _write_config(
        config_path,
        extra={"mecanum": {"strafe_compensation": 1.25}}
    )
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={"ROVER_SHUTDOWN_TOKEN": "shutdown-secret"}
    )

    configuration = loader.load()

    assert configuration.mecanum["strafe_compensation"] == 1.25
    assert configuration.mecanum["front_left_motor_code"] == "LLM"
    assert configuration.mecanum["front_left_speed_factor"] == -0.8
    assert configuration.mecanum["rear_left_speed_factor"] == 1.0


def test_environment_overrides_json_and_defaults(tmp_path):
    config_path = tmp_path / "config" / "rover_config.json"
    _write_config(
        config_path,
        extra={"rest_host": "127.0.0.1", "rest_port": 8081}
    )
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={
            "ROVER_SHUTDOWN_TOKEN": "shutdown-secret",
            "ROVER_REST_HOST": "0.0.0.0",
            "ROVER_REST_PORT": "8090"
        }
    )

    configuration = loader.load()

    assert configuration.rest_host == "0.0.0.0"
    assert configuration.rest_port == 8090


def test_loader_exposes_exact_supported_environment_surface():
    assert RoverConfigurationLoader.SUPPORTED_ENVIRONMENT_VARIABLES == (
        "ROVER_CONFIG_FILE",
        "ROVER_HARDWARE_ENABLED",
        "ROVER_SHUTDOWN_TOKEN",
        "ROVER_HARDWARE_API_TOKEN",
        "ROVER_REST_HOST",
        "ROVER_REST_PORT"
    )


def test_retired_environment_values_remain_configurable_through_json(tmp_path):
    config_path = tmp_path / "config" / "rover_config.json"
    _write_config(
        config_path,
        extra={
            "application_version": "json-version",
            "shutdown_confirmation_required": False,
            "motor_gateway_max_objects": 17,
            "motor_gateway_object_ttl_seconds": 701,
            "motor_gateway_max_watchdog_ms": 702,
            "motor_gateway_wait_max_timeout_ms": 703
        }
    )
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={"ROVER_SHUTDOWN_TOKEN": "shutdown-secret"}
    )

    configuration = loader.load()

    assert configuration.application_version == "json-version"
    assert configuration.shutdown_confirmation_required is False
    assert configuration.motor_gateway_max_objects == 17
    assert configuration.motor_gateway_object_ttl_seconds == 701
    assert configuration.motor_gateway_max_watchdog_ms == 702
    assert configuration.motor_gateway_wait_max_timeout_ms == 703


def test_unsupported_rover_environment_variables_fail_fast(tmp_path):
    config_path = tmp_path / "config" / "rover_config.json"
    _write_config(config_path)
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={
            "ROVER_SHUTDOWN_TOKEN": "shutdown-secret",
            "ROVER_MOTOR_GATEWAY_MAX_OBJECTS": "99"
        }
    )

    with pytest.raises(RuntimeError, match="Unsupported Rover environment"):
        loader.load()


def test_environment_variable_typo_fails_fast(tmp_path):
    config_path = tmp_path / "config" / "rover_config.json"
    _write_config(config_path)
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={
            "ROVER_SHUTDOWN_TOKEN": "shutdown-secret",
            "ROVER_REST_PROT": "8090"
        }
    )

    with pytest.raises(RuntimeError, match="ROVER_REST_PROT"):
        loader.load()


def test_loader_reports_invalid_approved_integer_as_configuration_error(tmp_path):
    config_path = tmp_path / "config" / "rover_config.json"
    _write_config(config_path)
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={
            "ROVER_SHUTDOWN_TOKEN": "shutdown-secret",
            "ROVER_REST_PORT": "abc"
        }
    )
    with pytest.raises(RuntimeError, match="ROVER_REST_PORT"):
        loader.load()


def test_default_json_path_may_be_absent_and_uses_python_defaults(tmp_path):
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={
            "ROVER_SHUTDOWN_TOKEN": "shutdown-secret",
            "ROVER_HARDWARE_ENABLED": "false"
        }
    )

    configuration = loader.load()

    assert configuration.source_path is None
    assert configuration.drive["left_motor_code"] == "LLM"
    assert configuration.mecanum["front_left_speed_factor"] == -0.8
    assert configuration.mecanum["rear_left_speed_factor"] == 1.0


def test_environment_configuration_file_selects_explicit_json(tmp_path):
    config_path = tmp_path / "external" / "rover.json"
    _write_config(config_path, extra={"rest_port": 8181})
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={
            "ROVER_CONFIG_FILE": str(config_path),
            "ROVER_SHUTDOWN_TOKEN": "shutdown-secret"
        }
    )

    configuration = loader.load()

    assert configuration.source_path == str(config_path)
    assert configuration.rest_port == 8181


def test_explicit_missing_configuration_file_is_rejected(tmp_path):
    missing_path = tmp_path / "missing.json"
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={"ROVER_SHUTDOWN_TOKEN": "shutdown-secret"}
    )

    with pytest.raises(RuntimeError, match="Unable to read Rover configuration"):
        loader.load(str(missing_path))


@pytest.mark.parametrize("angle_sign", [0, 0.5, -2, 2])
def test_loader_rejects_invalid_field_heading_sign(tmp_path, angle_sign):
    config_path = tmp_path / "config" / "rover_config.json"
    _write_config(
        config_path,
        extra={"field_heading": {"angle_sign": angle_sign}}
    )
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={"ROVER_SHUTDOWN_TOKEN": "shutdown-secret"}
    )

    with pytest.raises(RuntimeError, match="either -1.0 or 1.0"):
        loader.load()


@pytest.mark.parametrize(
    "field_name", ["runtime_recenter_enabled", "recenter_requires_neutral"]
)
def test_loader_rejects_non_boolean_field_recenter_value(
        tmp_path, field_name):
    config_path = tmp_path / "config" / "rover_config.json"
    _write_config(
        config_path,
        extra={"field_heading": {field_name: "true"}}
    )
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={"ROVER_SHUTDOWN_TOKEN": "shutdown-secret"}
    )

    with pytest.raises(RuntimeError, match=field_name):
        loader.load()


def test_loader_rejects_empty_sensor_port_mode(tmp_path):
    config_path = tmp_path / "config" / "rover_config.json"
    _write_config(
        config_path,
        extra={"sensor_definitions": {"GYR": {"port_mode": ""}}}
    )
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={"ROVER_SHUTDOWN_TOKEN": "shutdown-secret"}
    )

    with pytest.raises(RuntimeError, match="port_mode must not be empty"):
        loader.load()


def test_loader_rejects_gyro_retry_longer_than_timeout(tmp_path):
    config_path = tmp_path / "config" / "rover_config.json"
    _write_config(
        config_path,
        extra={
            "field_heading": {
                "connection_timeout_seconds": 0.1,
                "connection_retry_seconds": 0.2
            }
        }
    )
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={"ROVER_SHUTDOWN_TOKEN": "shutdown-secret"}
    )

    with pytest.raises(RuntimeError, match="must not exceed"):
        loader.load()


def test_loader_uses_configurable_passive_joystick_reconnect(tmp_path):
    config_path = tmp_path / "config" / "rover_config.json"
    _write_config(
        config_path,
        extra={"joystick": {"passive_reconnect_seconds": 5.0}}
    )
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={"ROVER_SHUTDOWN_TOKEN": "shutdown-secret"}
    )

    configuration = loader.load()

    assert configuration.joystick["passive_reconnect_seconds"] == 5.0


@pytest.mark.parametrize("value", [-0.1, 10.0, 11.0])
def test_loader_rejects_invalid_passive_joystick_reconnect(tmp_path, value):
    config_path = tmp_path / "config" / "rover_config.json"
    _write_config(
        config_path,
        extra={"joystick": {"passive_reconnect_seconds": value}}
    )
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={"ROVER_SHUTDOWN_TOKEN": "shutdown-secret"}
    )

    with pytest.raises(RuntimeError, match="passive_reconnect_seconds"):
        loader.load()


def test_loader_uses_configurable_joystick_response_values(tmp_path):
    config_path = tmp_path / "config" / "rover_config.json"
    _write_config(
        config_path,
        extra={
            "joystick": {
                "axis_deadzone": 5,
                "axis_response_intensity": 2.5
            }
        }
    )
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={"ROVER_SHUTDOWN_TOKEN": "shutdown-secret"}
    )

    configuration = loader.load()

    assert configuration.joystick["axis_deadzone"] == 5
    assert configuration.joystick["axis_response_intensity"] == 2.5


@pytest.mark.parametrize("intensity", [0, -1, float("inf"), float("nan")])
def test_loader_rejects_invalid_joystick_response_intensity(
        tmp_path, intensity):
    config_path = tmp_path / "config" / "rover_config.json"
    _write_config(
        config_path,
        extra={"joystick": {"axis_response_intensity": intensity}}
    )
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={"ROVER_SHUTDOWN_TOKEN": "shutdown-secret"}
    )

    with pytest.raises(RuntimeError, match="axis_response_intensity"):
        loader.load()


def test_loader_uses_configurable_neutral_stability_values(tmp_path):
    config_path = tmp_path / "config" / "rover_config.json"
    _write_config(
        config_path,
        extra={
            "joystick": {
                "neutral_stability_seconds": 0.3,
                "neutral_poll_seconds": 0.05
            }
        }
    )
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={"ROVER_SHUTDOWN_TOKEN": "shutdown-secret"}
    )

    configuration = loader.load()

    assert configuration.joystick["neutral_stability_seconds"] == 0.3
    assert configuration.joystick["neutral_poll_seconds"] == 0.05


def test_loader_rejects_neutral_poll_longer_than_stability(tmp_path):
    config_path = tmp_path / "config" / "rover_config.json"
    _write_config(
        config_path,
        extra={
            "joystick": {
                "neutral_stability_seconds": 0.1,
                "neutral_poll_seconds": 0.2
            }
        }
    )
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={"ROVER_SHUTDOWN_TOKEN": "shutdown-secret"}
    )

    with pytest.raises(RuntimeError, match="neutral_poll_seconds"):
        loader.load()


@pytest.mark.parametrize(
    "field_name",
    ["neutral_stability_seconds", "neutral_poll_seconds"]
)
def test_loader_rejects_non_positive_neutral_timing(tmp_path, field_name):
    config_path = tmp_path / "config" / "rover_config.json"
    _write_config(
        config_path,
        extra={"joystick": {field_name: 0}}
    )
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={"ROVER_SHUTDOWN_TOKEN": "shutdown-secret"}
    )

    with pytest.raises(RuntimeError, match=field_name):
        loader.load()


def test_loader_rejects_deadzone_that_consumes_one_axis_side(tmp_path):
    config_path = tmp_path / "config" / "rover_config.json"
    _write_config(
        config_path,
        extra={
            "joystick": {
                "axis_center": 127,
                "axis_deadzone": 127,
                "axis_max": 255
            }
        }
    )
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={"ROVER_SHUTDOWN_TOKEN": "shutdown-secret"}
    )

    with pytest.raises(RuntimeError, match="axis_deadzone"):
        loader.load()


def test_loader_rejects_fractional_deadzone(tmp_path):
    config_path = tmp_path / "config" / "rover_config.json"
    _write_config(
        config_path, extra={"joystick": {"axis_deadzone": 7.5}}
    )
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={"ROVER_SHUTDOWN_TOKEN": "shutdown-secret"}
    )

    with pytest.raises(RuntimeError, match="non-negative integer"):
        loader.load()


def test_loader_rejects_duplicate_joystick_button_codes(tmp_path):
    config_path = tmp_path / "config" / "rover_config.json"
    _write_config(
        config_path,
        extra={
            "joystick": {
                "button_codes": {
                    "emergency_stop": 304,
                    "field_recenter": 304
                }
            }
        }
    )
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={"ROVER_SHUTDOWN_TOKEN": "shutdown-secret"}
    )

    with pytest.raises(RuntimeError, match="must be distinct"):
        loader.load()


def test_loader_rejects_non_integer_joystick_button_code(tmp_path):
    config_path = tmp_path / "config" / "rover_config.json"
    _write_config(
        config_path,
        extra={
            "joystick": {
                "button_codes": {"field_recenter": 307.5}
            }
        }
    )
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={"ROVER_SHUTDOWN_TOKEN": "shutdown-secret"}
    )

    with pytest.raises(RuntimeError, match="non-negative integer"):
        loader.load()


def test_loader_rejects_non_boolean_json_value(tmp_path):
    config_path = tmp_path / "config" / "rover_config.json"
    _write_config(config_path, extra={"joystick": {"auto_connect": "false"}})
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={"ROVER_SHUTDOWN_TOKEN": "shutdown-secret"}
    )

    with pytest.raises(RuntimeError, match="joystick.auto_connect"):
        loader.load()


def test_loader_rejects_invalid_boolean_environment_value(tmp_path):
    config_path = tmp_path / "config" / "rover_config.json"
    _write_config(config_path)
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={
            "ROVER_SHUTDOWN_TOKEN": "shutdown-secret",
            "ROVER_HARDWARE_ENABLED": "perhaps"
        }
    )

    with pytest.raises(RuntimeError, match="ROVER_HARDWARE_ENABLED"):
        loader.load()


def test_loader_requires_distinct_hardware_credentials(tmp_path):
    config_path = tmp_path / "config" / "rover_config.json"
    _write_config(config_path, hardware_enabled=True)
    loader = RoverConfigurationLoader(
        project_root=str(tmp_path),
        environment={
            "ROVER_SHUTDOWN_TOKEN": "same",
            "ROVER_HARDWARE_API_TOKEN": "same"
        }
    )
    with pytest.raises(RuntimeError, match="different values"):
        loader.load()
