#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Central application command dispatcher."""

from app.commands.controller_handler import ControllerCommandHandler
from app.commands.drive_handler import DriveCommandHandler
from app.commands.motor_handler import MotorCommandHandler
from app.commands.sensor_handler import SensorCommandHandler
from app.commands.state_handler import StateCommandHandler
from app.operation_mode_service import coerce_operation_mode
from app.models import (
    CommandActions, CommandResult, CommandTargets, ResultStatuses
)


class CommandService(object):
    """Routes commands to domain handlers and enforces control ownership."""

    def __init__(self, sensor_query_port=None, sensor_command_port=None,
                 motor_query_port=None, controller_port=None,
                 rover_state_query_port=None, motor_command_port=None,
                 motor_command_query_port=None, drive_motor_port=None,
                 drive_port=None, operation_mode_service=None):
        self.operation_mode_service = operation_mode_service
        self.handlers = {
            CommandTargets.SENSOR: SensorCommandHandler(
                sensor_query_port, sensor_command_port
            ),
            CommandTargets.MOTOR: MotorCommandHandler(
                motor_query_port=motor_query_port,
                motor_command_port=motor_command_port,
                motor_command_query_port=motor_command_query_port,
                drive_motor_port=drive_motor_port
            ),
            CommandTargets.CONTROLLER: ControllerCommandHandler(
                controller_port
            ),
            CommandTargets.STATE: StateCommandHandler(
                rover_state_query_port
            ),
            CommandTargets.DRIVE: DriveCommandHandler(drive_port)
        }

    def execute(self, target, action, params=None):
        params = dict(params or {})
        handler = self.handlers.get(target)
        if handler is None:
            return CommandResult(
                success=False,
                status=ResultStatuses.INVALID_ARGUMENT,
                error="Unsupported command target: {}".format(target)
            )

        authorization_error = self._authorize(target, action)
        if authorization_error is not None:
            return authorization_error

        return handler.execute(action, params)

    def _authorize(self, target, action):
        if self.operation_mode_service is None:
            return None
        mode = coerce_operation_mode(self.operation_mode_service)
        if not mode.is_local_manual():
            return None

        if target == CommandTargets.DRIVE:
            return CommandResult(
                success=False,
                status=ResultStatuses.CONFLICT,
                error=(
                    "Drive commands are unavailable while LOCAL + MANUAL "
                    "control owns the motor hardware."
                )
            )

        motor_writes = frozenset((
            CommandActions.STOP_MOTOR,
            CommandActions.STOP_ALL_MOTORS,
            CommandActions.RUN_TIMED_MOTOR,
            CommandActions.RUN_FOREVER_MOTOR,
            CommandActions.RUN_DIRECT_MOTOR,
            CommandActions.RUN_TO_REL_POS_MOTOR,
            CommandActions.RUN_TO_ABS_POS_MOTOR,
            CommandActions.DRIVE_TANK,
            CommandActions.STOP_DRIVE,
            CommandActions.RESET_MOTOR,
            CommandActions.CANCEL_MOTOR_COMMANDS,
            CommandActions.RUN_SYNCHRONIZED_MOTORS
        ))
        if target == CommandTargets.MOTOR and action in motor_writes:
            return CommandResult(
                success=False,
                status=ResultStatuses.CONFLICT,
                error=(
                    "Motor writes are unavailable while LOCAL + MANUAL "
                    "control owns the motor hardware."
                )
            )

        if (target == CommandTargets.SENSOR and
                action == CommandActions.CHANGE_SENSOR_MODE):
            return CommandResult(
                success=False,
                status=ResultStatuses.CONFLICT,
                error=(
                    "Sensor mode changes are unavailable while LOCAL + "
                    "MANUAL control is active."
                )
            )
        return None
