#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output adapter exposing sensor state through SensorPort."""

from ports.sensor_port import SensorPort


class SensorMonitorAdapter(SensorPort):
    """Exposes the sensor repository through the application output port."""

    def __init__(self, sensor_monitor, state_store=None):
        self.sensor_monitor = sensor_monitor
        self.state_store = state_store or sensor_monitor.state_store

    def list_sensors(self):
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
        return self.state_store.get_sensor(code)

    def read_all_sensors(self):
        return self.state_store.get_all_sensors()
