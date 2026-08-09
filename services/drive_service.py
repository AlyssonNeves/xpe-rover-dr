#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Initial differential-drive service for Rover-DR."""

import copy
import threading
import time

from app.rover_config import (
    DRIVE_LEFT_MOTOR_CODE,
    DRIVE_RIGHT_MOTOR_CODE,
    MOTOR_DEFAULT_STOP_ACTION,
    MOTOR_RUN_FOREVER_WATCHDOG_MS,
)


class DriveService(object):
    """Coordinates the configured left/right traction motors as one subsystem.

    This first drive increment deliberately does not perform odometry, gyro
    feedback or geometric navigation. It only provides tank-style differential
    control above the existing motor orchestration port.
    """

    def __init__(self, motor_port):
        self.motor_port = motor_port
        self.left_motor_code = DRIVE_LEFT_MOTOR_CODE
        self.right_motor_code = DRIVE_RIGHT_MOTOR_CODE
        self._lock = threading.RLock()
        self._last_drive_command = None

    def get_status(self):
        """Returns drive configuration, latest request and motor snapshots."""
        with self._lock:
            last_command = copy.deepcopy(self._last_drive_command)

        return {
            "mode": "differential",
            "left_motor_code": self.left_motor_code,
            "right_motor_code": self.right_motor_code,
            "left_motor": self.motor_port.read_motor(self.left_motor_code),
            "right_motor": self.motor_port.read_motor(self.right_motor_code),
            "last_drive_command": last_command,
        }

    def drive_tank(
        self, left_speed_sp, right_speed_sp, priority=None,
        stop_action=None, watchdog_ms=None
    ):
        """Submits a synchronized continuous command for both traction motors."""
        stop_action = stop_action or MOTOR_DEFAULT_STOP_ACTION
        watchdog_ms = (
            MOTOR_RUN_FOREVER_WATCHDOG_MS
            if watchdog_ms is None
            else watchdog_ms
        )
        priority = 0 if priority is None else priority

        if left_speed_sp == 0 and right_speed_sp == 0:
            return self.stop(stop_action)

        commands = [
            {
                "code": self.left_motor_code,
                "action": "run-forever",
                "priority": priority,
                "parameters": {
                    "speed_sp": left_speed_sp,
                    "stop_action": stop_action,
                    "watchdog_ms": watchdog_ms,
                },
            },
            {
                "code": self.right_motor_code,
                "action": "run-forever",
                "priority": priority,
                "parameters": {
                    "speed_sp": right_speed_sp,
                    "stop_action": stop_action,
                    "watchdog_ms": watchdog_ms,
                },
            },
        ]
        result = self.motor_port.run_synchronized_motors(commands)

        with self._lock:
            self._last_drive_command = {
                "action": "tank",
                "left_speed_sp": left_speed_sp,
                "right_speed_sp": right_speed_sp,
                "priority": priority,
                "stop_action": stop_action,
                "watchdog_ms": watchdog_ms,
                "submitted_at": time.time(),
                "accepted": bool(result and result.get("accepted")),
                "batch_id": result.get("batch_id") if result else None,
            }

        return result

    def stop(self, stop_action=None):
        """Stops both traction motors using the existing preemptive stop path."""
        stop_action = stop_action or MOTOR_DEFAULT_STOP_ACTION
        left = self.motor_port.stop_motor(self.left_motor_code, stop_action)
        right = self.motor_port.stop_motor(self.right_motor_code, stop_action)
        accepted = bool(
            left and right and left.get("accepted") and right.get("accepted")
        )

        result = {
            "accepted": accepted,
            "action": "stop",
            "stop_action": stop_action,
            "motors": {
                self.left_motor_code: left,
                self.right_motor_code: right,
            },
        }
        if not accepted:
            result["error"] = "One or more traction motors could not be stopped"

        with self._lock:
            self._last_drive_command = {
                "action": "stop",
                "stop_action": stop_action,
                "submitted_at": time.time(),
                "accepted": accepted,
            }
        return result
