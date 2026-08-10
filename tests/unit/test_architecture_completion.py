#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Regression tests for the v0.48.0 canonical architecture boundaries."""

import ast
import inspect
from pathlib import Path

from adapters.in_rest_api_server import RestApiServer, RoverRequestHandler
from adapters.out_ev3_motor_hardware import Ev3MotorHardwareAdapter
from adapters.out_local_manual_queries import LocalManualSensorQueryAdapter
from app.rover_application import RoverApplication
from app.rover_config import build_default_configuration_values
from bootstrap import rover_assembly
from app.services.drive_service import DriveService
from app.services.joystick_control_service import JoystickControlService
from app.services.manual_drive_service import ManualDriveService
from infrastructure.monitoring.motor_monitor import MotorMonitor
from ports.sensor_query_port import SensorQueryPort


ROOT = Path(__file__).parents[2]


def _imports(relative_path):
    tree = ast.parse((ROOT / relative_path).read_text())
    result = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.append(node.module)
    return result


def test_main_is_only_an_entry_point_and_imports_no_concrete_layers():
    imports = _imports("main.py")
    forbidden = ("adapters", "app", "infrastructure", "ports")
    assert not any(name.startswith(forbidden) for name in imports)
    assert "bootstrap.rover_assembly" in imports
    source = (ROOT / "main.py").read_text()
    assert "prepare_rover_runtime()" in source
    assert "RestApiServer(" not in source
    assert "MotorMonitor(" not in source


def test_application_configuration_modules_have_no_import_time_io():
    for relative_path in ("app/configuration.py", "app/rover_config.py"):
        path = ROOT / relative_path
        tree = ast.parse(path.read_text())
        top_level_calls = [
            node for node in tree.body if isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
        ]
        assert not top_level_calls, relative_path
        top_level_imports = []
        for node in tree.body:
            if isinstance(node, ast.Import):
                top_level_imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                top_level_imports.append(node.module)
        assert "json" not in top_level_imports
        assert "os" not in top_level_imports


def _module_level_assignment_names(relative_path):
    tree = ast.parse((ROOT / relative_path).read_text())
    result = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                result.add(target.id)
    return result


def test_adapters_do_not_declare_canonical_business_defaults():
    canonical_keys = set(build_default_configuration_values())
    violations = []
    for path in (ROOT / "adapters").rglob("*.py"):
        relative_path = path.relative_to(ROOT)
        for name in _module_level_assignment_names(relative_path):
            normalized = name.lower()
            matches_canonical_key = any(
                normalized == key or normalized.endswith("_" + key)
                for key in canonical_keys
            )
            if matches_canonical_key:
                violations.append("{}:{}".format(relative_path, name))
    assert not violations, violations

    security_attributes = (
        "shutdown_token",
        "hardware_api_token",
        "shutdown_confirmation_required"
    )
    for name in security_attributes:
        assert name not in vars(RoverRequestHandler)


def test_rest_api_server_requires_explicit_transport_and_security_values():
    signature = inspect.signature(RestApiServer.__init__)
    empty = inspect.Parameter.empty
    required = (
        "host",
        "port",
        "shutdown_token",
        "hardware_api_token",
        "shutdown_confirmation_required"
    )
    for name in required:
        assert signature.parameters[name].default is empty


def test_rest_assembly_forwards_resolved_configuration(monkeypatch):
    captured = {}
    expected_server = object()

    class Configuration(object):
        rest_host = "127.0.0.1"
        rest_port = 9090
        shutdown_token = "shutdown-token"
        hardware_api_token = "hardware-token"
        shutdown_confirmation_required = False

    def build_server(**kwargs):
        captured.update(kwargs)
        return expected_server

    monkeypatch.setattr(rover_assembly, "RestApiServer", build_server)
    command_service = object()
    motor_gateway_port = object()
    result = rover_assembly._build_rest_server(
        command_service, Configuration(), motor_gateway_port
    )

    assert result is expected_server
    assert captured == {
        "command_service": command_service,
        "host": "127.0.0.1",
        "port": 9090,
        "motor_gateway_port": motor_gateway_port,
        "shutdown_token": "shutdown-token",
        "hardware_api_token": "hardware-token",
        "shutdown_confirmation_required": False
    }


