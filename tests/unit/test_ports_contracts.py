#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Tests for formal abstract output port contracts."""

import inspect
import unittest

from ports.command_control_selector_port import CommandControlSelectorPort
from ports.controller_port import ControllerPort
from ports.joystick_port import JoystickPort
from ports.local_drive_setup_selector_port import LocalDriveSetupSelectorPort
from ports.manual_drive_port import ManualDrivePort
from ports.motor_hardware_port import MotorHardwarePort
from ports.operator_alert_port import OperatorAlertPort
from ports.drive_port import DrivePort
from ports.motor_port import MotorPort
from ports.rover_state_query_port import RoverStateQueryPort
from ports.sensor_command_port import SensorCommandPort
from ports.sensor_query_port import SensorQueryPort
from ports.startup_progress_port import StartupProgressPort
from ports.status_led_port import StatusLedPort


class PortContractsTestCase(unittest.TestCase):
    """Ensures ports are explicit abstract contracts."""

    def test_all_ports_are_abstract(self):
        for port_class in (
            SensorQueryPort,
            SensorCommandPort,
            MotorPort,
            ControllerPort,
            RoverStateQueryPort,
            DrivePort,
            CommandControlSelectorPort,
            LocalDriveSetupSelectorPort,
            JoystickPort,
            ManualDrivePort,
            MotorHardwarePort,
            OperatorAlertPort,
            StartupProgressPort,
            StatusLedPort,
        ):
            self.assertTrue(inspect.isabstract(port_class))

    def test_abstract_ports_cannot_be_instantiated(self):
        for port_class in (
            SensorQueryPort,
            SensorCommandPort,
            MotorPort,
            ControllerPort,
            RoverStateQueryPort,
            DrivePort,
            CommandControlSelectorPort,
            LocalDriveSetupSelectorPort,
            JoystickPort,
            ManualDrivePort,
            MotorHardwarePort,
            OperatorAlertPort,
            StartupProgressPort,
            StatusLedPort,
        ):
            with self.assertRaises(TypeError):
                port_class()

    def test_concrete_controller_adapter_implements_port_contract(self):
        class ControllerAdapter(ControllerPort):
            def read_controller_status(self):
                return {"status": "ok"}

            def read_network_status(self):
                return {"network": "ok"}

            def read_battery_status(self):
                return {"battery": "ok"}

            def read_system_status(self):
                return {"system": "ok"}

        adapter = ControllerAdapter()


if __name__ == "__main__":
    unittest.main()
