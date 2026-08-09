#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output port for selecting the Rover operating mode."""

from abc import ABC, abstractmethod


class OperationModeSelectorPort(ABC):
    """Defines the contract for an operator-visible mode selector."""

    @abstractmethod
    def select_mode(self, command_mode, operation_mode):
        """Returns the command and operation modes selected by the operator."""
        raise NotImplementedError
