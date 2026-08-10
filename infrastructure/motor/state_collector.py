#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Motor-state publication extracted from MotorMonitor."""


class MotorStateCollector(object):
    """Builds and refreshes motor snapshots through a driver repository."""

    def __init__(self, state_store, motor_definitions, motor_repository,
                 hardware_enabled, lifecycle_idle, safety):
        self.state_store = state_store
        self.motor_definitions = motor_definitions
        self.motor_repository = motor_repository
        self.hardware_enabled = bool(hardware_enabled)
        self.lifecycle_idle = lifecycle_idle
        self.safety = dict(safety)

    def base_snapshot(self, motor_code, definition):
        return {
            "code": motor_code,
            "name": definition["name"],
            "address": definition["address"],
            "motor_class": definition.get("motor_class"),
            "polarity": definition.get("polarity"),
            "position": 0,
            "speed": 0,
            "duty_cycle": 0,
            "state": [],
            "driver_name": None,
            "max_speed": None,
            "connected": False,
            "source": "ev3dev2" if self.hardware_enabled else "disabled",
            "error": None,
            "lifecycle_state": self.lifecycle_idle,
            "command_queue_size": 0,
            "active_command_id": None,
            "last_command_id": None,
            "last_safety_event": None,
            "safety": dict(self.safety)
        }

    def load_initial_motors(self):
        for code, definition in self.motor_definitions.items():
            self.state_store.update_motor(
                code, self.base_snapshot(code, definition)
            )

    def refresh_motor(self, motor_code):
        definition = self.motor_definitions[motor_code]
        previous = self.state_store.get_motor(motor_code) or {}
        snapshot = self.base_snapshot(motor_code, definition)
        for field in (
            "lifecycle_state", "command_queue_size", "active_command_id",
            "last_command_id", "last_safety_event", "safety"
        ):
            if field in previous:
                snapshot[field] = previous[field]

        hardware_snapshot = self.motor_repository.read_motor(motor_code)
        if hardware_snapshot is not None:
            snapshot.update(hardware_snapshot)
            snapshot["error"] = None
        else:
            snapshot["error"] = self.motor_repository.get_error(motor_code)
        self.state_store.update_motor(motor_code, snapshot)
        return snapshot

    def refresh_all_motors(self):
        for motor_code in self.motor_definitions:
            self.refresh_motor(motor_code)
