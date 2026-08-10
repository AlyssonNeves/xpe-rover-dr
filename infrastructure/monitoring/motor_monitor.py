#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""EV3 motor monitoring with queued, prioritized command orchestration."""

import queue
import threading
import time

from app.rover_config import (
    HARDWARE_ENABLED, MONITOR_INTERVAL_SECONDS, MOTOR_COMMAND_TIMEOUT_MS,
    MOTOR_DEFAULT_STOP_ACTION, MOTOR_POSITION_TOLERANCE,
    MOTOR_RAMP_DOWN_MS, MOTOR_RAMP_UP_MS, MOTOR_RUN_FOREVER_WATCHDOG_MS,
    MOTOR_STALL_TIMEOUT_MS, get_motor_definitions
)
from infrastructure.ev3.motor_driver_factory import Ev3MotorDriverFactory
from infrastructure.monitoring.monitor_base import MonitorBase
from infrastructure.motor.command_executor import MotorCommandExecutor
from infrastructure.motor.driver_repository import Ev3MotorDriverRepository
from infrastructure.motor.registries import (
    GuardedOperationRegistry, MotorCommandRegistry
)
from infrastructure.motor.state_collector import MotorStateCollector
from infrastructure.state.motor_state_store import MotorStateStore


class MotorLifecycleStates(object):
    """Public execution states exposed in motor snapshots."""

    IDLE = "IDLE"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    STALLED = "STALLED"


class MotorCommandActions(object):
    """Motor operations supported by the first command queue."""

    STOP = "stop"
    RUN_TIMED = "run-timed"
    RUN_FOREVER = "run-forever"
    RUN_TO_REL_POS = "run-to-rel-pos"
    RESET = "reset"


