#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Low-level output port for direct EV3 motor hardware operations."""

from abc import ABCMeta, abstractmethod


class MotorHardwarePort(object, metaclass=ABCMeta):
    """Defines the hardware primitives required by manual motor control."""

    @abstractmethod
    def get_motor_definition(self, motor_code):
        """Returns configuration metadata for one motor code."""
        raise NotImplementedError

    @abstractmethod
    def ensure_connected(self, motor_code):
        """Returns a connected motor handle or None when unavailable."""
        raise NotImplementedError

    @abstractmethod
    def get_error(self, motor_code):
        """Returns the latest hardware error for one motor code."""
        raise NotImplementedError

    @abstractmethod
    def read_motor_state(self, motor_code):
        """Returns the current physical telemetry snapshot for one motor."""
        raise NotImplementedError

    @abstractmethod
    def run_forever(self, motor_code, speed_sp):
        """Runs one motor continuously at the supplied regulated speed."""
        raise NotImplementedError

    @abstractmethod
    def stop(self, motor_code, stop_action=None, connected_only=False):
        """Stops one motor synchronously."""
        raise NotImplementedError
