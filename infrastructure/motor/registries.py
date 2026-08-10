#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Thread-safe registries owned by the motor-monitor infrastructure."""

import copy
import threading

from app.sequence_utils import unique_preserving_order


class MotorCommandRegistry(object):
    """Encapsulates motor-command lifecycle records and synchronization."""

    def __init__(self):
        self._items = {}
        self._lock = threading.RLock()

    def create(self, command_id, motor_code, action, priority, batch_id,
               queued_at, parameters):
        record = {
            "id": command_id,
            "command_id": command_id,
            "motor_code": motor_code,
            "action": action,
            "priority": priority,
            "batch_id": batch_id,
            "status": "QUEUED",
            "queued_at": queued_at,
            "started_at": None,
            "completed_at": None,
            "error": None,
            "parameters": copy.deepcopy(parameters or {})
        }
        with self._lock:
            self._items[command_id] = record
            return copy.deepcopy(record)

    def get(self, command_id):
        with self._lock:
            record = self._items.get(command_id)
            return copy.deepcopy(record) if record is not None else None

    def list(self, motor_code=None):
        with self._lock:
            records = list(self._items.values())
            if motor_code is not None:
                records = [
                    item for item in records
                    if item.get("motor_code") == motor_code
                ]
            records.sort(key=lambda item: item.get("id", 0))
            return copy.deepcopy(records)

    def update(self, command_id, status, **fields):
        with self._lock:
            record = self._items.get(command_id)
            if record is None:
                return None
            record["status"] = status
            record.update(fields)
            return copy.deepcopy(record)


class GuardedOperationRegistry(object):
    """Owns reservations and lifecycle history for native operations."""

    def __init__(self):
        self._lock = threading.RLock()
        self._active_motor_codes = set()
        self._operations = {}

    def conflicts(self, motor_codes):
        codes = set(motor_codes or [])
        with self._lock:
            return bool(codes.intersection(self._active_motor_codes))

    def is_reserved(self, motor_code):
        with self._lock:
            return motor_code in self._active_motor_codes

    def reserve(self, operation_id, motor_codes, operation_name,
                started_at=None):
        codes = list(unique_preserving_order(motor_codes))
        with self._lock:
            if set(codes).intersection(self._active_motor_codes):
                raise RuntimeError(
                    "One or more motors are already reserved by a guarded "
                    "operation."
                )
            record = {
                "id": operation_id,
                "operation": operation_name,
                "motor_codes": codes,
                "status": "ACTIVE",
                "started_at": started_at,
                "completed_at": None,
                "error": None
            }
            self._operations[operation_id] = record
            self._active_motor_codes.update(codes)
            return copy.deepcopy(record)

    def get(self, operation_id):
        with self._lock:
            record = self._operations.get(operation_id)
            return copy.deepcopy(record) if record is not None else None

    def release(self, operation_id, status="COMPLETED", error=None,
                completed_at=None, stop_errors=None):
        with self._lock:
            record = self._operations.pop(operation_id, None)
            if record is None:
                return None
            self._active_motor_codes.difference_update(
                record.get("motor_codes", [])
            )
            record["status"] = status
            record["error"] = error
            record["completed_at"] = completed_at
            if stop_errors:
                record["stop_errors"] = list(stop_errors)
            return copy.deepcopy(record)
