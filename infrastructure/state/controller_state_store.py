#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Stores the current Rover controller state.
"""

import threading


class ControllerStateStore(object):
    """
    Stores controller states in a thread-safe way.

    This class acts as an in-memory repository responsible for
    maintaining the latest controller-related information shared
    between monitors, adapters, and application services.
    """

    def __init__(self):
        """
        Initializes the controller state repository.

        A thread lock is used to guarantee safe concurrent access
        between multiple monitoring and API threads.
        """
        self._lock = threading.Lock()

        #
        # Internal controller state sections.
        #
        self._controller_status = {}
        self._network_status = {}
        self._battery_status = {}
        self._system_status = {}

    def update_controller_status(self, controller_status):
        """
        Updates the general controller status.

        Args:
            controller_status (dict):
                Controller status information.
        """
        with self._lock:
            self._controller_status = dict(controller_status)

    def get_controller_status(self):
        """
        Returns the general controller status.

        Returns:
            dict:
                Current controller status.
        """
        with self._lock:
            return dict(self._controller_status)

    def update_network_status(self, network_status):
        """
        Updates the controller network status.

        Args:
            network_status (dict):
                Network status information.
        """
        with self._lock:
            self._network_status = dict(network_status)

    def get_network_status(self):
        """
        Returns the controller network status.

        Returns:
            dict:
                Current network status.
        """
        with self._lock:
            return dict(self._network_status)

    def update_battery_status(self, battery_status):
        """
        Updates the controller battery status.

        Args:
            battery_status (dict):
                Battery status information.
        """
        with self._lock:
            self._battery_status = dict(battery_status)

    def get_battery_status(self):
        """
        Returns the controller battery status.

        Returns:
            dict:
                Current battery status.
        """
        with self._lock:
            return dict(self._battery_status)

    def update_system_status(self, system_status):
        """
        Updates the controller system status.

        Args:
            system_status (dict):
                System status information.
        """
        with self._lock:
            self._system_status = dict(system_status)

    def get_system_status(self):
        """
        Returns the controller system status.

        Returns:
            dict:
                Current system status.
        """
        with self._lock:
            return dict(self._system_status)

    def clear(self):
        """
        Removes all stored controller states.

        This method clears every controller-related section
        from the repository.
        """
        with self._lock:
            self._controller_status.clear()
            self._network_status.clear()
            self._battery_status.clear()
            self._system_status.clear()
