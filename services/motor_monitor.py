#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Initial motor monitoring service for Rover-DR."""

import copy
import threading

from services.monitor_base import MonitorBase


class MotorMonitor(MonitorBase):
    """Maintains an in-memory snapshot of the Rover motors."""

    def __init__(self, interval_seconds=1.0):
        MonitorBase.__init__(self, "MotorMonitor", interval_seconds)
        self._lock = threading.Lock()
        self._motors = {
            "LLM": self._motor("LLM", "Left Large Motor", "outA", "LargeMotor", "normal"),
            "LMM": self._motor("LMM", "Left Medium Motor", "outB", "MediumMotor", "normal"),
            "RMM": self._motor("RMM", "Right Medium Motor", "outC", "MediumMotor", "normal"),
            "RLM": self._motor("RLM", "Right Large Motor", "outD", "LargeMotor", "inversed")
        }

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
            for item in self.read_all_motors()
        ]

    def read_motor(self, motor_code):
        """Returns one motor snapshot or None when it is unknown."""
        with self._lock:
            motor = self._motors.get(motor_code)
            return copy.deepcopy(motor) if motor is not None else None

    def read_all_motors(self):
        """Returns snapshots of all known motors."""
        with self._lock:
            return copy.deepcopy(list(self._motors.values()))
