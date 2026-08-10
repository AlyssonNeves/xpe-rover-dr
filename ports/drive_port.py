#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output port for high-level Rover navigation operations."""


from abc import ABCMeta, abstractmethod


class DrivePort(object, metaclass=ABCMeta):
    """Defines the contract for differential-drive navigation."""

    @abstractmethod
    def get_status(self):
        """Return the current navigation service status."""
        raise NotImplementedError

    @abstractmethod
    def get_telemetry(self, limit=None):
        """Return recent navigation telemetry, optionally limited in size."""
        raise NotImplementedError

    @abstractmethod
    def reset_odometry(self, x_mm=0.0, y_mm=0.0, heading_deg=0.0):
        """Reset the estimated Rover pose to the supplied coordinates."""
        raise NotImplementedError

    @abstractmethod
    def move_distance(self, distance_mm, speed_sp, **options):
        """Move the Rover by a linear distance using the requested speed."""
        raise NotImplementedError

    @abstractmethod
    def rotate_angle(self, angle_deg, speed_sp, **options):
        """Rotate the Rover through the requested angle at the given speed."""
        raise NotImplementedError

    @abstractmethod
    def curve_radius(self, radius_mm, angle_deg, speed_sp, **options):
        """Drive along an arc defined by radius, angle, and speed."""
        raise NotImplementedError

    @abstractmethod
    def stop(self, stop_action=None):
        """Stop differential-drive motion using the requested stop action."""
        raise NotImplementedError
