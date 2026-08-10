#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Thread-safe repository for the current Rover-DR sensor state."""

import copy
import threading


class SensorStateStore(object):
    """Stores the latest state of each known sensor."""

    def __init__(self):
        self._lock = threading.Lock()
        self._sensors = {}

    def update_sensor(self, sensor_code, sensor_data):
        """Creates or replaces the current state of one sensor."""
        with self._lock:
            self._sensors[sensor_code] = copy.deepcopy(sensor_data)

    def get_sensor(self, sensor_code):
        """Returns one sensor snapshot or None when it is unknown."""
        with self._lock:
            sensor = self._sensors.get(sensor_code)
            return copy.deepcopy(sensor) if sensor is not None else None

    def get_all_sensors(self):
        """Returns snapshots of all sensors."""
        with self._lock:
            return copy.deepcopy(list(self._sensors.values()))

    def clear(self):
        """Removes all stored sensor states."""
        with self._lock:
            self._sensors.clear()
