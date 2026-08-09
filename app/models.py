#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Application command models used by the Rover-DR REST API."""


class CommandTargets(object):
    """Logical targets available to the application service."""

    SENSOR = "sensor"
    MOTOR = "motor"
    CONTROLLER = "controller"
    ROVER = "rover"


class CommandActions(object):
    """Read-only actions exposed by the current REST API."""

    LIST_SENSORS = "list_sensors"
    READ_SENSOR = "read_sensor"
    READ_ALL_SENSORS = "read_all_sensors"

    LIST_MOTORS = "list_motors"
    READ_MOTOR = "read_motor"
    READ_ALL_MOTORS = "read_all_motors"

    READ_CONTROLLER_STATUS = "read_controller_status"
    READ_CONTROLLER_NETWORK = "read_controller_network"
    READ_CONTROLLER_BATTERY = "read_controller_battery"
    READ_CONTROLLER_SYSTEM = "read_controller_system"

    READ_ROVER_STATE = "read_rover_state"


class CommandResult(object):
    """Standard result returned by the application command service."""

    def __init__(self, success, status_code=200, data=None, error=None):
        self.success = success
        self.status_code = status_code
        self.data = data
        self.error = error

    def to_dict(self):
        """Returns a JSON-serializable representation of this result."""
        payload = {
            "success": self.success,
            "status_code": self.status_code
        }
        if self.data is not None:
            payload["data"] = self.data
        if self.error:
            payload["error"] = self.error
        return payload
