#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Motor state publisher backed by the existing state repository."""

import copy

from ports.motor_state_publisher_port import MotorStatePublisherPort


class MotorStateStorePublisherAdapter(MotorStatePublisherPort):
    """Translates the publishing port to ``MotorStateStore`` updates.

    The adapter merges partial manual-control snapshots with the state already
    known by the monitoring side. This keeps persistence details outside the
    manual-drive service and avoids exposing the store as a write dependency.
    """

    def __init__(self, state_store):
        if state_store is None:
            raise ValueError("state_store is required.")
        self._state_store = state_store

    def publish_motor_state(self, motor_code, state):
        if not motor_code:
            raise ValueError("motor_code is required.")
        if not isinstance(state, dict):
            raise ValueError("state must be a dictionary.")

        current = self._state_store.get_motor(motor_code) or {}
        merged = copy.deepcopy(current)
        merged.update(copy.deepcopy(state))
        merged["code"] = motor_code
        self._state_store.update_motor(motor_code, merged)
