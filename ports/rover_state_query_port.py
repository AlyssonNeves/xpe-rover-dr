#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Output port for querying the overall Rover state.

Defines the contract that must be implemented by components
capable of querying and returning the consolidated Rover state.
"""


from abc import ABCMeta, abstractmethod


class RoverStateQueryPort(object, metaclass=ABCMeta):
    """Contract for querying the overall Rover state."""

    @abstractmethod
    def get_rover_state(self):
        """
        Returns the current consolidated Rover state.

        Returns:
            dict:
                Consolidated Rover state containing information
                from sensors, motors, controller, and other
                monitored subsystems.
        """
        raise NotImplementedError
