#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output adapter exposing motor monitor queries through MotorPort."""

from ports.motor_port import MotorPort


class MotorMonitorAdapter(MotorPort):
    """Adapts MotorMonitor to the motor output-port contract."""

    def __init__(self, motor_monitor):
        self.motor_monitor = motor_monitor

    def list_motors(self):
        return self.motor_monitor.list_motors()

    def read_motor(self, motor_code):
        return self.motor_monitor.read_motor(motor_code)

    def read_all_motors(self):
        return self.motor_monitor.read_all_motors()
