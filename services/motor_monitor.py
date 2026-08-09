#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Initial motor monitoring service for Rover-DR."""

from services.monitor_base import MonitorBase
from services.motor_state_store import MotorStateStore


class MotorMonitor(MonitorBase):
    """Publishes the current motor registry to a dedicated state store."""

    def __init__(self, state_store=None, interval_seconds=1.0):
        MonitorBase.__init__(self, "MotorMonitor", interval_seconds)
        self.state_store = state_store or MotorStateStore()
        self._load_initial_motors()

    @staticmethod
    def _motor(code, name, address, motor_class, polarity):
        return {
            "code": code,
            "name": name,
            "address": address,
            "motor_class": motor_class,
            "polarity": polarity,
            "position": 0,
            "speed": 0,
            "duty_cycle": 0,
            "state": [],
            "connected": False,
            "source": "simulated"
        }

    def _load_initial_motors(self):
        motors = {
            "LLM": self._motor(
                "LLM", "Left Large Motor", "outA", "LargeMotor", "normal"
            ),
            "LMM": self._motor(
                "LMM", "Left Medium Motor", "outB", "MediumMotor", "normal"
            ),
            "RMM": self._motor(
                "RMM", "Right Medium Motor", "outC", "MediumMotor", "normal"
            ),
            "RLM": self._motor(
                "RLM", "Right Large Motor", "outD", "LargeMotor", "inversed"
            )
        }

        for code, motor in motors.items():
            self.state_store.update_motor(code, motor)

    def on_cycle(self):
        """Refreshes the motor snapshot.

        Physical EV3 motor integration is intentionally deferred to a later
        increment; this commit establishes only the monitoring contract.
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
