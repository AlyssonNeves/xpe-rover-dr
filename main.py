#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Main entry point for the Rover-DR monitoring application."""

import time

from adapters.out_controller_monitor import ControllerMonitorAdapter
from adapters.out_motor_monitor import MotorMonitorAdapter
from adapters.out_sensor_monitor import SensorMonitorAdapter
from services.controller_monitor import ControllerMonitor
from services.motor_monitor import MotorMonitor
from services.sensor_monitor import SensorMonitor


def main():
    """Starts the initial Rover-DR monitoring services."""
    sensor_monitor = SensorMonitor()
    motor_monitor = MotorMonitor()
    controller_monitor = ControllerMonitor()

    monitors = [sensor_monitor, motor_monitor, controller_monitor]

    sensor_port = SensorMonitorAdapter(sensor_monitor)
    motor_port = MotorMonitorAdapter(motor_monitor)
    controller_port = ControllerMonitorAdapter(controller_monitor)

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
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("Stopping Rover-DR monitoring services...")
    finally:
        for monitor in monitors:
            monitor.stop()
        for monitor in monitors:
            monitor.join(2.0)

    print("Rover-DR stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
