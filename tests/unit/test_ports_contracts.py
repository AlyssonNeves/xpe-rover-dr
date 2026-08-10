import inspect

from ports.controller_port import ControllerPort
from ports.drive_port import DrivePort
from ports.joystick_port import JoystickPort
from ports.motor_port import MotorPort
from ports.command_control_selector_port import CommandControlSelectorPort
from ports.rover_state_query_port import RoverStateQueryPort
from ports.sensor_port import SensorPort


def test_ports_are_abstract_contracts():
    contracts = (
        ControllerPort,
        DrivePort,
        JoystickPort,
        MotorPort,
        CommandControlSelectorPort,
        RoverStateQueryPort,
        SensorPort
    )
    for cls in contracts:
        assert inspect.isabstract(cls)
