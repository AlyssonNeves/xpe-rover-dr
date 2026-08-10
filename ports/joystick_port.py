#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Input port for local manual joystick events."""

from abc import ABCMeta, abstractmethod


class JoystickPort(object, metaclass=ABCMeta):
    """Defines the minimal controller contract used by manual control."""

    @abstractmethod
    def is_available(self):
        """Returns whether the configured joystick is already in evdev."""
        raise NotImplementedError

    @abstractmethod
    def open(self):
        """Opens the configured joystick and returns its display name."""
        raise NotImplementedError

    @abstractmethod
    def read_event(self, timeout_seconds=None):
        """Returns the next normalized controller event or ``None``."""
        raise NotImplementedError

    @abstractmethod
    def close(self):
        """Releases the controller device."""
        raise NotImplementedError
