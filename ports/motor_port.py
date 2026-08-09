#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output port for querying and controlling Rover-DR motors."""

from abc import ABCMeta, abstractmethod


class MotorPort(object, metaclass=ABCMeta):
    """Defines the motor query and basic execution contract."""

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

    @abstractmethod
    def stop_motor(self, motor_code, stop_action=None):
        """Stops a specific motor."""
        raise NotImplementedError

    @abstractmethod
    def run_timed_motor(self, motor_code, speed_sp, time_sp, stop_action=None):
        """Runs a motor for a defined time interval."""
        raise NotImplementedError

    @abstractmethod
    def run_forever_motor(self, motor_code, speed_sp, stop_action=None):
        """Runs a motor continuously until a later stop command."""
        raise NotImplementedError

    @abstractmethod
    def run_to_rel_pos_motor(
        self, motor_code, speed_sp, position_sp, stop_action=None
    ):
        """Moves a motor by a relative encoder position."""
        raise NotImplementedError

    @abstractmethod
    def reset_motor(self, motor_code):
        """Resets a specific motor through the EV3 driver."""
        raise NotImplementedError
