#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Synchronized multi-motor command batch orchestration."""

import time


class SynchronizedMotorExecutor(object):
    """Builds and enqueues one deterministic synchronized motor batch."""

    def __init__(self, motor_definitions, actions, enqueue_callback,
                 state_store, command_list_provider):
        self.motor_definitions = motor_definitions
        self.actions = actions
        self.enqueue_callback = enqueue_callback
        self.state_store = state_store
        self.command_list_provider = command_list_provider

    def execute(self, commands):
        if not commands:
            return {
                "success": False,
                "error": "At least one motor command is required."
            }
        invalid = self._first_unknown_motor(commands)
        if invalid is not None:
            return {
                "success": False,
                "error": "Motor not found: {}".format(invalid)
            }
        batch_id = int(time.time() * 1000)
        synchronized_start_at = time.time() + 0.05
        queued = []
        for command in commands:
            motor = self._enqueue(command, batch_id, synchronized_start_at)
            if motor is not None:
                motor["batch_id"] = batch_id
                self.state_store.update_motor(command.get("code"), motor)
                queued.append(motor)
        command_ids = [
            item["command_id"] for item in self.command_list_provider()
            if item.get("batch_id") == batch_id
        ]
        return {
            "success": True,
            "batch_id": batch_id,
            "scheduled_start_at": synchronized_start_at,
            "command_ids": command_ids,
            "motors": queued
        }

    def _first_unknown_motor(self, commands):
        for command in commands:
            code = command.get("code")
            if code not in self.motor_definitions:
                return code
        return None

    def _enqueue(self, command, batch_id, synchronized_start_at):
        motor_code = command.get("code")
        action = command.get("action", self.actions.RUN_FOREVER)
        priority = command.get("priority", 0)
        parameters = self._parameters(command, action, synchronized_start_at)
        return self.enqueue_callback(
            motor_code,
            action if action in self._supported_actions() else self.actions.RUN_FOREVER,
            parameters,
            priority=priority,
            batch_id=batch_id
        )

    def _supported_actions(self):
        return (
            self.actions.RUN_TIMED,
            self.actions.RUN_TO_REL_POS,
            self.actions.RUN_TO_ABS_POS,
            self.actions.STOP,
            self.actions.RUN_FOREVER
        )

    def _parameters(self, command, action, synchronized_start_at):
        if action == self.actions.STOP:
            return {}
        result = {
            "speed_sp": command.get("speed_sp"),
            "profile": command.get("profile"),
            "priority": command.get("priority", 0),
            "start_at": synchronized_start_at
        }
        if action == self.actions.RUN_TIMED:
            result["time_sp"] = command.get("time_sp")
        if action in (
            self.actions.RUN_TO_REL_POS, self.actions.RUN_TO_ABS_POS
        ):
            result["position_sp"] = command.get("position_sp")
        return result
