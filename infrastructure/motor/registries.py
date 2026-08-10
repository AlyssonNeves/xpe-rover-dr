#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Thread-safe command registries used by motor orchestration."""

import copy
import threading
import time


class MotorCommandRegistry(object):
    """Stores externally consultable motor-command lifecycle snapshots."""

    def __init__(self):
        self._items = {}
        self._lock = threading.RLock()

    def create(self, command):
        """Registers a newly accepted command."""
        item = copy.deepcopy(command)
        command_id = int(item["command_id"])
        with self._lock:
            self._items[command_id] = item
        return copy.deepcopy(item)

    def get(self, command_id):
        """Returns one lifecycle snapshot by identifier."""
        try:
            command_id = int(command_id)
        except (TypeError, ValueError):
            return None
        with self._lock:
            item = self._items.get(command_id)
            return copy.deepcopy(item) if item is not None else None

    def list(self, motor_code=None):
        """Lists command snapshots, optionally filtered by motor."""
        with self._lock:
            items = [copy.deepcopy(item) for item in self._items.values()]
        if motor_code is not None:
            items = [
                item for item in items
                if item.get("motor_code") == motor_code
            ]
        return sorted(items, key=lambda item: item["command_id"])

    def update(self, command_id, status, **fields):
        """Updates lifecycle fields for a previously registered command."""
        try:
            command_id = int(command_id)
        except (TypeError, ValueError):
            return None
        with self._lock:
            item = self._items.get(command_id)
            if item is None:
                return None
            item["status"] = status
            item.update(copy.deepcopy(fields))
            return copy.deepcopy(item)


class GuardedOperationRegistry(object):
    """Tracks motor reservations used by native EV3Dev2 operations."""

    HISTORY_LIMIT = 100

    def __init__(self):
        self.lock = threading.RLock()
        self.active_motor_codes = set()
        self.operations = {}
        self.history = []

    def reserve(self, motor_codes, operation_name, operation_id):
        with self.lock:
            conflicts = [
                code for code in motor_codes
                if code in self.active_motor_codes
            ]
            if conflicts:
                raise ValueError(
                    "Motors already reserved: {}".format(", ".join(conflicts))
                )
            record = {
                "operation_id": operation_id,
                "operation": operation_name,
                "motor_codes": list(motor_codes),
                "started_at": time.time(),
                "status": "RUNNING"
            }
            self.operations[operation_id] = record
            self.active_motor_codes.update(motor_codes)
            return copy.deepcopy(record)

    def release(self, operation_id, status="COMPLETED", error=None,
                stop_errors=None):
        with self.lock:
            record = self.operations.pop(operation_id, None)
            if record is None:
                return None
            stop_errors = list(stop_errors or [])
            record["status"] = "STOP_FAILED" if stop_errors else status
            if stop_errors:
                record["stop_errors"] = stop_errors
            if error is not None:
                record["error"] = str(error)
            record["finished_at"] = time.time()
            self.active_motor_codes.difference_update(record["motor_codes"])
            self.history.append(copy.deepcopy(record))
            if len(self.history) > self.HISTORY_LIMIT:
                self.history[:] = self.history[-self.HISTORY_LIMIT:]
            return copy.deepcopy(record)
