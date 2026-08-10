#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output port for differential-drive navigation."""

from abc import ABCMeta, abstractmethod


class DrivePort(object, metaclass=ABCMeta):
    """Defines differential-drive control, odometry and basic navigation."""

    @abstractmethod
    def get_status(self):
        """Returns drive state, calibration, traction snapshots and odometry."""
        raise NotImplementedError

    @abstractmethod
    def reset_odometry(self, x_mm=0.0, y_mm=0.0, heading_deg=0.0):
        """Resets the estimated rover pose."""
        raise NotImplementedError

    @abstractmethod
    def drive_tank(
        self, left_speed_sp, right_speed_sp, priority=None,
        stop_action=None, watchdog_ms=None, profile=None
    ):
        """Controls left and right traction motors independently."""
        raise NotImplementedError

    @abstractmethod
    def move_distance(
        self, distance_mm, speed_sp, priority=None, stop_action=None,
        timeout_ms=None, profile=None
    ):
        """Queues a straight-line displacement in millimetres."""
        raise NotImplementedError

    @abstractmethod
    def rotate_angle(
        self, angle_deg, speed_sp, priority=None, stop_action=None,
        timeout_ms=None, profile=None
    ):
        """Queues an in-place rover rotation in degrees."""
        raise NotImplementedError

    @abstractmethod
    def curve_radius(
        self, radius_mm, angle_deg, speed_sp, priority=None,
        stop_action=None, timeout_ms=None, profile=None
    ):
        """Queues a circular arc defined by radius and angle."""
        raise NotImplementedError

    @abstractmethod
    def stop(self, stop_action=None):
        """Stops both traction motors immediately."""
        raise NotImplementedError
