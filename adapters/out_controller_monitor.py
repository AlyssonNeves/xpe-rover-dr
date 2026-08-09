#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output adapter exposing controller state through ControllerPort."""

from ports.controller_port import ControllerPort


class ControllerMonitorAdapter(ControllerPort):
    """Exposes the controller repository through the application output port."""

    def __init__(self, controller_monitor, state_store=None):
        self.controller_monitor = controller_monitor
        self.state_store = state_store or controller_monitor.state_store

    def read_controller_status(self):
        return self.state_store.get_controller_status()

    def read_network_status(self):
        return self.state_store.get_network_status()

    def read_battery_status(self):
        return self.state_store.get_battery_status()

    def read_system_status(self):
        return self.state_store.get_system_status()
