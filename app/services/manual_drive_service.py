#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Synchronous motor-control service for LOCAL + MANUAL operation."""

import threading
from datetime import datetime

from ports.manual_drive_port import ManualDrivePort


class ManualDriveService(ManualDrivePort):
    """Owns joystick-controlled motors and writes setpoints synchronously.

    The service intentionally bypasses ``MotorPort``, ``DriveService`` and the
    ``MotorMonitor`` command queues. Physical drivers are preconnected when a
    manual session is acquired and retained by the hardware adapter/registry.
    """

    def __init__(self, motor_hardware_port, drive_config, mecanum_config,
                 joystick_config, default_stop_action="brake",
                 motor_state_publisher_port=None):
        if motor_hardware_port is None:
            raise ValueError("motor_hardware_port is required.")
        if not isinstance(drive_config, dict):
            raise ValueError("drive_config is required.")
        if not isinstance(mecanum_config, dict) or not mecanum_config:
            raise ValueError("mecanum_config is required.")
        if not isinstance(joystick_config, dict):
            raise ValueError("joystick_config is required.")

        self._hardware = motor_hardware_port
        self._state_publisher = motor_state_publisher_port
        self._left_motor_code = drive_config.get("left_motor_code", "LLM")
        self._right_motor_code = drive_config.get("right_motor_code", "RLM")
        self._left_auxiliary_motor_code = joystick_config.get(
            "left_auxiliary_motor_code", "LMM"
        )
        self._right_auxiliary_motor_code = joystick_config.get(
            "right_auxiliary_motor_code", "RMM"
        )
        self._mecanum_motor_codes = (
            mecanum_config.get("front_left_motor_code"),
            mecanum_config.get("rear_left_motor_code"),
            mecanum_config.get("front_right_motor_code"),
            mecanum_config.get("rear_right_motor_code")
        )
        if None in self._mecanum_motor_codes:
            raise ValueError("Mecanum motor codes are required.")
        if len(set(self._mecanum_motor_codes)) != 4:
            raise ValueError(
                "Mecanum motor codes must identify four distinct motors."
            )
        self._mecanum_speed_factors = (
            self._positive_factor(
                mecanum_config.get("front_left_speed_factor", 1.0),
                "front_left_speed_factor"
            ),
            self._positive_factor(
                mecanum_config.get("rear_left_speed_factor", 1.0),
                "rear_left_speed_factor"
            ),
            self._positive_factor(
                mecanum_config.get("front_right_speed_factor", 1.0),
                "front_right_speed_factor"
            ),
            self._positive_factor(
                mecanum_config.get("rear_right_speed_factor", 1.0),
                "rear_right_speed_factor"
            )
        )
        self._default_stop_action = default_stop_action or "brake"
        self._default_motor_codes = self._unique((
            self._left_motor_code,
            self._right_motor_code,
            self._left_auxiliary_motor_code,
            self._right_auxiliary_motor_code
        ) + self._mecanum_motor_codes)
        self._lock = threading.RLock()
        self._session_id = None
        self._controlled_motor_codes = self._default_motor_codes

    @staticmethod
    def _unique(values):
        result = []
        for value in values:
            if value is not None and value not in result:
                result.append(value)
        return tuple(result)

    @staticmethod
    def _positive_factor(value, name):
        try:
            factor = float(value)
        except (TypeError, ValueError):
            raise ValueError("{} must be numeric.".format(name))
        if factor <= 0.0:
            raise ValueError("{} must be positive.".format(name))
        return factor

    def acquire(self, session_id, motor_codes=None):
        if not session_id:
            return {"success": False, "error": "Manual session id is required."}

        requested = tuple(motor_codes or ())
        controlled = self._unique(self._default_motor_codes + requested)

        with self._lock:
            if self._session_id is not None and self._session_id != session_id:
                return {
                    "success": False,
                    "error": "Local manual control is already owned."
                }

            connected = []
            for motor_code in controlled:
                if self._hardware.ensure_connected(motor_code) is None:
                    error = (
                        self._hardware.get_error(motor_code)
                        or "Motor hardware is unavailable."
                    )
                    self._stop_codes(connected)
                    self._publish_state(
                        motor_code, speed_sp=0, connected=False,
                        running=False, hardware_error=error
                    )
                    return {
                        "success": False,
                        "failed_motor_code": motor_code,
                        "error": error,
                        "hardware_error": error
                    }
                connected.append(motor_code)
                self._publish_state(
                    motor_code, speed_sp=0, connected=True, running=False
                )

            self._controlled_motor_codes = controlled
            self._session_id = session_id
            stopped = self._stop_codes(controlled)
            if not stopped.get("success"):
                self._session_id = None
                return stopped

            return {
                "success": True,
                "session_id": session_id,
                "motor_codes": list(controlled),
                "direct_hardware": True,
                "watchdog_enabled": False
            }

    def apply_drive_setpoint(
            self, session_id, left_speed_sp, right_speed_sp,
            stop_action=None):
        with self._lock:
            invalid = self._validate_session(session_id)
            if invalid is not None:
                return invalid

            left_speed = int(left_speed_sp)
            right_speed = int(right_speed_sp)
            resolved_stop = stop_action or self._default_stop_action
            if left_speed == 0 and right_speed == 0:
                return self._stop_codes(
                    (self._left_motor_code, self._right_motor_code),
                    resolved_stop
                )

            left_result = self._hardware.run_forever(
                self._left_motor_code, left_speed
            )
            if not left_result.get("success"):
                self._stop_codes(
                    (self._left_motor_code, self._right_motor_code),
                    resolved_stop
                )
                return self._failure(self._left_motor_code, left_result)

            right_result = self._hardware.run_forever(
                self._right_motor_code, right_speed
            )
            if not right_result.get("success"):
                self._stop_codes(
                    (self._left_motor_code, self._right_motor_code),
                    resolved_stop
                )
                return self._failure(self._right_motor_code, right_result)

            self._publish_state(
                self._left_motor_code, left_speed, True, True
            )
            self._publish_state(
                self._right_motor_code, right_speed, True, True
            )
            return {
                "success": True,
                "direct_hardware": True,
                "watchdog_enabled": False,
                "setpoint": (left_speed, right_speed)
            }

    def apply_mecanum_setpoint(
            self, session_id, front_left_speed_sp, rear_left_speed_sp,
            front_right_speed_sp, rear_right_speed_sp, stop_action=None):
        """Applies four independently calibrated wheel setpoints directly."""
        raw_speeds = (
            front_left_speed_sp,
            rear_left_speed_sp,
            front_right_speed_sp,
            rear_right_speed_sp
        )
        calibrated = tuple(
            int(round(float(speed) * factor))
            for speed, factor in zip(
                raw_speeds, self._mecanum_speed_factors
            )
        )

        with self._lock:
            invalid = self._validate_session(session_id)
            if invalid is not None:
                return invalid

            resolved_stop = stop_action or self._default_stop_action
            if not any(calibrated):
                return self._stop_codes(
                    self._mecanum_motor_codes, resolved_stop
                )

            for motor_code, speed in zip(
                    self._mecanum_motor_codes, calibrated):
                result = self._hardware.run_forever(motor_code, speed)
                if not result.get("success"):
                    self._stop_codes(
                        self._mecanum_motor_codes, resolved_stop
                    )
                    return self._failure(motor_code, result)
                self._publish_state(motor_code, speed, True, True)

            return {
                "success": True,
                "direct_hardware": True,
                "watchdog_enabled": False,
                "setpoint": calibrated,
                "motor_codes": list(self._mecanum_motor_codes)
            }

    def apply_auxiliary_setpoint(
            self, session_id, motor_code, speed_sp, stop_action=None):
        with self._lock:
            invalid = self._validate_session(session_id)
            if invalid is not None:
                return invalid
            if motor_code not in self._controlled_motor_codes:
                return {
                    "success": False,
                    "error": "Motor is not owned by the local manual session."
                }

            speed = int(speed_sp)
            if speed == 0:
                result = self._hardware.stop(
                    motor_code,
                    stop_action or self._default_stop_action,
                    connected_only=True
                )
                if result.get("success"):
                    self._publish_state(
                        motor_code, speed_sp=0, connected=True, running=False
                    )
                return result

            result = self._hardware.run_forever(motor_code, speed)
            if not result.get("success"):
                return self._failure(motor_code, result)
            self._publish_state(motor_code, speed, True, True)
            return {
                "success": True,
                "direct_hardware": True,
                "watchdog_enabled": False,
                "motor_code": motor_code,
                "speed_sp": speed
            }

    def emergency_stop(self, stop_action=None):
        with self._lock:
            return self._stop_codes(
                self._controlled_motor_codes,
                stop_action or self._default_stop_action
            )

    def release(self, session_id, stop=True):
        with self._lock:
            invalid = self._validate_session(session_id)
            if invalid is not None:
                return invalid
            result = {"success": True}
            if stop:
                result = self._stop_codes(self._controlled_motor_codes)
            self._session_id = None
            return result

    def close(self):
        with self._lock:
            if self._session_id is not None:
                self._stop_codes(self._controlled_motor_codes)
                self._session_id = None

    def _validate_session(self, session_id):
        if self._session_id is None:
            return {"success": False, "error": "Manual drive is not acquired."}
        if session_id != self._session_id:
            return {"success": False, "error": "Invalid manual session id."}
        return None

    def _stop_codes(self, motor_codes, stop_action=None):
        first_failure = None
        for motor_code in motor_codes:
            result = self._hardware.stop(
                motor_code,
                stop_action or self._default_stop_action,
                connected_only=True
            )
            if result.get("success"):
                self._publish_state(
                    motor_code, speed_sp=0, connected=True, running=False
                )
            else:
                self._publish_state(
                    motor_code, speed_sp=0, connected=True, running=False,
                    hardware_error=(
                        result.get("hardware_error") or result.get("error")
                    )
                )
            if not result.get("success") and first_failure is None:
                first_failure = self._failure(motor_code, result)
        if first_failure is not None:
            return first_failure
        return {
            "success": True,
            "direct_hardware": True,
            "watchdog_enabled": False
        }

    def _publish_state(
            self, motor_code, speed_sp, connected, running,
            hardware_error=None):
        """Publishes state through a port, never through a concrete store."""
        if self._state_publisher is None:
            return
        definition = self._hardware.get_motor_definition(motor_code) or {}
        snapshot = {
            "code": motor_code,
            "name": definition.get("name"),
            "address": definition.get("address"),
            "motor_class": definition.get("motor_class"),
            "polarity": definition.get("polarity"),
            "speed": int(speed_sp),
            "state": ["running"] if running else [],
            "connected": bool(connected),
            "source": "local-manual-direct",
            "error": hardware_error,
            "lifecycle_state": "RUNNING" if running else "IDLE",
            "command_queue_size": 0,
            "active_command_id": None,
            "last_safety_event": None,
            "manual_control": True,
            "watchdog_enabled": False,
            "updated_at": datetime.now().strftime(
                "%d/%m/%y %H:%M:%S.%f"
            )[:-3]
        }
        self._state_publisher.publish_motor_state(motor_code, snapshot)

    @staticmethod
    def _failure(motor_code, result):
        error = (
            result.get("hardware_error") or result.get("error")
            or "Motor hardware operation failed."
        )
        return {
            "success": False,
            "failed_motor_code": motor_code,
            "error": error,
            "hardware_error": error
        }
