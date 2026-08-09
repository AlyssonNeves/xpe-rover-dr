#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""EV3 motor monitoring with queued, prioritized command orchestration."""

import queue
import threading
import time

from app.rover_config import MONITOR_INTERVAL_SECONDS, get_motor_definitions
from services.monitor_base import MonitorBase
from services.motor.registries import MotorCommandRegistry
from services.motor_state_store import MotorStateStore


class MotorLifecycleStates(object):
    """Public execution states exposed in motor snapshots."""

    IDLE = "IDLE"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class MotorCommandActions(object):
    """Motor operations supported by the first command queue."""

    STOP = "stop"
    RUN_TIMED = "run-timed"
    RUN_FOREVER = "run-forever"
    RUN_TO_REL_POS = "run-to-rel-pos"
    RESET = "reset"


class Ev3MotorHardwareBackend(object):
    """Loads the supported python-ev3dev2 motor classes when available."""

    def __init__(self):
        self._motor_classes = {}
        self.error_message = None
        self._load_motor_classes()

    def _load_motor_classes(self):
        try:
            from ev3dev2.motor import LargeMotor  # pylint: disable=import-error
            from ev3dev2.motor import MediumMotor  # pylint: disable=import-error

            self._motor_classes = {
                "LargeMotor": LargeMotor,
                "MediumMotor": MediumMotor
            }
            self.error_message = None
        except Exception as error:  # pragma: no cover - environment dependent
            self._motor_classes = {}
            self.error_message = str(error)

    def is_available(self):
        return bool(self._motor_classes)

    def get_motor_class(self, motor_class_name):
        return self._motor_classes.get(motor_class_name)


class MotorRegistry(object):
    """Owns physical motor instances and performs EV3 read/write access."""

    def __init__(self, motor_definitions, hardware_backend):
        self.motor_definitions = motor_definitions
        self.hardware_backend = hardware_backend
        self._motors = {}
        self._errors = {}

    @staticmethod
    def _safe_get(motor, attribute_name, default=None):
        try:
            return getattr(motor, attribute_name)
        except Exception:  # pragma: no cover - depends on EV3 driver
            return default

    @staticmethod
    def _normalize_state(value):
        if value is None:
            return []
        if isinstance(value, (tuple, set)):
            return list(value)
        if isinstance(value, list):
            return value
        return [value]

    def connect_motor(self, motor_code):
        definition = self.motor_definitions.get(motor_code)
        if definition is None:
            return None

        motor_class = self.hardware_backend.get_motor_class(
            definition.get("motor_class")
        )
        if motor_class is None:
            self._errors[motor_code] = (
                self.hardware_backend.error_message
                or "Configured motor class is not available"
            )
            return None

        try:
            motor = motor_class(definition["address"])
            polarity = definition.get("polarity")
            if polarity is not None:
                motor.polarity = polarity
            self._motors[motor_code] = motor
            self._errors[motor_code] = None
            return motor
        except Exception as error:  # pragma: no cover - hardware dependent
            self._motors.pop(motor_code, None)
            self._errors[motor_code] = str(error)
            return None

    def get_motor(self, motor_code):
        motor = self._motors.get(motor_code)
        if motor is None:
            motor = self.connect_motor(motor_code)
        if motor is None:
            return None

        connected = self._safe_get(motor, "connected", True)
        if connected is False:
            self._motors.pop(motor_code, None)
            self._errors[motor_code] = "Motor is disconnected"
            return None
        return motor

    def read_motor(self, motor_code):
        motor = self.get_motor(motor_code)
        if motor is None:
            return None

        return {
            "position": self._safe_get(motor, "position", 0),
            "speed": self._safe_get(motor, "speed", 0),
            "duty_cycle": self._safe_get(motor, "duty_cycle", 0),
            "state": self._normalize_state(self._safe_get(motor, "state", [])),
            "driver_name": self._safe_get(motor, "driver_name"),
            "max_speed": self._safe_get(motor, "max_speed"),
            "polarity": self._safe_get(motor, "polarity"),
            "connected": True
        }

    def execute(self, motor_code, operation_name, operation):
        """Executes one hardware operation and captures driver failures."""
        motor = self.get_motor(motor_code)
        if motor is None:
            return False, self.get_error(motor_code)

        try:
            operation(motor)
            self._errors[motor_code] = None
            return True, None
        except Exception as error:  # pragma: no cover - hardware dependent
            self._errors[motor_code] = "{} failed: {}".format(
                operation_name, error
            )
            return False, self._errors[motor_code]

    @staticmethod
    def _apply_stop_action(motor, stop_action):
        if stop_action is not None:
            motor.stop_action = stop_action

    def stop_motor(self, motor_code, stop_action=None):
        def operation(motor):
            self._apply_stop_action(motor, stop_action)
            motor.stop()
        return self.execute(motor_code, "stop", operation)

    def run_timed_motor(self, motor_code, speed_sp, time_sp, stop_action=None):
        def operation(motor):
            self._apply_stop_action(motor, stop_action)
            motor.run_timed(speed_sp=speed_sp, time_sp=time_sp)
        return self.execute(motor_code, "run-timed", operation)

    def run_forever_motor(self, motor_code, speed_sp, stop_action=None):
        def operation(motor):
            self._apply_stop_action(motor, stop_action)
            motor.run_forever(speed_sp=speed_sp)
        return self.execute(motor_code, "run-forever", operation)

    def run_to_rel_pos_motor(
        self, motor_code, speed_sp, position_sp, stop_action=None
    ):
        def operation(motor):
            self._apply_stop_action(motor, stop_action)
            motor.run_to_rel_pos(speed_sp=speed_sp, position_sp=position_sp)
        return self.execute(motor_code, "run-to-rel-pos", operation)

    def reset_motor(self, motor_code):
        return self.execute(motor_code, "reset", lambda motor: motor.reset())

    def is_running(self, motor_code):
        motor = self.get_motor(motor_code)
        if motor is None:
            return False
        state = self._normalize_state(self._safe_get(motor, "state", []))
        return "running" in state

    def get_error(self, motor_code):
        return self._errors.get(motor_code)


