#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output contract for operator-visible Bluetooth joystick status."""

from abc import ABCMeta, abstractmethod


class JoystickConnectionStatusPort(object, metaclass=ABCMeta):
    """Presents joystick connection failures and successful recovery."""

    @abstractmethod
    def show_joystick_connection_error(self, message, retry_seconds):
        """Shows that the joystick is unavailable and a retry is pending."""
        raise NotImplementedError

    @abstractmethod
    def show_joystick_connected(self, device_name):
        """Restores the normal display after the joystick is connected."""
        raise NotImplementedError
