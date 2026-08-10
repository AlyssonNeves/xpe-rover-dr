#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Read-only output port for Rover motor state queries."""

from abc import ABCMeta, abstractmethod


class MotorQueryPort(object, metaclass=ABCMeta):
    """Defines discovery and state access for configured motors."""

    @abstractmethod
    def list_motors(self):
        """Returns summarized motor records."""
        raise NotImplementedError

    @abstractmethod
    def read_motor(self, motor_code):
        """Returns one complete motor state record."""
        raise NotImplementedError

    @abstractmethod
    def read_all_motors(self):
        """Returns complete state records for every configured motor."""
        raise NotImplementedError
