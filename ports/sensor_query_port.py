#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Read-only output port for sensor information."""

from abc import ABCMeta, abstractmethod


class SensorQueryPort(object, metaclass=ABCMeta):
    """Defines sensor queries without exposing hardware mutations."""

    @abstractmethod
    def list_sensors(self):
        raise NotImplementedError

    @abstractmethod
    def read_sensor(self, code):
        raise NotImplementedError

    @abstractmethod
    def read_all_sensors(self):
        raise NotImplementedError

    @abstractmethod
    def list_sensor_modes(self, code):
        raise NotImplementedError
