#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Output adapter exposing queued motor orchestration through MotorPort."""

from ports.motor_port import MotorPort


class MotorMonitorAdapter(MotorPort):
    """Exposes motor state and command orchestration to the application layer."""

    def __init__(self, motor_monitor, state_store=None):
        self.motor_monitor = motor_monitor
        self.state_store = state_store or motor_monitor.state_store

    def list_motors(self):
        return self.motor_monitor.list_motors()

    def read_motor(self, motor_code):
        return self.state_store.get_motor(motor_code)

    def read_all_motors(self):
        return self.state_store.get_all_motors()

    def stop_motor(self, motor_code, stop_action=None):
        return self.motor_monitor.stop_motor(motor_code, stop_action)

    def run_timed_motor(
        self, motor_code, speed_sp, time_sp, priority=None, stop_action=None,
        timeout_ms=None
    ):
        return self.motor_monitor.run_timed_motor(
            motor_code, speed_sp, time_sp, priority, stop_action, timeout_ms
        )

    def run_forever_motor(
        self, motor_code, speed_sp, priority=None, stop_action=None,
        watchdog_ms=None, timeout_ms=None
    ):
        return self.motor_monitor.run_forever_motor(
            motor_code, speed_sp, priority, stop_action, watchdog_ms, timeout_ms
        )

    def run_to_rel_pos_motor(
        self, motor_code, speed_sp, position_sp, priority=None,
        stop_action=None, timeout_ms=None
    ):
        return self.motor_monitor.run_to_rel_pos_motor(
            motor_code, speed_sp, position_sp, priority, stop_action, timeout_ms
        )

    def reset_motor(self, motor_code, priority=None):
        return self.motor_monitor.reset_motor(motor_code, priority)

    def get_command(self, command_id):
        return self.motor_monitor.get_command(command_id)

    def list_commands(self, motor_code=None):
        return self.motor_monitor.list_commands(motor_code)

    def cancel_motor_commands(self, motor_code):
        return self.motor_monitor.cancel_motor_commands(motor_code)

    def run_synchronized_motors(self, commands):
        return self.motor_monitor.run_synchronized_motors(commands)


    def execute_guarded_operation(self, motor_codes, operation_name, operation):
        return self.motor_monitor.execute_guarded_operation(
            motor_codes, operation_name, operation
        )

    def begin_guarded_operation(self, motor_codes, operation_name, operation_id):
        return self.motor_monitor.begin_guarded_operation(
            motor_codes, operation_name, operation_id
        )

    def end_guarded_operation(self, operation_id, status="COMPLETED",
                              error=None, stop=False):
        return self.motor_monitor.end_guarded_operation(
            operation_id, status=status, error=error, stop=stop
        )
