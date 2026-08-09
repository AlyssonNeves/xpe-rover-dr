#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output port for querying the consolidated Rover-DR state."""

from abc import ABCMeta, abstractmethod


class RoverStateQueryPort(object, metaclass=ABCMeta):
    """Contract implemented by adapters that expose the Rover state."""

    @abstractmethod
    def get_rover_state(self):
        """Returns a consolidated snapshot of the current Rover state."""
        raise NotImplementedError
