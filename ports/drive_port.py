#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output port for differential-drive control."""

from abc import ABCMeta, abstractmethod


class DrivePort(object, metaclass=ABCMeta):
    """Defines the initial differential-drive contract."""

    @abstractmethod
    def get_status(self):
        """Returns current drive configuration and traction motor snapshots."""
        raise NotImplementedError

    @abstractmethod
    def drive_tank(
        self, left_speed_sp, right_speed_sp, priority=None,
        stop_action=None, watchdog_ms=None
    ):
        """Controls left and right traction motors independently."""
        raise NotImplementedError

    @abstractmethod
    def stop(self, stop_action=None):
        """Stops both traction motors immediately."""
        raise NotImplementedError
