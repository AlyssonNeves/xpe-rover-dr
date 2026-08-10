#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""AST-based regression tests for Rover architecture boundaries."""

import ast
import inspect
from pathlib import Path

from adapters.out_local_manual_queries import LocalManualMotorQueryAdapter
from app.monitor_registration import MonitorRegistration
from app.services.joystick_control_service import JoystickControlService
from app.services.manual_drive_service import ManualDriveService
from bootstrap import rover_assembly
from infrastructure.monitoring.motor_monitor import MotorMonitor
from ports.manual_drive_port import ManualDrivePort
from ports.motor_query_port import MotorQueryPort


ROOT = Path(__file__).parents[2]


def _imports(path):
    tree = ast.parse((ROOT / path).read_text())
    result = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            result.append(node.module)
        elif isinstance(node, ast.Import):
            result.extend(alias.name for alias in node.names)
    return result


def _called_names(function):
    tree = ast.parse(inspect.getsource(function))
    return {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def test_manual_service_implements_dedicated_output_port():
    assert issubclass(ManualDriveService, ManualDrivePort)


def test_local_manual_motor_adapter_is_read_only():
    assert issubclass(LocalManualMotorQueryAdapter, MotorQueryPort)
    forbidden = {
        "stop_motor", "run_timed_motor", "run_forever_motor",
        "run_direct_motor", "drive_tank", "execute_guarded_operation"
    }
    assert forbidden.isdisjoint(vars(LocalManualMotorQueryAdapter))


def test_joystick_service_uses_explicit_manual_drive_contract_only():
    source = inspect.getsource(JoystickControlService)
    assert "hasattr(" not in source
    assert "manual_drive_port" in source
    assert "self.motor_port" not in source


def test_local_manual_graph_excludes_general_monitored_components():
    called = _called_names(rover_assembly.build_local_manual_application)
    assert "MotorMonitor" not in called
    assert "SensorMonitor" not in called
    assert "ControllerMonitor" not in called
    assert "DriveService" not in called
    assert "Ev3Dev2MotorGateway" not in called
    assert "ManualDriveService" in called


def test_motor_monitor_has_no_manual_session_api_or_joystick_dependency():
    forbidden = {
        "acquire_manual_control", "renew_manual_control",
        "release_manual_control", "set_manual_motor_speed"
    }
    assert forbidden.isdisjoint(vars(MotorMonitor))
    assert "joystick" not in inspect.getsource(MotorMonitor).lower()


def test_application_layer_does_not_import_adapters_or_infrastructure():
    for file_path in sorted((ROOT / "app").rglob("*.py")):
        path = file_path.relative_to(ROOT)
        imports = _imports(path)
        assert not any(name.startswith("adapters") for name in imports), path
        assert not any(name.startswith("infrastructure") for name in imports), path


def test_ports_do_not_import_application_or_implementations():
    forbidden_prefixes = ("app", "adapters", "infrastructure")
    for file_path in sorted((ROOT / "ports").rglob("*.py")):
        path = file_path.relative_to(ROOT)
        imports = _imports(path)
        assert not any(
            name.startswith(forbidden_prefixes) for name in imports
        ), path


def test_rest_gateway_dispatch_is_explicit_not_reflective():
    path = ROOT / "adapters/in_rest_api_server.py"
    tree = ast.parse(path.read_text())
    imported_names = _imports(path.relative_to(ROOT))
    assert "adapters.rest.api_routes" in imported_names
    assert not any(
        isinstance(node, ast.Call) and
        isinstance(node.func, ast.Name) and
        node.func.id == "getattr" and
        node.args and
        isinstance(node.args[0], ast.Name) and
        node.args[0].id == "motor_gateway_port"
        for node in ast.walk(tree)
    )


def test_monitor_criticality_is_explicit_in_composition_root():
    source = inspect.getsource(rover_assembly.build_standard_application)
    assert "MonitorRegistration" in source
    assert "MonitorRegistration(sensor_monitor, \"Sensor\", True)" in source
    assert "MonitorRegistration(motor_monitor, \"Motor\", True)" in source
    assert isinstance(MonitorRegistration(object(), "test", True).critical, bool)
