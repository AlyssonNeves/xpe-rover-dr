#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output port for selecting Rover Command and Control parameters."""

from abc import ABCMeta, abstractmethod


class CommandControlSelectorPort(object, metaclass=ABCMeta):
    """Defines the operator-facing Command/Control selection contract."""

    @abstractmethod
    def select_mode(self, command, control):
        """Returns ``command``/``control`` or ``None`` when cancelled."""
        raise NotImplementedError
