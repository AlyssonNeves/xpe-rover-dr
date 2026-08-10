#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Sensor query and mutation command handler."""

from app.commands.base_handler import BaseCommandHandler
from app.models import CommandActions, CommandResult, ResultStatuses


class SensorCommandHandler(BaseCommandHandler):
    """Uses segregated query and command ports."""

    def __init__(self, sensor_query_port, sensor_command_port=None):
        self.sensor_query_port = sensor_query_port
        self.sensor_command_port = sensor_command_port

    def execute(self, action, params):
        if action == CommandActions.CHANGE_SENSOR_MODE:
            return self._change_sensor_mode(params)
        if self.sensor_query_port is None:
            return CommandResult(
                success=False, status=ResultStatuses.UNAVAILABLE,
                error="Sensor query port is not configured"
            )
        actions = {
            CommandActions.LIST_SENSORS: lambda: CommandResult(
                success=True, data=self.sensor_query_port.list_sensors()),
            CommandActions.READ_SENSOR: lambda: self._read_sensor(params),
            CommandActions.READ_ALL_SENSORS: lambda: CommandResult(
                success=True, data=self.sensor_query_port.read_all_sensors()),
            CommandActions.LIST_SENSOR_MODES: lambda: self._list_sensor_modes(params)
        }
        operation = actions.get(action)
        return operation() if operation else self.unsupported("sensor", action)

    def _read_sensor(self, params):
        code = params.get("code")
        if not code:
            return CommandResult(
                success=False, status=ResultStatuses.INVALID_ARGUMENT,
                error="Missing required parameter: code"
            )
        return self._success_or_not_found(
            self.sensor_query_port.read_sensor(code), "Sensor", code
        )

    def _list_sensor_modes(self, params):
        code = params.get("code")
        if not code:
            return CommandResult(
                success=False, status=ResultStatuses.INVALID_ARGUMENT,
                error="Missing required parameter: code"
            )
        return self._success_or_not_found(
            self.sensor_query_port.list_sensor_modes(code), "Sensor", code
        )

    def _change_sensor_mode(self, params):
        if self.sensor_command_port is None:
            return CommandResult(
                success=False, status=ResultStatuses.UNAVAILABLE,
                error="Sensor command port is not configured"
            )
        code = params.get("code")
        mode = params.get("mode")
        if not code:
            return CommandResult(
                success=False, status=ResultStatuses.INVALID_ARGUMENT,
                error="Missing required parameter: code"
            )
        if not mode:
            return CommandResult(
                success=False, status=ResultStatuses.INVALID_ARGUMENT,
                error="Missing required parameter: mode"
            )
        return self._success_or_not_found(
            self.sensor_command_port.change_sensor_mode(code, mode),
            "Sensor", code
        )
