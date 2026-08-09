#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output port for querying Rover-DR controller information."""

from abc import ABCMeta, abstractmethod


class ControllerPort(object, metaclass=ABCMeta):
    """Defines controller monitoring query operations."""

    @abstractmethod
    def read_controller_status(self):
        """Returns general controller status."""
        raise NotImplementedError

    @abstractmethod
    def read_network_status(self):
        """Returns controller network information."""
        raise NotImplementedError

    @abstractmethod
    def read_battery_status(self):
        """Returns controller battery information."""
        raise NotImplementedError

    @abstractmethod
    def read_system_status(self):
        """Returns controller system information."""
        raise NotImplementedError
