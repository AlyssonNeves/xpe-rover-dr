#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Configured Rover sensor state monitor.

This module provides a configuration-backed sensor state implementation
for simulation, development, and integration testing.
"""

from app.rover_config import DEFAULT_CONFIGURATION
from infrastructure.monitoring.monitor_base import MonitorBase
from infrastructure.state.sensor_state_store import SensorStateStore


class SensorMonitor(MonitorBase):
    """
    Represents a configuration-backed sensor monitoring service.

    Loads sensor definitions from the application configuration
    and maintains sensor state information in the sensor repository.
    """

    def __init__(self, state_store=None, interval_seconds=1.0,
                 sensor_definitions=None):
        """
        Initializes the sensor monitor.

        Args:
            state_store (SensorStateStore, optional):
                Sensor state repository. If not provided,
                a new instance will be created.
            interval_seconds (float):
                Monitoring cycle interval in seconds.
        """
        MonitorBase.__init__(
            self,
            name="SensorMonitor",
            interval_seconds=interval_seconds
        )

        self.state_store = state_store or SensorStateStore()
        self.sensor_definitions = (
            sensor_definitions or DEFAULT_CONFIGURATION.sensor_definitions
        )

        # Populate the state repository with the initial sensor registry
        # defined in the application configuration.
        self._load_initial_sensors()

    def _load_initial_sensors(self):
        """
        Loads the configured sensor registry into the state store.

        Sensor definitions are converted into the internal data structure
        used by the monitoring subsystem and persisted in the repository.
        """
        for sensor_code, sensor_definition in self.sensor_definitions.items():
            sensor_data = {
                "code": sensor_code,
                "name": sensor_definition.get("name"),
                "address": sensor_definition.get("address"),
                "mode": sensor_definition.get("mode"),
                "unit": sensor_definition.get("unit"),
                "supported_modes": list(sensor_definition.get(
                    "supported_modes",
                    []
                )),
                "value": sensor_definition.get("value", 0),
                "connected": sensor_definition.get("connected", True)
            }

            self.state_store.update_sensor(sensor_code, sensor_data)

    def on_cycle(self):
        """
        Executes a monitoring cycle.

        This simulated implementation does not interact with
        physical hardware and preserves the current sensor state.

        Returns:
            None
        """
        return None

    def change_sensor_mode(self, sensor_code, sensor_mode):
        """
        Changes the operating mode of a simulated sensor.

        Args:
            sensor_code (str):
                Unique sensor identifier.
            sensor_mode (str):
                Target operating mode.

        Returns:
            dict | None:
                Updated sensor information when the operation succeeds,
                an error dictionary when the requested mode is not
                supported, or None when the sensor does not exist.
        """
        sensor = self.state_store.get_sensor(sensor_code)

        if sensor is None:
            return None

        supported_modes = sensor.get("supported_modes", [])

        # Validate the requested mode against the sensor capabilities
        # defined during initialization.
        if sensor_mode not in supported_modes:
            return {
                "success": False,
                "error": "Unsupported mode for the sensor.",
                "sensor": sensor
            }

        # Persist the mode update through the state repository to keep a
        # single source of truth for sensor state information.
        sensor["mode"] = sensor_mode

        self.state_store.update_sensor(sensor_code, sensor)

        return sensor
