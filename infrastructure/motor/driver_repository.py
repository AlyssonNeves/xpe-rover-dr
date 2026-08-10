#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Shared EV3 motor driver repository and safe native operations."""

import threading
import time

from app.motor_lifecycle import MotorLifecycleStates


class Ev3MotorDriverRepository(object):
    """
    Manages physical EV3 motor instances and safe hardware operations.

    The registry keeps hardware access isolated from ``MotorMonitor`` so
    monitoring cycles can recover from unavailable, disconnected, or
    partially failing motor drivers without stopping the application.
    """

    READ_ATTRIBUTES = (
        "address",
        "command",
        "commands",
        "count_per_rot",
        "count_per_m",
        "driver_name",
        "max_speed",
        "duty_cycle",
        "duty_cycle_sp",
        "ramp_up_sp",
        "ramp_down_sp",
        "speed_p",
        "speed_i",
        "speed_d",
        "position_p",
        "position_i",
        "position_d",
        "polarity",
        "position",
        "position_sp",
        "speed",
        "speed_sp",
        "state",
        "stop_action",
        "stop_actions",
        "time_sp"
    )

    # LOCAL + MANUAL status screens need only these live values. Keeping this
    # list deliberately small avoids dozens of EV3 sysfs reads competing with
    # joystick motor writes on the resource-constrained brick.
    TELEMETRY_ATTRIBUTES = (
        "speed",
        "duty_cycle",
        "position",
        "state"
    )

    def __init__(
        self,
        motor_definitions,
        hardware_backend,
        retry_interval_seconds=5.0,
        max_retry_attempts=None
    ):
        """
        Initializes the physical motor registry.

        Args:
            motor_definitions (dict): Centralized motor definitions.
            hardware_backend (Ev3MotorHardwareBackend): Optional EV3
                backend used to resolve motor driver classes.
            retry_interval_seconds (float): Minimum interval between
                connection attempts for the same motor.
            max_retry_attempts (int, optional): Maximum connection
                attempts before reporting FAILED. None means unlimited.
        """
        self.motor_definitions = motor_definitions
        self.hardware_backend = hardware_backend
        self.retry_interval_seconds = retry_interval_seconds
        self.max_retry_attempts = max_retry_attempts
        self._motors = {}
        self._errors = {}
        self._retry_state = {}
        self._lock = threading.RLock()

    def _safe_get(self, motor, attribute_name, default=None):
        """
        Safely reads a motor driver attribute.
        """
        try:
            return getattr(motor, attribute_name)
        except Exception:  # pragma: no cover - depends on EV3 driver
            return default

    def _normalize_state_value(self, value):
        """
        Converts driver collections to JSON-friendly values.
        """
        if isinstance(value, tuple):
            return list(value)

        if isinstance(value, set):
            return sorted(value)

        return value

    def _get_retry_state(self, motor_code):
        """
        Returns retry metadata for a motor.
        """
        return self._retry_state.setdefault(
            motor_code,
            {
                "attempts": 0,
                "last_retry_at": None,
                "next_retry_at": None
            }
        )

    def _can_retry(self, motor_code):
        """
        Checks whether a new connection attempt is allowed.
        """
        retry_state = self._get_retry_state(motor_code)

        if self.max_retry_attempts is not None:
            if retry_state["attempts"] >= self.max_retry_attempts:
                return False

        next_retry_at = retry_state.get("next_retry_at")

        if next_retry_at is None:
            return True

        return time.time() >= next_retry_at

    def _register_retry_attempt(self, motor_code):
        """
        Updates retry metadata before a connection attempt.
        """
        retry_state = self._get_retry_state(motor_code)
        retry_state["attempts"] += 1
        retry_state["last_retry_at"] = time.time()
        retry_state["next_retry_at"] = (
            retry_state["last_retry_at"] + self.retry_interval_seconds
        )

    def _reset_retry_state(self, motor_code):
        """
        Clears retry metadata after a successful connection.
        """
        self._retry_state[motor_code] = {
            "attempts": 0,
            "last_retry_at": None,
            "next_retry_at": None
        }

    def get_retry_metadata(self, motor_code):
        """
        Returns a copy of motor retry metadata.
        """
        retry_state = self._get_retry_state(motor_code)
        return {
            "retry_attempts": retry_state.get("attempts", 0),
            "last_retry_at": retry_state.get("last_retry_at"),
            "next_retry_at": retry_state.get("next_retry_at")
        }

    def connect_motor(self, motor_code, force=False):
        """
        Attempts to instantiate a physical motor driver.

        Args:
            motor_code (str): Unique motor identifier.
            force (bool): If True, bypasses retry interval checks.

        Returns:
            object | None: Motor driver instance when successful;
            otherwise None.
        """
        with self._lock:
            motor_definition = self.motor_definitions.get(motor_code)

            if motor_definition is None:
                return None

            if not force and not self._can_retry(motor_code):
                return None

            self._register_retry_attempt(motor_code)

            try:
                motor = self.hardware_backend.create_motor(motor_definition)
                self._motors[motor_code] = motor
                self._errors[motor_code] = None
                self._reset_retry_state(motor_code)
                return motor
            except Exception as error:  # pragma: no cover - hardware dependent
                self._motors.pop(motor_code, None)
                self._errors[motor_code] = str(error)
                return None

    def get_motor_max_speed(self, motor_code):
        """
        Returns the maximum speed reported by the connected EV3 driver.

        The value is read from ``motor.max_speed`` and therefore reflects
        the motor type detected by ev3dev2 instead of a duplicated fixed
        constant in the Rover configuration.
        """
        motor = self._motors.get(motor_code)

        if motor is None:
            motor = self.connect_motor(motor_code)

        if motor is None:
            return None

        max_speed = self._safe_get(motor, "max_speed")

        try:
            return abs(int(max_speed))
        except (TypeError, ValueError):
            return None

    def disconnect_motor(self, motor_code):
        """
        Removes a cached motor driver instance.
        """
        with self._lock:
            self._motors.pop(motor_code, None)

    def get_connected_motor(self, motor_code):
        """Returns a cached driver without triggering a connection attempt."""
        with self._lock:
            return self._motors.get(motor_code)

    def get_motor_error(self, motor_code):
        """
        Returns the latest hardware error for a motor.
        """
        return self._errors.get(motor_code)

    def _build_disconnected_snapshot(self, motor_code, motor_definition):
        """
        Builds a disconnected motor snapshot with retry metadata.
        """
        retry_metadata = self.get_retry_metadata(motor_code)
        lifecycle_state = MotorLifecycleStates.DISCONNECTED

        if self.max_retry_attempts is not None:
            if retry_metadata["retry_attempts"] >= self.max_retry_attempts:
                lifecycle_state = MotorLifecycleStates.FAILED
            elif retry_metadata["next_retry_at"] is not None:
                lifecycle_state = MotorLifecycleStates.RETRYING

        snapshot = {
            "code": motor_code,
            "name": motor_definition["name"],
            "address": motor_definition["address"],
            "motor_class": motor_definition.get("motor_class"),
            "connected": False,
            "hardware_error": self.get_motor_error(motor_code),
            "lifecycle_state": lifecycle_state
        }
        snapshot.update(retry_metadata)
        return snapshot

    def read_motor(self, motor_code):
        """
        Reads the current state of a physical motor.
        """
        motor_definition = self.motor_definitions.get(motor_code)

        if motor_definition is None:
            return None

        motor = self._motors.get(motor_code)

        if motor is None:
            motor = self.connect_motor(motor_code)

        if motor is None:
            return self._build_disconnected_snapshot(
                motor_code,
                motor_definition
            )

        snapshot = {
            "code": motor_code,
            "name": motor_definition["name"],
            "address": motor_definition["address"],
            "motor_class": motor_definition.get("motor_class"),
            "connected": True,
            "hardware_error": None,
            "lifecycle_state": MotorLifecycleStates.CONNECTED
        }

        try:
            for attribute_name in self.READ_ATTRIBUTES:
                snapshot[attribute_name] = self._normalize_state_value(
                    self._safe_get(motor, attribute_name)
                )

            self._errors[motor_code] = None
            snapshot.update(self.get_retry_metadata(motor_code))
        except Exception as error:  # pragma: no cover - defensive guard
            self.disconnect_motor(motor_code)
            self._errors[motor_code] = str(error)
            snapshot["connected"] = False
            snapshot["hardware_error"] = str(error)
            snapshot["lifecycle_state"] = MotorLifecycleStates.DISCONNECTED
            snapshot.update(self.get_retry_metadata(motor_code))

        return snapshot

    def read_motor_telemetry(self, motor_code):
        """Reads lightweight live telemetry for manual status screens.

        This path intentionally never reconnects a missing motor. Status
        presentation is informational and must not introduce connection work or
        broad sysfs polling into the latency-sensitive LOCAL + MANUAL runtime.
        """
        motor_definition = self.motor_definitions.get(motor_code)
        if motor_definition is None:
            return None

        motor = self.get_connected_motor(motor_code)
        if motor is None:
            return self._build_disconnected_snapshot(
                motor_code, motor_definition
            )

        snapshot = {
            "code": motor_code,
            "name": motor_definition["name"],
            "address": motor_definition["address"],
            "motor_class": motor_definition.get("motor_class"),
            "connected": True,
            "hardware_error": None,
            "lifecycle_state": MotorLifecycleStates.CONNECTED
        }
        for attribute_name in self.TELEMETRY_ATTRIBUTES:
            snapshot[attribute_name] = self._normalize_state_value(
                self._safe_get(motor, attribute_name)
            )
        return snapshot


    def ensure_connected_motor(self, motor_code):
        """Returns a cached motor driver or connects it immediately."""
        with self._lock:
            motor = self._motors.get(motor_code)
            if motor is not None:
                return motor
            return self.connect_motor(motor_code, force=True)

    def _get_or_connect_motor(self, motor_code):
        """
        Retrieves or connects a physical motor driver instance.
        """
        return self.ensure_connected_motor(motor_code)

    def _execute_with_motor(self, motor_code, callback):
        """
        Executes a callback against a connected motor.
        """
        motor = self._get_or_connect_motor(motor_code)

        if motor is None:
            return {
                "success": False,
                "hardware_error": self.get_motor_error(motor_code)
            }

        try:
            callback(motor)
            self._errors[motor_code] = None
            return {
                "success": True,
                "hardware_error": None
            }
        except Exception as error:  # pragma: no cover - hardware dependent
            self.disconnect_motor(motor_code)
            self._errors[motor_code] = str(error)
            return {
                "success": False,
                "hardware_error": str(error)
            }

    def execute_stop(self, motor_code, stop_action="brake"):
        """
        Executes a physical stop command on a motor.
        """
        return self._execute_with_motor(
            motor_code,
            lambda motor: motor.stop(stop_action=stop_action)
        )


    def execute_run_timed(self, motor_code, speed_sp, time_sp):
        """
        Executes a physical timed run command on a motor.
        """
        return self._execute_with_motor(
            motor_code,
            lambda motor: motor.run_timed(
                speed_sp=speed_sp,
                time_sp=time_sp
            )
        )

    def execute_run_forever(self, motor_code, speed_sp):
        """Executes a physical regulated continuous command."""
        return self._execute_with_motor(
            motor_code, lambda motor: motor.run_forever(speed_sp=speed_sp)
        )


    def execute_run_direct(self, motor_code, duty_cycle_sp):
        """Executes a physical unregulated direct duty-cycle command."""
        return self._execute_with_motor(
            motor_code, lambda motor: motor.run_direct(duty_cycle_sp=duty_cycle_sp)
        )

    def execute_run_to_rel_pos(self, motor_code, speed_sp, position_sp):
        """
        Executes a physical relative-position command on a motor.
        """
        return self._execute_with_motor(
            motor_code,
            lambda motor: motor.run_to_rel_pos(
                speed_sp=speed_sp,
                position_sp=position_sp
            )
        )

    def execute_run_to_abs_pos(self, motor_code, speed_sp, position_sp):
        """Executes a physical absolute-position command on a motor."""
        return self._execute_with_motor(
            motor_code,
            lambda motor: motor.run_to_abs_pos(
                speed_sp=speed_sp,
                position_sp=position_sp
            )
        )

    def execute_reset(self, motor_code):
        """
        Executes a physical reset command on a motor.
        """
        return self._execute_with_motor(
            motor_code,
            lambda motor: motor.reset()
        )

    def configure_motion(self, motor_code, stop_action="brake", ramp_up_sp=0, ramp_down_sp=0):
        """Configures native EV3 stop and acceleration parameters."""

        # Applies the validated motion settings directly to the connected
        # EV3 motor instance through the registry callback mechanism.
        def configure(motor):
            # Reads the stop actions supported by the active motor driver.
            available = self._safe_get(motor, "stop_actions", ()) or ()

            # Rejects unsupported stop behavior before changing the motor.
            if stop_action and available and stop_action not in available:
                raise ValueError("Unsupported stop_action: {0}".format(stop_action))
            # Updates the native stop action when one was requested.
            if stop_action:
                motor.stop_action = stop_action

            # Configures acceleration time only when supported by the driver.
            if hasattr(motor, "ramp_up_sp"):
                motor.ramp_up_sp = max(0, int(ramp_up_sp or 0))
            # Configures deceleration time only when supported by the driver.
            if hasattr(motor, "ramp_down_sp"):
                motor.ramp_down_sp = max(0, int(ramp_down_sp or 0))

        # Reuses the registry's protected execution and error handling flow.
        return self._execute_with_motor(motor_code, configure)

    def stop_all_motors(self, stop_action="brake"):
        """Stops every configured physical motor independently."""
        results = {}

        # Attempts to stop each motor independently so one failure does not
        # prevent the remaining configured motors from receiving the command.
        for motor_code in self.motor_definitions:
            results[motor_code] = self.execute_stop(motor_code, stop_action)
        return results

    def read_all_motors(self):
        """
        Reads all configured physical motors.
        """
        return [
            self.read_motor(motor_code)
            for motor_code in self.motor_definitions
        ]

