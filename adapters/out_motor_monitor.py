#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output adapter exposing motor state and basic execution through MotorPort."""

from ports.motor_port import MotorPort


class MotorMonitorAdapter(MotorPort):
    """Exposes motor monitoring/control operations to the application layer."""

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

    def stop_motor(self, motor_code, stop_action=None):
        return self.motor_monitor.stop_motor(motor_code, stop_action)

    def run_timed_motor(self, motor_code, speed_sp, time_sp, stop_action=None):
        return self.motor_monitor.run_timed_motor(
            motor_code, speed_sp, time_sp, stop_action
        )

    def run_forever_motor(self, motor_code, speed_sp, stop_action=None):
        return self.motor_monitor.run_forever_motor(
            motor_code, speed_sp, stop_action
        )

    def run_to_rel_pos_motor(
        self, motor_code, speed_sp, position_sp, stop_action=None
    ):
        return self.motor_monitor.run_to_rel_pos_motor(
            motor_code, speed_sp, position_sp, stop_action
        )

    def reset_motor(self, motor_code):
        return self.motor_monitor.reset_motor(motor_code)
