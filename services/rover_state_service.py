#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Service that builds a consolidated Rover-DR state snapshot."""

from datetime import datetime


class RoverStateService(object):
    """Aggregates the snapshots already maintained by monitoring services."""

    def __init__(self, sensor_port, motor_port, controller_port):
        self.sensor_port = sensor_port
        self.motor_port = motor_port
        self.controller_port = controller_port

    def get_rover_state(self):
        """Returns the current state without introducing a separate repository."""
        return {
            "controller": self.controller_port.read_controller_status(),
            "network": self.controller_port.read_network_status(),
            "battery": self.controller_port.read_battery_status(),
            "system": self.controller_port.read_system_status(),
            "sensors": self.sensor_port.read_all_sensors(),
            "motors": self.motor_port.read_all_motors(),
            "timestamp": datetime.now().strftime("%d/%m/%y %H:%M:%S.%f")[:-3]
        }
