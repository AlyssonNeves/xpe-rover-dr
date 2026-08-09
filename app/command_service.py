#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Initial application service used to query Rover-DR monitoring ports."""

from app.models import CommandActions, CommandResult, CommandTargets


class CommandService(object):
    """Coordinates read-only commands without depending on HTTP details."""

    def __init__(self, sensor_port, motor_port, controller_port):
        self.sensor_port = sensor_port
        self.motor_port = motor_port
        self.controller_port = controller_port

    def execute(self, target, action, params=None):
        """Executes a command against one of the monitoring output ports."""
        params = params or {}

        if target == CommandTargets.SENSOR:
            return self._execute_sensor(action, params)
        if target == CommandTargets.MOTOR:
            return self._execute_motor(action, params)
        if target == CommandTargets.CONTROLLER:
            return self._execute_controller(action)

        return CommandResult(
            success=False,
            status_code=400,
            error="Unsupported command target: {}".format(target)
        )

    def _execute_sensor(self, action, params):
        if action == CommandActions.LIST_SENSORS:
            return CommandResult(True, data=self.sensor_port.list_sensors())

        if action == CommandActions.READ_ALL_SENSORS:
            return CommandResult(True, data=self.sensor_port.read_all_sensors())

        if action == CommandActions.READ_SENSOR:
            sensor = self.sensor_port.read_sensor(params.get("code"))
            if sensor is None:
                return CommandResult(False, 404, error="Sensor not found")
            return CommandResult(True, data=sensor)

        return CommandResult(
            False,
            400,
            error="Unsupported sensor action: {}".format(action)
        )

    def _execute_motor(self, action, params):
        if action == CommandActions.LIST_MOTORS:
            return CommandResult(True, data=self.motor_port.list_motors())

        if action == CommandActions.READ_ALL_MOTORS:
            return CommandResult(True, data=self.motor_port.read_all_motors())

        if action == CommandActions.READ_MOTOR:
            motor = self.motor_port.read_motor(params.get("code"))
            if motor is None:
                return CommandResult(False, 404, error="Motor not found")
            return CommandResult(True, data=motor)

        return CommandResult(
            False,
            400,
            error="Unsupported motor action: {}".format(action)
        )

    def _execute_controller(self, action):
        if action == CommandActions.READ_CONTROLLER_STATUS:
            return CommandResult(
                True,
                data=self.controller_port.read_controller_status()
            )
        if action == CommandActions.READ_CONTROLLER_NETWORK:
            return CommandResult(
                True,
                data=self.controller_port.read_network_status()
            )
        if action == CommandActions.READ_CONTROLLER_BATTERY:
            return CommandResult(
                True,
                data=self.controller_port.read_battery_status()
            )
        if action == CommandActions.READ_CONTROLLER_SYSTEM:
            return CommandResult(
                True,
                data=self.controller_port.read_system_status()
            )

        return CommandResult(
            False,
            400,
            error="Unsupported controller action: {}".format(action)
        )
