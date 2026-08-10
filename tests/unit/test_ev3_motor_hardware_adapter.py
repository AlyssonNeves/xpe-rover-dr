#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for the low-latency adapter over the shared EV3 motor registry."""

from adapters.out_ev3_motor_hardware import Ev3MotorHardwareAdapter
from ports.motor_hardware_port import MotorHardwarePort


class FakeRegistry(object):
    def __init__(self):
        self.motors = {"LLM": object()}
        self.errors = {}
        self.run_calls = []
        self.stop_calls = []

    def get_motor(self, motor_code):
        return self.motors.get(motor_code)

    def get_error(self, motor_code):
        return self.errors.get(motor_code)

    def run_forever_motor(self, motor_code, speed_sp, stop_action=None):
        self.run_calls.append((motor_code, speed_sp, stop_action))
        return True, None

    def stop_motor(self, motor_code, stop_action=None):
        self.stop_calls.append((motor_code, stop_action))
        return True, None


def build_adapter():
    registry = FakeRegistry()
    definitions = {
        "LLM": {
            "name": "Left Large Motor",
            "address": "outA",
            "motor_class": "LargeMotor",
            "polarity": "normal"
        }
    }
    return Ev3MotorHardwareAdapter(definitions, registry), registry


def test_adapter_implements_motor_hardware_port_and_returns_definition_copy():
    adapter, _ = build_adapter()

    assert isinstance(adapter, MotorHardwarePort)
    definition = adapter.get_motor_definition("LLM")
    definition["address"] = "changed"
    assert adapter.get_motor_definition("LLM")["address"] == "outA"


def test_run_forever_calls_registry_primitive_without_queue_or_watchdog():
    adapter, registry = build_adapter()

    result = adapter.run_forever("LLM", 325)

    assert result == {"success": True, "hardware_error": None}
    assert registry.run_calls == [("LLM", 325, "brake")]


def test_connected_only_stop_does_not_attempt_to_connect_unknown_motor():
    adapter, registry = build_adapter()

    result = adapter.stop("LLM", connected_only=True)

    assert result["success"] is False
    assert result["hardware_error"] == "Motor is not connected."
    assert registry.stop_calls == []


def test_preconnected_motor_can_be_stopped_synchronously():
    adapter, registry = build_adapter()
    assert adapter.ensure_connected("LLM") is registry.motors["LLM"]

    result = adapter.stop("LLM", "hold", connected_only=True)

    assert result["success"] is True
    assert registry.stop_calls == [("LLM", "hold")]
