#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Motor state publisher adapter backed by the state repository."""

from ports.motor_state_publisher_port import MotorStatePublisherPort


class MotorStateStorePublisherAdapter(MotorStatePublisherPort):
    """Translates the publishing contract to ``MotorStateStore`` updates."""

    def __init__(self, state_store):
        if state_store is None:
            raise ValueError("state_store is required.")
        self._state_store = state_store

    def publish_motor_state(self, motor_code, state):
        self._state_store.update_motor(motor_code, state)
