#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Outbound adapter for controller information.

This adapter connects the application layer to the controller
monitor state store implementation.
"""

from ports.controller_port import ControllerPort


class ControllerMonitorAdapter(ControllerPort):
    """
    Adapts the controller state store to the ControllerPort interface.

    This class acts as an outbound adapter in the hexagonal architecture,
    allowing the application layer to access controller information
    without depending directly on concrete monitoring implementations.
    """

    def __init__(self, controller_monitor, state_store=None):
        """
        Initializes the controller adapter.

        Args:
            controller_monitor:
                Concrete controller monitor instance.

            state_store (optional):
                External state store instance. If not provided,
                the adapter uses the monitor internal state store.
        """
        self.controller_monitor = controller_monitor
        self.state_store = state_store or controller_monitor.state_store

    def read_controller_status(self):
        """
        Reads the general controller status.

        Returns:
            dict:
                General controller status information.
        """
        return self.state_store.get_controller_status()

    def read_network_status(self):
        """
        Reads controller network information.

        Returns:
            dict:
                Network status information.
        """
        return self.state_store.get_network_status()

    def read_battery_status(self):
        """
        Reads controller battery information.

        Returns:
            dict:
                Battery status information.
        """
        return self.state_store.get_battery_status()

    def read_system_status(self):
        """
        Reads controller system information.

        Returns:
            dict:
                System status information.
        """
        return self.state_store.get_system_status()
