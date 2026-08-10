#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Low-level output port for direct EV3 motor hardware operations."""

from abc import ABCMeta, abstractmethod


class MotorHardwarePort(object, metaclass=ABCMeta):
    """Defines the hardware primitives required by local manual control."""

    @abstractmethod
    def get_motor_definition(self, motor_code):
        raise NotImplementedError

    @abstractmethod
    def ensure_connected(self, motor_code):
        raise NotImplementedError

    @abstractmethod
    def get_error(self, motor_code):
        raise NotImplementedError

    @abstractmethod
    def run_forever(self, motor_code, speed_sp):
        raise NotImplementedError

    @abstractmethod
    def stop(self, motor_code, stop_action=None, connected_only=False):
        raise NotImplementedError
