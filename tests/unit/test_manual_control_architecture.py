#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Regression tests for LOCAL + MANUAL hexagonal boundaries."""

import ast
from pathlib import Path

from adapters.in_evdev_joystick import EvdevJoystickAdapter
from adapters.out_ev3_motor_hardware import Ev3MotorHardwareAdapter
from adapters.out_motor_state_publisher import MotorStateStorePublisherAdapter
from ports.joystick_port import JoystickPort
from ports.manual_drive_port import ManualDrivePort
from ports.motor_hardware_port import MotorHardwarePort
from ports.motor_state_publisher_port import MotorStatePublisherPort
from services.manual_drive_service import ManualDriveService


ROOT = Path(__file__).parents[2]


def _imports(relative_path):
    tree = ast.parse((ROOT / relative_path).read_text())
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
        elif isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
    return names


def test_manual_control_implementations_conform_to_explicit_ports():
    assert issubclass(EvdevJoystickAdapter, JoystickPort)
    assert issubclass(ManualDriveService, ManualDrivePort)
    assert issubclass(Ev3MotorHardwareAdapter, MotorHardwarePort)
    assert issubclass(MotorStateStorePublisherAdapter, MotorStatePublisherPort)


def test_manual_application_services_do_not_import_concrete_adapters():
    for relative_path in (
        "services/joystick_control_service.py",
        "services/manual_drive_service.py"
    ):
        imports = _imports(relative_path)
        assert not any(name.startswith("adapters") for name in imports), (
            relative_path, imports
        )


def test_manual_drive_service_does_not_depend_on_monitor_or_state_store():
    imports = _imports("services/manual_drive_service.py")
    assert "services.motor_monitor" not in imports
    assert "services.motor_state_store" not in imports
    tree = ast.parse((ROOT / "services/manual_drive_service.py").read_text())
    referenced_names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    assert "MotorMonitor" not in referenced_names
    assert "MotorStateStore" not in referenced_names


def test_manual_control_ports_are_independent_from_implementations():
    for relative_path in (
        "ports/joystick_port.py",
        "ports/manual_drive_port.py",
        "ports/motor_hardware_port.py",
        "ports/motor_state_publisher_port.py"
    ):
        imports = _imports(relative_path)
        forbidden = ("adapters", "services", "app")
        assert not any(name.startswith(forbidden) for name in imports), (
            relative_path, imports
        )


def test_hardware_write_and_state_publication_are_separate_contracts():
    hardware_methods = set(vars(MotorHardwarePort))
    publisher_methods = set(vars(MotorStatePublisherPort))

    assert "publish_motor_state" not in hardware_methods
    assert "run_forever" not in publisher_methods
    assert "stop" not in publisher_methods
