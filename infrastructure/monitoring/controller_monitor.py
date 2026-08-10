#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Simulated controller information monitor.

This implementation returns simulated data to support the
development and testing without depending on physical controller telemetry.
"""

from infrastructure.state.controller_state_store import ControllerStateStore
from infrastructure.monitoring.monitor_base import MonitorBase


class ControllerMonitor(MonitorBase):
    """
    Publishes simulated controller information.

    Provides simulated controller, network, battery,
    and system information for development and testing.
    """

    def __init__(self, state_store=None, interval_seconds=1.0):
        """
        Initializes the simulated controller monitor.

        Args:
            state_store (ControllerStateStore, optional):
                Controller state repository. If not provided,
                a new instance will be created.
            interval_seconds (float):
                Monitoring cycle interval in seconds.
        """
        MonitorBase.__init__(
            self,
            name="ControllerMonitor",
            interval_seconds=interval_seconds
        )

        self.state_store = state_store or ControllerStateStore()

        # Publish the initial controller state.
        self._publish_controller_state()

    def _publish_controller_state(self):
        """
        Publishes the simulated controller state
        to the state repository.
        """
        self.state_store.update_controller_status(
            self._build_controller_status()
        )

        self.state_store.update_network_status(
            self._build_network_status()
        )

        self.state_store.update_battery_status(
            self._build_battery_status()
        )

        self.state_store.update_system_status(
            self._build_system_status()
        )

    def _build_controller_status(self):
        """
        Builds the simulated controller status.

        Returns:
            dict:
                Simulated controller information.
        """
        return {
            "controller": "Rover Controller",
            "status": "available",
            "connected": True,
            "mode": "simulated"
        }

    def _build_network_status(self):
        """
        Builds the simulated network status.

        Returns:
            dict:
                Simulated network information.
        """
        return {
            "hostname": "rover-controller",
            "ip_address": "0.0.0.0",
            "mac_address": "00:00:00:00:00:00",
            "connected": False,
            "mode": "simulated"
        }

    def _build_battery_status(self):
        """
        Builds the simulated battery status.

        Returns:
            dict:
                Simulated battery information.
        """
        return {
            "voltage": None,
            "current": None,
            "percentage": None,
            "status": "unknown",
            "mode": "simulated"
        }

    def _build_system_status(self):
        """
        Builds the simulated system status.

        Returns:
            dict:
                Simulated system information.
        """
        return {
            "cpu_usage": None,
            "memory_usage": None,
            "disk_usage": None,
            "uptime": None,
            "mode": "simulated"
        }

    def on_cycle(self):
        """
        Executes a controller monitoring cycle.

        Refreshes the simulated controller information
        stored in the state repository.

        Returns:
            None
        """
        self._publish_controller_state()
