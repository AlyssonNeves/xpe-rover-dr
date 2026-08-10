#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Output port for querying controller information.

Defines the contract that any controller adapter must follow,
regardless of whether the data source is simulated, local,
a real EV3, the operating system, the network,
or another physical device.
"""


from abc import ABCMeta, abstractmethod


class ControllerPort(object, metaclass=ABCMeta):
    """Defines controller state query operations."""

    @abstractmethod
    def read_controller_status(self):
        """
        Queries the general controller status.

        Returns:
            dict:
                General controller status information.
        """
        raise NotImplementedError

    @abstractmethod
    def read_network_status(self):
        """
        Queries controller network information.

        Returns:
            dict:
                Network-related information.
        """
        raise NotImplementedError

    @abstractmethod
    def read_battery_status(self):
        """
        Queries controller battery information.

        Returns:
            dict:
                Battery-related information.
        """
        raise NotImplementedError

    @abstractmethod
    def read_system_status(self):
        """
        Queries controller system information.

        Returns:
            dict:
                System-related information.
        """
        raise NotImplementedError
