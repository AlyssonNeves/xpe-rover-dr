#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Output adapter for sensor query and control operations.

Provides an implementation of the sensor query/command port interfaces
using the sensor monitor and sensor state repository.
"""

from ports.sensor_command_port import SensorCommandPort
from ports.sensor_query_port import SensorQueryPort


class SensorMonitorAdapter(SensorQueryPort, SensorCommandPort):
    """
    Adapts the sensor state repository to the sensor query/command port interfaces.

    This adapter exposes sensor query and mode management
    operations required by the application layer.
    """

    def __init__(self, sensor_monitor, state_store=None):
        """
        Initializes the sensor adapter.

        Args:
            sensor_monitor (SensorMonitor):
                Sensor monitoring service responsible for
                sensor operations.
            state_store (SensorStateStore, optional):
                Sensor state repository. If not provided,
                the repository associated with the monitor
                will be used.
        """
        self.sensor_monitor = sensor_monitor
        self.state_store = state_store or sensor_monitor.state_store

    def list_sensors(self):
        """
        Returns a summarized list of registered sensors.

        Returns:
            list:
                List containing basic information about
                each available sensor.
        """
        sensors = []

        for sensor in self.state_store.get_all_sensors():
            sensors.append({
                "code": sensor.get("code"),
                "name": sensor.get("name"),
                "address": sensor.get("address"),
                "connected": sensor.get("connected")
            })

        return sensors

    def read_sensor(self, code):
        """
        Returns the complete information of a specific sensor.

        Args:
            code (str):
                Unique sensor identifier.

        Returns:
            dict | None:
                Sensor information if found;
                otherwise None.
        """
        return self.state_store.get_sensor(code)

    def read_all_sensors(self):
        """
        Returns the complete information of all sensors.

        Returns:
            list:
                Collection containing all registered
                sensor records.
        """
        return self.state_store.get_all_sensors()

    def list_sensor_modes(self, code):
        """
        Returns the supported operating modes of a sensor.

        Args:
            code (str):
                Unique sensor identifier.

        Returns:
            list | None:
                List of supported modes if the sensor exists;
                otherwise None.
        """
        sensor = self.state_store.get_sensor(code)

        if sensor is None:
            return None

        return sensor.get("supported_modes", [])

    def change_sensor_mode(self, code, mode):
        """
        Changes the operating mode of a sensor.

        Args:
            code (str):
                Unique sensor identifier.
            mode (str):
                New operating mode to be assigned.

        Returns:
            dict | None:
                Updated sensor information, an error
                response, or None if the sensor does
                not exist.
        """
        return self.sensor_monitor.change_sensor_mode(
            code,
            mode
        )
