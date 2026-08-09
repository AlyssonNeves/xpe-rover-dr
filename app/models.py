#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Application command models used by the Rover-DR REST API."""


class CommandTargets(object):
    """Logical targets available to the application service."""

    SENSOR = "sensor"
    MOTOR = "motor"
    CONTROLLER = "controller"
    ROVER = "rover"

    @classmethod
    def values(cls):
        """Returns the targets supported by this application increment."""
        return (cls.SENSOR, cls.MOTOR, cls.CONTROLLER, cls.ROVER)


class CommandActions(object):
    """Query and basic motor-execution actions exposed by the application."""

    LIST_SENSORS = "list_sensors"
    READ_SENSOR = "read_sensor"
    READ_ALL_SENSORS = "read_all_sensors"

    LIST_MOTORS = "list_motors"
    READ_MOTOR = "read_motor"
    READ_ALL_MOTORS = "read_all_motors"
    STOP_MOTOR = "stop_motor"
    RUN_TIMED_MOTOR = "run_timed_motor"
    RUN_FOREVER_MOTOR = "run_forever_motor"
    RUN_TO_REL_POS_MOTOR = "run_to_rel_pos_motor"
    RESET_MOTOR = "reset_motor"

    READ_CONTROLLER_STATUS = "read_controller_status"
    READ_CONTROLLER_NETWORK = "read_controller_network"
    READ_CONTROLLER_BATTERY = "read_controller_battery"
    READ_CONTROLLER_SYSTEM = "read_controller_system"

    READ_ROVER_STATE = "read_rover_state"


class CommandResult(object):
    """Standard result returned by the application command service."""

    def __init__(self, success, status_code=200, data=None, error=None):
        self.success = bool(success)
        self.status_code = int(status_code)
        self.data = data
        self.error = error

    @classmethod
    def ok(cls, data=None, status_code=200):
        return cls(True, status_code=status_code, data=data)

    @classmethod
    def bad_request(cls, message):
        return cls(False, status_code=400, error=message)

    @classmethod
    def not_found(cls, message):
        return cls(False, status_code=404, error=message)

    @classmethod
    def method_not_allowed(cls, message="Method not allowed"):
        return cls(False, status_code=405, error=message)

    @classmethod
    def service_unavailable(cls, message):
        return cls(False, status_code=503, error=message)

    @classmethod
    def internal_error(cls, message="Internal server error"):
        return cls(False, status_code=500, error=message)

    def to_dict(self):
        payload = {"success": self.success, "status_code": self.status_code}
        if self.data is not None:
            payload["data"] = self.data
        if self.error:
            payload["error"] = self.error
        return payload
