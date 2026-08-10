#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Direct EV3 motor hardware adapter for local manual operation."""

from infrastructure.ev3.motor_driver_factory import Ev3MotorDriverFactory
from infrastructure.motor.driver_repository import Ev3MotorDriverRepository
from ports.motor_hardware_port import MotorHardwarePort


class Ev3MotorHardwareAdapter(MotorHardwarePort):
    """Exposes one shared low-level driver repository through the port."""

    def __init__(self, motor_definitions, motor_classes=None,
                 driver_factory=None, driver_repository=None,
                 default_stop_action="brake"):
        if motor_definitions is None:
            raise ValueError("motor_definitions is required.")
        self._motor_definitions = motor_definitions
        self._default_stop_action = default_stop_action or "brake"
        factory = driver_factory or Ev3MotorDriverFactory(motor_classes)
        self._repository = driver_repository or Ev3MotorDriverRepository(
            motor_definitions=motor_definitions,
            hardware_backend=factory,
            retry_interval_seconds=0.0
        )

    def get_motor_definition(self, motor_code):
        definition = self._motor_definitions.get(motor_code)
        return dict(definition) if definition is not None else None

    def ensure_connected(self, motor_code):
        return self._repository.ensure_connected_motor(motor_code)

    def get_error(self, motor_code):
        return self._repository.get_motor_error(motor_code)

    def read_motor_state(self, motor_code):
        """Returns lightweight live telemetry without broad EV3 state polling."""
        return self._repository.read_motor_telemetry(motor_code)

    def run_forever(self, motor_code, speed_sp):
        return self._normalize_result(
            self._repository.execute_run_forever(motor_code, int(speed_sp))
        )

    def stop(self, motor_code, stop_action=None, connected_only=False):
        if connected_only and self._repository.get_connected_motor(motor_code) is None:
            return {
                "success": False,
                "hardware_error": (
                    self._repository.get_motor_error(motor_code)
                    or "Motor is not connected."
                )
            }
        return self._normalize_result(
            self._repository.execute_stop(
                motor_code, stop_action or self._default_stop_action
            )
        )

    @staticmethod
    def _normalize_result(result):
        if result is None:
            return {"success": False, "hardware_error": "Motor is not connected."}
        if isinstance(result, dict):
            return {
                "success": bool(result.get("success")),
                "hardware_error": result.get("hardware_error") or result.get("error")
            }
        return {"success": bool(result), "hardware_error": None}
