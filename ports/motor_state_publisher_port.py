#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output port for publishing motor state snapshots."""

from abc import ABCMeta, abstractmethod


class MotorStatePublisherPort(object, metaclass=ABCMeta):
    """Publishes state without exposing the underlying persistence mechanism."""

    @abstractmethod
    def publish_motor_state(self, motor_code, state):
        raise NotImplementedError
