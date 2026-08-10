#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Motor mutation and low-level drive command handler."""

from app.commands.base_handler import BaseCommandHandler
from app.commands.motor_validation import MotorParameterValidator
from app.models import CommandActions, CommandResult, ResultStatuses


class MotorMotionCommandHandler(BaseCommandHandler):
    ACTIONS = frozenset((
        CommandActions.STOP_MOTOR, CommandActions.STOP_ALL_MOTORS,
        CommandActions.RUN_TIMED_MOTOR, CommandActions.RUN_FOREVER_MOTOR,
        CommandActions.RUN_DIRECT_MOTOR, CommandActions.RUN_TO_REL_POS_MOTOR,
        CommandActions.RUN_TO_ABS_POS_MOTOR, CommandActions.RESET_MOTOR,
        CommandActions.CANCEL_MOTOR_COMMANDS,
        CommandActions.RUN_SYNCHRONIZED_MOTORS,
        CommandActions.DRIVE_TANK, CommandActions.STOP_DRIVE
    ))

    def __init__(self, motor_command_port=None, drive_motor_port=None,
                 validator=None):
        self.motor_command_port = motor_command_port
        self.drive_motor_port = drive_motor_port
        self.validator = validator or MotorParameterValidator()

    def execute(self, action, params):
        if action in (CommandActions.DRIVE_TANK, CommandActions.STOP_DRIVE):
            if self.drive_motor_port is None:
                return self._unavailable("Drive motor")
        elif self.motor_command_port is None:
            return self._unavailable("Motor command")
        actions = {
            CommandActions.STOP_MOTOR: lambda: self._stop_motor(params),
            CommandActions.STOP_ALL_MOTORS: lambda: CommandResult(
                success=True, data=self.motor_command_port.stop_all_motors(params.get("stop_action"))),
            CommandActions.RUN_TIMED_MOTOR: lambda: self._run_timed_motor(params),
            CommandActions.RUN_FOREVER_MOTOR: lambda: self._run_forever_motor(params),
            CommandActions.RUN_DIRECT_MOTOR: lambda: self._run_direct_motor(params),
            CommandActions.RUN_TO_REL_POS_MOTOR: lambda: self._run_to_rel_pos_motor(params),
            CommandActions.RUN_TO_ABS_POS_MOTOR: lambda: self._run_to_abs_pos_motor(params),
            CommandActions.DRIVE_TANK: lambda: self._drive_tank(params),
            CommandActions.STOP_DRIVE: lambda: CommandResult(
                success=True, data=self.drive_motor_port.stop_drive(params.get("stop_action"))),
            CommandActions.RESET_MOTOR: lambda: self._reset_motor(params),
            CommandActions.CANCEL_MOTOR_COMMANDS: lambda: self._cancel_motor_commands(params),
            CommandActions.RUN_SYNCHRONIZED_MOTORS: lambda: self._run_synchronized_motors(params)
        }
        operation = actions.get(action)
        return operation() if operation else self.unsupported("motor", action)

    def _validate_run_timed_parameters(self, speed_sp, time_sp):
        return self.validator._validate_run_timed_parameters(speed_sp, time_sp)

    def _validate_speed_parameter(self, speed_sp):
        return self.validator._validate_speed_parameter(speed_sp)

    def _validate_run_to_rel_pos_parameters(self, speed_sp, position_sp):
        return self.validator._validate_run_to_rel_pos_parameters(
            speed_sp, position_sp
        )

    @staticmethod
    def _unavailable(name):
        return CommandResult(success=False, status=ResultStatuses.UNAVAILABLE,
                             error="{} port is not configured".format(name))

    def _stop_motor(self, params):
        """
        Stops a specific motor.

        Args:
            params (dict): Parameters containing the motor code.

        Returns:
            CommandResult: Standardized command execution result.
        """
        code = params.get("code")

        if not code:
            return CommandResult(
                success=False,
                status=ResultStatuses.INVALID_ARGUMENT,
                error="Missing required parameter: code"
            )

        stop_action = params.get("stop_action")
        data = self.motor_command_port.stop_motor(
            code, stop_action) if stop_action is not None else self.motor_command_port.stop_motor(code)

        return self._success_or_not_found(
            data=data,
            resource_name="Motor",
            code=code
        )

    def _run_timed_motor(self, params):
        """
        Runs a motor for a specified amount of time.

        Args:
            params (dict): Parameters containing the motor code, speed,
                and execution time.

        Returns:
            CommandResult: Standardized command execution result.
        """
        code = params.get("code")
        speed_sp = params.get("speed_sp")
        time_sp = params.get("time_sp")

        if not code:
            return CommandResult(
                success=False,
                status=ResultStatuses.INVALID_ARGUMENT,
                error="Missing required parameter: code"
            )

        validation_error = self._validate_run_timed_parameters(
            speed_sp,
            time_sp
        )

        if validation_error is not None:
            return validation_error

        optional = {}
        if params.get("timeout_ms") is not None:
            optional["timeout_ms"] = params.get("timeout_ms")
        if params.get("stop_action") is not None:
            optional["stop_action"] = params.get("stop_action")
        data = self.motor_command_port.run_timed_motor(
            code, speed_sp, time_sp,
            priority=params.get("priority"), profile=params.get("profile"),
            **optional
        )

        return self._success_or_not_found(
            data=data,
            resource_name="Motor",
            code=code
        )

    def _run_forever_motor(self, params):
        """
        Runs a motor continuously until another command stops it.

        Args:
            params (dict): Parameters containing the motor code and speed.

        Returns:
            CommandResult: Standardized command execution result.
        """
        code = params.get("code")
        speed_sp = params.get("speed_sp")

        if not code:
            return CommandResult(
                success=False,
                status=ResultStatuses.INVALID_ARGUMENT,
                error="Missing required parameter: code"
            )

        validation_error = self._validate_speed_parameter(speed_sp)

        if validation_error is not None:
            return validation_error

        optional = {}
        for key in ("watchdog_ms", "timeout_ms", "stop_action"):
            if params.get(key) is not None:
                optional[key] = params.get(key)
        data = self.motor_command_port.run_forever_motor(
            code, speed_sp,
            priority=params.get("priority"), profile=params.get("profile"),
            **optional
        )

        return self._success_or_not_found(
            data=data,
            resource_name="Motor",
            code=code
        )

    def _run_to_rel_pos_motor(self, params):
        """
        Runs a motor to a relative target position.

        Args:
            params (dict): Parameters containing the motor code, speed,
                and relative target position.

        Returns:
            CommandResult: Standardized command execution result.
        """
        code = params.get("code")
        speed_sp = params.get("speed_sp")
        position_sp = params.get("position_sp")

        if not code:
            return CommandResult(
                success=False,
                status=ResultStatuses.INVALID_ARGUMENT,
                error="Missing required parameter: code"
            )

        validation_error = self._validate_run_to_rel_pos_parameters(
            speed_sp,
            position_sp
        )

        if validation_error is not None:
            return validation_error

        optional = {}
        if params.get("timeout_ms") is not None:
            optional["timeout_ms"] = params.get("timeout_ms")
        if params.get("stop_action") is not None:
            optional["stop_action"] = params.get("stop_action")
        data = self.motor_command_port.run_to_rel_pos_motor(
            code, speed_sp, position_sp,
            priority=params.get("priority"), profile=params.get("profile"),
            **optional
        )

        return self._success_or_not_found(
            data=data,
            resource_name="Motor",
            code=code
        )

    def _reset_motor(self, params):
        """
        Resets a specific motor.

        Args:
            params (dict): Parameters containing the motor code.

        Returns:
            CommandResult: Standardized command execution result.
        """
        code = params.get("code")

        if not code:
            return CommandResult(
                success=False,
                status=ResultStatuses.INVALID_ARGUMENT,
                error="Missing required parameter: code"
            )

        data = self.motor_command_port.reset_motor(code)

        return self._success_or_not_found(
            data=data,
            resource_name="Motor",
            code=code
        )

    def _run_direct_motor(self, params):
        """Validates and queues a direct duty-cycle command."""
        error = self.validator.validate_motor_action_parameters(CommandActions.RUN_DIRECT_MOTOR, params)
        if error:
            return error
        data = self.motor_command_port.run_direct_motor(
            params.get("code"), params.get("duty_cycle_sp"),
            priority=params.get("priority"), watchdog_ms=params.get("watchdog_ms"),
            timeout_ms=params.get("timeout_ms"), stop_action=params.get("stop_action")
        )
        return self._success_or_not_found(data, "Motor", params.get("code"))

    def _run_to_abs_pos_motor(self, params):
        """Validates and queues an absolute-position command."""
        error = self.validator.validate_motor_action_parameters(CommandActions.RUN_TO_ABS_POS_MOTOR, params)
        if error:
            return error
        data = self.motor_command_port.run_to_abs_pos_motor(
            params.get("code"), params.get("speed_sp"), params.get("position_sp"),
            priority=params.get("priority"), profile=params.get("profile"),
            timeout_ms=params.get("timeout_ms"), stop_action=params.get("stop_action")
        )
        return self._success_or_not_found(data, "Motor", params.get("code"))

    def _drive_tank(self, params):
        """Validates and executes differential traction control."""
        for name in ("left_speed_sp", "right_speed_sp"):
            value = params.get(name)
            if not self._is_integer(value):
                return CommandResult(success=False, status=ResultStatuses.INVALID_ARGUMENT, error="Parameter {0} must be an integer".format(name))
            if value < self.MIN_MOTOR_SPEED_SP or value > self.MAX_MOTOR_SPEED_SP:
                return CommandResult(success=False, status=ResultStatuses.INVALID_ARGUMENT, error="Parameter {0} is outside the allowed range".format(name))
        data = self.drive_motor_port.drive_tank(
            params["left_speed_sp"], params["right_speed_sp"],
            priority=params.get("priority"), profile=params.get("profile")
        )
        return CommandResult(
            success=bool(data.get("success")),
            status=(ResultStatuses.SUCCESS if data.get("success")
                    else ResultStatuses.CONFLICT),
            data=data, error=data.get("error")
        )

    def _cancel_motor_commands(self, params):
        """
        Cancels queued motor commands for a specific motor.
        """
        code = params.get("code")

        if not code:
            return CommandResult(
                success=False,
                status=ResultStatuses.INVALID_ARGUMENT,
                error="Missing required parameter: code"
            )

        data = self.motor_command_port.cancel_motor_commands(code)

        return self._success_or_not_found(
            data=data,
            resource_name="Motor",
            code=code
        )

    def _run_synchronized_motors(self, params):
        """
        Queues synchronized commands for multiple motors.
        """
        commands = params.get("commands")

        if not isinstance(commands, list) or not commands:
            return CommandResult(
                success=False,
                status=ResultStatuses.INVALID_ARGUMENT,
                error="Parameter commands must be a non-empty list"
            )

        for command in commands:
            if not isinstance(command, dict):
                return CommandResult(
                    success=False,
                    status=ResultStatuses.INVALID_ARGUMENT,
                    error="Each synchronized command must be an object"
                )

            if not command.get("code"):
                return CommandResult(
                    success=False,
                    status=ResultStatuses.INVALID_ARGUMENT,
                    error="Missing required parameter: code"
                )

            action = command.get("action", "run-forever")
            speed_required = action in (
                "run-forever",
                "run-timed",
                "run-to-rel-pos",
                "run-to-abs-pos"
            )

            if speed_required and not self._is_integer(command.get("speed_sp")):
                return CommandResult(
                    success=False,
                    status=ResultStatuses.INVALID_ARGUMENT,
                    error="Parameter speed_sp must be an integer"
                )

            if action == "run-timed":
                if not self._is_integer(command.get("time_sp")):
                    return CommandResult(
                        success=False,
                        status=ResultStatuses.INVALID_ARGUMENT,
                        error="Parameter time_sp must be an integer"
                    )

            if action in ("run-to-rel-pos", "run-to-abs-pos"):
                if not self._is_integer(command.get("position_sp")):
                    return CommandResult(
                        success=False,
                        status=ResultStatuses.INVALID_ARGUMENT,
                        error="Parameter position_sp must be an integer"
                    )

        data = self.motor_command_port.run_synchronized_motors(commands)

        if not data.get("success"):
            return CommandResult(
                success=False,
                status=ResultStatuses.INVALID_ARGUMENT,
                error=data.get("error")
            )

        return CommandResult(success=True, data=data)

