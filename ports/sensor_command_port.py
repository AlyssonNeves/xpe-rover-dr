#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Mutation output port for sensor control."""

from abc import ABCMeta, abstractmethod


class SensorCommandPort(object, metaclass=ABCMeta):
    """Defines sensor commands independently from read operations."""

    @abstractmethod
    def change_sensor_mode(self, code, mode):
        raise NotImplementedError
