#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from pathlib import Path
from types import ModuleType

import pytest

from infrastructure.ev3.ev3dev2_motor_gateway import Ev3Dev2MotorGateway, Ev3Dev2MotorGatewayError


class DemoSpeed(object):
    def __init__(self, value):
        self.value = value


class LargeMotor(object):
    def __init__(self, address=None):
        self.address = address
        self._position = 0

    @property
    def position(self):
        return self._position

    @position.setter
    def position(self, value):
        self._position = value

    def on_for_rotations(self, speed, rotations):
        self._position += rotations
        return self._position

    def on(self, speed, brake=True, block=False):
        return True

    def off(self, brake=True):
        return brake

    def wait(self, condition, timeout=None):
        return True


class MediumMotor(LargeMotor):
    pass


class MotorSet(object):
    def __init__(self, motor_specs=None, desc=None):
        self.motor_specs = motor_specs or {}

    def off(self, brake=True):
        return brake


class MoveTank(object):
    def __init__(self, left_motor_port, right_motor_port):
        self.ports = (left_motor_port, right_motor_port)

    def on_for_seconds(self, left_speed, right_speed, seconds, brake=True, block=True):
        return seconds


class MoveSteering(MoveTank):
    pass


class MoveJoystick(MoveTank):
    pass


class MoveDifferential(MoveTank):
    pass


class UnsafeMotor(object):
    pass


class FakeMotorPort(object):
    def __init__(self):
        self.guarded = []

    def list_motors(self):
        return [
            {"code": "ML", "address": "outB"},
            {"code": "MR", "address": "outC"}
        ]

    def read_motor(self, code):
        return {"code": code, "max_speed": 1050, "state": []}

    def begin_guarded_operation(self, motor_codes, operation_name, operation_id):
        self.guarded.append((list(motor_codes), operation_name))
        return {"operation_id": operation_id}

    def end_guarded_operation(self, operation_id, status="COMPLETED", error=None, stop=False):
        return {"operation_id": operation_id, "status": status, "stop": stop}

    def execute_guarded_operation(self, motor_codes, operation_name, operation):
        self.guarded.append((list(motor_codes), operation_name))
        return operation()


def _module():
    module = ModuleType("ev3dev2.motor")
    for cls in (DemoSpeed, LargeMotor, MediumMotor, MotorSet, MoveTank,
                MoveSteering, MoveJoystick, MoveDifferential, UnsafeMotor):
        cls.__module__ = module.__name__
        setattr(module, cls.__name__, cls)
    module.OUTPUT_B = "outB"
    module.OUTPUT_C = "outC"
    return module


def test_gateway_exposes_only_supported_domain_classes_and_guards_motor_calls():
    port = FakeMotorPort()
    gateway = Ev3Dev2MotorGateway(port, port, motor_module=_module())
    catalog = gateway.catalog()
    assert set(catalog["classes"]) == Ev3Dev2MotorGateway.SUPPORTED_CLASSES
    created = gateway.create("LargeMotor", kwargs={"address": "outB"}, object_id="m1")
    assert created["motor_codes"] == ["ML"]
    result = gateway.invoke("m1", "on_for_rotations", args=[50, 3])
    assert result["result"] == 3
    assert port.guarded == [(["ML"], "LargeMotor.on_for_rotations")]
    assert gateway.set_property("m1", "position", 8)["value"] == 8
    assert port.guarded[-1] == (["ML"], "LargeMotor.position=")
    gateway.close()


def test_movement_helpers_are_bound_to_both_rover_motors_and_guarded():
    port = FakeMotorPort()
    gateway = Ev3Dev2MotorGateway(port, port, motor_module=_module())
    created = gateway.create("MoveTank", args=["outB", "outC"], object_id="tank")
    assert created["motor_codes"] == ["ML", "MR"]
    gateway.invoke("tank", "on_for_seconds", args=[30, 30, 1])
    assert port.guarded[-1] == (["ML", "MR"], "MoveTank.on_for_seconds")
    gateway.close()


def test_gateway_rejects_classes_outside_large_medium_motor_scope():
    gateway = Ev3Dev2MotorGateway(FakeMotorPort(), FakeMotorPort(), motor_module=_module())
    with pytest.raises(Ev3Dev2MotorGatewayError):
        gateway.create("UnsafeMotor")
    gateway.close()


def test_official_manifest_keeps_the_declared_motor_domain_helpers():
    manifest = json.loads(Path("docs/ev3dev2_motor_api_manifest.json").read_text())
    classes = set(manifest["classes"])
    assert {"LargeMotor", "MediumMotor", "MotorSet", "MoveTank", "MoveSteering", "MoveJoystick", "MoveDifferential"} <= classes
    assert {"follow_line", "follow_gyro_angle", "turn_degrees"} <= set(manifest["classes"]["MoveTank"]["methods"])
    assert {"on_to_coordinates", "odometry_start", "turn_to_angle"} <= set(manifest["classes"]["MoveDifferential"]["methods"])


