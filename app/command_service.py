#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Application service used to validate and execute Rover-DR commands."""

import re

from app.models import CommandActions, CommandResult, CommandTargets


class CommandService(object):
    """Coordinates validated queries and immediate motor commands."""

    RESOURCE_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_-]{0,15}$")
    VALID_STOP_ACTIONS = ("coast", "brake", "hold")
    MIN_SPEED_SP = -2000
    MAX_SPEED_SP = 2000
    MAX_TIME_SP_MS = 600000
    MAX_REL_POSITION = 1000000

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

    @staticmethod
    def _is_integer(value):
        return isinstance(value, int) and not isinstance(value, bool)

    def _validate_speed(self, value):
        if not self._is_integer(value):
            return CommandResult.bad_request(
                "Parameter speed_sp must be an integer"
            )
        if value < self.MIN_SPEED_SP or value > self.MAX_SPEED_SP:
            return CommandResult.bad_request(
                "Parameter speed_sp must be between {} and {}".format(
                    self.MIN_SPEED_SP, self.MAX_SPEED_SP
                )
            )
        if value == 0:
            return CommandResult.bad_request(
                "Parameter speed_sp must be non-zero"
            )
        return None

    def _validate_stop_action(self, value):
        if value is None:
            return None
        if not isinstance(value, str) or value not in self.VALID_STOP_ACTIONS:
            return CommandResult.bad_request(
                "Parameter stop_action must be one of: {}".format(
                    ", ".join(self.VALID_STOP_ACTIONS)
                )
            )
        return None

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
            return self._read_motor(params)
        if action == CommandActions.STOP_MOTOR:
            return self._stop_motor(params)
        if action == CommandActions.RUN_TIMED_MOTOR:
            return self._run_timed_motor(params)
        if action == CommandActions.RUN_FOREVER_MOTOR:
            return self._run_forever_motor(params)
        if action == CommandActions.RUN_TO_REL_POS_MOTOR:
            return self._run_to_rel_pos_motor(params)
        if action == CommandActions.RESET_MOTOR:
            return self._reset_motor(params)

        return CommandResult.bad_request(
            "Unsupported motor action: {}".format(action)
        )

    def _read_motor(self, params):
        code, validation = self._validate_resource_code(params, "Motor")
        if validation is not None:
            return validation
        motor = self.motor_port.read_motor(code)
        if motor is None:
            return CommandResult.not_found("Motor not found: {}".format(code))
        return CommandResult.ok(motor)

    def _validate_motor_execution(self, params, require_speed=False):
        code, validation = self._validate_resource_code(params, "Motor")
        if validation is not None:
            return None, validation

        if require_speed:
            validation = self._validate_speed(params.get("speed_sp"))
            if validation is not None:
                return None, validation

        validation = self._validate_stop_action(params.get("stop_action"))
        if validation is not None:
            return None, validation
        return code, None

    @staticmethod
    def _execution_result(data, code):
        if data is None:
            return CommandResult.not_found("Motor not found: {}".format(code))
        if not data.get("accepted"):
            return CommandResult.service_unavailable(
                data.get("error") or "Motor command could not be executed"
            )
        return CommandResult.ok(data)

    def _stop_motor(self, params):
        code, validation = self._validate_motor_execution(params)
        if validation is not None:
            return validation
        data = self.motor_port.stop_motor(code, params.get("stop_action"))
        return self._execution_result(data, code)

    def _run_timed_motor(self, params):
        code, validation = self._validate_motor_execution(
            params, require_speed=True
        )
        if validation is not None:
            return validation

        time_sp = params.get("time_sp")
        if not self._is_integer(time_sp):
            return CommandResult.bad_request(
                "Parameter time_sp must be an integer"
            )
        if time_sp < 1 or time_sp > self.MAX_TIME_SP_MS:
            return CommandResult.bad_request(
                "Parameter time_sp must be between 1 and {} milliseconds".format(
                    self.MAX_TIME_SP_MS
                )
            )

        data = self.motor_port.run_timed_motor(
            code,
            params["speed_sp"],
            time_sp,
            params.get("stop_action")
        )
        return self._execution_result(data, code)

    def _run_forever_motor(self, params):
        code, validation = self._validate_motor_execution(
            params, require_speed=True
        )
        if validation is not None:
            return validation
        data = self.motor_port.run_forever_motor(
            code, params["speed_sp"], params.get("stop_action")
        )
        return self._execution_result(data, code)

    def _run_to_rel_pos_motor(self, params):
        code, validation = self._validate_motor_execution(
            params, require_speed=True
        )
        if validation is not None:
            return validation

        position_sp = params.get("position_sp")
        if not self._is_integer(position_sp):
            return CommandResult.bad_request(
                "Parameter position_sp must be an integer"
            )
        if abs(position_sp) > self.MAX_REL_POSITION:
            return CommandResult.bad_request(
                "Parameter position_sp is outside the allowed range"
            )

        data = self.motor_port.run_to_rel_pos_motor(
            code,
            params["speed_sp"],
            position_sp,
            params.get("stop_action")
        )
        return self._execution_result(data, code)

    def _reset_motor(self, params):
        code, validation = self._validate_resource_code(params, "Motor")
        if validation is not None:
            return validation
        data = self.motor_port.reset_motor(code)
        return self._execution_result(data, code)

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
            return CommandResult.ok(self.controller_port.read_network_status())
        if action == CommandActions.READ_CONTROLLER_BATTERY:
            return CommandResult.ok(self.controller_port.read_battery_status())
        if action == CommandActions.READ_CONTROLLER_SYSTEM:
            return CommandResult.ok(self.controller_port.read_system_status())
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
