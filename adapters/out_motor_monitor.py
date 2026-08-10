#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Output adapter for motor query and control operations.

Provides an implementation of the MotorPort interface
using the motor monitor and motor state repository.
"""

from ports.motor_port import MotorPort


class MotorMonitorAdapter(MotorPort):
    """
    Adapts the motor state repository to the MotorPort interface.

    This adapter exposes motor query and control operations
    required by the application layer.
    """

    def __init__(self, motor_monitor, state_store=None):
        """
        Initializes the motor adapter.

        Args:
            motor_monitor (MotorMonitor):
                Motor monitoring service responsible for
                motor operations.
            state_store (MotorStateStore, optional):
                Motor state repository. If not provided,
                the repository associated with the monitor
                will be used.
        """
        self.motor_monitor = motor_monitor
        self.state_store = state_store or motor_monitor.state_store

    def list_motors(self):
        """
        Returns a summarized list of registered motors.

        Returns:
            list:
                List containing basic information about
                each available motor.
        """
        motors = []

        # Returns a reduced representation suitable for
        # discovery and listing operations.
        for motor in self.state_store.get_all_motors():
            motors.append({
                "code": motor.get("code"),
                "name": motor.get("name"),
                "address": motor.get("address"),
                "connected": motor.get("connected")
            })

        return motors

    def read_motor(self, motor_code):
        """
        Returns the complete information of a specific motor.

        Args:
            motor_code (str):
                Unique motor identifier.

        Returns:
            dict | None:
                Motor information if found;
                otherwise None.
        """
        return self.state_store.get_motor(motor_code)

    def read_all_motors(self):
        """
        Returns the complete information of all motors.

        Returns:
            list:
                Collection containing all registered
                motor records.
        """
        return self.state_store.get_all_motors()

    def stop_motor(self, motor_code, stop_action=None):
        """
        Executes a motor stop operation.

        Args:
            motor_code (str):
                Unique motor identifier.
            stop_action (str, optional):
                Stop behavior applied by the EV3 motor driver.

        Returns:
            dict | None:
                Updated motor information if the operation
                succeeds; otherwise None.
        """
        # Delegates hardware control operations to the monitor layer.
        return self.motor_monitor.stop_motor(motor_code, stop_action)

    def run_timed_motor(
        self,
        motor_code,
        speed_sp,
        time_sp,
        priority=None,
        profile=None,
        timeout_ms=None,
        stop_action=None
    ):
        """
        Executes a timed motor command.

        Args:
            motor_code (str):
                Unique motor identifier.
            speed_sp (int):
                Target motor speed.
            time_sp (int):
                Execution duration in milliseconds.
            priority (int, optional):
                Queue priority for command orchestration.
            profile (dict, optional):
                Movement profile configuration.
            timeout_ms (int, optional):
                Maximum execution time in milliseconds.
            stop_action (str, optional):
                Stop behavior applied when the command finishes.

        Returns:
            dict | None:
                Updated motor information if the operation
                succeeds; otherwise None.
        """
        # Delegates command execution to the monitor responsible
        # for interacting with the underlying motor implementation.
        return self.motor_monitor.run_timed_motor(
            motor_code,
            speed_sp,
            time_sp,
            priority=priority,
            profile=profile,
            timeout_ms=timeout_ms,
            stop_action=stop_action
        )

    def run_forever_motor(
        self,
        motor_code,
        speed_sp,
        priority=None,
        profile=None,
        watchdog_ms=None,
        timeout_ms=None,
        stop_action=None
    ):
        """
        Executes a continuous motor command.

        Args:
            motor_code (str):
                Unique motor identifier.
            speed_sp (int):
                Target motor speed.
            priority (int, optional):
                Queue priority for command orchestration.
            profile (dict, optional):
                Movement profile configuration.
            watchdog_ms (int, optional):
                Safety watchdog duration in milliseconds.
            timeout_ms (int, optional):
                Maximum operation duration in milliseconds.
            stop_action (str, optional):
                Stop behavior applied when the operation ends.

        Returns:
            dict | None:
                Updated motor information if the operation
                succeeds; otherwise None.
        """
        return self.motor_monitor.run_forever_motor(
            motor_code,
            speed_sp,
            priority=priority,
            profile=profile,
            watchdog_ms=watchdog_ms,
            timeout_ms=timeout_ms,
            stop_action=stop_action
        )

    def run_direct_motor(
        self,
        motor_code,
        duty_cycle_sp,
        priority=None,
        watchdog_ms=None,
        timeout_ms=None,
        stop_action=None
    ):
        """
        Executes an unregulated direct duty-cycle command.

        Args:
            motor_code (str):
                Unique motor identifier.
            duty_cycle_sp (int):
                Target duty cycle percentage.
            priority (int, optional):
                Queue priority for command orchestration.
            watchdog_ms (int, optional):
                Safety watchdog duration in milliseconds.
            timeout_ms (int, optional):
                Maximum operation duration in milliseconds.
            stop_action (str, optional):
                Stop behavior applied when the operation ends.

        Returns:
            dict | None:
                Updated motor information if the operation
                succeeds; otherwise None.
        """
        return self.motor_monitor.run_direct_motor(
            motor_code, duty_cycle_sp, priority=priority, watchdog_ms=watchdog_ms,
            timeout_ms=timeout_ms, stop_action=stop_action
        )

    def run_to_rel_pos_motor(
        self,
        motor_code,
        speed_sp,
        position_sp,
        priority=None,
        profile=None,
        timeout_ms=None,
        stop_action=None
    ):
        """
        Executes a relative-position motor command.

        Args:
            motor_code (str):
                Unique motor identifier.
            speed_sp (int):
                Target motor speed.
            position_sp (int):
                Relative target position.
            priority (int, optional):
                Queue priority for command orchestration.
            profile (dict, optional):
                Movement profile configuration.
            timeout_ms (int, optional):
                Maximum execution time in milliseconds.
            stop_action (str, optional):
                Stop behavior applied when the command finishes.

        Returns:
            dict | None:
                Updated motor information if the operation
                succeeds; otherwise None.
        """
        return self.motor_monitor.run_to_rel_pos_motor(
            motor_code,
            speed_sp,
            position_sp,
            priority=priority,
            profile=profile,
            timeout_ms=timeout_ms,
            stop_action=stop_action
        )

    def run_to_abs_pos_motor(
        self,
        motor_code,
        speed_sp,
        position_sp,
        priority=None,
        profile=None,
        timeout_ms=None,
        stop_action=None
    ):
        """
        Executes an absolute-position motor command.

        Args:
            motor_code (str):
                Unique motor identifier.
            speed_sp (int):
                Target motor speed.
            position_sp (int):
                Absolute target position.
            priority (int, optional):
                Queue priority for command orchestration.
            profile (dict, optional):
                Movement profile configuration.
            timeout_ms (int, optional):
                Maximum execution time in milliseconds.
            stop_action (str, optional):
                Stop behavior applied when the command finishes.

        Returns:
            dict | None:
                Updated motor information if the operation
                succeeds; otherwise None.
        """
        return self.motor_monitor.run_to_abs_pos_motor(
            motor_code, speed_sp, position_sp, priority=priority, profile=profile,
            timeout_ms=timeout_ms, stop_action=stop_action
        )

    def get_command(self, command_id):
        """Returns a command lifecycle snapshot."""
        return self.motor_monitor.get_command(command_id)

    def list_commands(self, motor_code=None):
        """Lists command lifecycle snapshots."""
        return self.motor_monitor.list_commands(motor_code)

    def drive_tank(self, left_speed_sp, right_speed_sp, **options):
        """Controls both configured traction motors."""
        return self.motor_monitor.drive_tank(left_speed_sp, right_speed_sp, **options)

    def stop_drive(self, stop_action=None):
        """Stops both configured traction motors."""
        return self.motor_monitor.stop_drive(stop_action)

    def stop_all_motors(self, stop_action=None):
        """Stops all configured motors immediately."""
        return self.motor_monitor.stop_all_motors(stop_action)

    def reset_motor(self, motor_code):
        """
        Executes a motor reset operation.

        Args:
            motor_code (str):
                Unique motor identifier.

        Returns:
            dict | None:
                Updated motor information if the operation
                succeeds; otherwise None.
        """
        return self.motor_monitor.reset_motor(motor_code)

    def cancel_motor_commands(self, motor_code):
        """
        Cancels queued motor commands.

        Args:
            motor_code (str):
                Unique motor identifier.

        Returns:
            dict | None:
                Updated motor information if the operation succeeds;
                otherwise None.
        """
        return self.motor_monitor.cancel_motor_commands(motor_code)

    def run_synchronized_motors(self, commands):
        """
        Executes a synchronized command batch for multiple motors.

        Args:
            commands (list):
                Motor command definitions.

        Returns:
            dict:
                Synchronized command batch result.
        """
        return self.motor_monitor.run_synchronized_motors(commands)

    def execute_guarded_operation(self, motor_codes, operation_name, operation):
        """Runs a native EV3Dev2 operation inside the monitor safety boundary."""
        return self.motor_monitor.execute_guarded_operation(
            motor_codes, operation_name, operation
        )

    def begin_guarded_operation(self, motor_codes, operation_name, operation_id):
        """Reserves motors for a persistent native EV3Dev2 operation."""
        return self.motor_monitor.begin_guarded_operation(
            motor_codes, operation_name, operation_id
        )

    def end_guarded_operation(
        self,
        operation_id,
        status="COMPLETED",
        error=None,
        stop=False
    ):
        """Releases a persistent native EV3Dev2 operation."""
        return self.motor_monitor.end_guarded_operation(
            operation_id, status=status, error=error, stop=stop
        )
