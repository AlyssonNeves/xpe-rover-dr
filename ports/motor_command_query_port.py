#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output port for querying motor-command lifecycle snapshots."""

from abc import ABCMeta, abstractmethod


class MotorCommandQueryPort(object, metaclass=ABCMeta):
    """Defines read operations over motor command lifecycle records."""

    @abstractmethod
    def get_command(self, command_id):
        raise NotImplementedError

    @abstractmethod
    def list_commands(self, motor_code=None):
        raise NotImplementedError
