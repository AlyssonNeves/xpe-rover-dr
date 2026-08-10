#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Read-only motor and command-lifecycle handler."""

from app.commands.base_handler import BaseCommandHandler
from app.models import CommandActions, CommandResult, ResultStatuses


class MotorQueryCommandHandler(BaseCommandHandler):
    ACTIONS = frozenset((
        CommandActions.LIST_MOTORS, CommandActions.READ_MOTOR,
        CommandActions.READ_ALL_MOTORS, CommandActions.READ_MOTOR_COMMAND,
        CommandActions.LIST_MOTOR_COMMANDS
    ))

    def __init__(self, motor_query_port, motor_command_query_port=None):
        self.motor_query_port = motor_query_port
        self.motor_command_query_port = motor_command_query_port

    def execute(self, action, params):
        if action in (CommandActions.LIST_MOTORS, CommandActions.READ_MOTOR,
                      CommandActions.READ_ALL_MOTORS):
            if self.motor_query_port is None:
                return self._unavailable("Motor query")
        else:
            if self.motor_command_query_port is None:
                return self._unavailable("Motor command query")
        if action == CommandActions.LIST_MOTORS:
            return CommandResult(success=True, data=self.motor_query_port.list_motors())
        if action == CommandActions.READ_MOTOR:
            return self._read_motor(params)
        if action == CommandActions.READ_ALL_MOTORS:
            return CommandResult(success=True, data=self.motor_query_port.read_all_motors())
        if action == CommandActions.READ_MOTOR_COMMAND:
            return self._read_motor_command(params)
        if action == CommandActions.LIST_MOTOR_COMMANDS:
            return CommandResult(success=True, data=self.motor_command_query_port.list_commands(params.get("code")))
        return self.unsupported("motor", action)

    @staticmethod
    def _unavailable(name):
        return CommandResult(success=False, status=ResultStatuses.UNAVAILABLE,
                             error="{} port is not configured".format(name))

    def _read_motor(self, params):
        """
        Reads a specific motor.

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

        data = self.motor_query_port.read_motor(code)

        return self._success_or_not_found(
            data=data,
            resource_name="Motor",
            code=code
        )

    def _read_motor_command(self, params):
        """Reads one queued or completed command by command_id."""
        command_id = params.get("command_id")
        if not self._is_integer(command_id):
            return CommandResult(success=False, status=ResultStatuses.INVALID_ARGUMENT, error="Parameter command_id must be an integer")
        data = self.motor_command_query_port.get_command(command_id)
        return self._success_or_not_found(data, "Motor command", command_id)

