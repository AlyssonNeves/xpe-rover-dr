import types
import pytest

from services.ev3dev2_motor_gateway import Ev3Dev2MotorGateway, Ev3Dev2MotorGatewayError
from tests.unit.fakes import FakeMotorPort


class FakeLargeMotor(object):
    def __init__(self, address):
        self.address = address
        self._stop_action = "coast"
        self.position = 0
        self.speed = 0
        self.state = []

    @property
    def stop_action(self):
        return self._stop_action

    @stop_action.setter
    def stop_action(self, value):
        self._stop_action = value

    def stop(self):
        self.state = []

    def off(self):
        self.state = []

    def run_forever(self, **kwargs):
        self.state = ["running"]
        return None


class FakeSpeedPercent(object):
    def __init__(self, value): self.value = value


def fake_module():
    module = types.ModuleType("ev3dev2.motor")
    module.LargeMotor = FakeLargeMotor
    module.MediumMotor = FakeLargeMotor
    module.SpeedPercent = FakeSpeedPercent
    module.OUTPUT_A = "outA"
    return module


def test_gateway_catalog_create_property_and_delete():
    port = FakeMotorPort()
    gateway = Ev3Dev2MotorGateway(port, motor_module=fake_module(), object_ttl_seconds=60)
    try:
        catalog = gateway.catalog()
        assert "LargeMotor" in catalog["classes"]
        created = gateway.create("LargeMotor", args=["outA"], object_id="m1")
        assert created["motor_codes"] == ["LLM"]
        assert gateway.list_objects()[0]["object_id"] == "m1"
        assert gateway.get_property("m1", "stop_action")["value"] == "coast"
        assert gateway.set_property("m1", "stop_action", "brake")["value"] == "brake"
        assert gateway.module_value("OUTPUT_A")["value"] == "outA"
        assert gateway.delete("m1")["deleted"] is True
    finally:
        gateway.close()


def test_gateway_rejects_unknown_ports_classes_and_dangerous_property():
    port = FakeMotorPort()
    gateway = Ev3Dev2MotorGateway(port, motor_module=fake_module())
    try:
        with pytest.raises(Ev3Dev2MotorGatewayError):
            gateway.create("LargeMotor", args=["outZ"])
        with pytest.raises(Ev3Dev2MotorGatewayError):
            gateway.create("Unknown", args=["outA"])
        gateway.create("LargeMotor", args=["outA"], object_id="m2")
        with pytest.raises(Ev3Dev2MotorGatewayError):
            gateway.set_property("m2", "speed_sp", 100)
        with pytest.raises(Ev3Dev2MotorGatewayError):
            gateway.get_property("missing", "position")
    finally:
        gateway.close()
