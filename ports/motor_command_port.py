#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output port for individual and synchronized Rover motor commands."""

from abc import ABCMeta, abstractmethod


class MotorCommandPort(object, metaclass=ABCMeta):
    """Defines motor write operations independently from motor queries."""

    @abstractmethod
    def stop_motor(self, motor_code, stop_action=None):
        raise NotImplementedError

    @abstractmethod
    def run_timed_motor(self, motor_code, speed_sp, time_sp, priority=None,
                        profile=None, timeout_ms=None, stop_action=None):
        raise NotImplementedError

    @abstractmethod
    def run_forever_motor(self, motor_code, speed_sp, priority=None,
                          profile=None, watchdog_ms=None, timeout_ms=None,
                          stop_action=None):
        raise NotImplementedError

    @abstractmethod
    def run_direct_motor(self, motor_code, duty_cycle_sp, priority=None,
                         watchdog_ms=None, timeout_ms=None, stop_action=None):
        raise NotImplementedError

    @abstractmethod
    def run_to_rel_pos_motor(self, motor_code, speed_sp, position_sp,
                             priority=None, profile=None, timeout_ms=None,
                             stop_action=None):
        raise NotImplementedError

    @abstractmethod
    def run_to_abs_pos_motor(self, motor_code, speed_sp, position_sp,
                             priority=None, profile=None, timeout_ms=None,
                             stop_action=None):
        raise NotImplementedError

    @abstractmethod
    def reset_motor(self, motor_code):
        raise NotImplementedError

    @abstractmethod
    def cancel_motor_commands(self, motor_code):
        raise NotImplementedError

    @abstractmethod
    def stop_all_motors(self, stop_action=None):
        raise NotImplementedError

    @abstractmethod
    def run_synchronized_motors(self, commands):
        raise NotImplementedError
