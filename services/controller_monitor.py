#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Initial controller monitoring service for Rover-DR."""

import platform
import socket

from app.rover_config import MONITOR_INTERVAL_SECONDS
from services.controller_state_store import ControllerStateStore
from services.monitor_base import MonitorBase


class ControllerMonitor(MonitorBase):
    """Publishes controller, network, battery and system snapshots."""

    def __init__(self, state_store=None, interval_seconds=None):
        interval = (
            MONITOR_INTERVAL_SECONDS
            if interval_seconds is None
            else interval_seconds
        )
        MonitorBase.__init__(self, "ControllerMonitor", interval)
        self.state_store = state_store or ControllerStateStore()
        self._refresh()

    def _refresh(self):
        hostname = socket.gethostname()

        self.state_store.update_controller_status({
            "controller": "Rover Controller",
            "status": "available",
            "connected": True,
            "mode": "local"
        })
        self.state_store.update_network_status({
            "hostname": hostname,
            "ip_address": self._resolve_ip(hostname),
            "connected": True
        })
        self.state_store.update_battery_status({
            "voltage": None,
            "current": None,
            "percentage": None,
            "status": "not_available"
        })
        self.state_store.update_system_status({
            "platform": platform.system(),
            "release": platform.release(),
            "python_version": platform.python_version()
        })

    @staticmethod
    def _resolve_ip(hostname):
        try:
            return socket.gethostbyname(hostname)
        except socket.error:
            return "0.0.0.0"

    def on_cycle(self):
        """Refreshes controller information in the repository."""
        self._refresh()

    def read_controller_status(self):
        return self.state_store.get_controller_status()

    def read_network_status(self):
        return self.state_store.get_network_status()

    def read_battery_status(self):
        return self.state_store.get_battery_status()

    def read_system_status(self):
        return self.state_store.get_system_status()
