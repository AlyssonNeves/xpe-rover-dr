#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output port for publishing motor state snapshots."""

from abc import ABCMeta, abstractmethod


class MotorStatePublisherPort(object, metaclass=ABCMeta):
    """Publishes motor state without exposing the persistence mechanism."""

    @abstractmethod
    def publish_motor_state(self, motor_code, state):
        """Publishes the latest application-visible state for one motor."""
        raise NotImplementedError
