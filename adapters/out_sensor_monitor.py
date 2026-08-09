#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output adapter exposing sensor monitor queries through SensorPort."""

from ports.sensor_port import SensorPort


class SensorMonitorAdapter(SensorPort):
    """Adapts SensorMonitor to the sensor output-port contract."""

    def __init__(self, sensor_monitor):
        self.sensor_monitor = sensor_monitor

    def list_sensors(self):
        return self.sensor_monitor.list_sensors()

    def read_sensor(self, code):
        return self.sensor_monitor.read_sensor(code)

    def read_all_sensors(self):
        return self.sensor_monitor.read_all_sensors()
