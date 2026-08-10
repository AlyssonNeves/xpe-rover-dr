#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Raw output port for one physical heading sensor."""

from abc import ABCMeta, abstractmethod


class HeadingSensorPort(object, metaclass=ABCMeta):
    """Defines the hardware operations required by heading monitoring."""

    @abstractmethod
    def open(self):
        """Connects to and configures the physical heading sensor."""
        raise NotImplementedError

    @abstractmethod
    def read_heading_deg(self):
        """Returns the current accumulated heading in degrees."""
        raise NotImplementedError

    @abstractmethod
    def close(self):
        """Releases references owned by the hardware adapter."""
        raise NotImplementedError
