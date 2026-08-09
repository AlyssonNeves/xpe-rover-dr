#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Motor monitoring service for Rover-DR."""

from app.rover_config import MONITOR_INTERVAL_SECONDS, get_motor_definitions
from services.monitor_base import MonitorBase
from services.motor_state_store import MotorStateStore


class MotorMonitor(MonitorBase):
    """Publishes the configured motor registry to a dedicated state store."""

    def __init__(self, state_store=None, interval_seconds=None):
        interval = (
            MONITOR_INTERVAL_SECONDS
            if interval_seconds is None
            else interval_seconds
        )
        MonitorBase.__init__(self, "MotorMonitor", interval)
        self.state_store = state_store or MotorStateStore()
        self._load_configured_motors()

    def _load_configured_motors(self):
        for code, definition in get_motor_definitions().items():
            motor = dict(definition)
            motor.update({
                "code": code,
                "position": 0,
                "speed": 0,
                "duty_cycle": 0,
                "state": [],
                "connected": False,
                "source": "simulated"
            })
            self.state_store.update_motor(code, motor)

    def on_cycle(self):
        """Refreshes the motor snapshot.

        Physical EV3 motor integration is intentionally deferred to the next
        increment; this commit only centralizes configuration metadata.
        """
        return None

    def list_motors(self):
        """Returns summarized information for all motors."""
        return [
            {
                "code": item["code"],
                "name": item["name"],
                "address": item["address"],
                "connected": item["connected"]
            }
            for item in self.state_store.get_all_motors()
        ]

    def read_motor(self, motor_code):
        """Returns one motor snapshot or None when it is unknown."""
        return self.state_store.get_motor(motor_code)

    def read_all_motors(self):
        """Returns snapshots of all known motors."""
        return self.state_store.get_all_motors()
