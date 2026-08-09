#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Initial controller monitoring service for Rover-DR."""

import copy
import platform
import socket
import threading

from services.monitor_base import MonitorBase


class ControllerMonitor(MonitorBase):
    """Maintains basic controller, network, battery, and system snapshots."""

    def __init__(self, interval_seconds=1.0):
        MonitorBase.__init__(self, "ControllerMonitor", interval_seconds)
        self._lock = threading.Lock()
        self._controller_status = {}
        self._network_status = {}
        self._battery_status = {}
        self._system_status = {}
        self._refresh()

    def _refresh(self):
        hostname = socket.gethostname()
        with self._lock:
            self._controller_status = {
                "controller": "Rover Controller",
                "status": "available",
                "connected": True,
                "mode": "local"
            }
            self._network_status = {
                "hostname": hostname,
                "ip_address": self._resolve_ip(hostname),
                "connected": True
            }
            self._battery_status = {
                "voltage": None,
                "current": None,
                "percentage": None,
                "status": "not_available"
            }
            self._system_status = {
                "platform": platform.system(),
                "release": platform.release(),
                "python_version": platform.python_version()
            }

    @staticmethod
    def _resolve_ip(hostname):
        try:
            return socket.gethostbyname(hostname)
        except socket.error:
            return "0.0.0.0"

    def on_cycle(self):
        """Refreshes controller information."""
        self._refresh()

    def read_controller_status(self):
        with self._lock:
            return copy.deepcopy(self._controller_status)

    def read_network_status(self):
        with self._lock:
            return copy.deepcopy(self._network_status)

    def read_battery_status(self):
        with self._lock:
            return copy.deepcopy(self._battery_status)

    def read_system_status(self):
        with self._lock:
            return copy.deepcopy(self._system_status)
