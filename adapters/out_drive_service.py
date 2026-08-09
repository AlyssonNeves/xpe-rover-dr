#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output adapter exposing differential-drive navigation through DrivePort."""

from ports.drive_port import DrivePort


class DriveServiceAdapter(DrivePort):
    """Adapts DriveService to the application layer."""

    def __init__(self, drive_service):
        self.drive_service = drive_service

    def get_status(self):
        return self.drive_service.get_status()

    def reset_odometry(self, x_mm=0.0, y_mm=0.0, heading_deg=0.0):
        return self.drive_service.reset_odometry(x_mm, y_mm, heading_deg)

    def drive_tank(
        self, left_speed_sp, right_speed_sp, priority=None,
        stop_action=None, watchdog_ms=None
    ):
        return self.drive_service.drive_tank(
            left_speed_sp,
            right_speed_sp,
            priority=priority,
            stop_action=stop_action,
            watchdog_ms=watchdog_ms,
        )

    def move_distance(
        self, distance_mm, speed_sp, priority=None, stop_action=None,
        timeout_ms=None
    ):
        return self.drive_service.move_distance(
            distance_mm, speed_sp, priority, stop_action, timeout_ms
        )

    def rotate_angle(
        self, angle_deg, speed_sp, priority=None, stop_action=None,
        timeout_ms=None
    ):
        return self.drive_service.rotate_angle(
            angle_deg, speed_sp, priority, stop_action, timeout_ms
        )

    def curve_radius(
        self, radius_mm, angle_deg, speed_sp, priority=None,
        stop_action=None, timeout_ms=None
    ):
        return self.drive_service.curve_radius(
            radius_mm, angle_deg, speed_sp, priority, stop_action, timeout_ms
        )

    def stop(self, stop_action=None):
        return self.drive_service.stop(stop_action)
