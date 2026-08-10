#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for the S02.21 dedicated EV3 gyroscope integration."""

import sys
import types

import pytest

from adapters.out_ev3_gyro_sensor import Ev3GyroSensorAdapter
from adapters.out_local_manual_queries import FieldManualSensorQueryAdapter
from adapters.out_heading_state import HeadingStateQueryAdapter
from app import rover_config
from app.operation_mode_service import Centrics, Drives, OperationModeService
from app.services.joystick_control_service import JoystickControlService
from bootstrap import rover_assembly
from infrastructure.monitoring.gyro_heading_monitor import GyroHeadingMonitor
from infrastructure.state.heading_state_store import HeadingStateStore
from ports.heading_sensor_port import HeadingSensorPort


class FakeSensor(object):
    def __init__(self, angle=12.0):
        self.mode = None
        self.angle = angle
        self.reset_calls = 0

    def reset(self):
        self.reset_calls += 1
        self.angle = 0.0


class FakePort(object):
    def __init__(self):
        self.mode = "auto"
        self.modes = ("auto", "ev3-uart")


class SensorPort(object):
    def __init__(self, values):
        self.values = list(values)
        self.open_calls = 0
        self.close_calls = 0

    def open(self):
        self.open_calls += 1

    def read_heading_deg(self):
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    def close(self):
        self.close_calls += 1


def test_heading_sensor_port_contract_is_hardware_only():
    assert set(("open", "read_heading_deg", "close")) <= set(
        vars(HeadingSensorPort)
    )


def test_ev3_gyro_adapter_prepares_uart_resets_and_calibrates_heading():
    sensor = FakeSensor(angle=30.0)
    port = FakePort()
    captured = {}

    def sensor_factory(address=None):
        captured["sensor_address"] = address
        return sensor

    def port_factory(address=None):
        captured["port_address"] = address
        return port

    adapter = Ev3GyroSensorAdapter(
        address="in3",
        mode="GYRO-ANG",
        reset_on_start=False,
        angle_sign=-1.0,
        angle_offset_deg=5.0,
        port_mode="ev3-uart",
        sensor_factory=sensor_factory,
        port_factory=port_factory
    )

    adapter.open()

    assert captured == {"sensor_address": "in3", "port_address": "in3"}
    assert port.mode == "ev3-uart"
    assert sensor.mode == "GYRO-ANG"
    assert sensor.reset_calls == 0
    assert adapter.read_heading_deg() == -25.0


def test_ev3_gyro_adapter_reset_restores_requested_mode():
    class ResettingSensor(FakeSensor):
        def reset(self):
            self.reset_calls += 1
            self.mode = "GYRO-RATE"
            self.angle = 0.0

    sensor = ResettingSensor()
    adapter = Ev3GyroSensorAdapter(
        reset_on_start=True,
        sensor_factory=lambda address=None: sensor
    )
    adapter.open()

    assert sensor.reset_calls == 1
    assert sensor.mode == "GYRO-ANG"


def test_ev3_gyro_adapter_retries_detection_until_sensor_appears():
    attempts = []
    moments = [0.0, 0.0, 0.05, 0.1]

    def clock():
        return moments.pop(0)

    def sensor_factory(address=None):
        attempts.append(address)
        if len(attempts) < 2:
            raise RuntimeError("not ready")
        return FakeSensor()

    adapter = Ev3GyroSensorAdapter(
        connection_timeout_seconds=1.0,
        connection_retry_seconds=0.1,
        sensor_factory=sensor_factory,
        clock=clock,
        sleeper=lambda seconds: None
    )
    adapter.open()

    assert attempts == ["in3", "in3"]


def test_ev3_gyro_adapter_maps_ev3_input_address_without_import_side_effects():
    ev3dev2_module = types.ModuleType("ev3dev2")
    ev3dev2_module.__path__ = []
    sensor_module = types.ModuleType("ev3dev2.sensor")
    sensor_module.__path__ = []
    sensor_module.INPUT_1 = "ev3-ports:in1"
    sensor_module.INPUT_2 = "ev3-ports:in2"
    sensor_module.INPUT_3 = "ev3-ports:in3"
    sensor_module.INPUT_4 = "ev3-ports:in4"
    lego_module = types.ModuleType("ev3dev2.sensor.lego")
    port_module = types.ModuleType("ev3dev2.port")

    class FakeGyroSensor(object):
        pass

    class FakeLegoPort(object):
        pass

    lego_module.GyroSensor = FakeGyroSensor
    port_module.LegoPort = FakeLegoPort
    modules = {
        "ev3dev2": ev3dev2_module,
        "ev3dev2.port": port_module,
        "ev3dev2.sensor": sensor_module,
        "ev3dev2.sensor.lego": lego_module
    }
    old_modules = dict((key, sys.modules.get(key)) for key in modules)
    try:
        sys.modules.update(modules)
        loaded = Ev3GyroSensorAdapter._load_ev3_factories("in3")
    finally:
        for key, value in old_modules.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value

    assert loaded[0] is FakeGyroSensor
    assert loaded[1] is FakeLegoPort
    assert loaded[2] == "ev3-ports:in3"


