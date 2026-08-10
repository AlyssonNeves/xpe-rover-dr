#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Motor command parameter validation."""

from app.commands.base_handler import BaseCommandHandler
from app.models import CommandActions, CommandResult, ResultStatuses

class MotorParameterValidator(BaseCommandHandler):
    """Validates motor command parameters."""

    MIN_MOTOR_SPEED_SP = -1000
    MAX_MOTOR_SPEED_SP = 1000
    MIN_MOTOR_TIME_SP = 1

    MOTOR_PARAMETER_RULES = {
        CommandActions.STOP_MOTOR: {"required": ("code",)},
        CommandActions.RUN_TIMED_MOTOR: {
            "required": ("code", "speed_sp", "time_sp"),
            "integer": ("speed_sp", "time_sp"),
            "ranges": {
                "speed_sp": (MIN_MOTOR_SPEED_SP, MAX_MOTOR_SPEED_SP),
                "time_sp": (MIN_MOTOR_TIME_SP, None)
            }
        },
        CommandActions.RUN_FOREVER_MOTOR: {
            "required": ("code", "speed_sp"),
            "integer": ("speed_sp",),
            "ranges": {"speed_sp": (MIN_MOTOR_SPEED_SP, MAX_MOTOR_SPEED_SP)}
        },
        CommandActions.RUN_DIRECT_MOTOR: {
            "required": ("code", "duty_cycle_sp"),
            "integer": ("duty_cycle_sp",),
            "ranges": {"duty_cycle_sp": (-100, 100)}
        },
        CommandActions.RUN_TO_REL_POS_MOTOR: {
            "required": ("code", "speed_sp", "position_sp"),
            "integer": ("speed_sp", "position_sp"),
            "ranges": {"speed_sp": (MIN_MOTOR_SPEED_SP, MAX_MOTOR_SPEED_SP)}
        },
        CommandActions.RUN_TO_ABS_POS_MOTOR: {
            "required": ("code", "speed_sp", "position_sp"),
            "integer": ("speed_sp", "position_sp"),
            "ranges": {"speed_sp": (MIN_MOTOR_SPEED_SP, MAX_MOTOR_SPEED_SP)}
        },
        CommandActions.RESET_MOTOR: {"required": ("code",)}
    }

    def validate_motor_action_parameters(self, action, params):
        """
        Validates motor command parameters using action-based rules.

        Args:
            action (str): Motor command action.
            params (dict): Command parameters.

        Returns:
            CommandResult: Validation error when invalid; otherwise None.
        """
        rules = self.MOTOR_PARAMETER_RULES.get(action)

        if rules is None:
            return None

        for parameter_name in rules.get("required", ()):
            if params.get(parameter_name) is None:
                return CommandResult(
                    success=False,
                    status=ResultStatuses.INVALID_ARGUMENT,
                    error="Missing required parameter: {}".format(
                        parameter_name
                    )
                )

        for parameter_name in rules.get("integer", ()):
            if not self._is_integer(params.get(parameter_name)):
                return CommandResult(
                    success=False,
                    status=ResultStatuses.INVALID_ARGUMENT,
                    error="Parameter {} must be an integer".format(
                        parameter_name
                    )
                )

        for parameter_name, bounds in rules.get("ranges", {}).items():
            minimum_value, maximum_value = bounds
            value = params.get(parameter_name)

            if minimum_value is not None and value < minimum_value:
                return self._build_range_validation_error(
                    parameter_name,
                    minimum_value,
                    maximum_value
                )

            if maximum_value is not None and value > maximum_value:
                return self._build_range_validation_error(
                    parameter_name,
                    minimum_value,
                    maximum_value
                )

        return None

    def _build_range_validation_error(
            self,
            parameter_name,
            minimum_value,
            maximum_value
        ):
        """
        Builds a standardized range validation error.

        Args:
            parameter_name (str): Name of the invalid parameter.
            minimum_value: Minimum accepted value.
            maximum_value: Maximum accepted value.

        Returns:
            CommandResult: Standardized range validation error.
        """
        if maximum_value is None:
            return CommandResult(
                success=False,
                status=ResultStatuses.INVALID_ARGUMENT,
                error="Parameter {} must be greater than zero".format(
                    parameter_name
                )
            )

        return CommandResult(
            success=False,
            status=ResultStatuses.INVALID_ARGUMENT,
            error=(
                "Parameter {} must be between {} and {}"
                .format(parameter_name, minimum_value, maximum_value)
            )
        )

    def _validate_run_timed_parameters(self, speed_sp, time_sp):
        """
        Validates parameters used by the timed motor command.

        Args:
            speed_sp: Motor speed setpoint.
            time_sp: Motor execution time setpoint.

        Returns:
            CommandResult: Validation error when invalid; otherwise None.
        """
        return self.validate_motor_action_parameters(
            CommandActions.RUN_TIMED_MOTOR,
            {
                "code": "validated-by-caller",
                "speed_sp": speed_sp,
                "time_sp": time_sp
            }
        )

    def _validate_speed_parameter(self, speed_sp):
        """
        Validates a motor speed setpoint.

        Args:
            speed_sp: Motor speed setpoint.

        Returns:
            CommandResult: Validation error when invalid; otherwise None.
        """
        return self.validate_motor_action_parameters(
            CommandActions.RUN_FOREVER_MOTOR,
            {
                "code": "validated-by-caller",
                "speed_sp": speed_sp
            }
        )

    def _validate_run_to_rel_pos_parameters(self, speed_sp, position_sp):
        """
        Validates parameters used by the relative-position motor command.

        Args:
            speed_sp: Motor speed setpoint.
            position_sp: Motor relative position setpoint.

        Returns:
            CommandResult: Validation error when invalid; otherwise None.
        """
        return self.validate_motor_action_parameters(
            CommandActions.RUN_TO_REL_POS_MOTOR,
            {
                "code": "validated-by-caller",
                "speed_sp": speed_sp,
                "position_sp": position_sp
            }
        )

