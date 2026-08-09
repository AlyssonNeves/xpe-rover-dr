#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Initial sensor monitoring service for Rover-DR."""

import copy
import threading

from services.monitor_base import MonitorBase


class SensorMonitor(MonitorBase):
    """Maintains an in-memory snapshot of the configured Rover sensors."""

    def __init__(self, interval_seconds=1.0):
        MonitorBase.__init__(self, "SensorMonitor", interval_seconds)
        self._lock = threading.Lock()
        self._sensors = {
            "TMP": {
                "code": "TMP",
                "name": "Temperature",
                "address": "in1:i2c76",
                "mode": "NXT-TEMP-C",
                "unit": "C",
                "value": None,
                "connected": False,
                "source": "simulated"
            },
            "GYR": {
                "code": "GYR",
                "name": "Gyroscope",
                "address": "in3",
                "mode": "GYRO-ANG",
                "unit": "deg",
                "value": None,
                "connected": False,
                "source": "simulated"
            },
            "RCS": {
                "code": "RCS",
                "name": "Right Color Sensor",
                "address": "in2:i2c80:mux1",
                "mode": "COL-REFLECT",
                "unit": "%",
                "value": None,
                "connected": False,
                "source": "simulated"
            },
            "LCS": {
                "code": "LCS",
                "name": "Left Color Sensor",
                "address": "in2:i2c81:mux2",
                "mode": "COL-REFLECT",
                "unit": "%",
                "value": None,
                "connected": False,
                "source": "simulated"
            },
            "TCH": {
                "code": "TCH",
                "name": "Touch Sensor",
                "address": "in2:i2c82:mux3",
                "mode": "TOUCH",
                "unit": "pressed",
                "value": None,
                "connected": False,
                "source": "simulated"
            }
        }

    def on_cycle(self):
        """Refreshes the sensor snapshot.

        Hardware access is intentionally deferred to later increments.
        """
        return None

    def list_sensors(self):
        """Returns summarized information for all sensors."""
        return [
            {
                "code": item["code"],
                "name": item["name"],
                "address": item["address"],
                "connected": item["connected"]
            }
            for item in self.read_all_sensors()
        ]

    def read_sensor(self, code):
        """Returns one sensor snapshot or None when it is unknown."""
        with self._lock:
            sensor = self._sensors.get(code)
            return copy.deepcopy(sensor) if sensor is not None else None

    def read_all_sensors(self):
        """Returns snapshots of all known sensors."""
        with self._lock:
            return copy.deepcopy(list(self._sensors.values()))
