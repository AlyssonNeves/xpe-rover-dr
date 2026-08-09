#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Thread-safe repository for the current Rover-DR motor state."""

import copy
import threading


class MotorStateStore(object):
    """Stores the latest state of each known motor."""

    def __init__(self):
        self._lock = threading.Lock()
        self._motors = {}

    def update_motor(self, motor_code, motor_data):
        """Creates or replaces the current state of one motor."""
        with self._lock:
            self._motors[motor_code] = copy.deepcopy(motor_data)

    def get_motor(self, motor_code):
        """Returns one motor snapshot or None when it is unknown."""
        with self._lock:
            motor = self._motors.get(motor_code)
            return copy.deepcopy(motor) if motor is not None else None

    def get_all_motors(self):
        """Returns snapshots of all motors."""
        with self._lock:
            return copy.deepcopy(list(self._motors.values()))

    def clear(self):
        """Removes all stored motor states."""
        with self._lock:
            self._motors.clear()
