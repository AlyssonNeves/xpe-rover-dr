#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Application service that builds the consolidated Rover state."""

from datetime import datetime

from ports.monitor_diagnostics_port import MonitorDiagnosticsPort
from ports.rover_state_query_port import RoverStateQueryPort


class RoverStateService(RoverStateQueryPort):
    """Queries application ports and consolidates a read-only state snapshot."""

    def __init__(self, sensor_query_port=None, motor_query_port=None,
                 controller_port=None, monitors=None,
                 operation_mode_service=None):
        self.sensor_query_port = sensor_query_port
        self.motor_query_port = motor_query_port
        self.controller_port = controller_port
        self.monitors = dict(monitors or {})
        self.operation_mode_service = operation_mode_service
        for name, monitor in self.monitors.items():
            if monitor is not None and not isinstance(
                    monitor, MonitorDiagnosticsPort):
                raise TypeError(
                    "Monitor '{}' must implement MonitorDiagnosticsPort."
                    .format(name)
                )

    def get_rover_state(self):
        return {
            "controller": self._get_controller(),
            "sensors": self._get_sensors(),
            "motors": self._get_motors(),
            "system": self._get_system(),
            "monitors": self._get_monitors(),
            "operation": self._get_operation_mode(),
            "timestamp": self._get_timestamp()
        }

    def _get_sensors(self):
        if self.sensor_query_port is None:
            return []
        return self.sensor_query_port.read_all_sensors()

    def _get_motors(self):
        if self.motor_query_port is None:
            return []
        return self.motor_query_port.read_all_motors()

    def _get_controller(self):
        if self.controller_port is None:
            return {"connected": False}
        return self.controller_port.read_controller_status()

    def _get_system(self):
        if self.controller_port is None:
            return {}
        return self.controller_port.read_system_status()

    def _get_monitors(self):
        return {
            name: self._get_monitor_state(monitor)
            for name, monitor in self.monitors.items()
        }

    @staticmethod
    def _get_monitor_state(monitor):
        if monitor is None:
            return {
                "failed": False,
                "critical": False,
                "failure_type": None,
                "failure_message": None
            }
        return monitor.get_failure_state()

    def _get_operation_mode(self):
        if self.operation_mode_service is None:
            return {}
        return self.operation_mode_service.get_snapshot()

    @staticmethod
    def _get_timestamp():
        return datetime.now().strftime("%d/%m/%y %H:%M:%S.%f")[:-3]
