#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output port for querying Rover-DR sensor information."""

from abc import ABCMeta, abstractmethod


class SensorPort(object, metaclass=ABCMeta):
    """Defines the sensor query operations exposed to the application."""

    @abstractmethod
    def list_sensors(self):
        """Returns a summarized list of known sensors."""
        raise NotImplementedError

    @abstractmethod
    def read_sensor(self, code):
        """Returns the current state of one sensor."""
        raise NotImplementedError

    @abstractmethod
    def read_all_sensors(self):
        """Returns the current state of all sensors."""
        raise NotImplementedError
