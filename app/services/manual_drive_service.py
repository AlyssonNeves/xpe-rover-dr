#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Application service for deterministic local manual drive control."""

import threading
import time

from app.motor_lifecycle import MotorLifecycleStates
from app.sequence_utils import unique_preserving_order
from ports.manual_drive_port import ManualDrivePort
from ports.runtime_component_port import RuntimeComponentPort


class NullApplicationLogger(object):
    """No-op logger used when no logging port is injected."""

    @staticmethod
    def status(message):
        del message

    @staticmethod
    def error(message):
        del message


class NullStartupProgress(object):
    """No-op progress output used outside the EV3 startup screen."""

    @staticmethod
    def show_startup_progress(message):
        del message


class NullStatusLed(object):
    """No-op status LED output used outside EV3 hardware execution."""

    @staticmethod
    def set_fault(source, active=True):
        del source, active


class ManualDriveService(ManualDrivePort, RuntimeComponentPort):
    """Owns every joystick-controlled motor for one local manual session.

    Motor control depends on ``MotorHardwarePort`` and state publication uses
    the explicit ``MotorStatePublisherPort``. The service does not use
    ``MotorMonitor``, command queues, watchdogs or concrete state stores. Motor
    driver instances are connected when a Bluetooth joystick session is
    acquired and remain cached by the hardware adapter for that session.
    """

    def __init__(self, motor_hardware_port, drive_config, mecanum_config,
                 joystick_config, default_stop_action,
                 motor_state_publisher_port=None, clock=None,
                 monotonic_clock=None, logger=None,
                 startup_progress_port=None, status_led_port=None):
        if motor_hardware_port is None:
            raise ValueError(
                "motor_hardware_port is required for local manual control."
            )
        if drive_config is None or mecanum_config is None or joystick_config is None:
            raise ValueError(
                "Resolved drive, mecanum, and joystick configuration is required."
            )
        if not default_stop_action:
            raise ValueError("default_stop_action is required.")

        self._hardware = motor_hardware_port
        self._state_publisher = motor_state_publisher_port
        self._drive_config = dict(drive_config)
        self._mecanum_config = dict(mecanum_config)
        self._joystick_config = dict(joystick_config)
        self._default_stop_action = default_stop_action
        self._clock = clock or time.time
        self._monotonic_clock = monotonic_clock or time.monotonic
        self._logger = logger or NullApplicationLogger
        self._startup_progress = (
            startup_progress_port or NullStartupProgress()
        )
        self._status_led = status_led_port or NullStatusLed()
        self._left = self._drive_config["left_motor_code"]
        self._right = self._drive_config["right_motor_code"]
        # The EV3 hardware adapter applies each motor's global polarity from
        # motor_definitions to every command path. Mecanum factors are a second,
        # mode-specific layer used only to compensate the front Large-motor
        # gear train; they must never replace or duplicate the global polarity.
        self._mecanum_codes = (
            self._mecanum_config["front_left_motor_code"],
            self._mecanum_config["rear_left_motor_code"],
            self._mecanum_config["front_right_motor_code"],
            self._mecanum_config["rear_right_motor_code"]
        )
        if len(set(self._mecanum_codes)) != 4:
            raise ValueError("Mecanum motor codes must identify four distinct motors.")
        self._mecanum_mode_factors = (
            float(self._mecanum_config["front_left_speed_factor"]),
            float(self._mecanum_config["rear_left_speed_factor"]),
            float(self._mecanum_config["front_right_speed_factor"]),
            float(self._mecanum_config["rear_right_speed_factor"])
        )
        self._default_motor_codes = unique_preserving_order((
            self._left,
            self._right,
            self._joystick_config["left_auxiliary_motor_code"],
            self._joystick_config["right_auxiliary_motor_code"]
        ) + self._mecanum_codes)
        self._lock = threading.RLock()
        self._session_id = None
        self._controlled_motor_codes = self._default_motor_codes
        self._running = dict(
            (motor_code, False) for motor_code in self._default_motor_codes
        )
        self._last_setpoint = (0, 0)
        self._last_mecanum_setpoint = (0, 0, 0, 0)

    def prepare_start(self):
        """Defers motor I/O until the Bluetooth joystick session is open."""
        return None

    def start(self):
        """Runtime-component hook; acquisition follows joystick connection."""
        return None

    def stop(self):
        """Synchronously stops every motor owned by the manual service."""
        self.close()

    def _prepare_connected_motor_locked(self, motor_code, motor):
        """Stops one connected motor and zeroes its position when supported."""
        stop_method = getattr(motor, "stop", None)
        if callable(stop_method):
            try:
                stop_method(stop_action=self._default_stop_action)
            except TypeError:
                stop_method()
        elif hasattr(self._hardware, "stop"):
            self._hardware.stop(
                motor_code,
                self._default_stop_action,
                connected_only=False
            )

        if hasattr(motor, "position"):
            try:
                motor.position = 0
            except Exception:
                pass

        self._publish_state(
            motor_code,
            0,
            False,
            True,
            stop_action=self._default_stop_action,
            hardware_error=None
        )
        self._running[motor_code] = False

    def acquire(self, session_id, motor_codes=None):
        """Acquires and preconnects all motors for one joystick session."""
        if not session_id:
            return {"success": False, "error": "Manual session id is required."}

        requested_codes = tuple(motor_codes or ())
        controlled_codes = unique_preserving_order(
            self._default_motor_codes + requested_codes
        )

        with self._lock:
            if self._session_id is not None and self._session_id != session_id:
                return {
                    "success": False,
                    "error": "Local manual control is already owned."
                }

            initialization_started = self._monotonic_clock()
            connected_codes = []
            for motor_code in controlled_codes:
                self._report_startup_progress(
                    "Connecting motor {0}.".format(motor_code)
                )
                motor_started = self._monotonic_clock()
                motor = self._hardware.ensure_connected(motor_code)
                elapsed = self._monotonic_clock() - motor_started
                if motor is None:
                    error = (
                        self._hardware.get_error(motor_code)
                        or "Motor hardware is unavailable."
                    )
                    self._report_startup_progress(
                        "Motor {0} failed after {1:.3f} s.".format(
                            motor_code, elapsed
                        )
                    )
                    self._stop_codes_locked(connected_codes)
                    self._publish_state(
                        motor_code, 0, False, False,
                        hardware_error=error
                    )
                    self._set_motor_fault(True)
                    return {
                        "success": False,
                        "failed_motor_code": motor_code,
                        "error": error,
                        "hardware_error": error
                    }
                connected_codes.append(motor_code)
                self._prepare_connected_motor_locked(motor_code, motor)
                self._report_startup_progress(
                    "Motor {0} connected and zeroed in {1:.3f} s.".format(
                        motor_code, elapsed
                    )
                )

            self._session_id = session_id
            self._controlled_motor_codes = controlled_codes
            for motor_code in controlled_codes:
                self._running[motor_code] = False

            # Every new operator session starts from a physically stopped state.
            self._report_startup_progress(
                "Stopping motors for safe startup."
            )
            stop_result = self._stop_codes_locked(controlled_codes)
            if not stop_result.get("success"):
                self._session_id = None
                self._set_motor_fault(True)
                return stop_result

            self._last_setpoint = (0, 0)
            self._last_mecanum_setpoint = (0, 0, 0, 0)
            self._report_startup_progress(
                "Motor session ready in {0:.3f} s.".format(
                    self._monotonic_clock() - initialization_started
                )
            )
            self._set_motor_fault(False)
            return {
                "success": True,
                "session_id": session_id,
                "motor_codes": list(controlled_codes),
                "direct_hardware": True,
                "watchdog_enabled": False
            }

    def apply_drive_setpoint(
            self, session_id, left_speed_sp, right_speed_sp,
            stop_action=None):
        """Applies one traction setpoint directly to EV3 motor drivers."""
        left_speed = int(left_speed_sp)
        right_speed = int(right_speed_sp)
        resolved_stop_action = (
            stop_action or self._default_stop_action
        )

        with self._lock:
            invalid = self._validate_session(session_id)
            if invalid is not None:
                return invalid

            if left_speed == 0 and right_speed == 0:
                return self._stop_codes_locked(
                    (self._left, self._right), resolved_stop_action
                )

            left_result = self._apply_speed_locked(
                self._left, left_speed, resolved_stop_action
            )
            if not left_result.get("success"):
                self._stop_codes_locked(
                    (self._left, self._right), resolved_stop_action
                )
                return self._failure(self._left, left_result)

            right_result = self._apply_speed_locked(
                self._right, right_speed, resolved_stop_action
            )
            if not right_result.get("success"):
                self._stop_codes_locked(
                    (self._left, self._right), resolved_stop_action
                )
                return self._failure(self._right, right_result)

            self._last_setpoint = (left_speed, right_speed)
            self._set_motor_fault(False)
            return {
                "success": True,
                "direct_hardware": True,
                "watchdog_enabled": False,
                "setpoint": self._last_setpoint
            }

    def apply_mecanum_setpoint(
            self, session_id, front_left_speed_sp, rear_left_speed_sp,
            front_right_speed_sp, rear_right_speed_sp, stop_action=None):
        """Applies Mecanum-only factors above global motor polarity."""
        raw_speeds = (
            front_left_speed_sp,
            rear_left_speed_sp,
            front_right_speed_sp,
            rear_right_speed_sp
        )
        speeds = tuple(
            int(round(float(speed) * factor))
            for speed, factor in zip(raw_speeds, self._mecanum_mode_factors)
        )
        resolved_stop_action = stop_action or self._default_stop_action

        with self._lock:
            invalid = self._validate_session(session_id)
            if invalid is not None:
                return invalid

            if not any(speeds):
                return self._stop_codes_locked(
                    self._mecanum_codes, resolved_stop_action
                )

            for motor_code, speed in zip(self._mecanum_codes, speeds):
                result = self._apply_speed_locked(
                    motor_code, speed, resolved_stop_action
                )
                if not result.get("success"):
                    self._stop_codes_locked(
                        self._mecanum_codes, resolved_stop_action
                    )
                    return self._failure(motor_code, result)

            self._last_mecanum_setpoint = speeds
            self._set_motor_fault(False)
            return {
                "success": True,
                "direct_hardware": True,
                "watchdog_enabled": False,
                "setpoint": self._last_mecanum_setpoint,
                "motor_codes": list(self._mecanum_codes)
            }

    def apply_auxiliary_setpoint(
            self, session_id, motor_code, speed_sp, stop_action=None):
        """Applies one auxiliary setpoint without a queue or watchdog."""
        speed = int(speed_sp)
        resolved_stop_action = (
            stop_action or self._default_stop_action
        )

        with self._lock:
            invalid = self._validate_session(session_id)
            if invalid is not None:
                return invalid
            if motor_code not in self._controlled_motor_codes:
                return {
                    "success": False,
                    "error": "Motor is not owned by the local manual session."
                }

            result = self._apply_speed_locked(
                motor_code, speed, resolved_stop_action
            )
            if not result.get("success"):
                self._set_motor_fault(True)
                return self._failure(motor_code, result)
            self._set_motor_fault(False)
            return {
                "success": True,
                "direct_hardware": True,
                "watchdog_enabled": False,
                "motor_code": motor_code,
                "speed_sp": speed
            }

    def emergency_stop(self, stop_action=None):
        """Stops all manual motors synchronously, including on Bluetooth loss."""
        with self._lock:
            return self._stop_codes_locked(
                self._controlled_motor_codes,
                stop_action or self._default_stop_action
            )

    def release(self, session_id, stop=True):
        """Releases ownership after an optional synchronous physical stop."""
        with self._lock:
            if session_id != self._session_id:
                return {
                    "success": False,
                    "error": "Manual session was not found."
                }
            results = {}
            if stop:
                results = self._stop_codes_locked(
                    self._controlled_motor_codes
                ).get("motors", {})
            self._session_id = None
            self._last_setpoint = (0, 0)
            self._last_mecanum_setpoint = (0, 0, 0, 0)
            return {"success": True, "motors": results}

    def close(self):
        """Closes the service in a fail-safe stopped state."""
        self.emergency_stop(self._default_stop_action)
        with self._lock:
            self._session_id = None

    def _report_startup_progress(self, message):
        """Publishes the same timed step to logs and the EV3 display."""
        self._logger.status(message)
        try:
            self._startup_progress.show_startup_progress(message)
        except Exception as error:
            self._logger.error(
                "Unable to update startup progress screen: {0}".format(
                    error
                )
            )

    def _validate_session(self, session_id):
        if session_id is None or session_id != self._session_id:
            return {
                "success": False,
                "session_invalid": True,
                "reason": "session_not_found",
                "error": "Local manual control session is no longer valid."
            }
        return None

    def _apply_speed_locked(self, motor_code, speed_sp, stop_action):
        if speed_sp == 0:
            result = self._hardware.stop(
                motor_code, stop_action, connected_only=True
            )
            if result.get("success"):
                self._running[motor_code] = False
            self._publish_result_state(
                motor_code, speed_sp, False, result, stop_action
            )
            return result

        # Reissue native run_forever for every changed manual setpoint. On the
        # target EV3/ev3dev combination, updating speed_sp alone while the
        # command is active does not reliably change the physical speed.
        result = self._hardware.run_forever(motor_code, speed_sp)
        if result.get("success"):
            self._running[motor_code] = True

        self._publish_result_state(
            motor_code, speed_sp, True, result, stop_action
        )
        if not result.get("success"):
            self._set_motor_fault(True)
        return result

    def _stop_codes_locked(self, motor_codes, stop_action=None):
        resolved_stop_action = (
            stop_action or self._default_stop_action
        )
        results = {}
        success = True

        motor_codes = tuple(motor_codes)
        for motor_code in motor_codes:
            result = self._hardware.stop(
                motor_code, resolved_stop_action, connected_only=True
            )
            results[motor_code] = result
            success = success and bool(result.get("success"))
            self._running[motor_code] = False
            self._publish_result_state(
                motor_code, 0, False, result, resolved_stop_action
            )

        if self._left in motor_codes or self._right in motor_codes:
            self._last_setpoint = (0, 0)
        if any(code in motor_codes for code in self._mecanum_codes):
            self._last_mecanum_setpoint = (0, 0, 0, 0)

        self._set_motor_fault(not success)
        response = {
            "success": success,
            "direct_hardware": True,
            "watchdog_enabled": False,
            "motors": results
        }
        if not success:
            for motor_code, result in results.items():
                if not result.get("success"):
                    response.update(self._failure(motor_code, result))
                    break
        return response

    def _publish_result_state(
            self, motor_code, speed_sp, running, result, stop_action):
        self._publish_state(
            motor_code,
            speed_sp,
            running,
            bool(result.get("success")),
            stop_action=stop_action,
            hardware_error=result.get("hardware_error")
        )

    def _publish_state(self, motor_code, speed_sp, running, success,
                       stop_action=None, hardware_error=None):
        if self._state_publisher is None:
            return

        definition = self._hardware.get_motor_definition(motor_code) or {}
        now = self._clock()
        self._state_publisher.publish_motor_state(motor_code, {
            "code": motor_code,
            "name": definition.get("name"),
            "address": definition.get("address"),
            "motor_class": definition.get("motor_class"),
            "connected": bool(success),
            "hardware_error": hardware_error,
            "command": "run_forever" if running else "stop",
            "speed_sp": int(speed_sp),
            "stop_action": (
                stop_action or self._default_stop_action
            ),
            "control_source": "local_manual",
            "success": bool(success),
            "command_state": (
                MotorLifecycleStates.DISPATCHED
                if running else MotorLifecycleStates.COMPLETED
            ),
            "motion_state": (
                MotorLifecycleStates.RUNNING
                if running else MotorLifecycleStates.STOPPED
            ),
            "direct_hardware": True,
            "watchdog_enabled": False,
            "last_command_dispatched_at": now,
            "last_success_at": now if success else None
        })

    def _set_motor_fault(self, active):
        """Publishes authoritative LOCAL + MANUAL motor health to the LED."""
        try:
            self._status_led.set_fault("motor", bool(active))
        except Exception as error:
            self._logger.error(
                "Unable to update motor status LED fault: {0}".format(error)
            )

    @staticmethod
    def _failure(motor_code, result):
        error = (
            result.get("hardware_error")
            or "Motor hardware rejected the setpoint."
        )
        return {
            "success": False,
            "failed_motor_code": motor_code,
            "error": error,
            "hardware_error": result.get("hardware_error")
        }
