#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Composition root and process lifecycle entry point for Rover-DR."""

import signal

from adapters.in_rest_api_server import RestApiServer
from adapters.out_controller_monitor import ControllerMonitorAdapter
from adapters.out_drive_service import DriveServiceAdapter
from adapters.out_motor_monitor import MotorMonitorAdapter
from adapters.out_rover_state_query import RoverStateQueryAdapter
from adapters.out_sensor_monitor import SensorMonitorAdapter
from app.command_service import CommandService
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


def build_application():
    """Builds the current Rover-DR application dependency graph."""
    sensor_state_store = SensorStateStore()
    motor_state_store = MotorStateStore()
    controller_state_store = ControllerStateStore()

    sensor_monitor = SensorMonitor(state_store=sensor_state_store)
    motor_monitor = MotorMonitor(state_store=motor_state_store)
    controller_monitor = ControllerMonitor(state_store=controller_state_store)
    monitors = [sensor_monitor, motor_monitor, controller_monitor]

    sensor_port = SensorMonitorAdapter(
        sensor_monitor=sensor_monitor,
        state_store=sensor_state_store
    )
    motor_port = MotorMonitorAdapter(
        motor_monitor=motor_monitor,
        state_store=motor_state_store
    )
    controller_port = ControllerMonitorAdapter(
        controller_monitor=controller_monitor,
        state_store=controller_state_store
    )

    rover_state_service = RoverStateService(
        sensor_port=sensor_port,
        motor_port=motor_port,
        controller_port=controller_port
    )
    rover_state_port = RoverStateQueryAdapter(rover_state_service)

    drive_service = DriveService(
        motor_port=motor_port,
        sensor_port=sensor_port
    )
    drive_port = DriveServiceAdapter(drive_service)

    command_service = CommandService(
        sensor_port=sensor_port,
        motor_port=motor_port,
        controller_port=controller_port,
        rover_state_port=rover_state_port,
        drive_port=drive_port
    )

    try:
        ev3dev2_motor_gateway = Ev3Dev2MotorGateway(
            motor_port=motor_port,
            drive_port=drive_port
        )
    except Ev3Dev2MotorGatewayError as error:
        AppLogger.warning(
            "EV3Dev2 motor gateway unavailable: {}".format(error)
        )
        ev3dev2_motor_gateway = None

    rest_api = RestApiServer(
        command_service, REST_HOST, REST_PORT,
        ev3dev2_motor_gateway=ev3dev2_motor_gateway
    )

    managed_services = (
        [ev3dev2_motor_gateway]
        if ev3dev2_motor_gateway is not None
        else []
    )
    return RoverApplication(
        monitors=monitors,
        rest_api=rest_api,
        managed_services=managed_services
    )


def main():
    """Starts Rover-DR and handles normal process termination signals."""
    application = build_application()

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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
