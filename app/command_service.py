#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Application service used to validate and execute Rover-DR queries."""

import re

from app.models import CommandActions, CommandResult, CommandTargets


class CommandService(object):
    """Coordinates validated read-only commands through application ports."""

    RESOURCE_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_-]{0,15}$")

    def __init__(
        self,
        sensor_port,
        motor_port,
        controller_port,
        rover_state_port=None
    ):
        self.sensor_port = sensor_port
        self.motor_port = motor_port
        self.controller_port = controller_port
        self.rover_state_port = rover_state_port

    def execute(self, target, action, params=None):
        """Validates a command and dispatches it to the corresponding port."""
        validation = self._validate_envelope(target, action, params)
        if validation is not None:
            return validation

        params = params or {}

        if target == CommandTargets.SENSOR:
            return self._execute_sensor(action, params)
        if target == CommandTargets.MOTOR:
            return self._execute_motor(action, params)
        if target == CommandTargets.CONTROLLER:
            return self._execute_controller(action)
        if target == CommandTargets.ROVER:
            return self._execute_rover(action)

        return CommandResult.bad_request(
            "Unsupported command target: {}".format(target)
        )

    @staticmethod
    def _validate_envelope(target, action, params):
        if not isinstance(target, str) or not target.strip():
            return CommandResult.bad_request("Command target is required")

        if not isinstance(action, str) or not action.strip():
            return CommandResult.bad_request("Command action is required")

        if params is not None and not isinstance(params, dict):
            return CommandResult.bad_request(
                "Command parameters must be a JSON object"
            )

        return None

    def _validate_resource_code(self, params, resource_name):
        raw_code = params.get("code")
        if raw_code is None:
            return None, CommandResult.bad_request(
                "{} code is required".format(resource_name)
            )

        if not isinstance(raw_code, str):
            return None, CommandResult.bad_request(
                "{} code must be a string".format(resource_name)
            )

        code = raw_code.strip().upper()
        if not code:
            return None, CommandResult.bad_request(
                "{} code is required".format(resource_name)
            )

        if self.RESOURCE_CODE_PATTERN.match(code) is None:
            return None, CommandResult.bad_request(
                "Invalid {} code: {}".format(resource_name.lower(), raw_code)
            )

        return code, None

    def _execute_sensor(self, action, params):
        if self.sensor_port is None:
            return CommandResult.service_unavailable(
                "Sensor port is not configured"
            )

        if action == CommandActions.LIST_SENSORS:
            return CommandResult.ok(self.sensor_port.list_sensors())

        if action == CommandActions.READ_ALL_SENSORS:
            return CommandResult.ok(self.sensor_port.read_all_sensors())

        if action == CommandActions.READ_SENSOR:
            code, validation = self._validate_resource_code(params, "Sensor")
            if validation is not None:
                return validation

            sensor = self.sensor_port.read_sensor(code)
            if sensor is None:
                return CommandResult.not_found(
                    "Sensor not found: {}".format(code)
                )
            return CommandResult.ok(sensor)

        return CommandResult.bad_request(
            "Unsupported sensor action: {}".format(action)
        )

    def _execute_motor(self, action, params):
        if self.motor_port is None:
            return CommandResult.service_unavailable(
                "Motor port is not configured"
            )

        if action == CommandActions.LIST_MOTORS:
            return CommandResult.ok(self.motor_port.list_motors())

        if action == CommandActions.READ_ALL_MOTORS:
            return CommandResult.ok(self.motor_port.read_all_motors())

        if action == CommandActions.READ_MOTOR:
            code, validation = self._validate_resource_code(params, "Motor")
            if validation is not None:
                return validation

            motor = self.motor_port.read_motor(code)
            if motor is None:
                return CommandResult.not_found(
                    "Motor not found: {}".format(code)
                )
            return CommandResult.ok(motor)

        return CommandResult.bad_request(
            "Unsupported motor action: {}".format(action)
        )

    def _execute_controller(self, action):
        if self.controller_port is None:
            return CommandResult.service_unavailable(
                "Controller port is not configured"
            )

        if action == CommandActions.READ_CONTROLLER_STATUS:
            return CommandResult.ok(
                self.controller_port.read_controller_status()
            )
        if action == CommandActions.READ_CONTROLLER_NETWORK:
            return CommandResult.ok(
                self.controller_port.read_network_status()
            )
        if action == CommandActions.READ_CONTROLLER_BATTERY:
            return CommandResult.ok(
                self.controller_port.read_battery_status()
            )
        if action == CommandActions.READ_CONTROLLER_SYSTEM:
            return CommandResult.ok(
                self.controller_port.read_system_status()
            )

        return CommandResult.bad_request(
            "Unsupported controller action: {}".format(action)
        )

    def _execute_rover(self, action):
        if action != CommandActions.READ_ROVER_STATE:
            return CommandResult.bad_request(
                "Unsupported Rover action: {}".format(action)
            )

        if self.rover_state_port is None:
            return CommandResult.service_unavailable(
                "Rover state query port is not configured"
            )

        return CommandResult.ok(self.rover_state_port.get_rover_state())