class MotorMonitor(MonitorBase):
    """Publishes motor state and orchestrates commands through per-motor queues."""

    DEFAULT_PRIORITY = 0
    DIRECT_PROFILE = "direct"
    RAMP_UP_PROFILE = "ramp-up"
    RAMP_DOWN_PROFILE = "ramp-down"
    RAMP_UP_DOWN_PROFILE = "ramp-up-down"
    SUPPORTED_PROFILES = (
        DIRECT_PROFILE, RAMP_UP_PROFILE, RAMP_DOWN_PROFILE,
        RAMP_UP_DOWN_PROFILE
    )

    def __init__(
        self,
        state_store=None,
        interval_seconds=None,
        hardware_backend=None
    ):
        interval = (
            MONITOR_INTERVAL_SECONDS
            if interval_seconds is None
            else interval_seconds
        )
        MonitorBase.__init__(self, "MotorMonitor", interval)
        self.state_store = state_store or MotorStateStore()
        self.motor_definitions = get_motor_definitions()
        self.hardware_backend = hardware_backend or Ev3MotorDriverFactory(
            enabled=HARDWARE_ENABLED
        )
        self.motor_registry = Ev3MotorDriverRepository(
            self.motor_definitions, self.hardware_backend
        )
        self.command_executor = MotorCommandExecutor(
            self.motor_registry,
            MotorCommandActions,
            MOTOR_DEFAULT_STOP_ACTION,
            MOTOR_RAMP_UP_MS,
            MOTOR_RAMP_DOWN_MS,
            self.DIRECT_PROFILE,
            self.RAMP_UP_PROFILE,
            self.RAMP_DOWN_PROFILE,
            self.RAMP_UP_DOWN_PROFILE
        )
        self.state_collector = MotorStateCollector(
            self.state_store,
            self.motor_definitions,
            self.motor_registry,
            HARDWARE_ENABLED,
            MotorLifecycleStates.IDLE,
            {
                "command_timeout_ms": MOTOR_COMMAND_TIMEOUT_MS,
                "run_forever_watchdog_ms": MOTOR_RUN_FOREVER_WATCHDOG_MS,
                "stall_timeout_ms": MOTOR_STALL_TIMEOUT_MS,
                "default_stop_action": MOTOR_DEFAULT_STOP_ACTION
            }
        )
        self.command_registry = MotorCommandRegistry()
        self.guarded_operation_registry = GuardedOperationRegistry()

        self._queue_lock = threading.RLock()
        self._command_sequence = 0
        self._batch_sequence = 0
        self._queued_commands_by_motor = {
            code: [] for code in self.motor_definitions
        }
        self._motor_command_queues = {
            code: queue.PriorityQueue() for code in self.motor_definitions
        }
        self._worker_stop_event = threading.Event()
        self._worker_threads = {}
        self._active_commands = {}
        self._active_cancel_events = {}

        self._load_configured_motors()
        self._refresh_all_motors()

    def _load_configured_motors(self):
        self.state_collector.load_initial_motors()

    def _refresh_motor(self, motor_code):
        return self.state_collector.refresh_motor(motor_code)

    def _refresh_all_motors(self):
        self.state_collector.refresh_all_motors()

    def on_initialize(self):
        """Starts one queue worker for every configured motor."""
        self._worker_stop_event.clear()
        for motor_code in self.motor_definitions:
            worker = threading.Thread(
                target=self._motor_worker,
                args=(motor_code,),
                name="MotorWorker-{}".format(motor_code)
            )
            worker.daemon = True
            worker.start()
            self._worker_threads[motor_code] = worker

    def on_cycle(self):
        self._refresh_all_motors()

    def on_finalize(self):
        """Cancels queue workers and requests a safe motor stop."""
        self._worker_stop_event.set()
        for motor_code in self.motor_definitions:
            self._cancel_motor_commands(motor_code, stop_running=True)
        for worker in list(self._worker_threads.values()):
            if worker.is_alive():
                worker.join(0.5)

    def list_motors(self):
        return [
            {
                "code": item["code"],
                "name": item["name"],
                "address": item["address"],
                "connected": item["connected"],
                "command_queue_size": item.get("command_queue_size", 0),
                "active_command_id": item.get("active_command_id")
            }
            for item in self.state_store.get_all_motors()
        ]

    def read_motor(self, motor_code):
        return self.state_store.get_motor(motor_code)

    def read_all_motors(self):
        return self.state_store.get_all_motors()

    def get_command(self, command_id):
        return self.command_registry.get(command_id)

    def list_commands(self, motor_code=None):
        return self.command_registry.list(motor_code)

    def _next_command_id(self):
        with self._queue_lock:
            self._command_sequence += 1
            return self._command_sequence

    def _next_batch_id(self):
        with self._queue_lock:
            self._batch_sequence += 1
            return "BATCH-{}-{}".format(
                int(time.time() * 1000), self._batch_sequence
            )

    @staticmethod
    def _normalize_priority(priority):
        if isinstance(priority, bool) or not isinstance(priority, int):
            return MotorMonitor.DEFAULT_PRIORITY
        return priority

    def _normalize_profile(self, profile):
        """Returns a supported movement profile, defaulting to direct."""
        if profile in self.SUPPORTED_PROFILES:
            return profile
        return self.DIRECT_PROFILE

    def _queue_size(self, motor_code):
        commands = self._queued_commands_by_motor.get(motor_code, [])
        return len([item for item in commands if not item.get("cancelled")])

    def _update_motor_queue_metadata(
        self, motor_code, lifecycle_state=None, active_command_id=None,
        last_command_id=None
    ):
        motor = self.state_store.get_motor(motor_code)
        if motor is None:
            return None
        motor["command_queue_size"] = self._queue_size(motor_code)
        if lifecycle_state is not None:
            motor["lifecycle_state"] = lifecycle_state
        if active_command_id is not None or lifecycle_state in (
            MotorLifecycleStates.COMPLETED,
            MotorLifecycleStates.FAILED,
            MotorLifecycleStates.CANCELLED,
            MotorLifecycleStates.IDLE
        ):
            motor["active_command_id"] = active_command_id
        if last_command_id is not None:
            motor["last_command_id"] = last_command_id
        self.state_store.update_motor(motor_code, motor)
        return motor

    def _enqueue_motor_command(
        self, motor_code, action, parameters=None, priority=None,
        batch_id=None, start_at=None
    ):
        if motor_code not in self.motor_definitions:
            return None
        with self.guarded_operation_registry.lock:
            if motor_code in self.guarded_operation_registry.active_motor_codes:
                return {
                    "accepted": False,
                    "status": MotorLifecycleStates.FAILED,
                    "error": "Motor is reserved by an EV3Dev2 gateway operation",
                    "motor_code": motor_code
                }

        priority = self._normalize_priority(priority)
        command_id = self._next_command_id()
        queued_at = time.time()
        command = {
            "command_id": command_id,
            "motor_code": motor_code,
            "action": action,
            "parameters": dict(parameters or {}),
            "priority": priority,
            "batch_id": batch_id,
            "start_at": start_at,
            "cancelled": False,
            "queued_at": queued_at
        }

        public_record = {
            "command_id": command_id,
            "motor_code": motor_code,
            "action": action,
            "parameters": dict(parameters or {}),
            "priority": priority,
            "batch_id": batch_id,
            "status": MotorLifecycleStates.QUEUED,
            "queued_at": queued_at
        }
        if start_at is not None:
            public_record["scheduled_start_at"] = start_at
        self.command_registry.create(public_record)

        with self._queue_lock:
            self._queued_commands_by_motor[motor_code].append(command)
            # Higher numeric priority executes first; sequence preserves FIFO.
            self._motor_command_queues[motor_code].put(
                (-priority, command_id, command)
            )
            motor = self._update_motor_queue_metadata(
                motor_code,
                lifecycle_state=MotorLifecycleStates.QUEUED,
                last_command_id=command_id
            )

        return {
            "accepted": True,
            "command_id": command_id,
            "status": MotorLifecycleStates.QUEUED,
            "priority": priority,
            "batch_id": batch_id,
            "motor": motor
        }

    def _remove_queued_command(self, command):
        motor_code = command["motor_code"]
        with self._queue_lock:
            self._queued_commands_by_motor[motor_code] = [
                item for item in self._queued_commands_by_motor[motor_code]
                if item["command_id"] != command["command_id"]
            ]

    def _motor_worker(self, motor_code):
        motor_queue = self._motor_command_queues[motor_code]
        while not self._worker_stop_event.is_set():
            try:
                _, _, command = motor_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                if command.get("cancelled"):
                    self.command_registry.update(
                        command["command_id"],
                        MotorLifecycleStates.CANCELLED,
                        completed_at=time.time()
                    )
                else:
                    self._execute_queued_command(command)
            finally:
                self._remove_queued_command(command)
                self._update_motor_queue_metadata(motor_code)
                motor_queue.task_done()

    def _wait_for_scheduled_start(self, command, cancel_event):
        start_at = command.get("start_at")
        if start_at is None:
            return True
        while time.time() < start_at:
            if cancel_event.is_set() or self._worker_stop_event.is_set():
                return False
            remaining = start_at - time.time()
            time.sleep(min(0.01, max(0.0, remaining)))
        return True

    def _position_progressed(self, previous_position, current_position):
        if previous_position is None or current_position is None:
            return True
        try:
            return abs(current_position - previous_position) > MOTOR_POSITION_TOLERANCE
        except TypeError:
            return True

    def _wait_for_motion_completion(
        self, motor_code, cancel_event, deadline_monotonic, stall_timeout_ms
    ):
        """Waits for bounded motion and enforces timeout/stall protection."""
        last_progress_at = time.monotonic()
        snapshot = self.motor_registry.read_motor(motor_code) or {}
        last_position = snapshot.get("position")

        while self.motor_registry.is_running(motor_code):
            if cancel_event.is_set() or self._worker_stop_event.is_set():
                self.motor_registry.stop_motor(
                    motor_code, MOTOR_DEFAULT_STOP_ACTION
                )
                return "cancelled", "Command cancelled"

            now = time.monotonic()
            if now >= deadline_monotonic:
                self.motor_registry.stop_motor(
                    motor_code, MOTOR_DEFAULT_STOP_ACTION
                )
                return "timed_out", "Motor command execution timeout expired"

            snapshot = self.motor_registry.read_motor(motor_code) or {}
            states = snapshot.get("state") or []
            if "stalled" in states:
                self.motor_registry.stop_motor(
                    motor_code, MOTOR_DEFAULT_STOP_ACTION
                )
                return "stalled", "Motor driver reported stalled state"

            current_position = snapshot.get("position")
            if self._position_progressed(last_position, current_position):
                last_position = current_position
                last_progress_at = now
            elif (now - last_progress_at) * 1000.0 >= stall_timeout_ms:
                self.motor_registry.stop_motor(
                    motor_code, MOTOR_DEFAULT_STOP_ACTION
                )
                return "stalled", "Motor position did not progress within stall timeout"

            time.sleep(0.02)
        return "completed", None

    def _execute_hardware_command(self, command, cancel_event):
        motor_code = command["motor_code"]
        action = command["action"]
        params = command.get("parameters", {})
        stop_action = params.get("stop_action") or MOTOR_DEFAULT_STOP_ACTION
        timeout_ms = params.get("timeout_ms") or MOTOR_COMMAND_TIMEOUT_MS
        stall_timeout_ms = params.get("stall_timeout_ms") or MOTOR_STALL_TIMEOUT_MS

        if action == MotorCommandActions.RUN_TIMED:
            accepted, error = self.command_executor.execute(
                motor_code, action, params
            )
            if not accepted:
                return False, error, "failed"
            # Give run-timed its requested duration plus the general safety margin.
            deadline = time.monotonic() + (
                float(params["time_sp"] + timeout_ms) / 1000.0
            )
            outcome, error = self._wait_for_motion_completion(
                motor_code, cancel_event, deadline, stall_timeout_ms
            )
            return outcome == "completed", error, outcome

        if action == MotorCommandActions.RUN_FOREVER:
            accepted, error = self.command_executor.execute(
                motor_code, action, params
            )
            if not accepted:
                return False, error, "failed"
            watchdog_ms = params.get("watchdog_ms") or MOTOR_RUN_FOREVER_WATCHDOG_MS
            watchdog_deadline = time.monotonic() + float(watchdog_ms) / 1000.0
            execution_deadline = time.monotonic() + float(timeout_ms) / 1000.0
            last_progress_at = time.monotonic()
            snapshot = self.motor_registry.read_motor(motor_code) or {}
            last_position = snapshot.get("position")
            while True:
                if cancel_event.is_set() or self._worker_stop_event.is_set():
                    self.motor_registry.stop_motor(motor_code, stop_action)
                    return False, "Command cancelled", "cancelled"
                now = time.monotonic()
                if now >= watchdog_deadline:
                    self.motor_registry.stop_motor(motor_code, stop_action)
                    return False, "run-forever watchdog expired", "timed_out"
                if now >= execution_deadline:
                    self.motor_registry.stop_motor(motor_code, stop_action)
                    return False, "Motor command execution timeout expired", "timed_out"
                snapshot = self.motor_registry.read_motor(motor_code) or {}
                states = snapshot.get("state") or []
                if "stalled" in states:
                    self.motor_registry.stop_motor(motor_code, stop_action)
                    return False, "Motor driver reported stalled state", "stalled"
                current_position = snapshot.get("position")
                if self._position_progressed(last_position, current_position):
                    last_position = current_position
                    last_progress_at = now
                elif (now - last_progress_at) * 1000.0 >= stall_timeout_ms:
                    self.motor_registry.stop_motor(motor_code, stop_action)
                    return False, "Motor position did not progress within stall timeout", "stalled"
                time.sleep(0.02)

        if action == MotorCommandActions.RUN_TO_REL_POS:
            accepted, error = self.command_executor.execute(
                motor_code, action, params
            )
            if not accepted:
                return False, error, "failed"
            deadline = time.monotonic() + float(timeout_ms) / 1000.0
            outcome, error = self._wait_for_motion_completion(
                motor_code, cancel_event, deadline, stall_timeout_ms
            )
            return outcome == "completed", error, outcome

        if action == MotorCommandActions.RESET:
            accepted, error = self.command_executor.execute(
                motor_code, action, params
            )
            return accepted, error, "completed" if accepted else "failed"

        return False, "Unsupported queued motor action", "failed"

    def _execute_queued_command(self, command):
        motor_code = command["motor_code"]
        command_id = command["command_id"]
        cancel_event = threading.Event()

        with self._queue_lock:
            self._active_commands[motor_code] = command
            self._active_cancel_events[motor_code] = cancel_event

        self.command_registry.update(
            command_id, MotorLifecycleStates.RUNNING, started_at=time.time()
        )
        self._update_motor_queue_metadata(
            motor_code,
            lifecycle_state=MotorLifecycleStates.RUNNING,
            active_command_id=command_id,
            last_command_id=command_id
        )

        if not self._wait_for_scheduled_start(command, cancel_event):
            accepted, error, outcome = False, "Command cancelled", "cancelled"
        else:
            accepted, error, outcome = self._execute_hardware_command(
                command, cancel_event
            )

        finished_at = time.time()
        status_by_outcome = {
            "cancelled": MotorLifecycleStates.CANCELLED,
            "timed_out": MotorLifecycleStates.TIMED_OUT,
            "stalled": MotorLifecycleStates.STALLED,
            "completed": MotorLifecycleStates.COMPLETED,
            "failed": MotorLifecycleStates.FAILED
        }
        final_status = status_by_outcome.get(
            outcome, MotorLifecycleStates.COMPLETED if accepted else MotorLifecycleStates.FAILED
        )

        self.command_registry.update(
            command_id, final_status, completed_at=finished_at, error=error
        )

        if final_status in (
            MotorLifecycleStates.TIMED_OUT, MotorLifecycleStates.STALLED
        ):
            motor_snapshot = self.state_store.get_motor(motor_code) or {}
            motor_snapshot["last_safety_event"] = {
                "command_id": command_id,
                "status": final_status,
                "message": error,
                "timestamp": finished_at
            }
            self.state_store.update_motor(motor_code, motor_snapshot)

        with self._queue_lock:
            self._active_commands.pop(motor_code, None)
            self._active_cancel_events.pop(motor_code, None)

        self._refresh_motor(motor_code)
        current_motor = self.state_store.get_motor(motor_code) or {}
        newer_command_exists = (
            current_motor.get("last_command_id") is not None
            and current_motor.get("last_command_id") > command_id
        )
        if newer_command_exists:
            self._update_motor_queue_metadata(
                motor_code, active_command_id=None
            )
        else:
            self._update_motor_queue_metadata(
                motor_code,
                lifecycle_state=final_status,
                active_command_id=None,
                last_command_id=command_id
            )

    def _register_immediate_command(
        self, motor_code, action, parameters, accepted, error
    ):
        command_id = self._next_command_id()
        now = time.time()
        status = (
            MotorLifecycleStates.COMPLETED
            if accepted else MotorLifecycleStates.FAILED
        )
        record = {
            "command_id": command_id,
            "motor_code": motor_code,
            "action": action,
            "parameters": dict(parameters or {}),
            "priority": None,
            "batch_id": None,
            "status": status,
            "queued_at": now,
            "started_at": now,
            "completed_at": now,
            "error": error
        }
        self.command_registry.create(record)
        self._refresh_motor(motor_code)
        motor = self._update_motor_queue_metadata(
            motor_code, lifecycle_state=status,
            active_command_id=None, last_command_id=command_id
        )
        return {
            "accepted": bool(accepted),
            "command_id": command_id,
            "status": status,
            "motor": motor,
            "error": error
        }

    def _cancel_motor_commands(self, motor_code, stop_running=True):
        if motor_code not in self.motor_definitions:
            return None

        cancelled_ids = []
        with self._queue_lock:
            for command in self._queued_commands_by_motor[motor_code]:
                if not command.get("cancelled"):
                    command["cancelled"] = True
                    cancelled_ids.append(command["command_id"])
                    self.command_registry.update(
                        command["command_id"],
                        MotorLifecycleStates.CANCELLED,
                        completed_at=time.time()
                    )
            cancel_event = self._active_cancel_events.get(motor_code)
            active = self._active_commands.get(motor_code)
            if cancel_event is not None:
                cancel_event.set()
                if active is not None:
                    cancelled_ids.append(active["command_id"])

        if stop_running and active is not None:
            self.motor_registry.stop_motor(motor_code, MOTOR_DEFAULT_STOP_ACTION)

        motor = self._update_motor_queue_metadata(
            motor_code,
            lifecycle_state=(
                MotorLifecycleStates.CANCELLED
                if cancelled_ids else MotorLifecycleStates.IDLE
            ),
            active_command_id=None
        )
        return {
            "accepted": True,
            "motor_code": motor_code,
            "cancelled_command_ids": sorted(set(cancelled_ids)),
            "motor": motor
        }

    def _validate_external_motor_codes(self, motor_codes):
        codes = []
        for code in motor_codes or []:
            if code not in self.motor_definitions:
                raise ValueError("Unknown motor code: {}".format(code))
            if code not in codes:
                codes.append(code)
        if not codes:
            raise ValueError("At least one configured motor is required.")
        return codes

    def begin_guarded_operation(self, motor_codes, operation_name, operation_id):
        """Reserves configured motors for a native EV3Dev2 operation."""
        codes = self._validate_external_motor_codes(motor_codes)
        with self.guarded_operation_registry.lock:
            conflicts = [
                code for code in codes
                if code in self.guarded_operation_registry.active_motor_codes
            ]
            if conflicts:
                raise ValueError(
                    "Motors already reserved: {}".format(", ".join(conflicts))
                )
            for code in codes:
                self._cancel_motor_commands(code, stop_running=True)
            return self.guarded_operation_registry.reserve(
                codes, operation_name, operation_id
            )

    def end_guarded_operation(self, operation_id, status="COMPLETED",
                              error=None, stop=False):
        """Releases a native operation and optionally stops its motors."""
        with self.guarded_operation_registry.lock:
            record = self.guarded_operation_registry.operations.get(operation_id)
            if record is None:
                return None
            stop_errors = []
            if stop:
                for code in record["motor_codes"]:
                    accepted, stop_error = self.motor_registry.stop_motor(
                        code, MOTOR_DEFAULT_STOP_ACTION
                    )
                    if not accepted and stop_error:
                        stop_errors.append("{}: {}".format(code, stop_error))
            return self.guarded_operation_registry.release(
                operation_id, status=status, error=error, stop_errors=stop_errors
            )

    def execute_guarded_operation(self, motor_codes, operation_name, operation):
        """Executes one bounded native call under the motor reservation."""
        operation_id = "sync-{}-{}".format(
            int(time.time() * 1000), id(operation)
        )
        self.begin_guarded_operation(motor_codes, operation_name, operation_id)
        try:
            result = operation()
            self.end_guarded_operation(operation_id, status="COMPLETED")
            return result
        except Exception as error:
            self.end_guarded_operation(
                operation_id, status="FAILED", error=error, stop=True
            )
            raise

    def cancel_motor_commands(self, motor_code):
        return self._cancel_motor_commands(motor_code, stop_running=True)

    def stop_motor(self, motor_code, stop_action=None):
        if motor_code not in self.motor_definitions:
            return None
        self._cancel_motor_commands(motor_code, stop_running=False)
        accepted, error = self.motor_registry.stop_motor(
            motor_code, stop_action or MOTOR_DEFAULT_STOP_ACTION
        )
        return self._register_immediate_command(
            motor_code, MotorCommandActions.STOP,
            {"stop_action": stop_action}, accepted, error
        )

    def run_timed_motor(
        self, motor_code, speed_sp, time_sp, priority=None, stop_action=None,
        timeout_ms=None, profile=None
    ):
        return self._enqueue_motor_command(
            motor_code, MotorCommandActions.RUN_TIMED,
            {
                "speed_sp": speed_sp,
                "time_sp": time_sp,
                "stop_action": stop_action,
                "timeout_ms": timeout_ms,
                "profile": self._normalize_profile(profile)
            },
            priority=priority
        )

    def run_forever_motor(
        self, motor_code, speed_sp, priority=None, stop_action=None,
        watchdog_ms=None, timeout_ms=None, profile=None
    ):
        return self._enqueue_motor_command(
            motor_code, MotorCommandActions.RUN_FOREVER,
            {
                "speed_sp": speed_sp,
                "stop_action": stop_action,
                "watchdog_ms": watchdog_ms,
                "timeout_ms": timeout_ms,
                "profile": self._normalize_profile(profile)
            },
            priority=priority
        )

    def run_to_rel_pos_motor(
        self, motor_code, speed_sp, position_sp, priority=None,
        stop_action=None, timeout_ms=None, profile=None
    ):
        return self._enqueue_motor_command(
            motor_code, MotorCommandActions.RUN_TO_REL_POS,
            {
                "speed_sp": speed_sp,
                "position_sp": position_sp,
                "stop_action": stop_action,
                "timeout_ms": timeout_ms,
                "profile": self._normalize_profile(profile)
            },
            priority=priority
        )

    def reset_motor(self, motor_code, priority=None):
        return self._enqueue_motor_command(
            motor_code, MotorCommandActions.RESET, {}, priority=priority
        )

    def run_synchronized_motors(self, commands):
        """Queues a best-effort synchronized batch using a shared start time."""
        if not commands:
            return {
                "accepted": False,
                "error": "At least one motor command is required"
            }

        batch_id = self._next_batch_id()
        scheduled_start_at = time.time() + 0.10
        submissions = []

        for command in commands:
            action = command["action"]
            motor_code = command["code"]
            params = dict(command.get("parameters") or {})
            priority = command.get("priority", self.DEFAULT_PRIORITY)
            submission = self._enqueue_motor_command(
                motor_code, action, params, priority=priority,
                batch_id=batch_id, start_at=scheduled_start_at
            )
            if submission is None:
                return {
                    "accepted": False,
                    "error": "Motor not found: {}".format(motor_code)
                }
            submissions.append(submission)

        return {
            "accepted": True,
            "batch_id": batch_id,
            "scheduled_start_at": scheduled_start_at,
            "command_ids": [item["command_id"] for item in submissions],
            "commands": submissions
        }
