#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output port for queued motor mutation commands."""

from abc import ABCMeta, abstractmethod


class MotorCommandPort(object, metaclass=ABCMeta):
    @abstractmethod
    def stop_motor(self, motor_code, stop_action=None):
        raise NotImplementedError

    @abstractmethod
    def run_timed_motor(self, motor_code, speed_sp, time_sp, priority=None,
                        stop_action=None, timeout_ms=None, profile=None):
        raise NotImplementedError

    @abstractmethod
    def run_forever_motor(self, motor_code, speed_sp, priority=None,
                          stop_action=None, watchdog_ms=None, timeout_ms=None,
                          profile=None):
        raise NotImplementedError

    @abstractmethod
    def run_to_rel_pos_motor(self, motor_code, speed_sp, position_sp,
                             priority=None, stop_action=None, timeout_ms=None,
                             profile=None):
        raise NotImplementedError

    @abstractmethod
    def reset_motor(self, motor_code, priority=None):
        raise NotImplementedError

    @abstractmethod
    def cancel_motor_commands(self, motor_code):
        raise NotImplementedError

    @abstractmethod
    def run_synchronized_motors(self, commands):
        raise NotImplementedError
