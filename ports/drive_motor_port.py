#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output port for differential traction motor operations."""

from abc import ABCMeta, abstractmethod


class DriveMotorPort(object, metaclass=ABCMeta):
    """Defines paired traction commands required by drive use cases."""

    @abstractmethod
    def drive_tank(self, left_speed_sp, right_speed_sp, **options):
        raise NotImplementedError

    @abstractmethod
    def stop_drive(self, stop_action=None):
        raise NotImplementedError
