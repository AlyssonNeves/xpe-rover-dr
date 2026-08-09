#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output adapter exposing differential-drive operations through DrivePort."""

from ports.drive_port import DrivePort


class DriveServiceAdapter(DrivePort):
    """Adapts DriveService to the application layer."""

    def __init__(self, drive_service):
        self.drive_service = drive_service

    def get_status(self):
        return self.drive_service.get_status()

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

    def stop(self, stop_action=None):
        return self.drive_service.stop(stop_action)
