#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Stores the current Rover sensor state.
"""

import threading


class SensorStateStore(object):
    """Stores sensor readings and states in a thread-safe manner."""

    def __init__(self):
        """Initializes the sensor state repository."""
        # Lock used to ensure thread-safe access
        # to the sensor state collection.
        self._lock = threading.Lock()

        # Dictionary containing the latest state
        # of each sensor indexed by sensor code.
        self._sensors = {}

    def update_sensor(self, sensor_code, sensor_data):
        """
        Updates the state of a sensor.

        Args:
            sensor_code (str): Unique sensor identifier.
            sensor_data (dict): Sensor state data.
        """
        with self._lock:
            # Store a copy of the sensor data to avoid
            # unintended external modifications.
            self._sensors[sensor_code] = dict(sensor_data)

    def get_sensor(self, sensor_code):
        """
        Returns the state of a specific sensor.

        Args:
            sensor_code (str): Unique sensor identifier.

        Returns:
            dict | None: Sensor state if found,
            otherwise None.
        """
        with self._lock:
            sensor = self._sensors.get(sensor_code)

            if sensor is None:
                return None

            # Return a copy to preserve encapsulation
            # and prevent external modifications.
            return dict(sensor)

    def get_all_sensors(self):
        """
        Returns the state of all sensors.

        Returns:
            list: List containing the state of all sensors.
        """
        with self._lock:
            # Return copies of all sensor states to
            # prevent external modification.
            return [
                dict(sensor)
                for sensor in self._sensors.values()
            ]

    def clear(self):
        """
        Removes all stored sensor states.
        """
        with self._lock:
            self._sensors.clear()
