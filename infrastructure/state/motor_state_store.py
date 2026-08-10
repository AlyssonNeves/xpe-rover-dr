#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Stores the current Rover motor state.
"""

import threading


class MotorStateStore(object):
    """Stores motor states in a thread-safe manner."""

    def __init__(self):
        """Initializes the motor state repository."""
        # Lock used to ensure thread-safe access
        # to the motor state collection.
        self._lock = threading.Lock()

        # Dictionary containing the latest state
        # of each motor indexed by motor code.
        self._motors = {}

    def update_motor(self, motor_code, motor_data):
        """
        Updates the state of a motor.

        Args:
            motor_code (str): Unique motor identifier.
            motor_data (dict): Motor state data.
        """
        with self._lock:
            # Store a copy of the motor data to avoid
            # unintended external modifications.
            self._motors[motor_code] = dict(motor_data)

    def get_motor(self, motor_code):
        """
        Returns the state of a specific motor.

        Args:
            motor_code (str): Unique motor identifier.

        Returns:
            dict | None: Motor state if found,
            otherwise None.
        """
        with self._lock:
            motor = self._motors.get(motor_code)

            if motor is None:
                return None

            # Return a copy to preserve encapsulation
            # and prevent external modifications.
            return dict(motor)

    def get_all_motors(self):
        """
        Returns the state of all motors.

        Returns:
            list: List containing the state of all motors.
        """
        with self._lock:
            # Return copies of all motor states to
            # prevent external modification.
            return [
                dict(motor)
                for motor in self._motors.values()
            ]

    def clear(self):
        """
        Removes all stored motor states.
        """
        with self._lock:
            self._motors.clear()
