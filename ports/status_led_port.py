#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output port for Rover operational status LED indication."""

from abc import ABCMeta, abstractmethod


class StatusLedPort(object, metaclass=ABCMeta):
    """Defines fault-driven status LED updates."""

    @abstractmethod
    def set_fault(self, source, active=True):
        """Activates or clears one named operational fault source."""
        raise NotImplementedError

    def clear_faults(self, *sources):
        """Clears multiple related faults; adapters may override atomically."""
        for source in sources:
            self.set_fault(source, False)
