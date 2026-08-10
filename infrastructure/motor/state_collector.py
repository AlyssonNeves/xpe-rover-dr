#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Motor-state collection independent from command orchestration."""

from app.motor_lifecycle import MotorLifecycleStates


class MotorStateCollector(object):
    """Initializes and refreshes published motor state snapshots."""

    PRESERVED_COMMAND_FIELDS = (
        "command", "command_state", "motion_state", "active_command_id",
        "command_history", "last_command_at", "last_command_dispatched_at",
        "last_command_completed_at", "last_success_at", "last_failure_at",
        "success", "priority", "profile", "timeout_ms", "watchdog_ms",
        "stop_action", "cancelled_command_count"
    )

    def __init__(self, state_store, motor_definitions, hardware_enabled,
                 hardware_backend, motor_repository, queue_size_provider):
        self.state_store = state_store
        self.motor_definitions = motor_definitions
        self.hardware_enabled = hardware_enabled
        self.hardware_backend = hardware_backend
        self.motor_repository = motor_repository
        self.queue_size_provider = queue_size_provider

    def hardware_available(self):
        return self.hardware_enabled and self.hardware_backend.is_available()

    def hardware_error(self):
        if not self.hardware_enabled or self.hardware_backend.is_available():
            return None
        return getattr(self.hardware_backend, "error_message", None)

    def initial_lifecycle_state(self):
        if not self.hardware_enabled:
            return MotorLifecycleStates.SIMULATED
        if self.hardware_backend.is_available():
            return MotorLifecycleStates.HARDWARE_READY
        return MotorLifecycleStates.HARDWARE_UNAVAILABLE

    def load_initial_motors(self):
        backend_available = self.hardware_available()
        backend_error = self.hardware_error()
        lifecycle_state = self.initial_lifecycle_state()
        for motor_code, definition in self.motor_definitions.items():
            motor_class_name = definition.get("motor_class")
            motor_class = (
                self.hardware_backend.get_motor_class(motor_class_name)
                if backend_available else None
            )
            self.state_store.update_motor(motor_code, {
                "code": motor_code,
                "name": definition["name"],
                "address": definition["address"],
                "motor_class": motor_class_name,
                "connected": not self.hardware_enabled,
                "hardware_enabled": self.hardware_enabled,
                "hardware_backend_available": backend_available,
                "hardware_error": backend_error,
                "lifecycle_state": lifecycle_state,
                "driver_class_loaded": motor_class is not None,
                "command_queue_size": 0,
                "pending_command": None,
                "command_history": [],
                "last_command_at": None,
                "last_success_at": None,
                "last_failure_at": None,
                "cancelled_command_count": 0,
                "command_state": None,
                "motion_state": "IDLE",
                "active_command_id": None,
                "polarity": definition.get("polarity", "normal"),
                "limits": dict(definition.get("limits") or {})
            })

    def refresh_availability_state(self):
        backend_available = self.hardware_available()
        backend_error = self.hardware_error()
        lifecycle_state = self.initial_lifecycle_state()
        for motor_code in self.motor_definitions:
            motor = self.state_store.get_motor(motor_code)
            if motor is None:
                continue
            motor["hardware_backend_available"] = backend_available
            motor["hardware_error"] = backend_error
            if motor.get("pending_command") is None:
                motor["lifecycle_state"] = lifecycle_state
            self.state_store.update_motor(motor_code, motor)

    def refresh_hardware_state(self):
        if not self.hardware_available():
            self.refresh_availability_state()
            return
        for snapshot in self.motor_repository.read_all_motors():
            self._publish_snapshot(snapshot)

    def _publish_snapshot(self, snapshot):
        if snapshot is None:
            return
        motor_code = snapshot["code"]
        current = self.state_store.get_motor(motor_code) or {}
        if current.get("pending_command") is not None:
            return
        snapshot["hardware_enabled"] = self.hardware_enabled
        snapshot["hardware_backend_available"] = True
        snapshot["driver_class_loaded"] = (
            self.hardware_backend.get_motor_class(
                snapshot.get("motor_class")
            ) is not None
        )
        snapshot["command_queue_size"] = self.queue_size_provider(motor_code)
        snapshot["pending_command"] = current.get("pending_command")
        for field_name in self.PRESERVED_COMMAND_FIELDS:
            if field_name in current:
                snapshot[field_name] = current[field_name]
        self.state_store.update_motor(motor_code, snapshot)
