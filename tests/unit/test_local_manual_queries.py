#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for the thread-free LOCAL + MANUAL query adapters."""

from adapters.out_local_manual_queries import (
    LocalManualControllerQueryAdapter,
    LocalManualMotorQueryAdapter,
    LocalManualSensorQueryAdapter
)
from infrastructure.state.motor_state_store import MotorStateStore


def test_sensor_queries_expose_configured_metadata_without_monitor():
    adapter = LocalManualSensorQueryAdapter({
        "US": {
            "name": "Ultrasonic",
            "address": "in1",
            "supported_modes": ["US-DIST-CM"]
        }
    })

    assert adapter.list_sensors()[0]["code"] == "US"
    assert adapter.read_sensor("US")["connected"] is False
    assert adapter.list_sensor_modes("US") == ["US-DIST-CM"]


def test_motor_query_adapter_exposes_only_read_operations():
    store = MotorStateStore()
    adapter = LocalManualMotorQueryAdapter(store, {
        "LLM": {"name": "Left", "address": "outA"}
    })

    assert adapter.read_motor("LLM")["control_source"] == "local_manual"
    assert not hasattr(adapter, "list_commands")
    assert not hasattr(adapter, "drive_tank")



def test_motor_query_adapter_merges_live_physical_telemetry():
    class Hardware(object):
        @staticmethod
        def read_motor_state(motor_code):
            return {
                "code": motor_code,
                "connected": True,
                "speed": 321,
                "duty_cycle": 44,
                "state": ["running"]
            }

    store = MotorStateStore()
    adapter = LocalManualMotorQueryAdapter(
        store,
        {"LLM": {"name": "Left", "address": "outA"}},
        motor_hardware_port=Hardware()
    )

    motor = adapter.read_motor("LLM")

    assert motor["speed"] == 321
    assert motor["duty_cycle"] == 44
    assert motor["state"] == ["running"]
    assert motor["control_source"] == "local_manual"

def test_controller_queries_require_no_background_monitor():
    adapter = LocalManualControllerQueryAdapter()

    assert adapter.read_controller_status()["mode"] == "local_manual"
    assert adapter.read_network_status()["mode"] == "on_demand"


def test_command_service_rejects_sensor_mode_write_in_local_manual():
    from app.command_service import CommandService
    from app.models import CommandActions, CommandTargets, ResultStatuses
    from app.operation_mode_service import OperationModeService

    sensors = LocalManualSensorQueryAdapter({
        "US": {"name": "Ultrasonic", "address": "in1"}
    })
    motors = LocalManualMotorQueryAdapter(MotorStateStore(), {})
    service = CommandService(
        sensor_query_port=sensors,
        motor_query_port=motors,
        controller_port=LocalManualControllerQueryAdapter(),
        operation_mode_service=OperationModeService()
    )

    result = service.execute(
        CommandTargets.SENSOR,
        CommandActions.CHANGE_SENSOR_MODE,
        {"code": "US", "mode": "US-DIST-CM"}
    )

    assert result.success is False
    assert result.status == ResultStatuses.CONFLICT
