#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Direct EV3 motor hardware adapter for LOCAL + MANUAL control."""

import copy

from ports.motor_hardware_port import MotorHardwarePort
from services.manual_motor_hardware import DirectMotorRegistry


class Ev3MotorHardwareAdapter(MotorHardwarePort):
    """Owns or receives a low-level EV3 registry without command queues.

    In the LOCAL + MANUAL runtime the adapter creates a private registry, so no
    ``MotorMonitor`` instance is required. Tests may still inject a registry to
    exercise the hardware boundary deterministically.
    """

    def __init__(self, motor_definitions, motor_registry=None,
                 default_stop_action="brake", hardware_backend=None):
        if not isinstance(motor_definitions, dict) or not motor_definitions:
            raise ValueError("motor_definitions is required.")
        self._motor_definitions = copy.deepcopy(motor_definitions)
        if motor_registry is None:
            # LOCAL + MANUAL owns a private low-level registry. No monitor or
            # command queue participates in this path.
            motor_registry = DirectMotorRegistry(
                self._motor_definitions, hardware_backend=hardware_backend
            )
        self._motor_registry = motor_registry
        self._default_stop_action = default_stop_action or "brake"
        self._connected_codes = set()

    def get_motor_definition(self, motor_code):
        definition = self._motor_definitions.get(motor_code)
        return copy.deepcopy(definition) if definition is not None else None

    def ensure_connected(self, motor_code):
        motor = self._motor_registry.get_motor(motor_code)
        if motor is not None:
            self._connected_codes.add(motor_code)
        return motor

    def get_error(self, motor_code):
        return self._motor_registry.get_error(motor_code)

    def run_forever(self, motor_code, speed_sp):
        if self.ensure_connected(motor_code) is None:
            return self._failure(motor_code)
        success, error = self._motor_registry.run_forever_motor(
            motor_code, int(speed_sp), stop_action=self._default_stop_action
        )
        return {"success": bool(success), "hardware_error": error}

    def stop(self, motor_code, stop_action=None, connected_only=False):
        if connected_only and motor_code not in self._connected_codes:
            return {
                "success": False,
                "hardware_error": (
                    self.get_error(motor_code) or "Motor is not connected."
                )
            }
        if not connected_only and self.ensure_connected(motor_code) is None:
            return self._failure(motor_code)
        success, error = self._motor_registry.stop_motor(
            motor_code, stop_action or self._default_stop_action
        )
        return {"success": bool(success), "hardware_error": error}

    def _failure(self, motor_code):
        return {
            "success": False,
            "hardware_error": (
                self.get_error(motor_code) or "Motor hardware is unavailable."
            )
        }
