from infrastructure.ev3.motor_driver_factory import Ev3MotorDriverFactory
from infrastructure.motor.driver_repository import Ev3MotorDriverRepository


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


def build_repository(motor_class):
    factory = Ev3MotorDriverFactory(motor_classes={"LargeMotor": motor_class})
    return Ev3MotorDriverRepository(definitions(), factory)


def test_shared_repository_connects_once_and_applies_polarity():
    repository = build_repository(FakeMotor)
    first = repository.get_motor("LLM")
    second = repository.get_motor("LLM")
    assert first is second
    assert first.address == "outA"
    assert first.polarity == "inversed"


def test_shared_repository_runs_and_stops_without_queue():
    repository = build_repository(FakeMotor)
    success, error = repository.run_forever_motor("LLM", 320, "brake")
    assert success is True and error is None
    motor = repository.get_motor("LLM")
    assert motor.speed_sp == 320
    assert motor.stop_action == "brake"
    success, error = repository.stop_motor("LLM", "hold")
    assert success is True and error is None
    assert motor.stopped is True
    assert motor.stop_action == "hold"


def test_shared_repository_reports_unknown_motor():
    repository = build_repository(FakeMotor)
    assert repository.get_motor("BAD") is None
    assert repository.get_error("BAD") == "Unknown motor code"


def test_shared_repository_captures_driver_write_failure():
    repository = build_repository(BrokenMotor)
    success, error = repository.run_forever_motor("LLM", 100)
    assert success is False
    assert "driver failure" in error


def test_motor_driver_factory_owns_global_polarity_application():
    factory = Ev3MotorDriverFactory(
        motor_classes={"LargeMotor": FakeMotor}
    )
    motor = factory.create_motor({
        "address": "outA",
        "motor_class": "LargeMotor",
        "polarity": "inversed"
    })

    assert motor.address == "outA"
    assert motor.polarity == "inversed"
