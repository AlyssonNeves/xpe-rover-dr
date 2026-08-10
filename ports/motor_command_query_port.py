#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output port for querying queued motor commands."""

from abc import ABCMeta, abstractmethod


class MotorCommandQueryPort(object, metaclass=ABCMeta):
    @abstractmethod
    def get_command(self, command_id):
        raise NotImplementedError

    @abstractmethod
    def list_commands(self, motor_code=None):
        raise NotImplementedError
