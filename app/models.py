#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Protocol-independent application models for Rover DR."""


class CommandTargets(object):
    """Logical targets supported by the application layer."""

    SENSOR = "sensor"
    MOTOR = "motor"
    CONTROLLER = "controller"
    STATE = "state"
    DRIVE = "drive"


class CommandActions(object):
    """Logical actions supported by the application layer."""

    LIST_SENSORS = "list_sensors"
    READ_SENSOR = "read_sensor"
    READ_ALL_SENSORS = "read_all_sensors"
    LIST_SENSOR_MODES = "list_sensor_modes"
    CHANGE_SENSOR_MODE = "change_sensor_mode"

    LIST_MOTORS = "list_motors"
    READ_MOTOR = "read_motor"
    READ_ALL_MOTORS = "read_all_motors"
    STOP_MOTOR = "stop_motor"
    STOP_ALL_MOTORS = "stop_all_motors"
    RUN_TIMED_MOTOR = "run_timed_motor"
    RUN_FOREVER_MOTOR = "run_forever_motor"
    RUN_DIRECT_MOTOR = "run_direct_motor"
    RUN_TO_REL_POS_MOTOR = "run_to_rel_pos_motor"
    RUN_TO_ABS_POS_MOTOR = "run_to_abs_pos_motor"
    READ_MOTOR_COMMAND = "read_motor_command"
    LIST_MOTOR_COMMANDS = "list_motor_commands"
    DRIVE_TANK = "drive_tank"
    STOP_DRIVE = "stop_drive"
    RESET_MOTOR = "reset_motor"
    CANCEL_MOTOR_COMMANDS = "cancel_motor_commands"
    RUN_SYNCHRONIZED_MOTORS = "run_synchronized_motors"

    READ_CONTROLLER_STATUS = "read_controller_status"
    READ_CONTROLLER_NETWORK = "read_controller_network"
    READ_CONTROLLER_BATTERY = "read_controller_battery"
    READ_CONTROLLER_SYSTEM = "read_controller_system"

    READ_ROVER_STATE = "read_rover_state"

    READ_DRIVE_STATUS = "read_drive_status"
    READ_DRIVE_TELEMETRY = "read_drive_telemetry"
    RESET_DRIVE_ODOMETRY = "reset_drive_odometry"
    MOVE_DRIVE_DISTANCE = "move_drive_distance"
    ROTATE_DRIVE_ANGLE = "rotate_drive_angle"
    CURVE_DRIVE_RADIUS = "curve_drive_radius"
    STOP_NAVIGATION = "stop_navigation"


class ResultStatuses(object):
    """Semantic result classifications independent from transport protocols."""

    SUCCESS = "success"
    ACCEPTED = "accepted"
    INVALID_ARGUMENT = "invalid_argument"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    UNAVAILABLE = "unavailable"
    UNAUTHORIZED = "unauthorized"
    INTERNAL_ERROR = "internal_error"


class CommandResult(object):
    """Standardized application result without HTTP-specific semantics."""

    def __init__(self, success, status=ResultStatuses.SUCCESS,
                 data=None, error=None):
        self.success = bool(success)
        self.status = status
        self.data = data
        self.error = error

    def to_dict(self):
        payload = {
            "success": self.success,
            "status": self.status
        }
        if self.data is not None:
            payload["data"] = self.data
        if self.error:
            payload["error"] = self.error
        return payload
