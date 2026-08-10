from services.manual_motor_hardware import (
    DirectMotorHardwareBackend, DirectMotorRegistry
)


class FakeMotor(object):
    def __init__(self, address):
        self.address = address
        self.connected = True
        self.polarity = "normal"
        self.stop_action = "coast"
        self.speed_sp = None
        self.stopped = False

    def run_forever(self, speed_sp):
        self.speed_sp = speed_sp

    def stop(self):
        self.stopped = True


class BrokenMotor(FakeMotor):
    def run_forever(self, speed_sp):
        raise IOError("driver failure")


def definitions():
    return {
        "LLM": {
            "address": "outA", "motor_class": "LargeMotor",
            "polarity": "inversed"
        }
    }


def test_direct_registry_connects_once_and_applies_polarity():
    backend = DirectMotorHardwareBackend({"LargeMotor": FakeMotor})
    registry = DirectMotorRegistry(definitions(), backend)
    first = registry.get_motor("LLM")
    second = registry.get_motor("LLM")
    assert first is second
    assert first.address == "outA"
    assert first.polarity == "inversed"


def test_direct_registry_runs_and_stops_without_queue():
    backend = DirectMotorHardwareBackend({"LargeMotor": FakeMotor})
    registry = DirectMotorRegistry(definitions(), backend)
    success, error = registry.run_forever_motor("LLM", 320, "brake")
    assert success is True and error is None
    motor = registry.get_motor("LLM")
    assert motor.speed_sp == 320
    assert motor.stop_action == "brake"
    success, error = registry.stop_motor("LLM", "hold")
    assert success is True and error is None
    assert motor.stopped is True
    assert motor.stop_action == "hold"


def test_direct_registry_reports_unknown_or_unavailable_motor():
    backend = DirectMotorHardwareBackend({"LargeMotor": FakeMotor})
    registry = DirectMotorRegistry(definitions(), backend)
    assert registry.get_motor("BAD") is None
    assert registry.get_error("BAD") == "Unknown motor code"


def test_direct_registry_captures_driver_write_failure():
    backend = DirectMotorHardwareBackend({"LargeMotor": BrokenMotor})
    registry = DirectMotorRegistry(definitions(), backend)
    success, error = registry.run_forever_motor("LLM", 100)
    assert success is False
    assert "driver failure" in error
