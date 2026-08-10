#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Application service used to validate and execute Rover-DR commands."""

import re

from app.commands import (
    CommandHandlerRegistry,
    ControllerCommandHandler,
    DriveCommandHandler,
    MotorCommandHandler,
    RoverCommandHandler,
    SensorCommandHandler,
)
from app.models import CommandActions, CommandResult, CommandTargets


class CommandService(object):
    """Coordinates validated queries and queued motor commands."""

    RESOURCE_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_-]{0,15}$")
    VALID_STOP_ACTIONS = ("coast", "brake", "hold")
    VALID_MOVEMENT_PROFILES = (
        "direct", "ramp-up", "ramp-down", "ramp-up-down"
    )
    MIN_SPEED_SP = -2000
    MAX_SPEED_SP = 2000
    MAX_TIME_SP_MS = 600000
    MAX_REL_POSITION = 1000000
    MIN_PRIORITY = 0
    MAX_PRIORITY = 100
    MIN_SAFETY_TIMEOUT_MS = 100
    MAX_SAFETY_TIMEOUT_MS = 600000

    def __init__(
        self,
        sensor_port,
        motor_port,
        controller_port,
        rover_state_port=None,
        drive_port=None,
        operation_mode_service=None
    ):
        self.sensor_port = sensor_port
        self.motor_port = motor_port
        self.controller_port = controller_port
        self.rover_state_port = rover_state_port
        self.drive_port = drive_port
        self.operation_mode_service = operation_mode_service
        self._handlers = CommandHandlerRegistry((
            SensorCommandHandler(CommandTargets.SENSOR, self._execute_sensor),
            MotorCommandHandler(CommandTargets.MOTOR, self._execute_motor),
            ControllerCommandHandler(
                CommandTargets.CONTROLLER,
                lambda action, _params: self._execute_controller(action)
            ),
            RoverCommandHandler(
                CommandTargets.ROVER,
                lambda action, _params: self._execute_rover(action)
            ),
            DriveCommandHandler(CommandTargets.DRIVE, self._execute_drive),
        ))

    def execute(self, target, action, params=None):
        validation = self._validate_envelope(target, action, params)
        if validation is not None:
            return validation

        authorization = self._authorize_local_manual(target, action)
        if authorization is not None:
            return authorization

        handler = self._handlers.get(target)
        if handler is None:
            return CommandResult.bad_request(
                "Unsupported command target: {}".format(target)
            )
        return handler.handle(action, params or {})

    def _authorize_local_manual(self, target, action):
        if self.operation_mode_service is None:
            return None
        mode = self.operation_mode_service.get_mode()
        if not (
                mode.get("command") == "LOCAL" and
                mode.get("control") == "MANUAL"):
            return None

        motor_writes = (
            CommandActions.STOP_MOTOR,
            CommandActions.RUN_TIMED_MOTOR,
            CommandActions.RUN_FOREVER_MOTOR,
            CommandActions.RUN_TO_REL_POS_MOTOR,
            CommandActions.RESET_MOTOR,
            CommandActions.CANCEL_MOTOR_COMMANDS,
            CommandActions.RUN_SYNCHRONIZED_MOTORS
        )
        if target == CommandTargets.MOTOR and action in motor_writes:
            return CommandResult.conflict(
                "Motor writes are unavailable while LOCAL + MANUAL control "
                "owns the motor hardware."
            )
        if target == CommandTargets.DRIVE:
            return CommandResult.conflict(
                "Drive commands are unavailable while LOCAL + MANUAL control "
                "owns the motor hardware."
            )
        return None

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

    def _validate_profile(self, value):
        if value is None:
            return None
        if not isinstance(value, str) or value not in self.VALID_MOVEMENT_PROFILES:
            return CommandResult.bad_request(
                "Parameter profile must be one of: {}".format(
                    ", ".join(self.VALID_MOVEMENT_PROFILES)
                )
            )
        return None

    def _validate_priority(self, value):
        if value is None:
            return None
        if not self._is_integer(value):
            return CommandResult.bad_request(
                "Parameter priority must be an integer"
            )
        if value < self.MIN_PRIORITY or value > self.MAX_PRIORITY:
            return CommandResult.bad_request(
                "Parameter priority must be between {} and {}".format(
                    self.MIN_PRIORITY, self.MAX_PRIORITY
                )
            )
        return None

    def _validate_safety_timeout(self, value, parameter_name):
        if value is None:
            return None
        if not self._is_integer(value):
            return CommandResult.bad_request(
                "Parameter {} must be an integer".format(parameter_name)
            )
        if value < self.MIN_SAFETY_TIMEOUT_MS or value > self.MAX_SAFETY_TIMEOUT_MS:
            return CommandResult.bad_request(
                "Parameter {} must be between {} and {} milliseconds".format(
                    parameter_name, self.MIN_SAFETY_TIMEOUT_MS,
                    self.MAX_SAFETY_TIMEOUT_MS
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
        if action == CommandActions.GET_MOTOR_COMMAND:
            return self._get_motor_command(params)
        if action == CommandActions.LIST_MOTOR_COMMANDS:
            return self._list_motor_commands(params)
        if action == CommandActions.CANCEL_MOTOR_COMMANDS:
            return self._cancel_motor_commands(params)
        if action == CommandActions.RUN_SYNCHRONIZED_MOTORS:
            return self._run_synchronized_motors(params)

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

        validation = self._validate_priority(params.get("priority"))
        if validation is not None:
            return None, validation
        validation = self._validate_profile(params.get("profile"))
        if validation is not None:
            return None, validation
        for parameter_name in ("timeout_ms", "watchdog_ms"):
            validation = self._validate_safety_timeout(
                params.get(parameter_name), parameter_name
            )
            if validation is not None:
                return None, validation
        return code, None

    @staticmethod
    def _execution_result(data, code):
        if data is None:
            return CommandResult.not_found("Motor not found: {}".format(code))
        if not data.get("accepted"):
            return CommandResult.service_unavailable(
                data.get("error") or "Motor command could not be accepted"
            )
        status_code = 202 if data.get("status") == "QUEUED" else 200
        return CommandResult.ok(data, status_code=status_code)

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
            priority=params.get("priority"),
            stop_action=params.get("stop_action"),
            timeout_ms=params.get("timeout_ms"),
            profile=params.get("profile")
        )
        return self._execution_result(data, code)

    def _run_forever_motor(self, params):
        code, validation = self._validate_motor_execution(
            params, require_speed=True
        )
        if validation is not None:
            return validation
        data = self.motor_port.run_forever_motor(
            code,
            params["speed_sp"],
            priority=params.get("priority"),
            stop_action=params.get("stop_action"),
            watchdog_ms=params.get("watchdog_ms"),
            timeout_ms=params.get("timeout_ms"),
            profile=params.get("profile")
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
            priority=params.get("priority"),
            stop_action=params.get("stop_action"),
            timeout_ms=params.get("timeout_ms"),
            profile=params.get("profile")
        )
        return self._execution_result(data, code)

    def _reset_motor(self, params):
        code, validation = self._validate_resource_code(params, "Motor")
        if validation is not None:
            return validation
        validation = self._validate_priority(params.get("priority"))
        if validation is not None:
            return validation
        data = self.motor_port.reset_motor(code, params.get("priority"))
        return self._execution_result(data, code)

    def _get_motor_command(self, params):
        command_id = params.get("command_id")
        if not self._is_integer(command_id) or command_id < 1:
            return CommandResult.bad_request(
                "command_id must be a positive integer"
            )
        command = self.motor_port.get_command(command_id)
        if command is None:
            return CommandResult.not_found(
                "Motor command not found: {}".format(command_id)
            )
        return CommandResult.ok(command)

    def _list_motor_commands(self, params):
        motor_code = params.get("code")
        if motor_code is not None:
            code, validation = self._validate_resource_code(params, "Motor")
            if validation is not None:
                return validation
            if self.motor_port.read_motor(code) is None:
                return CommandResult.not_found(
                    "Motor not found: {}".format(code)
                )
            motor_code = code
        return CommandResult.ok(self.motor_port.list_commands(motor_code))

    def _cancel_motor_commands(self, params):
        code, validation = self._validate_resource_code(params, "Motor")
        if validation is not None:
            return validation
        data = self.motor_port.cancel_motor_commands(code)
        if data is None:
            return CommandResult.not_found("Motor not found: {}".format(code))
        return CommandResult.ok(data)

    def _normalize_synchronized_item(self, raw_item, default_priority):
        if not isinstance(raw_item, dict):
            return None, CommandResult.bad_request(
                "Each synchronized command must be a JSON object"
            )

        code, validation = self._validate_resource_code(raw_item, "Motor")
        if validation is not None:
            return None, validation
        if self.motor_port.read_motor(code) is None:
            return None, CommandResult.not_found(
                "Motor not found: {}".format(code)
            )

        action = raw_item.get("action")
        allowed_actions = (
            "run-timed",
            "run-forever",
            "run-to-rel-pos"
        )
        if action not in allowed_actions:
            return None, CommandResult.bad_request(
                "Unsupported synchronized motor action: {}".format(action)
            )

        priority = raw_item.get("priority", default_priority)
        validation = self._validate_priority(priority)
        if validation is not None:
            return None, validation

        params = {
            "speed_sp": raw_item.get("speed_sp"),
            "stop_action": raw_item.get("stop_action"),
            "timeout_ms": raw_item.get("timeout_ms"),
            "watchdog_ms": raw_item.get("watchdog_ms"),
            "profile": raw_item.get("profile")
        }
        validation = self._validate_speed(params["speed_sp"])
        if validation is not None:
            return None, validation
        validation = self._validate_stop_action(params.get("stop_action"))
        if validation is not None:
            return None, validation
        validation = self._validate_profile(params.get("profile"))
        if validation is not None:
            return None, validation
        for parameter_name in ("timeout_ms", "watchdog_ms"):
            validation = self._validate_safety_timeout(
                params.get(parameter_name), parameter_name
            )
            if validation is not None:
                return None, validation

        if action == "run-timed":
            time_sp = raw_item.get("time_sp")
            if not self._is_integer(time_sp) or time_sp < 1 or time_sp > self.MAX_TIME_SP_MS:
                return None, CommandResult.bad_request(
                    "Synchronized time_sp must be between 1 and {} milliseconds".format(
                        self.MAX_TIME_SP_MS
                    )
                )
            params["time_sp"] = time_sp

        if action == "run-to-rel-pos":
            position_sp = raw_item.get("position_sp")
            if not self._is_integer(position_sp) or abs(position_sp) > self.MAX_REL_POSITION:
                return None, CommandResult.bad_request(
                    "Synchronized position_sp is outside the allowed range"
                )
            params["position_sp"] = position_sp

        return {
            "code": code,
            "action": action,
            "priority": priority,
            "parameters": params
        }, None

    def _run_synchronized_motors(self, params):
        commands = params.get("commands")
        if not isinstance(commands, list) or not commands:
            return CommandResult.bad_request(
                "Parameter commands must be a non-empty array"
            )

        default_priority = params.get("priority", 0)
        validation = self._validate_priority(default_priority)
        if validation is not None:
            return validation

        normalized = []
        seen_codes = set()
        for raw_item in commands:
            item, validation = self._normalize_synchronized_item(
                raw_item, default_priority
            )
            if validation is not None:
                return validation
            if item["code"] in seen_codes:
                return CommandResult.bad_request(
                    "A synchronized batch may contain only one command per motor"
                )
            seen_codes.add(item["code"])
            normalized.append(item)

        data = self.motor_port.run_synchronized_motors(normalized)
        if not data.get("accepted"):
            return CommandResult.service_unavailable(
                data.get("error") or "Synchronized commands could not be accepted"
            )
        return CommandResult.ok(data, status_code=202)

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

    def _validate_drive_speed(self, value, parameter_name):
        if not self._is_integer(value):
            return CommandResult.bad_request(
                "Parameter {} must be an integer".format(parameter_name)
            )
        if value < self.MIN_SPEED_SP or value > self.MAX_SPEED_SP:
            return CommandResult.bad_request(
                "Parameter {} must be between {} and {}".format(
                    parameter_name, self.MIN_SPEED_SP, self.MAX_SPEED_SP
                )
            )
        return None

    def _execute_drive(self, action, params):
        if self.drive_port is None:
            return CommandResult.service_unavailable(
                "Drive port is not configured"
            )

        if action == CommandActions.READ_DRIVE_STATUS:
            return CommandResult.ok(self.drive_port.get_status())

        if action == CommandActions.STOP_DRIVE:
            validation = self._validate_stop_action(params.get("stop_action"))
            if validation is not None:
                return validation
            data = self.drive_port.stop(params.get("stop_action"))
            if not data.get("accepted"):
                return CommandResult.service_unavailable(
                    data.get("error") or "Drive could not be stopped"
                )
            return CommandResult.ok(data)

        if action == CommandActions.RESET_DRIVE_ODOMETRY:
            for parameter_name in ("x_mm", "y_mm", "heading_deg"):
                value = params.get(parameter_name, 0.0)
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    return CommandResult.bad_request(
                        "Parameter {} must be numeric".format(parameter_name)
                    )
            return CommandResult.ok(self.drive_port.reset_odometry(
                params.get("x_mm", 0.0),
                params.get("y_mm", 0.0),
                params.get("heading_deg", 0.0)
            ))

        if action in (
            CommandActions.MOVE_DRIVE_DISTANCE,
            CommandActions.ROTATE_DRIVE_ANGLE,
            CommandActions.CURVE_DRIVE_RADIUS
        ):
            return self._execute_navigation_drive(action, params)

        if action == CommandActions.DRIVE_TANK:
            for parameter_name in ("left_speed_sp", "right_speed_sp"):
                validation = self._validate_drive_speed(
                    params.get(parameter_name), parameter_name
                )
                if validation is not None:
                    return validation

            validation = self._validate_priority(params.get("priority"))
            if validation is not None:
                return validation
            validation = self._validate_stop_action(params.get("stop_action"))
            if validation is not None:
                return validation
            validation = self._validate_profile(params.get("profile"))
            if validation is not None:
                return validation
            validation = self._validate_safety_timeout(
                params.get("watchdog_ms"), "watchdog_ms"
            )
            if validation is not None:
                return validation

            data = self.drive_port.drive_tank(
                params["left_speed_sp"],
                params["right_speed_sp"],
                priority=params.get("priority"),
                stop_action=params.get("stop_action"),
                watchdog_ms=params.get("watchdog_ms"),
                profile=params.get("profile")
            )
            if not data.get("accepted"):
                return CommandResult.service_unavailable(
                    data.get("error") or "Drive command could not be accepted"
                )
            status_code = 202 if data.get("batch_id") else 200
            return CommandResult.ok(data, status_code=status_code)

        return CommandResult.bad_request(
            "Unsupported drive action: {}".format(action)
        )

    def _execute_navigation_drive(self, action, params):
        speed_sp = params.get("speed_sp")
        validation = self._validate_drive_speed(speed_sp, "speed_sp")
        if validation is not None:
            return validation
        if speed_sp <= 0:
            return CommandResult.bad_request("Parameter speed_sp must be positive")

        validation = self._validate_priority(params.get("priority"))
        if validation is not None:
            return validation
        validation = self._validate_stop_action(params.get("stop_action"))
        if validation is not None:
            return validation
        validation = self._validate_profile(params.get("profile"))
        if validation is not None:
            return validation
        validation = self._validate_safety_timeout(
            params.get("timeout_ms"), "timeout_ms"
        )
        if validation is not None:
            return validation

        def number(name, allow_zero=False):
            value = params.get(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return None, CommandResult.bad_request(
                    "Parameter {} must be numeric".format(name)
                )
            if not allow_zero and value == 0:
                return None, CommandResult.bad_request(
                    "Parameter {} must be non-zero".format(name)
                )
            return float(value), None

        try:
            if action == CommandActions.MOVE_DRIVE_DISTANCE:
                distance_mm, error = number("distance_mm")
                if error is not None:
                    return error
                data = self.drive_port.move_distance(
                    distance_mm, speed_sp, params.get("priority"),
                    params.get("stop_action"), params.get("timeout_ms"),
                    params.get("profile")
                )
            elif action == CommandActions.ROTATE_DRIVE_ANGLE:
                angle_deg, error = number("angle_deg")
                if error is not None:
                    return error
                data = self.drive_port.rotate_angle(
                    angle_deg, speed_sp, params.get("priority"),
                    params.get("stop_action"), params.get("timeout_ms"),
                    params.get("profile")
                )
            else:
                radius_mm, error = number("radius_mm")
                if error is not None:
                    return error
                angle_deg, error = number("angle_deg")
                if error is not None:
                    return error
                data = self.drive_port.curve_radius(
                    radius_mm, angle_deg, speed_sp, params.get("priority"),
                    params.get("stop_action"), params.get("timeout_ms"),
                    params.get("profile")
                )
        except ValueError as error:
            return CommandResult.bad_request(str(error))

        if not data.get("accepted"):
            return CommandResult.service_unavailable(
                data.get("error") or "Navigation command could not be accepted"
            )
        return CommandResult.ok(data, status_code=202)
