#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Input port for reading normalized joystick events."""

from abc import ABCMeta, abstractmethod


class JoystickPort(object, metaclass=ABCMeta):
    """Defines the joystick discovery and event-reading contract."""

    @abstractmethod
    def is_available(self):
        """Returns True when the configured joystick is already in evdev."""
        raise NotImplementedError

    @abstractmethod
    def open(self):
        """Opens the configured joystick and returns its display name."""
        raise NotImplementedError

    @abstractmethod
    def read_event_batch(self, timeout_seconds, max_events):
        """Returns one bounded batch of normalized events.

        The implementation waits at most ``timeout_seconds`` for the first
        event, then drains only promptly available input within its internal
        latency budget. At most ``max_events`` are returned.
        """
        raise NotImplementedError

    @abstractmethod
    def refresh_absolute_state(self, axis_codes):
        """Returns a fresh raw-axis snapshot after discarding queued input.

        Implementations must either return every requested axis or raise an
        explicit error. Silently omitting an axis can leave startup safety
        gates waiting forever.
        """
        raise NotImplementedError

    @abstractmethod
    def close(self):
        """Releases the joystick device."""
        raise NotImplementedError
