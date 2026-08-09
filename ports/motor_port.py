#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output port for querying Rover-DR motor information."""

from abc import ABCMeta, abstractmethod


class MotorPort(object, metaclass=ABCMeta):
    """Defines motor state query operations."""

    @abstractmethod
    def list_motors(self):
        """Returns a summarized list of known motors."""
        raise NotImplementedError

    @abstractmethod
    def read_motor(self, motor_code):
        """Returns the current state of one motor."""
        raise NotImplementedError

    @abstractmethod
    def read_all_motors(self):
        """Returns the current state of all motors."""
        raise NotImplementedError
