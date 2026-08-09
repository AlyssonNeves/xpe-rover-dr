#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Sensor monitoring service for Rover-DR."""

from app.rover_config import MONITOR_INTERVAL_SECONDS, get_sensor_definitions
from services.monitor_base import MonitorBase
from services.sensor_state_store import SensorStateStore


class SensorMonitor(MonitorBase):
    """Publishes the configured sensor registry to a dedicated state store."""

    def __init__(self, state_store=None, interval_seconds=None):
        interval = (
            MONITOR_INTERVAL_SECONDS
            if interval_seconds is None
            else interval_seconds
        )
        MonitorBase.__init__(self, "SensorMonitor", interval)
        self.state_store = state_store or SensorStateStore()
        self._load_configured_sensors()

    def _load_configured_sensors(self):
        for code, definition in get_sensor_definitions().items():
            sensor = dict(definition)
            sensor.update({
                "code": code,
                "value": None,
                "connected": False,
                "source": "simulated"
            })
            self.state_store.update_sensor(code, sensor)

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
            for item in self.state_store.get_all_sensors()
        ]

    def read_sensor(self, code):
        """Returns one sensor snapshot or None when it is unknown."""
        return self.state_store.get_sensor(code)

    def read_all_sensors(self):
        """Returns snapshots of all known sensors."""
        return self.state_store.get_all_sensors()
