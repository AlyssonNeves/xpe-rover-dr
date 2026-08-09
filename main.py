#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Composition root and process lifecycle entry point for Rover-DR."""

import os
import signal
import sys

from adapters.in_rest_api_server import RestApiServer
from adapters.out_controller_monitor import ControllerMonitorAdapter
from adapters.out_drive_service import DriveServiceAdapter
from adapters.out_ev3_operation_mode_selector import Ev3OperationModeSelectorAdapter
from adapters.out_ev3_operator_alert import Ev3OperatorAlertAdapter
from adapters.out_motor_monitor import MotorMonitorAdapter
from adapters.out_rover_state_query import RoverStateQueryAdapter
from adapters.out_sensor_monitor import SensorMonitorAdapter
from app import rover_config
from app.command_service import CommandService
from app.operation_mode_service import OperationModeService
from app.rover_application import RoverApplication
from app.rover_config import REST_HOST, REST_PORT
from services.app_logger import AppLogger
from services.controller_monitor import ControllerMonitor
from services.controller_state_store import ControllerStateStore
from services.drive_service import DriveService
from services.ev3dev2_motor_gateway import (
    Ev3Dev2MotorGateway, Ev3Dev2MotorGatewayError
)
from services.motor_monitor import MotorMonitor
from services.motor_state_store import MotorStateStore
from services.rover_state_service import RoverStateService
from services.sensor_monitor import SensorMonitor
from services.sensor_state_store import SensorStateStore
from services.startup_error_notifier import StartupErrorNotifier


def build_application(operation_mode_service=None):
    """Builds the Rover-DR dependency graph for the selected deployment mode."""
    sensor_state_store = SensorStateStore()
    motor_state_store = MotorStateStore()
    controller_state_store = ControllerStateStore()

    sensor_monitor = SensorMonitor(state_store=sensor_state_store)
    motor_monitor = MotorMonitor(state_store=motor_state_store)
    controller_monitor = ControllerMonitor(state_store=controller_state_store)
    monitors = [sensor_monitor, motor_monitor, controller_monitor]

    sensor_port = SensorMonitorAdapter(
        sensor_monitor=sensor_monitor, state_store=sensor_state_store
    )
    motor_port = MotorMonitorAdapter(
        motor_monitor=motor_monitor, state_store=motor_state_store
    )
    controller_port = ControllerMonitorAdapter(
        controller_monitor=controller_monitor, state_store=controller_state_store
    )

    rover_state_service = RoverStateService(
        sensor_port=sensor_port,
        motor_port=motor_port,
        controller_port=controller_port,
        operation_mode_service=operation_mode_service
    )
    rover_state_port = RoverStateQueryAdapter(rover_state_service)

    drive_service = DriveService(motor_port=motor_port, sensor_port=sensor_port)
    drive_port = DriveServiceAdapter(drive_service)

    command_service = CommandService(
        sensor_port=sensor_port,
        motor_port=motor_port,
        controller_port=controller_port,
        rover_state_port=rover_state_port,
        drive_port=drive_port
    )

    ev3dev2_motor_gateway = None
    if rover_config.HARDWARE_ENABLED:
        try:
            ev3dev2_motor_gateway = Ev3Dev2MotorGateway(
                motor_port=motor_port, drive_port=drive_port
            )
        except Ev3Dev2MotorGatewayError as error:
            AppLogger.warning(
                "EV3Dev2 motor gateway unavailable: {}".format(error)
            )
    else:
        AppLogger.status(
            "Physical EV3 hardware is disabled; motor gateway was not started."
        )

    rest_api = RestApiServer(
        command_service, REST_HOST, REST_PORT,
        ev3dev2_motor_gateway=ev3dev2_motor_gateway
    )
    managed_services = (
        [ev3dev2_motor_gateway] if ev3dev2_motor_gateway is not None else []
    )
    application = RoverApplication(
        monitors=monitors, rest_api=rest_api, managed_services=managed_services
    )
    rest_api.set_shutdown_callback(application.stop)
    rest_api.set_restart_callback(application.restart)
    return application


def _validate_startup_configuration():
    try:
        rover_config.validate_security_configuration()
        return True
    except RuntimeError as error:
        AppLogger.error("Security configuration error: {}".format(error))

        if rover_config.HARDWARE_ENABLED:
            startup_error_notifier = StartupErrorNotifier(
                Ev3OperatorAlertAdapter()
            )
            AppLogger.status(
                "Attempting to present the startup error on the EV3 brick."
            )
            shown = startup_error_notifier.show(str(error))
            if shown:
                AppLogger.status(
                    "EV3 startup alert acknowledged by the operator."
                )
            else:
                AppLogger.status(
                    "EV3 startup alert unavailable; terminating startup."
                )
        else:
            AppLogger.status(
                "EV3 startup alert skipped because physical hardware is disabled."
            )
        return False


def _select_operation_mode():
    if not rover_config.HARDWARE_ENABLED:
        service = OperationModeService()
        AppLogger.status(
            "Physical hardware disabled; using default LOCAL/MANUAL mode."
        )
        return service

    service = OperationModeService(
        selector_port=Ev3OperationModeSelectorAdapter()
    )
    AppLogger.status("Waiting for the operator to select the Rover mode.")
    selected = service.select()
    if selected is None:
        AppLogger.status("Rover startup cancelled by the operator.")
        return None
    AppLogger.status(
        "Selected mode: {}/{}.".format(
            selected["command_mode"], selected["operation_mode"]
        )
    )
    return service


def main():
    """Starts Rover-DR and handles normal process termination signals."""
    if not _validate_startup_configuration():
        return 1

    operation_mode_service = _select_operation_mode()
    if operation_mode_service is None:
        return 1

    application = build_application(
        operation_mode_service=operation_mode_service
    )

    def request_shutdown(signum, _frame):
        AppLogger.status("Shutdown requested by signal {}.".format(signum))
        application.stop()

    signal.signal(signal.SIGINT, request_shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_shutdown)

    try:
        application.start()
        application.wait()
    except KeyboardInterrupt:
        application.stop()
    finally:
        application.stop()

    if application.is_restart_requested():
        AppLogger.status("Restarting Rover-DR process.")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
