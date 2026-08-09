#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output adapter exposing motor state through MotorPort."""

from ports.motor_port import MotorPort


class MotorMonitorAdapter(MotorPort):
    """Exposes the motor repository through the application output port."""

    def __init__(self, motor_monitor, state_store=None):
        self.motor_monitor = motor_monitor
        self.state_store = state_store or motor_monitor.state_store

    def list_motors(self):
        return [
            {
                "code": item["code"],
                "name": item["name"],
                "address": item["address"],
                "connected": item["connected"]
            }
            for item in self.state_store.get_all_motors()
        ]

    def read_motor(self, motor_code):
        return self.state_store.get_motor(motor_code)

    def read_all_motors(self):
        return self.state_store.get_all_motors()