class MotorMonitor(MonitorBase):
    """Publishes motor state and orchestrates commands through per-motor queues."""

    DEFAULT_PRIORITY = 0

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
        self.hardware_backend = hardware_backend or Ev3MotorHardwareBackend()
        self.motor_registry = MotorRegistry(
            self.motor_definitions, self.hardware_backend
        )
        self.command_registry = MotorCommandRegistry()

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

    def _base_snapshot(self, motor_code, definition):
        return {
            "code": motor_code,
            "name": definition["name"],
            "address": definition["address"],
            "motor_class": definition.get("motor_class"),
            "polarity": definition.get("polarity"),
            "position": 0,
            "speed": 0,
            "duty_cycle": 0,
            "state": [],
            "driver_name": None,
            "max_speed": None,
            "connected": False,
            "source": "ev3dev2",
            "error": None,
            "lifecycle_state": MotorLifecycleStates.IDLE,
            "command_queue_size": 0,
            "active_command_id": None,
            "last_command_id": None
        }

    def _load_configured_motors(self):
        for code, definition in self.motor_definitions.items():
            self.state_store.update_motor(
                code, self._base_snapshot(code, definition)
            )

    def _refresh_motor(self, motor_code):
        definition = self.motor_definitions[motor_code]
        previous = self.state_store.get_motor(motor_code) or {}
        snapshot = self._base_snapshot(motor_code, definition)
        for field in (
            "lifecycle_state", "command_queue_size",
            "active_command_id", "last_command_id"
        ):
            if field in previous:
                snapshot[field] = previous[field]

        hardware_snapshot = self.motor_registry.read_motor(motor_code)
        if hardware_snapshot is not None:
            snapshot.update(hardware_snapshot)
            snapshot["error"] = None
        else:
            snapshot["error"] = self.motor_registry.get_error(motor_code)

        self.state_store.update_motor(motor_code, snapshot)
        return snapshot

    def _refresh_all_motors(self):
        for motor_code in self.motor_definitions:
            self._refresh_motor(motor_code)

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

    def _wait_until_not_running(self, motor_code, cancel_event):
        """Waits without timeout; Commit 11 introduces safety deadlines."""
        while self.motor_registry.is_running(motor_code):
            if cancel_event.is_set() or self._worker_stop_event.is_set():
                self.motor_registry.stop_motor(motor_code, "brake")
                return False
            time.sleep(0.02)
        return True

    def _execute_hardware_command(self, command, cancel_event):
        motor_code = command["motor_code"]
        action = command["action"]
        params = command.get("parameters", {})

        if action == MotorCommandActions.RUN_TIMED:
            accepted, error = self.motor_registry.run_timed_motor(
                motor_code, params["speed_sp"], params["time_sp"],
                params.get("stop_action")
            )
            if accepted and not self._wait_until_not_running(
                motor_code, cancel_event
            ):
                return False, "Command cancelled", True
            return accepted, error, False

        if action == MotorCommandActions.RUN_FOREVER:
            accepted, error = self.motor_registry.run_forever_motor(
                motor_code, params["speed_sp"], params.get("stop_action")
            )
            if not accepted:
                return False, error, False
            while not cancel_event.is_set() and not self._worker_stop_event.is_set():
                time.sleep(0.02)
            self.motor_registry.stop_motor(motor_code, params.get("stop_action") or "brake")
            return False, "Command cancelled", True

        if action == MotorCommandActions.RUN_TO_REL_POS:
            accepted, error = self.motor_registry.run_to_rel_pos_motor(
                motor_code, params["speed_sp"], params["position_sp"],
                params.get("stop_action")
            )
            if accepted and not self._wait_until_not_running(
                motor_code, cancel_event
            ):
                return False, "Command cancelled", True
            return accepted, error, False

        if action == MotorCommandActions.RESET:
            accepted, error = self.motor_registry.reset_motor(motor_code)
            return accepted, error, False

        return False, "Unsupported queued motor action", False

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
            accepted, error, cancelled = False, "Command cancelled", True
        else:
            accepted, error, cancelled = self._execute_hardware_command(
                command, cancel_event
            )

        finished_at = time.time()
        if cancelled:
            final_status = MotorLifecycleStates.CANCELLED
        elif accepted:
            final_status = MotorLifecycleStates.COMPLETED
        else:
            final_status = MotorLifecycleStates.FAILED

        self.command_registry.update(
            command_id, final_status, completed_at=finished_at, error=error
        )

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
            self.motor_registry.stop_motor(motor_code, "brake")

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

    def cancel_motor_commands(self, motor_code):
        return self._cancel_motor_commands(motor_code, stop_running=True)

    def stop_motor(self, motor_code, stop_action=None):
        if motor_code not in self.motor_definitions:
            return None
        self._cancel_motor_commands(motor_code, stop_running=False)
        accepted, error = self.motor_registry.stop_motor(
            motor_code, stop_action
        )
        return self._register_immediate_command(
            motor_code, MotorCommandActions.STOP,
            {"stop_action": stop_action}, accepted, error
        )

    def run_timed_motor(
        self, motor_code, speed_sp, time_sp, priority=None, stop_action=None
    ):
        return self._enqueue_motor_command(
            motor_code, MotorCommandActions.RUN_TIMED,
            {
                "speed_sp": speed_sp,
                "time_sp": time_sp,
                "stop_action": stop_action
            },
            priority=priority
        )

    def run_forever_motor(
        self, motor_code, speed_sp, priority=None, stop_action=None
    ):
        return self._enqueue_motor_command(
            motor_code, MotorCommandActions.RUN_FOREVER,
            {"speed_sp": speed_sp, "stop_action": stop_action},
            priority=priority
        )

    def run_to_rel_pos_motor(
        self, motor_code, speed_sp, position_sp, priority=None,
        stop_action=None
    ):
        return self._enqueue_motor_command(
            motor_code, MotorCommandActions.RUN_TO_REL_POS,
            {
                "speed_sp": speed_sp,
                "position_sp": position_sp,
                "stop_action": stop_action
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
