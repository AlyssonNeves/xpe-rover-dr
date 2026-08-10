#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Thread-safe repository for Rover-DR controller state sections."""

import copy
import threading


class ControllerStateStore(object):
    """Stores controller, network, battery and system snapshots."""

    def __init__(self):
        self._lock = threading.Lock()
        self._controller_status = {}
        self._network_status = {}
        self._battery_status = {}
        self._system_status = {}

    def update_controller_status(self, value):
        with self._lock:
            self._controller_status = copy.deepcopy(value)

    def get_controller_status(self):
        with self._lock:
            return copy.deepcopy(self._controller_status)

    def update_network_status(self, value):
        with self._lock:
            self._network_status = copy.deepcopy(value)

    def get_network_status(self):
        with self._lock:
            return copy.deepcopy(self._network_status)

    def update_battery_status(self, value):
        with self._lock:
            self._battery_status = copy.deepcopy(value)

    def get_battery_status(self):
        with self._lock:
            return copy.deepcopy(self._battery_status)

    def update_system_status(self, value):
        with self._lock:
            self._system_status = copy.deepcopy(value)

    def get_system_status(self):
        with self._lock:
            return copy.deepcopy(self._system_status)

    def clear(self):
        """Removes every controller-related state section."""
        with self._lock:
            self._controller_status.clear()
            self._network_status.clear()
            self._battery_status.clear()
            self._system_status.clear()
