#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Regression tests for the S02.10 hexagonal architecture refactoring."""

import ast
import inspect
from pathlib import Path

from adapters.out_ev3_motor_hardware import Ev3MotorHardwareAdapter
from adapters.out_local_manual_queries import (
    LocalManualMotorQueryAdapter, LocalManualSensorQueryAdapter
)
from app.services.manual_drive_service import ManualDriveService
from bootstrap import rover_assembly
from infrastructure.ev3.ev3dev2_motor_gateway import Ev3Dev2MotorGateway
from infrastructure.monitoring.motor_monitor import MotorMonitor
from ports.guarded_motor_operation_port import GuardedMotorOperationPort
from ports.motor_command_port import MotorCommandPort
from ports.motor_command_query_port import MotorCommandQueryPort
from ports.motor_gateway_port import MotorGatewayPort
from ports.motor_port import MotorPort
from ports.motor_query_port import MotorQueryPort
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


def test_legacy_services_package_is_removed():
    assert not (ROOT / "services").exists()


def test_application_layer_has_no_concrete_adapter_or_infrastructure_imports():
    for path in sorted((ROOT / "app").rglob("*.py")):
        imports = _imports(path.relative_to(ROOT))
        assert not any(name.startswith("adapters") for name in imports), path
        assert not any(name.startswith("infrastructure") for name in imports), path


def test_ports_have_no_inward_or_concrete_dependencies():
    for path in sorted((ROOT / "ports").rglob("*.py")):
        imports = _imports(path.relative_to(ROOT))
        assert not any(
            name.startswith(("app", "adapters", "infrastructure"))
            for name in imports
        ), path


def test_main_is_entry_point_and_concrete_assembly_is_in_bootstrap():
    imports = _imports("main.py")
    assert "bootstrap.rover_assembly" in imports
    assert not any(name.startswith("adapters") for name in imports)
    assert not any(name.startswith("app") for name in imports)
    assert not any(name.startswith("infrastructure") for name in imports)
    source = (ROOT / "main.py").read_text()
    assert "RestApiServer(" not in source
    assert "MotorMonitor(" not in source
    assert "prepare_rover_runtime()" in source


def test_local_manual_graph_stays_monitor_and_queue_free():
    source = inspect.getsource(rover_assembly.build_local_manual_application)
    assert "MotorMonitor(" not in source
    assert "SensorMonitor(" not in source
    assert "ControllerMonitor(" not in source
    assert "Ev3Dev2MotorGateway(" not in source
    assert "ManualDriveService(" in source


def test_local_manual_query_adapters_use_focused_read_only_ports():
    assert issubclass(LocalManualMotorQueryAdapter, MotorQueryPort)
    assert issubclass(LocalManualSensorQueryAdapter, SensorQueryPort)
    forbidden = {
        "stop_motor", "run_timed_motor", "run_forever_motor",
        "run_synchronized_motors", "execute_guarded_operation"
    }
    assert forbidden.isdisjoint(vars(LocalManualMotorQueryAdapter))


def test_motor_contract_is_composed_from_segregated_ports():
    assert issubclass(MotorPort, MotorQueryPort)
    assert issubclass(MotorPort, MotorCommandPort)
    assert issubclass(MotorPort, MotorCommandQueryPort)
    assert issubclass(MotorPort, GuardedMotorOperationPort)


def test_motor_gateway_implements_explicit_gateway_port():
    assert issubclass(Ev3Dev2MotorGateway, MotorGatewayPort)
    source = (ROOT / "adapters/rest/routing.py").read_text()
    assert "getattr(self.gateway" not in source


def test_monitor_and_manual_adapter_share_driver_repository():
    monitor_source = inspect.getsource(MotorMonitor)
    adapter_source = inspect.getsource(Ev3MotorHardwareAdapter)
    assert "Ev3MotorDriverRepository" in monitor_source
    assert "Ev3MotorDriverRepository" in adapter_source


def test_motor_state_collection_is_extracted_from_monitor():
    source = inspect.getsource(MotorMonitor)
    assert "MotorStateCollector" in source
    assert "def _base_snapshot" not in source


def test_domain_handler_monolith_is_replaced_by_focused_modules():
    assert not (ROOT / "app/commands/domain_handlers.py").exists()
    for filename in (
        "base_handler.py", "sensor_handler.py", "motor_handler.py",
        "controller_handler.py", "state_handler.py", "drive_handler.py"
    ):
        assert (ROOT / "app/commands" / filename).is_file()


def test_rest_routes_are_resolved_from_declarative_table():
    command_routes = (ROOT / "adapters/rest/command_routes.py").read_text()
    api_routes = (ROOT / "adapters/rest/api_routes.py").read_text()
    assert "ApiRouteTable" in command_routes
    assert "RouteDispatcher" in api_routes
    assert 'c("GET", ("api", "motors"' in api_routes


def test_manual_drive_remains_application_service_with_ports_only():
    imports = _imports("app/services/manual_drive_service.py")
    assert not any(name.startswith("infrastructure") for name in imports)
    assert not any(name.startswith("adapters") for name in imports)
    assert "motor_hardware_port" in inspect.getsource(ManualDriveService)
