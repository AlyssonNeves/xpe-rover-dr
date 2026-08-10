#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output port for safety-guarded native motor operations."""

from abc import ABCMeta, abstractmethod


class GuardedMotorOperationPort(object, metaclass=ABCMeta):
    """Defines reservation boundaries for direct native operations."""

    @abstractmethod
    def execute_guarded_operation(self, motor_codes, operation_name,
                                  operation):
        raise NotImplementedError

    @abstractmethod
    def begin_guarded_operation(self, motor_codes, operation_name,
                                operation_id):
        raise NotImplementedError

    @abstractmethod
    def end_guarded_operation(self, operation_id, status="COMPLETED",
                              error=None, stop=False):
        raise NotImplementedError