def test_local_manual_sensor_adapter_is_strictly_query_only():
    assert issubclass(LocalManualSensorQueryAdapter, SensorQueryPort)
    assert "change_sensor_mode" not in vars(LocalManualSensorQueryAdapter)


def test_manual_drive_uses_explicit_state_publisher_port_not_store_duck_typing():
    source = inspect.getsource(ManualDriveService)
    assert "motor_state_publisher_port" in source
    assert "state_store" not in source
    assert "infrastructure" not in " ".join(_imports(
        "app/services/manual_drive_service.py"
    ))


def test_drive_services_do_not_own_business_configuration_defaults():
    manual_source = inspect.getsource(ManualDriveService)
    drive_source = inspect.getsource(DriveService)
    joystick_signature = str(inspect.signature(JoystickControlService.__init__))

    forbidden_manual_fragments = (
        '.get("left_motor_code"', '.get("front_left_motor_code"',
        '.get("front_left_speed_factor"', 'default_stop_action="brake"'
    )
    for fragment in forbidden_manual_fragments:
        assert fragment not in manual_source

    assert '.get("wheel_diameter_mm"' not in drive_source
    assert "max_speed_sp=600" not in joystick_signature
    assert "axis_center=127" not in joystick_signature


def test_rest_lifecycle_handler_does_not_create_threads():
    source = inspect.getsource(RoverRequestHandler._handle_lifecycle)
    assert "threading.Thread" not in source
    assert ".start()" not in source


def test_rover_application_has_no_process_or_threading_implementation_imports():
    imports = _imports("app/rover_application.py")
    assert "os" not in imports
    assert "sys" not in imports
    assert "threading" not in imports
    source = inspect.getsource(RoverApplication)
    module_source = (ROOT / "app/rover_application.py").read_text()
    assert "restart_current_process" in source
    assert "os.execv" not in source
    assert "_InlineEvent" not in module_source
    assert "_InlineConcurrency" not in module_source
    assert "_NullProcessControl" not in module_source


def test_rover_application_requires_explicit_lifecycle_ports():
    signature = inspect.signature(RoverApplication.__init__)
    empty = inspect.Parameter.empty
    assert signature.parameters["concurrency_port"].default is empty
    assert signature.parameters["process_control_port"].default is empty


def test_motor_monitor_coordinates_extracted_components():
    source = inspect.getsource(MotorMonitor)
    expected = (
        "MotorCommandScheduler", "MotorSafetyWatchdog", "MotorStateCollector",
        "MotorCommandExecutor", "MotorGuardedOperationManager",
        "SynchronizedMotorExecutor", "Ev3MotorDriverRepository"
    )
    for component in expected:
        assert component in source
    assert "queue.PriorityQueue" not in source


def test_manual_and_monitored_paths_share_repository_implementation():
    adapter_source = inspect.getsource(Ev3MotorHardwareAdapter)
    monitor_source = inspect.getsource(MotorMonitor)
    assert "Ev3MotorDriverRepository" in adapter_source
    assert "Ev3MotorDriverRepository" in monitor_source


def test_removed_compatibility_modules_do_not_return():
    removed_paths = (
        "app/commands/domain_handlers.py",
        "ports/sensor_port.py",
        "app/control_mode_service.py",
        "app/drive_system_setup_service.py",
        "app/mecanum_centric_setup_service.py",
        "adapters/out_ev3_control_mode_selector.py",
        "adapters/out_ev3_drive_system_setup_selector.py",
        "adapters/out_ev3_mecanum_centric_setup_selector.py",
        "ports/control_mode_selector_port.py",
        "ports/drive_system_setup_selector_port.py",
        "ports/mecanum_centric_setup_selector_port.py",
    )
    for relative_path in removed_paths:
        assert not (ROOT / relative_path).exists(), relative_path
