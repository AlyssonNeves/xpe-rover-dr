#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Read-only output port for Rover motor state."""

from abc import ABCMeta, abstractmethod


class MotorQueryPort(object, metaclass=ABCMeta):
    @abstractmethod
    def list_motors(self):
        raise NotImplementedError

    @abstractmethod
    def read_motor(self, motor_code):
        raise NotImplementedError

    @abstractmethod
    def read_all_motors(self):
        raise NotImplementedError
