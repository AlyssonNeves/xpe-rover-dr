#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output adapter exposing controller monitor queries through ControllerPort."""

from ports.controller_port import ControllerPort


class ControllerMonitorAdapter(ControllerPort):
    """Adapts ControllerMonitor to the controller output-port contract."""

    def __init__(self, controller_monitor):
        self.controller_monitor = controller_monitor

    def read_controller_status(self):
        return self.controller_monitor.read_controller_status()

    def read_network_status(self):
        return self.controller_monitor.read_network_status()

    def read_battery_status(self):
        return self.controller_monitor.read_battery_status()

    def read_system_status(self):
        return self.controller_monitor.read_system_status()