def test_gyro_monitor_publishes_samples_and_sensor_metadata():
    sensor = SensorPort([10.0, 11.0])
    store = HeadingStateStore()
    clock_values = iter([1.0, 2.0])
    monitor = GyroHeadingMonitor(
        sensor, store, sensor_code="GYR", address="in3",
        mode="GYRO-ANG", interval_seconds=0.02,
        clock=lambda: next(clock_values)
    )

    monitor.on_initialize()
    first = store.get_snapshot()
    monitor.on_cycle()
    second = store.get_snapshot()
    monitor.on_finalize()

    assert first["heading_deg"] == 10.0
    assert second["heading_deg"] == 11.0
    assert second["sensor_code"] == "GYR"
    assert second["address"] == "in3"
    assert second["mode"] == "GYRO-ANG"
    assert monitor.critical is True
    assert (sensor.open_calls, sensor.close_calls) == (1, 1)


def test_gyro_monitor_marks_cache_unavailable_before_failure_threshold():
    sensor = SensorPort([5.0, RuntimeError("read failed")])
    store = HeadingStateStore()
    clock_values = iter([1.0, 2.0])
    monitor = GyroHeadingMonitor(
        sensor, store, max_consecutive_failures=2,
        clock=lambda: next(clock_values)
    )
    monitor.on_initialize()

    monitor.on_cycle()

    snapshot = store.get_snapshot()
    assert snapshot["available"] is False
    assert snapshot["heading_deg"] == 5.0
    assert "read failed" in snapshot["error"]


def test_field_sensor_query_exposes_only_fresh_cached_gyro():
    now = [10.0]
    store = HeadingStateStore()
    query = HeadingStateQueryAdapter(
        store, max_age_seconds=0.1, clock=lambda: now[0]
    )
    adapter = FieldManualSensorQueryAdapter(
        {"GYR": {"name": "Gyroscope", "address": "in3", "mode": "GYRO-ANG"}},
        gyro_sensor_code="GYR",
        heading_query_port=query
    )
    store.update(
        42.0, sample_monotonic=10.0, sensor_code="GYR",
        address="in3", mode="GYRO-ANG"
    )

    sensor = adapter.read_sensor("GYR")
    assert sensor["connected"] is True
    assert sensor["monitoring"] is True
    assert sensor["value"] == 42.0

    now[0] = 10.2
    sensor = adapter.read_sensor("GYR")
    assert sensor["connected"] is False
    assert sensor["value"] is None


def test_canonical_gyro_configuration_uses_in3_uart_and_mounting_sign():
    sensors = rover_config.get_sensor_definitions()
    heading = rover_config.get_field_heading_config()

    assert sensors["GYR"]["address"] == "in3"
    assert sensors["GYR"]["port_mode"] == "ev3-uart"
    assert sensors["GYR"]["mode"] == "GYRO-ANG"
    assert heading["sensor_code"] == "GYR"
    assert heading["poll_seconds"] == 0.02
    assert heading["max_age_seconds"] == 0.1
    assert heading["connection_timeout_seconds"] == 10.0
    assert heading["connection_retry_seconds"] == 0.1
    assert heading["reset_on_start"] is True
    assert heading["angle_sign"] == -1.0
    assert heading["angle_offset_deg"] == 0.0
    assert heading["max_consecutive_failures"] == 3


def test_field_heading_configuration_rejects_invalid_mounting_sign():
    config = rover_config.get_field_heading_config()
    config["angle_sign"] = 0.5
    with pytest.raises(RuntimeError, match="angle_sign"):
        rover_config.validate_field_heading_configuration(config)


def test_field_hardware_graph_autowires_only_dedicated_gyro_monitor(monkeypatch):
    monkeypatch.setattr(rover_assembly.rover_config, "HARDWARE_ENABLED", True)
    mode = OperationModeService(
        drive=Drives.MECANUM,
        centric=Centrics.FIELD
    )

    application = rover_assembly.build_local_manual_application(
        operation_mode_service=mode
    )

    assert len(application.monitors) == 1
    assert isinstance(application.monitors[0], GyroHeadingMonitor)
    joystick_services = [
        item for item in application.managed_services
        if isinstance(item, JoystickControlService)
    ]
    assert len(joystick_services) == 1
    assert isinstance(
        joystick_services[0].heading_query_port,
        HeadingStateQueryAdapter
    )


def test_chassis_hardware_graph_does_not_construct_gyro_monitor(monkeypatch):
    monkeypatch.setattr(rover_assembly.rover_config, "HARDWARE_ENABLED", True)
    mode = OperationModeService(
        drive=Drives.MECANUM,
        centric=Centrics.CHASSIS
    )

    application = rover_assembly.build_local_manual_application(
        operation_mode_service=mode
    )

    assert application.monitors == []
