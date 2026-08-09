#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Main entry point for Rover-DR monitoring and its initial REST API."""

from adapters.in_rest_api_server import RestApiServer
from adapters.out_controller_monitor import ControllerMonitorAdapter
from adapters.out_motor_monitor import MotorMonitorAdapter
from adapters.out_sensor_monitor import SensorMonitorAdapter
from app.command_service import CommandService
from services.controller_monitor import ControllerMonitor
from services.motor_monitor import MotorMonitor
from services.sensor_monitor import SensorMonitor


REST_HOST = "0.0.0.0"
REST_PORT = 8080


def main():
    """Starts the monitoring services and exposes them through HTTP."""
    sensor_monitor = SensorMonitor()
    motor_monitor = MotorMonitor()
    controller_monitor = ControllerMonitor()
    monitors = [sensor_monitor, motor_monitor, controller_monitor]

    sensor_port = SensorMonitorAdapter(sensor_monitor)
    motor_port = MotorMonitorAdapter(motor_monitor)
    controller_port = ControllerMonitorAdapter(controller_monitor)

    command_service = CommandService(
        sensor_port=sensor_port,
        motor_port=motor_port,
        controller_port=controller_port
    )
    rest_api = RestApiServer(command_service, REST_HOST, REST_PORT)

    for monitor in monitors:
        monitor.start()

    print("Rover-DR")
    print("Monitoring services initialized.")
    print("Sensors: {}".format(len(sensor_port.list_sensors())))
    print("Motors: {}".format(len(motor_port.list_motors())))
    print("Controller: {}".format(
        controller_port.read_controller_status().get("status")
    ))
    print("Press Ctrl+C to stop.")

    try:
        rest_api.start()
    except KeyboardInterrupt:
        print("Stopping Rover-DR...")
    finally:
        rest_api.stop()
        for monitor in monitors:
            monitor.stop()
        for monitor in monitors:
            monitor.join(2.0)

    print("Rover-DR stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