def test_motor_set_rejects_partially_unknown_motor_specs():
    gateway = Ev3Dev2MotorGateway(FakeMotorPort(), FakeMotorPort(), motor_module=_module())
    with pytest.raises(Ev3Dev2MotorGatewayError):
        gateway.create(
            "MotorSet",
            kwargs={"motor_specs": {"outB": LargeMotor, "outD": MediumMotor}}
        )
    gateway.close()


def test_continuous_operation_requires_watchdog_and_remains_active_until_stop():
    port = FakeMotorPort()
    gateway = Ev3Dev2MotorGateway(port, port, motor_module=_module())
    gateway.create("LargeMotor", kwargs={"address": "outB"}, object_id="m1")
    with pytest.raises(Ev3Dev2MotorGatewayError):
        gateway.invoke("m1", "on", args=[50])
    gateway.close()


def test_wait_requires_explicit_timeout():
    gateway = Ev3Dev2MotorGateway(FakeMotorPort(), FakeMotorPort(), motor_module=_module())
    gateway.create("LargeMotor", kwargs={"address": "outB"}, object_id="m1")
    with pytest.raises(Ev3Dev2MotorGatewayError):
        gateway.invoke("m1", "wait", args=[lambda state: True])
    gateway.close()


def test_dangerous_setpoint_properties_are_rejected():
    gateway = Ev3Dev2MotorGateway(FakeMotorPort(), FakeMotorPort(), motor_module=_module())
    gateway.create("LargeMotor", kwargs={"address": "outB"}, object_id="m1")
    with pytest.raises(Ev3Dev2MotorGatewayError):
        gateway.set_property("m1", "speed_sp", 500)
    gateway.close()


def test_delete_stops_object_before_removal():
    gateway = Ev3Dev2MotorGateway(FakeMotorPort(), FakeMotorPort(), motor_module=_module())
    gateway.create("MotorSet", kwargs={"motor_specs": {"outB": LargeMotor}}, object_id="set1")
    result = gateway.delete("set1")
    assert result["hardware_stopped"] is True
    with pytest.raises(Ev3Dev2MotorGatewayError):
        gateway.describe("set1")
    gateway.close()

def test_list_operations_returns_gateway_operation_snapshots():
    gateway = Ev3Dev2MotorGateway(FakeMotorPort(), FakeMotorPort(), motor_module=_module())
    gateway.create("LargeMotor", kwargs={"address": "outB"}, object_id="m1")
    assert gateway.list_operations() == []
    gateway.close()


def test_gateway_object_listing_properties_constants_and_duplicate_ids():
    gateway = Ev3Dev2MotorGateway(FakeMotorPort(), FakeMotorPort(), motor_module=_module(), max_objects=2)
    gateway.create("LargeMotor", kwargs={"address": "outB"}, object_id="m1")
    assert gateway.list_objects()[0]["object_id"] == "m1"
    assert gateway.get_property("m1", "position")["value"] == 0
    assert gateway.module_value("OUTPUT_B")["value"] == "outB"
    with pytest.raises(Ev3Dev2MotorGatewayError):
        gateway.create("LargeMotor", kwargs={"address": "outB"}, object_id="m1")
    with pytest.raises(Ev3Dev2MotorGatewayError):
        gateway.get_property("m1", "_position")
    with pytest.raises(Ev3Dev2MotorGatewayError):
        gateway.get_property("m1", "missing")
    gateway.close()


def test_gateway_validates_nonblocking_timeout_watchdog_and_dynamic_limits():
    gateway = Ev3Dev2MotorGateway(FakeMotorPort(), FakeMotorPort(), motor_module=_module())
    gateway.create("LargeMotor", kwargs={"address": "outB"}, object_id="m1")
    with pytest.raises(Ev3Dev2MotorGatewayError):
        gateway.invoke("m1", "on", args=[50], kwargs={"block": False})
    result = gateway.invoke(
        "m1", "on", args=[50],
        kwargs={"block": False, "rover_timeout_ms": 100, "rover_watchdog_ms": 100}
    )
    assert result["operation_id"]
    with pytest.raises(Ev3Dev2MotorGatewayError):
        gateway.invoke("m1", "on", args=[50], kwargs={"rover_watchdog_ms": 0})
    with pytest.raises(Ev3Dev2MotorGatewayError):
        gateway._validate_speed(2000, 1050)
    gateway.close()


def test_gateway_resolves_speed_tuple_and_rejects_private_or_unknown_members():
    gateway = Ev3Dev2MotorGateway(FakeMotorPort(), FakeMotorPort(), motor_module=_module())
    resolved = gateway._resolve({"$tuple": [1, 2]})
    assert resolved == (1, 2)
    with pytest.raises(Ev3Dev2MotorGatewayError):
        gateway._resolve({"$speed": "DemoSpeed", "value": 20})
    with pytest.raises(Ev3Dev2MotorGatewayError):
        gateway.create("_LargeMotor")
    gateway.create("LargeMotor", kwargs={"address": "outB"}, object_id="m1")
    with pytest.raises(Ev3Dev2MotorGatewayError):
        gateway.invoke("m1", "missing")
    with pytest.raises(Ev3Dev2MotorGatewayError):
        gateway.module_value("_SECRET")
    gateway.close()
