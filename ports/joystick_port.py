#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Input port for reading normalized joystick events."""

from abc import ABCMeta, abstractmethod


class JoystickPort(object, metaclass=ABCMeta):
    """Defines the joystick discovery and bounded event-reading contract."""

    @abstractmethod
    def is_available(self):
        """Returns whether the configured joystick is already in evdev."""
        raise NotImplementedError

    @abstractmethod
    def open(self):
        """Opens the configured joystick and returns its display name."""
        raise NotImplementedError

    @abstractmethod
    def read_event_batch(self, timeout_seconds, max_events):
        """Returns one bounded batch of normalized controller events.

        Implementations may wait up to ``timeout_seconds`` for initial input,
        then drain only promptly available data. At most ``max_events`` are
        returned in one control cycle.
        """
        raise NotImplementedError

    @abstractmethod
    def refresh_absolute_state(self, axis_codes):
        """Returns a fresh raw-axis snapshot for every requested axis."""
        raise NotImplementedError

    @abstractmethod
    def close(self):
        """Releases the controller device."""
        raise NotImplementedError
