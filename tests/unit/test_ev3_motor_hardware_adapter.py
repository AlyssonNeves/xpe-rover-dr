#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for the direct EV3 motor hardware adapter."""

from adapters.out_ev3_motor_hardware import Ev3MotorHardwareAdapter
from ports.motor_hardware_port import MotorHardwarePort


class FakeMotor(object):
    def __init__(self, address):
        self.address = address
        self.polarity = None
        self.run_calls = []
        self.stop_calls = []
        self.speed = 321
        self.duty_cycle = 44
        self.state = ["running"]

    def run_forever(self, speed_sp):
        self.run_calls.append(speed_sp)

    def stop(self, stop_action):
        self.stop_calls.append(stop_action)


def build_adapter():
    definitions = {
        "LLM": {
            "name": "Left",
            "address": "outA",
            "motor_class": "LargeMotor",
            "polarity": "inversed"
        },
        "RLM": {
            "name": "Right",
            "address": "outD",
            "motor_class": "LargeMotor",
            "polarity": "normal"
        }
    }
    adapter = Ev3MotorHardwareAdapter(
        motor_definitions=definitions,
        motor_classes={"LargeMotor": FakeMotor}
    )
    return adapter


def test_hardware_adapter_implements_port_and_caches_motor_instance():
    adapter = build_adapter()

    assert isinstance(adapter, MotorHardwarePort)
    assert adapter.get_motor_definition("LLM")["address"] == "outA"

    motor = adapter.ensure_connected("LLM")
    same_motor = adapter.ensure_connected("LLM")

    assert motor is same_motor
    assert motor.polarity == "inversed"
    assert adapter.run_forever("LLM", 250)["success"] is True
    assert adapter.stop("LLM", "brake", connected_only=True)["success"] is True
    assert motor.run_calls == [250]
    assert motor.stop_calls == ["brake"]



def test_hardware_adapter_exposes_live_motor_telemetry():
    adapter = build_adapter()
    adapter.ensure_connected("LLM")

    state = adapter.read_motor_state("LLM")

    assert state["connected"] is True
    assert state["speed"] == 321
    assert state["duty_cycle"] == 44
    assert state["state"] == ["running"]
    assert "commands" not in state
    assert "max_speed" not in state
    assert "speed_p" not in state

def test_connected_only_stop_never_reconnects_missing_motor():
    adapter = build_adapter()

    result = adapter.stop("LLM", "brake", connected_only=True)

    assert result["success"] is False
    assert result["hardware_error"] == "Motor is not connected."


def test_global_polarity_is_applied_to_every_connected_motor():
    adapter = build_adapter()

    left_motor = adapter.ensure_connected("LLM")
    right_motor = adapter.ensure_connected("RLM")

    assert left_motor.polarity == "inversed"
    assert right_motor.polarity == "normal"
