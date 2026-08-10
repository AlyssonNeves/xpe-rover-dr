#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from app.commands.base_handler import BaseCommandHandler
from app.models import CommandActions, CommandResult, ResultStatuses


class DriveCommandHandler(BaseCommandHandler):
    """Dispatches navigation commands using only the drive port."""

    def __init__(self, drive_port):
        self.drive_port = drive_port

    def execute(self, action, params):
        """Executes high-level differential-drive navigation commands."""
        if self.drive_port is None:
            return CommandResult(
                success=False,
                status=ResultStatuses.UNAVAILABLE,
                error="Drive port is not configured"
            )
        handlers = {
            CommandActions.READ_DRIVE_STATUS: self._read_status,
            CommandActions.READ_DRIVE_TELEMETRY: self._read_telemetry,
            CommandActions.RESET_DRIVE_ODOMETRY: self._reset_odometry,
            CommandActions.MOVE_DRIVE_DISTANCE: self._move_distance,
            CommandActions.ROTATE_DRIVE_ANGLE: self._rotate_angle,
            CommandActions.CURVE_DRIVE_RADIUS: self._curve_radius,
            CommandActions.STOP_NAVIGATION: self._stop_navigation
        }
        handler = handlers.get(action)
        if handler is None:
            return CommandResult(
                success=False,
                status=ResultStatuses.INVALID_ARGUMENT,
                error="Unsupported drive action: {}".format(action)
            )
        try:
            return handler(params)
        except (TypeError, ValueError) as error:
            return CommandResult(
                success=False,
                status=ResultStatuses.INVALID_ARGUMENT,
                error=str(error)
            )

    def _read_status(self, params):
        del params
        return CommandResult(success=True, data=self.drive_port.get_status())

    def _read_telemetry(self, params):
        limit = params.get("limit")
        if limit is not None and not self._is_integer(limit):
            return CommandResult(
                success=False,
                status=ResultStatuses.INVALID_ARGUMENT,
                error="Parameter limit must be an integer"
            )
        return CommandResult(success=True, data=self.drive_port.get_telemetry(limit))

    def _reset_odometry(self, params):
        return CommandResult(
            success=True,
            data=self.drive_port.reset_odometry(
                params.get("x_mm", 0.0),
                params.get("y_mm", 0.0),
                params.get("heading_deg", 0.0)
            )
        )

    def _move_distance(self, params):
        error = self._validate_navigation_numbers(params, ("distance_mm", "speed_sp"))
        if error:
            return error
        return self._accepted_result(self.drive_port.move_distance(
            params["distance_mm"],
            params["speed_sp"],
            stop_action=params.get("stop_action"),
            recover_on_stall=params.get("recover_on_stall", True)
        ))

    def _rotate_angle(self, params):
        error = self._validate_navigation_numbers(params, ("angle_deg", "speed_sp"))
        if error:
            return error
        return self._accepted_result(self.drive_port.rotate_angle(
            params["angle_deg"],
            params["speed_sp"],
            stop_action=params.get("stop_action"),
            recover_on_stall=params.get("recover_on_stall", True)
        ))

    def _curve_radius(self, params):
        error = self._validate_navigation_numbers(
            params, ("radius_mm", "angle_deg", "speed_sp")
        )
        if error:
            return error
        return self._accepted_result(self.drive_port.curve_radius(
            params["radius_mm"],
            params["angle_deg"],
            params["speed_sp"],
            stop_action=params.get("stop_action"),
            recover_on_stall=params.get("recover_on_stall", True)
        ))

    def _stop_navigation(self, params):
        return CommandResult(
            success=True,
            data=self.drive_port.stop(params.get("stop_action"))
        )

    @staticmethod
    def _accepted_result(data):
        accepted = bool(data.get("accepted"))
        return CommandResult(
            success=accepted,
            status=ResultStatuses.ACCEPTED if accepted else ResultStatuses.CONFLICT,
            data=data,
            error=data.get("error")
        )

    def _validate_navigation_numbers(self, params, names):
        """Validates required numeric navigation parameters."""
        for name in names:
            value = params.get(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return CommandResult(
                    success=False,
                    status=ResultStatuses.INVALID_ARGUMENT,
                    error="Parameter {} must be numeric".format(name)
                )
        if abs(int(params.get("speed_sp", 0))) < 1:
            return CommandResult(
                success=False,
                status=ResultStatuses.INVALID_ARGUMENT,
                error="Parameter speed_sp must be non-zero"
            )
        return None
