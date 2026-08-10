#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Rover motor monitor.

Centralizes motor registration, command orchestration, hardware reads,
controlled reconnection, and logical motor control through the
application state repository.
"""

import threading
import time

from app.rover_config import DEFAULT_CONFIGURATION
from app.motor_lifecycle import MotorLifecycleStates
from infrastructure.ev3.motor_driver_factory import Ev3MotorDriverFactory
from infrastructure.monitoring.monitor_base import MonitorBase
from infrastructure.state.motor_state_store import MotorStateStore
from infrastructure.logging.app_logger import AppLogger
from infrastructure.motor.registries import (
    GuardedOperationRegistry, MotorCommandRegistry
)
from infrastructure.motor.command_scheduler import MotorCommandScheduler
from infrastructure.motor.safety_watchdog import MotorSafetyWatchdog
from infrastructure.motor.state_collector import MotorStateCollector
from infrastructure.motor.command_executor import MotorCommandExecutor
from infrastructure.motor.guarded_operation_manager import MotorGuardedOperationManager
from infrastructure.motor.synchronized_executor import SynchronizedMotorExecutor
from infrastructure.motor.driver_repository import Ev3MotorDriverRepository


class MotorCommandActions(object):
    """Defines internal motor command action names."""

    STOP = "stop"
    RUN_TIMED = "run-timed"
    RUN_FOREVER = "run-forever"
    RUN_DIRECT = "run-direct"
    RUN_TO_REL_POS = "run-to-rel-pos"
    RUN_TO_ABS_POS = "run-to-abs-pos"
    RESET = "reset"
    CANCEL = "cancel"


class MotorMonitor(MonitorBase):
    """
    Motor monitoring and control service.

    Provides configured motor registration, explicit lifecycle states,
    command queue orchestration, preemption, controlled reconnection,
    and hardware or simulated execution depending on configuration.
    """

    TRANSIENT_COMMAND_FIELDS = (
        "speed_sp",
        "time_sp",
        "position_sp",
        "duty_cycle_sp",
        "profile",
        "priority",
        "batch_id",
        "timeout_ms",
        "watchdog_ms",
        "stop_action"
    )

    DIRECT_PROFILE = "direct"
    RAMP_UP_PROFILE = "ramp-up"
    RAMP_DOWN_PROFILE = "ramp-down"
    RAMP_UP_DOWN_PROFILE = "ramp-up-down"
    SUPPORTED_PROFILES = (
        DIRECT_PROFILE,
        RAMP_UP_PROFILE,
        RAMP_DOWN_PROFILE,
        RAMP_UP_DOWN_PROFILE
    )
    HISTORY_LIMIT = 20
    DEFAULT_PRIORITY = 5

    PREEMPTIVE_COMMANDS = (
        MotorCommandActions.STOP,
        MotorCommandActions.RUN_TIMED,
        MotorCommandActions.RUN_FOREVER,
        MotorCommandActions.RUN_DIRECT,
        MotorCommandActions.RUN_TO_REL_POS,
        MotorCommandActions.RUN_TO_ABS_POS,
        MotorCommandActions.RESET
    )

    def __init__(
        self,
        state_store=None,
        interval_seconds=1.0,
        motor_definitions=None,
        hardware_enabled=None,
        hardware_backend=None,
        retry_interval_seconds=5.0,
        max_retry_attempts=None,
        configuration=None
    ):
        """
        Initializes the motor registry and command queue.
        """
        MonitorBase.__init__(
            self,
            name="MotorMonitor",
            interval_seconds=interval_seconds
        )

        self.configuration = configuration or DEFAULT_CONFIGURATION
        self.state_store = state_store or MotorStateStore()
        self.motor_definitions = (
            motor_definitions or self.configuration.motor_definitions
        )
        self.hardware_enabled = (
            self.configuration.hardware_enabled
            if hardware_enabled is None
            else hardware_enabled
        )
        self.default_stop_action = self.configuration.motor_default_stop_action
        self.command_timeout_ms = self.configuration.motor_command_timeout_ms
        self.run_forever_watchdog_ms = (
            self.configuration.motor_run_forever_watchdog_ms
        )
        self.stall_timeout_ms = self.configuration.motor_stall_timeout_ms
        self.ramp_up_ms = self.configuration.motor_ramp_up_ms
        self.ramp_down_ms = self.configuration.motor_ramp_down_ms
        self.drive_left_motor_code = self.configuration.drive_left_motor_code
        self.drive_right_motor_code = self.configuration.drive_right_motor_code
        self.hardware_backend = hardware_backend or Ev3MotorDriverFactory()
        self.retry_interval_seconds = retry_interval_seconds
        self.max_retry_attempts = max_retry_attempts
        self.motor_registry = Ev3MotorDriverRepository(
            self.motor_definitions,
            self.hardware_backend,
            retry_interval_seconds=retry_interval_seconds,
            max_retry_attempts=max_retry_attempts
        )
        self._active_commands = {}
        self._active_lock = threading.RLock()
        self.command_registry = MotorCommandRegistry()
        self.command_scheduler = MotorCommandScheduler(
            self.motor_definitions, self._execute_queued_command
        )
        self._last_drive_setpoint = None
        self.safety_watchdog = MotorSafetyWatchdog(
            self._evaluate_watchdog_deadlines,
            AppLogger,
            interval_seconds=0.05
        )
        self.guarded_operation_registry = GuardedOperationRegistry()
        self.state_collector = MotorStateCollector(
            self.state_store,
            self.motor_definitions,
            self.hardware_enabled,
            self.hardware_backend,
            self.motor_registry,
            self._get_queue_size
        )
        self.command_executor = MotorCommandExecutor(
            self.motor_registry,
            MotorCommandActions,
            self._is_hardware_backend_available,
            self._get_hardware_error_message,
            self.default_stop_action,
            self.ramp_up_ms,
            self.ramp_down_ms,
            self.DIRECT_PROFILE,
            self.RAMP_UP_PROFILE,
            self.RAMP_DOWN_PROFILE,
            self.RAMP_UP_DOWN_PROFILE
        )
        self.guarded_operation_manager = MotorGuardedOperationManager(
            self.motor_definitions,
            self.guarded_operation_registry,
            self.motor_registry,
            self._preempt_motor_commands,
            self.default_stop_action,
            AppLogger
        )
        self.synchronized_executor = SynchronizedMotorExecutor(
            self.motor_definitions,
            MotorCommandActions,
            self._enqueue_motor_command,
            self.state_store,
            self.list_commands
        )

        self._load_initial_motors()

    def _is_hardware_backend_available(self):
        """Reports whether physical motor hardware is available."""
        return self.state_collector.hardware_available()


    def _get_hardware_error_message(self):
        """Returns the current backend error without side effects."""
        return self.state_collector.hardware_error()


    def _load_initial_motors(self):
        """Delegates initial state publication to the state collector."""
        self.state_collector.load_initial_motors()


    def _refresh_hardware_motor_state(self):
        """Delegates physical-state collection to the state collector."""
        self.state_collector.refresh_hardware_state()


    def _clear_transient_command_fields(self, motor):
        """
        Clears transient command parameters from the motor state.
        """
        for field_name in self.TRANSIENT_COMMAND_FIELDS:
            motor.pop(field_name, None)

        return motor

    def _get_queue_size(self, motor_code):
        """
        Returns current queue size for a motor.
        """
        return self.command_scheduler.size(motor_code)

    def _normalize_priority(self, priority):
        """
        Normalizes command priority values for deterministic ordering.
        """
        if isinstance(priority, bool):
            return self.DEFAULT_PRIORITY

        if isinstance(priority, int):
            return priority

        return self.DEFAULT_PRIORITY

    def _normalize_profile(self, profile):
        """
        Normalizes motor movement profiles.
        """
        if profile in self.SUPPORTED_PROFILES:
            return profile

        return self.DIRECT_PROFILE

    def _append_command_history(self, motor, command_entry):
        """
        Appends a bounded command history entry to a motor state.
        """
        history = list(motor.get("command_history") or [])
        history.append(command_entry)
        motor["command_history"] = history[-self.HISTORY_LIMIT:]
        return motor

    def _enqueue_motor_command(
        self,
        motor_code,
        action,
        parameters=None,
        priority=None,
        batch_id=None
    ):
        """
        Adds a motor command to the monitor execution queue.
        """
        motor = self.state_store.get_motor(motor_code)

        if motor is None:
            return None

        if self.guarded_operation_registry.is_reserved(motor_code):
            motor["success"] = False
            motor["error"] = "Motor is reserved by a guarded EV3Dev2 domain operation."
            motor["lifecycle_state"] = MotorLifecycleStates.COMMAND_FAILED
            self.state_store.update_motor(motor_code, motor)
            return motor

        parameters = dict(parameters or {})
        priority = self._normalize_priority(
            parameters.pop("priority", priority)
        )
        profile = self._normalize_profile(parameters.pop("profile", None))

        if action in (
            MotorCommandActions.RUN_TIMED,
            MotorCommandActions.RUN_FOREVER,
            MotorCommandActions.RUN_DIRECT,
            MotorCommandActions.RUN_TO_REL_POS,
            MotorCommandActions.RUN_TO_ABS_POS
        ):
            parameters["profile"] = profile

        parameters["priority"] = priority
        validation_error = self._validate_motor_limits(motor_code, action, parameters)
        if validation_error:
            motor["success"] = False
            motor["error"] = validation_error
            motor["lifecycle_state"] = MotorLifecycleStates.COMMAND_FAILED
            self.state_store.update_motor(motor_code, motor)
            return motor

        if batch_id is not None:
            parameters["batch_id"] = batch_id

        if action in self.PREEMPTIVE_COMMANDS:
            stop_running_command = action != MotorCommandActions.STOP
            self._preempt_motor_commands(
                motor_code,
                stop_running_command=stop_running_command
            )

        command = {
                "id": self.command_scheduler.next_id(),
                "motor_code": motor_code,
                "action": action,
                "parameters": parameters,
                "priority": priority,
                "batch_id": batch_id,
                "cancelled": False,
                "queued_at": time.time()
            }
        self.command_scheduler.enqueue(command)
        self.command_registry.create(
            command_id=command["id"],
            motor_code=motor_code,
            action=action,
            priority=priority,
            batch_id=batch_id,
            queued_at=command["queued_at"],
            parameters=parameters
        )

        motor = self._clear_transient_command_fields(motor)
        motor["pending_command"] = action
        motor["command"] = action
        motor["command_queue_size"] = self._get_queue_size(motor_code)
        motor["lifecycle_state"] = MotorLifecycleStates.QUEUED
        motor["success"] = True
        motor["priority"] = priority
        motor["last_command_at"] = command["queued_at"]
        motor = self._append_command_history(
            motor,
            {
                "id": command["id"],
                "action": action,
                "priority": priority,
                "batch_id": batch_id,
                "status": "QUEUED",
                "timestamp": command["queued_at"]
            }
        )

        for key, value in parameters.items():
            motor[key] = value

        self.state_store.update_motor(motor_code, motor)

        if not self.is_alive():
            self._process_motor_queue(motor_code)
            motor = self.state_store.get_motor(motor_code)

        return motor

    def _validate_motor_limits(self, motor_code, action, parameters):
        """Validates command values against per-motor configured limits."""
        definition = self.motor_definitions.get(motor_code) or {}
        limits = definition.get("limits") or {}
        speed_error = self._validate_speed_limit(
            motor_code, parameters.get("speed_sp"), limits
        )
        if speed_error:
            return speed_error
        return self._validate_position_limit(
            action, parameters.get("position_sp"), limits
        )

    def _validate_speed_limit(self, motor_code, speed, limits):
        if speed is None:
            return None
        max_speed_ratio = limits.get("max_speed_ratio", 1.0)
        try:
            max_speed_ratio = float(max_speed_ratio)
        except (TypeError, ValueError):
            return (
                "max_speed_ratio must be a numeric value greater than 0 "
                "and no greater than 1."
            )
        if max_speed_ratio <= 0 or max_speed_ratio > 1:
            return "max_speed_ratio must be greater than 0 and no greater than 1."
        if not self._is_hardware_backend_available():
            return None
        hardware_max_speed = self.motor_registry.get_motor_max_speed(motor_code)
        if hardware_max_speed is None:
            return None
        effective_max_speed = int(hardware_max_speed * max_speed_ratio)
        if abs(speed) <= effective_max_speed:
            return None
        return (
            "speed_sp exceeds the effective motor limit ({0}), calculated "
            "from motor.max_speed ({1}) and max_speed_ratio ({2})."
        ).format(effective_max_speed, hardware_max_speed, max_speed_ratio)

    @staticmethod
    def _validate_position_limit(action, position, limits):
        if position is None:
            return None
        if action == MotorCommandActions.RUN_TO_ABS_POS:
            min_position = limits.get("min_position_sp")
            max_position = limits.get("max_position_sp")
            if min_position is not None and position < min_position:
                return "position_sp is below minimum configured limit ({0}).".format(
                    min_position
                )
            if max_position is not None and position > max_position:
                return "position_sp exceeds maximum configured limit ({0}).".format(
                    max_position
                )
        max_delta = limits.get("max_relative_position_sp")
        if (
            action == MotorCommandActions.RUN_TO_REL_POS
            and max_delta is not None
            and abs(position) > max_delta
        ):
            return "position_sp exceeds maximum relative movement limit ({0}).".format(
                max_delta
            )
        return None

    def get_command(self, command_id):
        """Returns a public command snapshot by identifier."""
        return self.command_registry.get(command_id)

    def list_commands(self, motor_code=None):
        """Lists public command snapshots, optionally filtered by motor."""
        return self.command_registry.list(motor_code)

    def _update_command_registry(self, command_id, status, **fields):
        """Updates the externally consultable command lifecycle state."""
        self.command_registry.update(command_id, status, **fields)

    def _process_motor_queue(self, motor_code):
        """Processes all currently queued commands for one motor."""
        self.command_scheduler.process_available(motor_code)

    def on_initialize(self):
        """Starts the command scheduler and independent safety watchdog."""
        self.safety_watchdog.start()
        self.command_scheduler.start()

    def _evaluate_watchdog_deadlines(self):
        """Stops expired continuous commands without waiting for monitor cycles."""
        now = time.time()
        monotonic_now = time.monotonic()
        with self._active_lock:
            expired = [
                (motor_code, dict(active))
                for motor_code, active in self._active_commands.items()
                if active.get("action") in (
                    MotorCommandActions.RUN_FOREVER,
                    MotorCommandActions.RUN_DIRECT
                )
                and (
                    (
                        active.get("watchdog_deadline_monotonic") is not None
                        and monotonic_now >= active["watchdog_deadline_monotonic"]
                    )
                    or (
                        active.get("watchdog_deadline_monotonic") is None
                        and active.get("watchdog_deadline")
                        and now >= active["watchdog_deadline"]
                    )
                )
            ]
        if not expired:
            return

        for motor_code, active in expired:
            self.motor_registry.execute_stop(
                motor_code, active.get("stop_action")
            ) if self._is_hardware_backend_available() else None
            self._finish_active_command(
                motor_code,
                MotorLifecycleStates.TIMED_OUT,
                "STOPPED",
                "continuous motor watchdog expired."
            )

    def _preempt_motor_commands(self, motor_code, stop_running_command=True):
        """
        Cancels queued commands for a motor before a new command runs.
        """
        cancelled_count = self.command_scheduler.cancel(motor_code)

        motor = self.state_store.get_motor(motor_code)
        if motor is not None and cancelled_count:
            motor["cancelled_command_count"] = (
                motor.get("cancelled_command_count", 0) + cancelled_count
            )
            motor["lifecycle_state"] = MotorLifecycleStates.CANCELLED
            motor = self._append_command_history(
                motor,
                {
                    "action": MotorCommandActions.CANCEL,
                    "status": "CANCELLED",
                    "cancelled_count": cancelled_count,
                    "timestamp": time.time()
                }
            )
            self.state_store.update_motor(motor_code, motor)

        if stop_running_command and self._is_hardware_backend_available():
            self.motor_registry.execute_stop(motor_code)

    def on_cycle(self):
        """Refreshes physical state and evaluates active commands."""
        self._refresh_hardware_motor_state()
        self._evaluate_active_commands()

    def _execute_queued_command(self, command):
        """
        Executes a single queued motor command.
        """
        motor_code = command["motor_code"]
        start_at = command.get("parameters", {}).get("start_at")
        if start_at is not None:
            delay = float(start_at) - time.time()
            if delay > 0:
                time.sleep(delay)
        action = command["action"]
        parameters = command.get("parameters", {})
        motor = self.state_store.get_motor(motor_code)

        if motor is None:
            return

        command_result = self._execute_hardware_command(
            motor_code,
            action,
            parameters
        )
        motor = self._apply_command_state(
            motor,
            action,
            parameters,
            command_result
        )
        motor["command_queue_size"] = self._get_queue_size(motor_code)
        motor["pending_command"] = None
        if motor.get("command_state") == MotorLifecycleStates.DISPATCHED:
            self._register_active_command(command, motor)
            motor["active_command_id"] = command["id"]
        registry_status = motor.get("command_state") or MotorLifecycleStates.DISPATCHED
        self._update_command_registry(
            command["id"],
            registry_status,
            dispatched_at=time.time(),
            completed_at=(time.time() if registry_status == MotorLifecycleStates.COMPLETED else None),
            error=motor.get("hardware_error")
        )
        self.state_store.update_motor(motor_code, motor)

    def _execute_hardware_command(self, motor_code, action, parameters):
        """Delegates low-level execution to the motor command executor."""
        return self.command_executor.execute(motor_code, action, parameters)


    def _apply_command_state(
        self,
        motor,
        action,
        parameters,
        command_result
    ):
        """
        Applies command execution metadata to motor state.
        """
        motor = self._clear_transient_command_fields(motor)
        completed_at = time.time()
        motor["command"] = action
        motor["hardware_command_executed"] = command_result["executed"]
        motor["success"] = command_result["success"]
        motor["last_command_dispatched_at"] = completed_at

        for key, value in parameters.items():
            motor[key] = value

        if command_result.get("hardware_error"):
            motor["hardware_error"] = command_result["hardware_error"]
            motor["lifecycle_state"] = MotorLifecycleStates.COMMAND_FAILED
            motor["command_state"] = "FAILED"
            motor["last_failure_at"] = completed_at
        elif action in (MotorCommandActions.STOP, MotorCommandActions.RESET) or not command_result["executed"]:
            motor["hardware_error"] = None
            motor["lifecycle_state"] = MotorLifecycleStates.COMPLETED
            motor["command_state"] = MotorLifecycleStates.COMPLETED
            motor["motion_state"] = "STOPPED" if action == MotorCommandActions.STOP else "IDLE"
            motor["last_command_completed_at"] = completed_at
            motor["last_success_at"] = completed_at
            if action == MotorCommandActions.RESET:
                motor["position"] = 0
        else:
            motor["hardware_error"] = None
            motor["lifecycle_state"] = MotorLifecycleStates.COMPLETED
            motor["command_state"] = MotorLifecycleStates.DISPATCHED
            motor["motion_state"] = "RUNNING"
            motor["last_success_at"] = completed_at

        motor = self._append_command_history(
            motor,
            {
                "action": action,
                "status": motor["lifecycle_state"],
                "success": command_result["success"],
                "hardware_command_executed": command_result["executed"],
                "timestamp": completed_at
            }
        )

        return motor

    def _register_active_command(self, command, motor):
        """Registers execution deadlines and progress metadata."""
        now = time.time()
        parameters = command.get("parameters", {})
        action = command["action"]
        # Resolves the general execution timeout for the dispatched command.
        timeout_ms = parameters.get("timeout_ms") or self.command_timeout_ms

        # Extends timed commands by their requested movement duration.
        if action == MotorCommandActions.RUN_TIMED:
            timeout_ms = parameters.get("timeout_ms") or (parameters.get("time_sp", 0) + self.command_timeout_ms)
        # Resolves the safety watchdog used by continuous movement commands.
        watchdog_ms = parameters.get("watchdog_ms") or self.run_forever_watchdog_ms

        # Protects active-command metadata from concurrent monitor access.
        with self._active_lock:
            self._active_commands[command["motor_code"]] = {
                "id": command["id"], "action": action, "started_at": now,
                "deadline": now + (float(timeout_ms) / 1000.0),
                "watchdog_deadline": now + (float(watchdog_ms) / 1000.0) if action in (MotorCommandActions.RUN_FOREVER, MotorCommandActions.RUN_DIRECT) else None,
                "last_position": motor.get("position"), "last_progress_at": now,
                "position_sp": parameters.get("position_sp"),
                "start_position": motor.get("position"),
                "stop_action": parameters.get("stop_action", self.default_stop_action)
            }

    def _finish_active_command(self, motor_code, status, motion_state, error=None):
        """Finalizes an active command and publishes its terminal state."""
        # Removes the command from the active registry atomically.
        with self._active_lock:
            active = self._active_commands.pop(motor_code, None)
        # Retrieves the latest motor snapshot before applying final metadata.
        motor = self.state_store.get_motor(motor_code)
        if motor is None:
            return
        now = time.time()
        motor["lifecycle_state"] = status
        motor["command_state"] = status
        motor["motion_state"] = motion_state
        motor["active_command_id"] = None
        motor["last_command_completed_at"] = now
        motor["success"] = status in (MotorLifecycleStates.COMPLETED, MotorLifecycleStates.STOPPED)
        if error:
            motor["hardware_error"] = error
            motor["last_failure_at"] = now
        else:
            motor["last_success_at"] = now
        motor = self._append_command_history(motor, {"id": active.get("id") if active else None, "action": active.get("action") if active else motor.get("command"), "status": status, "success": motor["success"], "timestamp": now})
        self.state_store.update_motor(motor_code, motor)

    def _evaluate_active_commands(self):
        """Evaluates completion, timeout, watchdog, and stall conditions."""
        self._evaluate_watchdog_deadlines()
        now = time.time()
        # Copies active metadata so hardware reads occur outside the lock.
        with self._active_lock:
            active_items = list(self._active_commands.items())

        # Evaluates each active motor independently during the monitor cycle.
        for motor_code, active in active_items:
            snapshot = self.motor_registry.read_motor(motor_code) if self._is_hardware_backend_available() else None
            if snapshot is None:
                continue
            states = snapshot.get("state") or []
            if isinstance(states, str):
                states = [states]
            position = snapshot.get("position")
            # Prioritizes the stall condition reported directly by the driver.
            if "stalled" in states:
                self.motor_registry.execute_stop(motor_code, active["stop_action"])
                self._finish_active_command(motor_code, MotorLifecycleStates.STALLED, "STALLED", "Motor driver reported stalled state.")
                continue
            # Refreshes progress metadata whenever the encoder position changes.
            if position is not None and position != active.get("last_position"):
                active["last_position"] = position
                active["last_progress_at"] = now
            # Detects a logical stall when the motor reports running without
            # encoder progress for longer than the configured interval.
            elif "running" in states and now - active.get("last_progress_at", now) >= float(self.stall_timeout_ms) / 1000.0:
                self.motor_registry.execute_stop(motor_code, active["stop_action"])
                self._finish_active_command(motor_code, MotorLifecycleStates.STALLED, "STALLED", "Motor position did not progress within stall timeout.")
                continue
            # Applies the general execution timeout only to bounded commands.
            # Continuous commands are governed by their dedicated watchdog,
            # which is renewed by the active command owner.
            continuous = active["action"] in (
                MotorCommandActions.RUN_FOREVER,
                MotorCommandActions.RUN_DIRECT
            )
            if not continuous and now >= active["deadline"]:
                self.motor_registry.execute_stop(motor_code, active["stop_action"])
                self._finish_active_command(motor_code, MotorLifecycleStates.TIMED_OUT, "STOPPED", "Motor command execution timeout expired.")
                continue
            # Finishes bounded commands after the driver leaves running state.
            if not continuous and "running" not in states:
                self._finish_active_command(motor_code, MotorLifecycleStates.COMPLETED, "IDLE")

    def stop_all_motors(self, stop_action=None, clear_queues=True):
        """Stops every motor and optionally cancels all queued commands."""
        # Uses the application-wide stop behavior when none is provided.
        stop_action = stop_action or self.default_stop_action
        results = {}

        # Stops and finalizes each configured motor independently.
        for motor_code in self.motor_definitions:
            # Cancels queued commands before issuing the physical stop.
            if clear_queues:
                self._preempt_motor_commands(motor_code, stop_running_command=False)
            result = self.motor_registry.execute_stop(motor_code, stop_action) if self._is_hardware_backend_available() else {"success": True, "hardware_error": None}
            results[motor_code] = result
            self._finish_active_command(motor_code, MotorLifecycleStates.STOPPED, "STOPPED")
        return results


    def begin_guarded_operation(
        self, motor_codes, operation_name, operation_id
    ):
        """Reserves motors for an external native operation."""
        return self.guarded_operation_manager.begin(
            motor_codes, operation_name, operation_id
        )


    def end_guarded_operation(
        self, operation_id, status="COMPLETED", error=None, stop=False
    ):
        """Releases motors reserved by an external native operation."""
        return self.guarded_operation_manager.end(
            operation_id, status=status, error=error, stop=stop
        )


    def execute_guarded_operation(
        self, motor_codes, operation_name, operation
    ):
        """Runs a bounded native operation under exclusive reservation."""
        return self.guarded_operation_manager.execute(
            motor_codes, operation_name, operation
        )


    def prepare_for_shutdown(self):
        """Stops all motors and clears pending commands before shutdown."""
        self.stop_all_motors(clear_queues=True)

    def on_finalize(self):
        """Stops workers and guarantees a best-effort physical motor stop."""
        self.safety_watchdog.stop(0.5)
        self.command_scheduler.stop(0.5)
        self.stop_all_motors(clear_queues=True)

    def stop_motor(self, motor_code, stop_action=None):
        """
        Enqueues a motor stop command.
        """
        return self._enqueue_motor_command(
            motor_code,
            MotorCommandActions.STOP,
            {"stop_action": stop_action or self.default_stop_action}
        )

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
        Enqueues a timed motor command.
        """
        return self._enqueue_motor_command(
            motor_code,
            MotorCommandActions.RUN_TIMED,
            {
                "speed_sp": speed_sp,
                "time_sp": time_sp,
                "profile": profile,
                "priority": priority,
                "timeout_ms": timeout_ms,
                "stop_action": stop_action or self.default_stop_action
            }
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
        Enqueues a continuous motor command.
        """
        return self._enqueue_motor_command(
            motor_code,
            MotorCommandActions.RUN_FOREVER,
            {
                "speed_sp": speed_sp,
                "profile": profile,
                "priority": priority,
                "watchdog_ms": watchdog_ms,
                "timeout_ms": timeout_ms,
                "stop_action": stop_action or self.default_stop_action
            }
        )

    def run_direct_motor(self, motor_code, duty_cycle_sp, priority=None, watchdog_ms=None, timeout_ms=None, stop_action=None):
        """Enqueues an unregulated direct duty-cycle command."""
        return self._enqueue_motor_command(
            motor_code, MotorCommandActions.RUN_DIRECT,
            {"duty_cycle_sp": duty_cycle_sp, "priority": priority,
             "watchdog_ms": watchdog_ms, "timeout_ms": timeout_ms,
             "stop_action": stop_action or self.default_stop_action}
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
        Enqueues a relative-position motor command.
        """
        return self._enqueue_motor_command(
            motor_code,
            MotorCommandActions.RUN_TO_REL_POS,
            {
                "speed_sp": speed_sp,
                "position_sp": position_sp,
                "profile": profile,
                "priority": priority,
                "timeout_ms": timeout_ms,
                "stop_action": stop_action or self.default_stop_action
            }
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
        """Enqueues an absolute-position motor command."""
        return self._enqueue_motor_command(
            motor_code,
            MotorCommandActions.RUN_TO_ABS_POS,
            {
                "speed_sp": speed_sp,
                "position_sp": position_sp,
                "profile": profile,
                "priority": priority,
                "timeout_ms": timeout_ms,
                "stop_action": stop_action or self.default_stop_action
            }
        )

    def drive_tank(self, left_speed_sp, right_speed_sp, **options):
        """Moves both traction motors through the monitored command path."""
        left = self.drive_left_motor_code
        right = self.drive_right_motor_code
        setpoint = (left_speed_sp, right_speed_sp, options.get("profile"))
        if self._last_drive_setpoint == setpoint:
            now = time.time()
            watchdog_ms = options.get("watchdog_ms") or self.run_forever_watchdog_ms
            with self._active_lock:
                active_left = self._active_commands.get(left)
                active_right = self._active_commands.get(right)
                if active_left and active_right:
                    active_left["watchdog_deadline"] = now + float(watchdog_ms) / 1000.0
                    active_right["watchdog_deadline"] = now + float(watchdog_ms) / 1000.0
                    return {
                "success": True, "reused": True,
                "motors": [self.read_motor(left), self.read_motor(right)]
            }
        common = {
            "action": MotorCommandActions.RUN_FOREVER,
            "priority": options.get("priority", 0),
            "profile": options.get("profile"),
            "watchdog_ms": options.get("watchdog_ms")
        }
        result = self.run_synchronized_motors([
            dict(common, code=left, speed_sp=left_speed_sp),
            dict(common, code=right, speed_sp=right_speed_sp)
        ])
        if result.get("success"):
            self._last_drive_setpoint = setpoint
        return result



    def stop_drive(self, stop_action=None):
        """Stops both configured traction motors."""
        self._last_drive_setpoint = None
        return {
            self.drive_left_motor_code: self.stop_motor(self.drive_left_motor_code, stop_action),
            self.drive_right_motor_code: self.stop_motor(self.drive_right_motor_code, stop_action)
        }

    def reset_motor(self, motor_code):
        """
        Enqueues a motor reset command.
        """
        return self._enqueue_motor_command(
            motor_code,
            MotorCommandActions.RESET
        )

    def cancel_motor_commands(self, motor_code):
        """
        Cancels queued motor commands for one motor.
        """
        motor = self.state_store.get_motor(motor_code)

        if motor is None:
            return None

        self._preempt_motor_commands(
            motor_code,
            stop_running_command=True
        )
        motor = self.state_store.get_motor(motor_code) or motor
        motor["pending_command"] = None
        motor["command_queue_size"] = self._get_queue_size(motor_code)
        motor["command"] = MotorCommandActions.CANCEL
        motor["lifecycle_state"] = MotorLifecycleStates.CANCELLED
        self.state_store.update_motor(motor_code, motor)
        return motor

    def run_synchronized_motors(self, commands):
        """Delegates synchronized batch assembly to its dedicated executor."""
        return self.synchronized_executor.execute(commands)


