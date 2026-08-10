#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Read-only output port for Rover sensor state."""

from abc import ABCMeta, abstractmethod


class SensorQueryPort(object, metaclass=ABCMeta):
    """Defines sensor queries required by application use cases."""

    @abstractmethod
    def list_sensors(self):
        raise NotImplementedError

    @abstractmethod
    def read_sensor(self, code):
        raise NotImplementedError

    @abstractmethod
    def read_all_sensors(self):
        raise NotImplementedError
