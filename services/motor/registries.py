#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Thread-safe command registries used by motor orchestration."""

import copy
import threading


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
