import inspect

from ports.controller_port import ControllerPort
from ports.drive_port import DrivePort
from ports.motor_port import MotorPort
from ports.rover_state_query_port import RoverStateQueryPort
from ports.sensor_port import SensorPort


def test_ports_are_abstract_contracts():
    for cls in (ControllerPort, DrivePort, MotorPort, RoverStateQueryPort, SensorPort):
        assert inspect.isabstract(cls)
