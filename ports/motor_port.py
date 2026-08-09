#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output port for querying and orchestrating Rover-DR motors."""

from abc import ABCMeta, abstractmethod


class MotorPort(object, metaclass=ABCMeta):
    """Defines motor query, queue and execution operations."""

    @abstractmethod
    def list_motors(self):
        raise NotImplementedError

    @abstractmethod
    def read_motor(self, motor_code):
        raise NotImplementedError

    @abstractmethod
    def read_all_motors(self):
        raise NotImplementedError

    @abstractmethod
    def stop_motor(self, motor_code, stop_action=None):
        raise NotImplementedError

    @abstractmethod
    def run_timed_motor(
        self, motor_code, speed_sp, time_sp, priority=None, stop_action=None
    ):
        raise NotImplementedError

    @abstractmethod
    def run_forever_motor(
        self, motor_code, speed_sp, priority=None, stop_action=None
    ):
        raise NotImplementedError

    @abstractmethod
    def run_to_rel_pos_motor(
        self, motor_code, speed_sp, position_sp, priority=None,
        stop_action=None
    ):
        raise NotImplementedError

    @abstractmethod
    def reset_motor(self, motor_code, priority=None):
        raise NotImplementedError

    @abstractmethod
    def get_command(self, command_id):
        raise NotImplementedError

    @abstractmethod
    def list_commands(self, motor_code=None):
        raise NotImplementedError

    @abstractmethod
    def cancel_motor_commands(self, motor_code):
        raise NotImplementedError

    @abstractmethod
    def run_synchronized_motors(self, commands):
        raise NotImplementedError
